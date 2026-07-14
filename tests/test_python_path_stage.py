from __future__ import annotations

import hashlib
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from pcv_dms_benchmark.calibration import calibrate_models
from pcv_dms_benchmark.derived_export import build_derived_handoff
from pcv_dms_benchmark.python_path_stage import (
    ENVIRONMENT_ID,
    MEASUREMENT_SCOPE,
    audit_path_stage_smoke,
    decode_drc_path,
    load_ply_path,
    measure_path_candidate,
    run_python_path_stage_pilot,
)
from tests.test_open3d_python_backend import _v2_pilot_and_inventory


class FakeTensor:
    def __init__(self, value: np.ndarray) -> None:
        self.value = value

    def numpy(self) -> np.ndarray:
        return self.value


def candidate(asset_ref: str, size: int, representation: str = "ply") -> dict:
    return {
        "candidate_key": f"tile=one|repr={representation}",
        "candidate_id": representation,
        "representation": representation,
        "dataset_id": "synthetic",
        "frame_id": 1051,
        "grid_profile_id": "grid-test",
        "tile_id": f"tile-{representation}",
        "pdl_ratio": 1.0,
        "codec_params": {"qp": 8, "cl": 10} if representation == "drc" else {},
        "point_count": 1,
        "file_size_bytes": size,
        "asset_ref": asset_ref,
    }


def canonical() -> tuple[np.ndarray, np.ndarray]:
    return (
        np.array([[1, 2, 3]], dtype=np.float32, order="C", copy=True),
        np.array([[10, 20, 30]], dtype=np.uint8, order="C", copy=True),
    )


class PythonPathStageTest(unittest.TestCase):
    def test_open3d_tensor_path_output_is_canonical_without_normals(self) -> None:
        point_cloud = SimpleNamespace(
            point={
                "positions": FakeTensor(np.array([[1, 2, 3]], dtype=np.float64)),
                "colors": FakeTensor(np.array([[10 / 255, 20 / 255, 30 / 255]])),
            }
        )
        positions, colors = load_ply_path(Path("synthetic.ply"), loader=lambda _: point_cloud)
        self.assertEqual(positions.dtype, np.float32)
        self.assertEqual(colors.dtype, np.uint8)
        self.assertTrue(positions.flags.owndata)
        self.assertTrue(colors.flags.owndata)
        np.testing.assert_array_equal(colors, [[10, 20, 30]])

    def test_ply_timer_contains_loader_and_stat_is_outside(self) -> None:
        events: list[str] = []
        ticks = iter((100, 1_000_100))
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "asset.ply").write_bytes(b"x")
            result = measure_path_candidate(
                candidate("asset.ply", 1),
                data_prep_root=root,
                processor=lambda _: (events.append("loader"), canonical())[1],
                warmup_count=0,
                sample_count=1,
                clock_ns=lambda: (events.append("clock"), next(ticks))[1],
                stat_size=lambda _: (events.append("stat"), 1)[1],
                backend_name="fake-open3d",
                backend_version="test",
            )
        self.assertEqual(result["status"], "success")
        self.assertEqual(events, ["stat", "clock", "loader", "clock"])

    def test_drc_timer_contains_read_and_decode(self) -> None:
        events: list[str] = []
        ticks = iter((100, 1_000_100))
        decoded = SimpleNamespace(
            points=np.array([[1, 2, 3]], dtype=np.float64),
            colors=np.array([[10, 20, 30]], dtype=np.int32),
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "asset.drc").write_bytes(b"d")

            def processor(path: Path) -> tuple[np.ndarray, np.ndarray]:
                return decode_drc_path(
                    path,
                    read_bytes=lambda _: (events.append("read"), b"d")[1],
                    decoder=lambda _: (events.append("decode"), decoded)[1],
                )

            result = measure_path_candidate(
                candidate("asset.drc", 1, "drc"),
                data_prep_root=root,
                processor=processor,
                warmup_count=0,
                sample_count=1,
                clock_ns=lambda: (events.append("clock"), next(ticks))[1],
                stat_size=lambda _: (events.append("stat"), 1)[1],
                backend_name="fake-dracopy",
                backend_version="test",
            )
        self.assertEqual(result["status"], "success")
        self.assertEqual(events, ["stat", "clock", "read", "decode", "clock"])

    def test_run_uses_one_environment_and_stage_contract(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "a.ply").write_bytes(b"p")
            (root / "a.drc").write_bytes(b"d")
            result = run_python_path_stage_pilot(
                [candidate("a.ply", 1), candidate("a.drc", 1, "drc")],
                data_prep_root=root,
                warmup_count=2,
                sample_count=5,
                processor_overrides={"ply": lambda _: canonical(), "drc": lambda _: canonical()},
                environment_snapshot_override={
                    "python_version": "3.10.20",
                    "python_implementation": "CPython",
                    "open3d_version": "0.19.0",
                    "dracopy_version": "2.0.0",
                    "numpy_version": "2.2.6",
                    "operating_system": "Windows-test",
                    "timer_api": "time.perf_counter_ns",
                },
            )
        self.assertEqual(result["environment_id"], ENVIRONMENT_ID)
        self.assertEqual(result["measurement_kind"], "parse_stage_end_to_end")
        self.assertEqual(result["timing_start"], "path_delivered_to_loader")
        self.assertEqual(result["timing_end"], "positions_colors_ready")
        self.assertEqual(result["success_count"], 2)
        self.assertEqual({item["python_version"] for item in result["results"]}, {sys.version.split()[0]})
        audit_path_stage_smoke(result)

    def test_stage_handoff_covers_800_candidates(self) -> None:
        pilot, inventory = _v2_pilot_and_inventory()
        pilot.update(
            {
                "environment_id": ENVIRONMENT_ID,
                "measurement_scope": MEASUREMENT_SCOPE,
                "measurement_kind": "parse_stage_end_to_end",
                "timing_start": "path_delivered_to_loader",
                "timing_end": "positions_colors_ready",
                "profile_implementation_confirmed": True,
                "network_time_included": False,
                "rendering_time_included": False,
                "provenance_complete": True,
                "applicable_scope": {"dataset_id": "synthetic"},
            }
        )
        for record in pilot["results"]:
            record.update(
                measurement_scope=MEASUREMENT_SCOPE,
                measurement_kind="parse_stage_end_to_end",
                timing_start="path_delivered_to_loader",
                timing_end="positions_colors_ready",
            )
        calibration = calibrate_models(
            pilot,
            inventory,
            source_pilot_sha256="STAGE",
            source_inventory_sha256="INVENTORY",
            expected_environment_id=ENVIRONMENT_ID,
            expected_measurement_scope=MEASUREMENT_SCOPE,
        )
        calibration.update(
            profile_implementation_confirmed=True,
            validation_passed=True,
            applicable_scope={"dataset_id": "synthetic"},
        )
        handoff = build_derived_handoff(
            inventory,
            calibration,
            expected_representation_counts={"ply": 200, "drc": 600},
            allocation_integration_status="ready_for_provisional_integration",
        )
        self.assertEqual(handoff["candidate_count"], 800)
        self.assertEqual(len({item["candidate_key"] for item in handoff["candidates"]}), 800)
        self.assertTrue(all(item["d_stage_ms"] == item["d_hat_ms"] for item in handoff["candidates"]))

    def test_historical_v1_v2_artifacts_are_unchanged(self) -> None:
        expected = {
            "results/python_frame1051_measured_summary_v1.json": "3D39F11944F7702FEB8F47BE3AFE8853F1C1166930434358D66B1852C9E44E03",
            "results/python_frame1051_calibration_v1.json": "4ECA0AA2A40B989538695B8B62D5C71C5E3FF7D9E72062EA5A8D8AB7857BED49",
            "handoff/python_frame1051_candidate_dms_v1.json": "2FF769A8F0B3BB1AB167CFFE9089AAD0CDF5BD61092FF8CC24D6F5022CED17F4",
            "results/python_numpy_frame1051_measured_summary_v2.json": "4B15FF63339964F3339578C602C2EAE652105BEBFCAEC0CDD99FFD14D1F962D2",
            "results/python_numpy_frame1051_calibration_v2.json": "5AFAC010D1BD164659902C8D42F23600AC4C7F95531F2DC55582CF188E0760BE",
            "handoff/python_numpy_frame1051_candidate_dms_v2.json": "2301CCF3CBF76C7E1929933BBCB477F571B54A3612B173FBEDB483C9282C627B",
        }
        for relative_path, expected_hash in expected.items():
            digest = hashlib.sha256((ROOT / relative_path).read_bytes()).hexdigest().upper()
            self.assertEqual(digest, expected_hash, relative_path)


if __name__ == "__main__":
    unittest.main()
