from __future__ import annotations

import copy
import json
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from pcv_dms_benchmark.metadata_inventory import build_inventory_from_metadata


FIXTURE = Path(__file__).resolve().parent / "fixtures"


def load_fixture(name: str) -> dict:
    return json.loads((FIXTURE / name).read_text(encoding="utf-8"))


class MetadataInventoryTest(unittest.TestCase):
    def build_inventory(self) -> dict:
        return build_inventory_from_metadata(
            ply_index=load_fixture("synthetic_ply_tile_index.json"),
            drc_manifest=load_fixture("synthetic_drc_generation_manifest.json"),
            ply_source_manifest="artifacts/synthetic_ply/frame_1051_tile_index.json",
            drc_source_manifest="artifacts/synthetic_drc/generation_manifest.json",
        )

    def test_ply_candidate_is_normalized(self) -> None:
        inventory = self.build_inventory()
        ply = next(item for item in inventory["candidates"] if item["representation"] == "ply")
        self.assertEqual(ply["file_format"], "ply")
        self.assertEqual(ply["codec"], None)
        self.assertEqual(ply["dataset_id"], "synthetic_longdress")
        self.assertEqual(ply["frame_id"], 1051)
        self.assertIn("tile_", ply["tile_id"])

    def test_drc_candidate_is_normalized_with_codec_params(self) -> None:
        inventory = self.build_inventory()
        drc = next(item for item in inventory["candidates"] if item["representation"] == "drc")
        self.assertEqual(drc["file_format"], "drc")
        self.assertEqual(drc["codec"], "draco")
        self.assertEqual(drc["codec_params"]["cl"], 10)
        self.assertIn(drc["codec_params"]["qp"], {8, 10, 12})
        self.assertTrue(drc["codec_params"]["point_cloud_mode"])

    def test_unexplicit_qc_qg_are_not_fabricated(self) -> None:
        inventory = self.build_inventory()
        drc = next(item for item in inventory["candidates"] if item["representation"] == "drc")
        self.assertNotIn("qc", drc["codec_params"])
        self.assertNotIn("qg", drc["codec_params"])

    def test_candidate_key_does_not_depend_on_array_position(self) -> None:
        ply = load_fixture("synthetic_ply_tile_index.json")
        drc = load_fixture("synthetic_drc_generation_manifest.json")
        reversed_ply = copy.deepcopy(ply)
        reversed_drc = copy.deepcopy(drc)
        reversed_ply["tiles"] = list(reversed(reversed_ply["tiles"]))
        for tile in reversed_ply["tiles"]:
            tile["quality_assets"] = list(reversed(tile["quality_assets"]))
        reversed_drc["variants"] = list(reversed(reversed_drc["variants"]))

        first = build_inventory_from_metadata(ply_index=ply, drc_manifest=drc)
        second = build_inventory_from_metadata(ply_index=reversed_ply, drc_manifest=reversed_drc)
        self.assertEqual(
            [item["candidate_key"] for item in first["candidates"]],
            [item["candidate_key"] for item in second["candidates"]],
        )

    def test_key_metadata_fields_are_preserved(self) -> None:
        inventory = self.build_inventory()
        candidate = next(item for item in inventory["candidates"] if item["tile_id"] == "tile_small")
        self.assertIsNotNone(candidate["pdl_ratio"])
        self.assertIsNotNone(candidate["file_size_bytes"])
        self.assertIsNotNone(candidate["point_count"])
        self.assertIsNotNone(candidate["asset_ref"])

    def test_missing_metadata_yields_warning_not_fabrication(self) -> None:
        inventory = self.build_inventory()
        missing_sha = next(
            item
            for item in inventory["candidates"]
            if item["representation"] == "ply" and item["tile_id"] == "tile_large"
        )
        self.assertIsNone(missing_sha["asset_sha256"])
        self.assertIn("missing_asset_sha256", missing_sha["warning_codes"])

    def test_inventory_is_metadata_planning_not_measurement_result(self) -> None:
        inventory = self.build_inventory()
        self.assertEqual(inventory["inventory_kind"], "metadata_planning")
        for candidate in inventory["candidates"]:
            self.assertEqual(candidate["provenance"]["record_kind"], "metadata_planning")
            self.assertNotEqual(candidate["provenance"]["record_kind"], "measured")
            self.assertNotEqual(candidate["provenance"]["record_kind"], "calibrated")
            self.assertNotEqual(candidate["provenance"]["record_kind"], "derived")


if __name__ == "__main__":
    unittest.main()
