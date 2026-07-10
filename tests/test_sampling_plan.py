from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from pcv_dms_benchmark.metadata_inventory import build_inventory_from_metadata
from pcv_dms_benchmark.sampling_plan import build_sampling_plan


FIXTURE = Path(__file__).resolve().parent / "fixtures"


def load_fixture(name: str) -> dict:
    return json.loads((FIXTURE / name).read_text(encoding="utf-8"))


class SamplingPlanTest(unittest.TestCase):
    def build_plan(self) -> dict:
        inventory = build_inventory_from_metadata(
            ply_index=load_fixture("synthetic_ply_tile_index.json"),
            drc_manifest=load_fixture("synthetic_drc_generation_manifest.json"),
        )
        return build_sampling_plan(inventory, max_tiles=2, source_inventory="synthetic_inventory.json")

    def test_sampling_plan_has_no_duplicate_candidates(self) -> None:
        plan = self.build_plan()
        keys = [item["candidate_key"] for item in plan["selected_candidates"]]
        self.assertEqual(len(keys), len(set(keys)))

    def test_sampling_plan_covers_ply_and_drc(self) -> None:
        plan = self.build_plan()
        self.assertIn("ply", plan["coverage_summary"]["representations"])
        self.assertIn("drc", plan["coverage_summary"]["representations"])

    def test_sampling_plan_covers_multiple_pdl_values(self) -> None:
        plan = self.build_plan()
        self.assertGreaterEqual(len(plan["coverage_summary"]["pdl_values"]), 2)

    def test_sampling_plan_covers_multiple_drc_qp_values(self) -> None:
        plan = self.build_plan()
        self.assertGreaterEqual(len(plan["coverage_summary"]["drc_qp_values"]), 2)
        self.assertTrue({8, 10, 12}.issuperset(set(plan["coverage_summary"]["drc_qp_values"])))

    def test_sampling_plan_is_metadata_planning_not_result(self) -> None:
        plan = self.build_plan()
        self.assertEqual(plan["plan_kind"], "metadata_planning")
        for candidate in plan["selected_candidates"]:
            self.assertEqual(candidate["status"], "planned_metadata_only")


if __name__ == "__main__":
    unittest.main()
