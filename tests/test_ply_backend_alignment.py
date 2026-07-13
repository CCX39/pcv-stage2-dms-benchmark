from __future__ import annotations

import struct
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from pcv_dms_benchmark.ply_backend_alignment import (
    PlyBackendAlignmentError,
    measure_processor,
    parse_open3d_ply_path,
    select_alignment_candidates,
    validate_backend_equivalence,
    write_alignment_result,
)
from pcv_dms_benchmark.python_benchmark import parse_binary_ply


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


def inventory_candidate(tile: str, pdl: float, points: int) -> dict:
    pdl_key = str(pdl).replace(".", "p")
    return {
        "candidate_key": f"tile={tile}|repr=ply|pdl={pdl_key}",
        "candidate_id": f"ply__pdl_{pdl_key}",
        "representation": "ply",
        "tile_id": tile,
        "pdl_ratio": pdl,
        "point_count": points,
        "file_size_bytes": 100,
        "asset_ref": f"{tile}_{pdl_key}.ply",
    }


class PlyBackendAlignmentTest(unittest.TestCase):
    def test_selects_minimum_and_maximum_tiles_at_two_pdls(self) -> None:
        candidates = []
        for tile, full_points in (("tile_mid", 50), ("tile_max", 100), ("tile_min", 10)):
            candidates.extend(
                (
                    inventory_candidate(tile, 0.2, max(1, full_points // 5)),
                    inventory_candidate(tile, 1.0, full_points),
                )
            )
        inventory = {"candidates": list(reversed(candidates))}
        plan = {
            "selected_candidates": [
                {"candidate_key": candidate["candidate_key"]} for candidate in candidates
            ]
        }
        selected = select_alignment_candidates(inventory, plan)
        self.assertEqual(
            [(item["tile_id"], item["pdl_ratio"]) for item in selected],
            [("tile_min", 0.2), ("tile_min", 1.0), ("tile_max", 0.2), ("tile_max", 1.0)],
        )
        self.assertEqual(len({item["candidate_key"] for item in selected}), 4)

    def test_both_paths_produce_owned_canonical_arrays(self) -> None:
        expected_positions, expected_colors = parse_binary_ply(binary_ply_bytes())
        point_cloud = SimpleNamespace(
            points=expected_positions.astype(np.float64),
            colors=expected_colors.astype(np.float64) / 255.0,
        )
        positions, colors = parse_open3d_ply_path(
            "unused.ply", reader=lambda _: point_cloud
        )
        self.assertEqual(positions.dtype, np.float32)
        self.assertEqual(colors.dtype, np.uint8)
        self.assertTrue(positions.flags.owndata)
        self.assertTrue(colors.flags.owndata)
        validate_backend_equivalence((expected_positions, expected_colors), (positions, colors))

    def test_point_count_mismatch_fails(self) -> None:
        positions = np.zeros((2, 3), dtype=np.float32)
        colors = np.zeros((2, 3), dtype=np.uint8)
        with self.assertRaisesRegex(PlyBackendAlignmentError, "point count mismatch"):
            measure_processor(
                lambda: (positions.copy(), colors.copy()),
                warmup_count=0,
                sample_count=1,
                expected_point_count=3,
            )

    def test_coordinate_or_color_mismatch_fails(self) -> None:
        positions = np.zeros((2, 3), dtype=np.float32)
        colors = np.zeros((2, 3), dtype=np.uint8)
        changed_positions = positions.copy()
        changed_positions[0, 0] = 1.0
        with self.assertRaisesRegex(PlyBackendAlignmentError, "positions differ"):
            validate_backend_equivalence(
                (positions.copy(), colors.copy()),
                (changed_positions, colors.copy()),
            )
        changed_colors = colors.copy()
        changed_colors[0, 0] = 2
        with self.assertRaisesRegex(PlyBackendAlignmentError, "colors differ"):
            validate_backend_equivalence(
                (positions.copy(), colors.copy()),
                (positions.copy(), changed_colors),
            )

    def test_warmup_and_sample_counts(self) -> None:
        calls = 0
        positions = np.zeros((2, 3), dtype=np.float32)
        colors = np.zeros((2, 3), dtype=np.uint8)

        def processor() -> tuple[np.ndarray, np.ndarray]:
            nonlocal calls
            calls += 1
            return positions.copy(), colors.copy()

        ticks = iter(range(0, 10_000_001, 1_000_000))
        timing, _ = measure_processor(
            processor,
            warmup_count=2,
            sample_count=5,
            expected_point_count=2,
            clock_ns=lambda: next(ticks),
        )
        self.assertEqual(calls, 7)
        self.assertEqual(len(timing["raw_samples_ms"]), 5)
        self.assertEqual(timing["p50_ms"], 1.0)
        self.assertEqual(timing["mean_ms"], 1.0)

    def test_writer_does_not_modify_existing_model_or_handoff(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            calibration = root / "python_frame1051_calibration_v1.json"
            handoff = root / "python_frame1051_candidate_dms_v1.json"
            output = root / "alignment.json"
            calibration.write_bytes(b"calibration-sentinel")
            handoff.write_bytes(b"handoff-sentinel")

            write_alignment_result(output, {"conclusion": "diagnostic-only"})

            self.assertEqual(calibration.read_bytes(), b"calibration-sentinel")
            self.assertEqual(handoff.read_bytes(), b"handoff-sentinel")
            self.assertTrue(output.is_file())


if __name__ == "__main__":
    unittest.main()
