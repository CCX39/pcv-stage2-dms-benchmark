from __future__ import annotations

import json
import struct
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from pcv_dms_benchmark.measurement_stats import summarize_samples
from pcv_dms_benchmark.python_benchmark import (
    PythonBenchmarkError,
    decode_drc,
    measure_candidate,
    parse_binary_ply,
    run_python_pilot,
    select_candidates,
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
    rows = [
        struct.pack("<fffBBB", 1.0, 2.0, 3.0, 10, 20, 30),
        struct.pack("<fffBBB", 4.0, 5.0, 6.0, 40, 50, 60),
    ]
    return header + b"".join(rows)


def candidate(asset_ref: str, size: int, representation: str = "ply") -> dict:
    return {
        "candidate_key": f"tile=one|repr={representation}",
        "candidate_id": f"{representation}__pdl_1p0",
        "representation": representation,
        "dataset_id": "synthetic_longdress",
        "frame_id": 1051,
        "tile_id": "tile_one",
        "pdl_ratio": 1.0,
        "codec_params": {"qp": 8, "cl": 10} if representation == "drc" else {},
        "point_count": 2,
        "file_size_bytes": size,
        "asset_ref": asset_ref,
    }


class PythonBenchmarkTest(unittest.TestCase):
    def test_binary_little_endian_ply_produces_canonical_arrays(self) -> None:
        positions, colors = parse_binary_ply(binary_ply_bytes())
        self.assertEqual(positions.dtype, np.float32)
        self.assertEqual(colors.dtype, np.uint8)
        self.assertEqual(positions.shape, (2, 3))
        self.assertEqual(colors.shape, (2, 3))
        self.assertTrue(positions.flags.owndata)
        self.assertTrue(colors.flags.owndata)

    def test_ascii_ply_is_rejected(self) -> None:
        payload = (
            b"ply\nformat ascii 1.0\nelement vertex 1\n"
            b"property float x\nproperty float y\nproperty float z\n"
            b"property uchar red\nproperty uchar green\nproperty uchar blue\n"
            b"end_header\n0 0 0 1 2 3\n"
        )
        with self.assertRaisesRegex(PythonBenchmarkError, "binary little-endian"):
            parse_binary_ply(payload)

    def test_candidate_key_uniquely_locates_inventory_record(self) -> None:
        inventory = {
            "candidates": [
                {"candidate_key": "key-a", "representation": "ply"},
                {"candidate_key": "key-b", "representation": "drc"},
            ]
        }
        plan = {"selected_candidates": [{"candidate_key": "key-b"}]}
        selected = select_candidates(inventory, plan)
        self.assertEqual([item["candidate_key"] for item in selected], ["key-b"])

    def test_file_read_precedes_processor_timing(self) -> None:
        events: list[str] = []
        payload = binary_ply_bytes()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            asset = root / "asset.ply"
            asset.write_bytes(payload)

            def read_bytes(path: Path) -> bytes:
                events.append("read")
                return path.read_bytes()

            def processor(value: bytes) -> tuple[np.ndarray, np.ndarray]:
                events.append("processor")
                return parse_binary_ply(value)

            ticks = iter((100, 1_000_100))

            def clock_ns() -> int:
                events.append("clock")
                return next(ticks)

            result = measure_candidate(
                candidate("asset.ply", len(payload)),
                data_prep_root=root,
                warmup_count=0,
                sample_count=1,
                processor=processor,
                read_bytes=read_bytes,
                clock_ns=clock_ns,
            )
        self.assertEqual(result["status"], "success")
        self.assertEqual(events, ["read", "clock", "processor", "clock"])

    def test_warmup_samples_and_pilot_flags(self) -> None:
        payload = binary_ply_bytes()
        call_count = 0

        def processor(value: bytes) -> tuple[np.ndarray, np.ndarray]:
            nonlocal call_count
            call_count += 1
            return parse_binary_ply(value)

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "asset.ply").write_bytes(payload)
            result = run_python_pilot(
                [candidate("asset.ply", len(payload))],
                data_prep_root=root,
                warmup_count=2,
                sample_count=5,
                processor_overrides={"ply": processor},
                run_id="synthetic-smoke",
            )
        self.assertEqual(call_count, 7)
        self.assertEqual(len(result["results"][0]["raw_samples_ms"]), 5)
        self.assertFalse(result["eligible_for_final_model"])
        self.assertFalse(result["eligible_for_allocation"])
        self.assertFalse(result["results"][0]["eligible_for_final_model"])
        self.assertFalse(result["results"][0]["eligible_for_allocation"])

    def test_p50_and_mean(self) -> None:
        summary = summarize_samples([1.0, 2.0, 8.0, 4.0, 5.0])
        self.assertEqual(summary["p50_ms"], 4.0)
        self.assertEqual(summary["mean_ms"], 4.0)

    def test_fake_drc_decoder_output_is_copied_to_canonical_arrays(self) -> None:
        points = np.array([[1.0, 2.0, 3.0]], dtype=np.float64)
        colors = np.array([[1, 2, 3]], dtype=np.int32)
        decoded = SimpleNamespace(points=points, colors=colors)
        positions, converted_colors = decode_drc(b"synthetic", decoder=lambda _: decoded)
        self.assertEqual(positions.dtype, np.float32)
        self.assertEqual(converted_colors.dtype, np.uint8)
        self.assertTrue(positions.flags.owndata)
        self.assertTrue(converted_colors.flags.owndata)
        points[0, 0] = 99.0
        self.assertEqual(positions[0, 0], 1.0)


if __name__ == "__main__":
    unittest.main()
