from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from pcv_dms_benchmark.derived_export import (
    build_derived_handoff,
    build_measured_summary,
)


def inventory_candidate(
    tile: str,
    candidate_id: str,
    representation: str,
    point_count: int,
    file_size_bytes: int,
    *,
    qp: int | None = None,
) -> dict:
    return {
        "candidate_key": f"tile={tile}|candidate={candidate_id}",
        "candidate_id": candidate_id,
        "dataset_id": "synthetic",
        "frame_id": 1051,
        "grid_profile_id": "grid-test",
        "tile_id": tile,
        "representation": representation,
        "pdl_ratio": 1.0,
        "point_count": point_count,
        "file_size_bytes": file_size_bytes,
        "codec_params": {"qp": qp, "cl": 10} if representation == "drc" else {},
    }


class DerivedExportTest(unittest.TestCase):
    def setUp(self) -> None:
        self.inventory = {
            "candidates": [
                inventory_candidate("tile-a", "ply-1", "ply", 100, 1500),
                inventory_candidate("tile-b", "ply-1", "ply", 200, 3000),
                inventory_candidate("tile-a", "drc-1", "drc", 100, 500, qp=8),
                inventory_candidate("tile-b", "drc-1", "drc", 200, 800, qp=10),
            ]
        }
        common = {
            "cross_validation_metrics": {"normalized_mae": 0.1},
            "recommended_for_allocation_pilot": True,
        }
        self.calibration = {
            "calibration_id": "synthetic-calibration",
            "environment_id": "python_windows_x64",
            "dataset_id": "synthetic",
            "frame_id": 1051,
            "grid_profile_id": "grid-test",
            "target_statistic": "p50_ms",
            "representation_models": {
                "ply": {
                    **common,
                    "selected_model": "P1",
                    "fit_parameters": {
                        "intercept_ms": 0.5,
                        "point_count_coef_ms_per_1000_points": 1.0,
                    },
                },
                "drc": {
                    **common,
                    "selected_model": "D2",
                    "fit_parameters": {
                        "intercept_ms": 0.5,
                        "point_count_coef_ms_per_1000_points": 1.0,
                        "file_size_bytes_coef_ms_per_1000_bytes": 0.2,
                    },
                },
            },
        }

    def test_handoff_covers_all_unique_candidate_keys(self) -> None:
        handoff = build_derived_handoff(self.inventory, self.calibration)
        expected = {item["candidate_key"] for item in self.inventory["candidates"]}
        actual = {item["candidate_key"] for item in handoff["candidates"]}
        self.assertEqual(handoff["candidate_count"], 4)
        self.assertEqual(actual, expected)
        self.assertEqual(len(actual), len(handoff["candidates"]))

    def test_tile_and_candidate_id_are_unique_join_key(self) -> None:
        handoff = build_derived_handoff(self.inventory, self.calibration)
        join_keys = [(item["tile_id"], item["candidate_id"]) for item in handoff["candidates"]]
        self.assertEqual(len(join_keys), len(set(join_keys)))

    def test_handoff_is_derived_and_has_no_raw_samples(self) -> None:
        handoff = build_derived_handoff(self.inventory, self.calibration)
        self.assertEqual(handoff["provenance"], "derived")
        self.assertEqual(handoff["measurement_kind"], "core_parse_microbenchmark")
        self.assertFalse(handoff["eligible_for_allocation"])
        self.assertEqual(
            handoff["allocation_integration_status"], "ineligible_measurement_scope"
        )
        for candidate in handoff["candidates"]:
            self.assertEqual(candidate["provenance"], "derived")
            self.assertFalse(candidate["eligible_for_allocation"])
            self.assertNotIn("raw_samples_ms", candidate)
            self.assertGreater(candidate["d_hat_ms"], 0)

    def test_measured_summary_preserves_measured_provenance_without_raw_samples(self) -> None:
        pilot = {
            "environment_id": "python_windows_x64",
            "results": [
                {
                    "candidate_key": "key",
                    "candidate_id": "id",
                    "tile_id": "tile",
                    "representation": "ply",
                    "pdl_ratio": 1.0,
                    "qp": None,
                    "cl": None,
                    "point_count": 10,
                    "file_size_bytes": 100,
                    "p50_ms": 1.0,
                    "mean_ms": 1.1,
                    "raw_samples_ms": [1.0],
                    "measurement_scope": "longdress_frame1051_pilot",
                }
            ],
        }
        summary = build_measured_summary(pilot, source_pilot_sha256="ABC")
        self.assertEqual(summary["provenance"], "measured")
        self.assertEqual(summary["measurement_kind"], "core_parse_microbenchmark")
        self.assertFalse(summary["eligible_for_allocation"])
        self.assertEqual(summary["records"][0]["provenance"], "measured")
        self.assertNotIn("raw_samples_ms", summary["records"][0])


if __name__ == "__main__":
    unittest.main()
