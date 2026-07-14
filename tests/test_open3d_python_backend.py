from __future__ import annotations

import importlib.util
import struct
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from pcv_dms_benchmark.calibration import calibrate_models
from pcv_dms_benchmark.derived_export import (
    build_derived_handoff,
    build_measured_summary,
)
from pcv_dms_benchmark.open3d_python_backend import (
    ALLOCATION_USE_SCOPE,
    CALIBRATION_ID,
    ENVIRONMENT_ID,
    HANDOFF_ID,
    MEASUREMENT_SCOPE,
    Open3DPythonBackendError,
    parse_binary_ply_open3d,
    run_python_v2_pilot,
)


def binary_ply_bytes() -> bytes:
    header = (
        "ply\n"
        "format binary_little_endian 1.0\n"
        "element vertex 2\n"
        "property float x\n"
        "property float y\n"
        "property float z\n"
        "property uchar red\n"
        "property uchar green\n"
        "property uchar blue\n"
        "end_header\n"
    ).encode("ascii")
    return header + b"".join(
        (
            struct.pack("<fffBBB", 1.0, 2.0, 3.0, 10, 20, 30),
            struct.pack("<fffBBB", 4.0, 5.0, 6.0, 40, 50, 60),
        )
    )


def expected_snapshot() -> dict[str, str]:
    return {
        "python_version": "3.10.20",
        "python_implementation": "CPython",
        "operating_system": "Windows-test",
        "open3d_version": "0.19.0",
        "dracopy_version": "2.0.0",
        "numpy_version": np.__version__,
        "timer_api": "time.perf_counter_ns",
    }


class Open3DPythonBackendTest(unittest.TestCase):
    @unittest.skipUnless(importlib.util.find_spec("open3d"), "Open3D is not installed")
    def test_open3d_from_bytes_parses_synthetic_binary_ply(self) -> None:
        positions, colors = parse_binary_ply_open3d(binary_ply_bytes())
        if positions.shape[0] == 0:
            self.skipTest(
                "Open3D 0.19.0 Windows wheel exposes from_bytes but rejects PLY format"
            )
        self.assertEqual(positions.shape, (2, 3))
        self.assertEqual(colors.shape, (2, 3))
        np.testing.assert_array_equal(colors, [[10, 20, 30], [40, 50, 60]])

    def test_output_dtype_ownership_and_rgb_rounding(self) -> None:
        calls = []

        def reader(payload: bytes, *, format: str) -> SimpleNamespace:
            calls.append((payload, format))
            return SimpleNamespace(
                points=np.array([[1.0, 2.0, 3.0]], dtype=np.float64),
                colors=np.array([[10.0 / 255.0, 20.0 / 255.0, 30.0 / 255.0]]),
            )

        positions, colors = parse_binary_ply_open3d(binary_ply_bytes(), reader=reader)
        self.assertEqual(calls, [(binary_ply_bytes(), "ply")])
        self.assertEqual(positions.dtype, np.float32)
        self.assertEqual(colors.dtype, np.uint8)
        self.assertTrue(positions.flags.owndata)
        self.assertTrue(colors.flags.owndata)
        np.testing.assert_array_equal(colors, [[10, 20, 30]])

    def test_ascii_ply_is_rejected_before_reader(self) -> None:
        called = False

        def reader(payload: bytes, *, format: str) -> SimpleNamespace:
            nonlocal called
            called = True
            raise AssertionError("reader must not be called")

        payload = b"ply\nformat ascii 1.0\nelement vertex 0\nend_header\n"
        with self.assertRaisesRegex(Open3DPythonBackendError, "binary little-endian"):
            parse_binary_ply_open3d(payload, reader=reader)
        self.assertFalse(called)

    def test_formal_processor_uses_from_bytes_not_path_api(self) -> None:
        calls = {"from_bytes": 0, "path": 0}

        def from_bytes(payload: bytes, *, format: str) -> SimpleNamespace:
            calls["from_bytes"] += 1
            return SimpleNamespace(
                points=np.array([[1.0, 2.0, 3.0]]),
                colors=np.array([[0.0, 0.0, 0.0]]),
            )

        def path_reader(path: str) -> None:
            calls["path"] += 1
            raise AssertionError("path API must not be called")

        fake_open3d = SimpleNamespace(
            io=SimpleNamespace(
                read_point_cloud_from_bytes=from_bytes,
                read_point_cloud=path_reader,
            )
        )
        with patch.dict(sys.modules, {"open3d": fake_open3d}):
            parse_binary_ply_open3d(binary_ply_bytes())
        self.assertEqual(calls, {"from_bytes": 1, "path": 0})

    def test_ply_and_drc_share_one_v2_environment_snapshot(self) -> None:
        payload = binary_ply_bytes()
        positions = np.array([[1.0, 2.0, 3.0]], dtype=np.float32)
        colors = np.array([[1, 2, 3]], dtype=np.uint8)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "ply.bin").write_bytes(payload)
            (root / "drc.bin").write_bytes(b"drc")
            candidates = [
                _candidate("ply-key", "ply", "ply.bin", len(payload)),
                _candidate("drc-key", "drc", "drc.bin", 3),
            ]
            with patch(
                "pcv_dms_benchmark.open3d_python_backend.environment_snapshot",
                return_value=expected_snapshot(),
            ):
                result = run_python_v2_pilot(
                    candidates,
                    data_prep_root=root,
                    warmup_count=0,
                    sample_count=1,
                    processor_overrides={
                        "ply": lambda _: (positions.copy(), colors.copy()),
                        "drc": lambda _: (positions.copy(), colors.copy()),
                    },
                    run_id="synthetic-v2",
                )
        self.assertEqual(result["environment_id"], ENVIRONMENT_ID)
        self.assertEqual(result["environment_snapshot"], expected_snapshot())
        self.assertEqual({item["representation"] for item in result["results"]}, {"ply", "drc"})
        self.assertEqual({item["measurement_scope"] for item in result["results"]}, {MEASUREMENT_SCOPE})

    def test_v2_calibration_and_800_candidate_handoff_do_not_use_v1(self) -> None:
        pilot, inventory = _v2_pilot_and_inventory()
        with tempfile.TemporaryDirectory() as directory:
            v1 = Path(directory) / "python_frame1051_measured_summary_v1.json"
            v1.write_bytes(b"v1-sentinel")
            calibration = calibrate_models(
                pilot,
                inventory,
                source_pilot_sha256="V2-PILOT",
                source_inventory_sha256="INVENTORY",
                calibration_id=CALIBRATION_ID,
                expected_environment_id=ENVIRONMENT_ID,
                expected_measurement_scope=MEASUREMENT_SCOPE,
                allocation_use_scope=ALLOCATION_USE_SCOPE,
                profile_limitation="synthetic v2 profile",
                delivery_version="v2",
            )
            summary = build_measured_summary(
                pilot, source_pilot_sha256="V2-PILOT", delivery_version="v2"
            )
            handoff = build_derived_handoff(
                inventory,
                calibration,
                expected_representation_counts={"ply": 200, "drc": 600},
                handoff_id=HANDOFF_ID,
                allocation_use_scope=ALLOCATION_USE_SCOPE,
                delivery_version="v2",
                allocation_integration_status="ready_for_provisional_integration",
            )
            self.assertEqual(v1.read_bytes(), b"v1-sentinel")

        self.assertEqual(calibration["delivery_version"], "v2")
        self.assertEqual(calibration["provenance"], "calibrated")
        self.assertEqual(summary["candidate_count"], 100)
        self.assertEqual(summary["delivery_version"], "v2")
        self.assertEqual(summary["provenance"], "measured")
        self.assertTrue(all("raw_samples_ms" not in item for item in summary["records"]))
        self.assertEqual(handoff["candidate_count"], 800)
        self.assertEqual(handoff["delivery_version"], "v2")
        self.assertEqual(handoff["provenance"], "derived")
        self.assertEqual(len({item["candidate_key"] for item in handoff["candidates"]}), 800)


def _candidate(
    key: str, representation: str, asset_ref: str, file_size_bytes: int
) -> dict:
    return {
        "candidate_key": key,
        "candidate_id": key,
        "representation": representation,
        "dataset_id": "synthetic",
        "frame_id": 1051,
        "tile_id": f"tile-{representation}",
        "pdl_ratio": 1.0,
        "codec_params": {"qp": 10, "cl": 10} if representation == "drc" else {},
        "point_count": 1,
        "file_size_bytes": file_size_bytes,
        "asset_ref": asset_ref,
    }


def _v2_pilot_and_inventory() -> tuple[dict, dict]:
    measured = []
    candidates = []
    for tile_index in range(40):
        tile_id = f"tile-{tile_index:02d}"
        for pdl_index in range(5):
            point_count = 100 + tile_index * 20 + pdl_index * 10
            key = f"{tile_id}|ply|{pdl_index}"
            candidates.append(
                _inventory_record(key, tile_id, f"ply-{pdl_index}", "ply", point_count, point_count * 15)
            )
            if tile_index < 5:
                measured.append(
                    _measured_record(
                        key,
                        tile_id,
                        f"ply-{pdl_index}",
                        "ply",
                        point_count,
                        point_count * 15,
                        0.1 + point_count / 1000,
                    )
                )
        for pdl_index in range(5):
            for qp in (8, 10, 12):
                point_count = 100 + tile_index * 20 + pdl_index * 10
                file_size = point_count * 4 + qp
                key = f"{tile_id}|drc|{pdl_index}|{qp}"
                candidate_id = f"drc-{pdl_index}-{qp}"
                candidates.append(
                    _inventory_record(
                        key, tile_id, candidate_id, "drc", point_count, file_size, qp=qp
                    )
                )
                if tile_index < 5:
                    measured.append(
                        _measured_record(
                            key,
                            tile_id,
                            candidate_id,
                            "drc",
                            point_count,
                            file_size,
                            0.05 + 0.4 * point_count / 1000,
                            qp=qp,
                        )
                    )
    pilot = {
        "status": "success",
        "candidate_count": 100,
        "success_count": 100,
        "failure_count": 0,
        "environment_id": ENVIRONMENT_ID,
        "measurement_scope": MEASUREMENT_SCOPE,
        "provenance": "measured",
        "eligible_for_final_model": False,
        "eligible_for_allocation": False,
        "environment_snapshot": expected_snapshot(),
        "results": measured,
    }
    return pilot, {"candidates": candidates}


def _inventory_record(
    key: str,
    tile_id: str,
    candidate_id: str,
    representation: str,
    point_count: int,
    file_size_bytes: int,
    *,
    qp: int | None = None,
) -> dict:
    return {
        "candidate_key": key,
        "candidate_id": candidate_id,
        "dataset_id": "synthetic",
        "frame_id": 1051,
        "grid_profile_id": "grid-test",
        "tile_id": tile_id,
        "representation": representation,
        "pdl_ratio": 1.0,
        "point_count": point_count,
        "file_size_bytes": file_size_bytes,
        "codec_params": {"qp": qp, "cl": 10} if representation == "drc" else {},
    }


def _measured_record(
    key: str,
    tile_id: str,
    candidate_id: str,
    representation: str,
    point_count: int,
    file_size_bytes: int,
    p50_ms: float,
    *,
    qp: int | None = None,
) -> dict:
    return {
        "candidate_key": key,
        "candidate_id": candidate_id,
        "tile_id": tile_id,
        "representation": representation,
        "pdl_ratio": 1.0,
        "status": "success",
        "provenance": "measured",
        "measurement_scope": MEASUREMENT_SCOPE,
        "eligible_for_final_model": False,
        "eligible_for_allocation": False,
        "p50_ms": p50_ms,
        "mean_ms": p50_ms,
        "point_count": point_count,
        "decoded_point_count": point_count,
        "file_size_bytes": file_size_bytes,
        "qp": qp,
        "cl": 10 if representation == "drc" else None,
    }


if __name__ == "__main__":
    unittest.main()
