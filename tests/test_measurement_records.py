from __future__ import annotations

import hashlib
import json
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from pcv_dms_benchmark.derived_export import build_derived_handoff
from pcv_dms_benchmark.measurement_records import (
    BACKEND_CORE_ENTRY,
    COMPLETE_PAYLOAD_DELIVERED,
    CORE_PARSE_MICROBENCHMARK,
    INELIGIBLE_SCOPE,
    PARSE_STAGE_END_TO_END,
    PATH_DELIVERED,
    PATH_LOADER_DIAGNOSTIC,
    POSITIONS_COLORS_READY,
    READY,
    MeasurementContractError,
    evaluate_allocation_eligibility,
    resolve_measurement_contract,
)


HISTORICAL_HASHES = {
    "results/python_frame1051_measured_summary_v1.json": (
        "3D39F11944F7702FEB8F47BE3AFE8853F1C1166930434358D66B1852C9E44E03"
    ),
    "results/python_frame1051_calibration_v1.json": (
        "4ECA0AA2A40B989538695B8B62D5C71C5E3FF7D9E72062EA5A8D8AB7857BED49"
    ),
    "handoff/python_frame1051_candidate_dms_v1.json": (
        "2FF769A8F0B3BB1AB167CFFE9089AAD0CDF5BD61092FF8CC24D6F5022CED17F4"
    ),
    "results/python_numpy_frame1051_measured_summary_v2.json": (
        "4B15FF63339964F3339578C602C2EAE652105BEBFCAEC0CDD99FFD14D1F962D2"
    ),
    "results/python_numpy_frame1051_calibration_v2.json": (
        "5AFAC010D1BD164659902C8D42F23600AC4C7F95531F2DC55582CF188E0760BE"
    ),
    "handoff/python_numpy_frame1051_candidate_dms_v2.json": (
        "2301CCF3CBF76C7E1929933BBCB477F571B54A3612B173FBEDB483C9282C627B"
    ),
}


def eligible_stage_record() -> dict:
    return {
        "measurement_kind": PARSE_STAGE_END_TO_END,
        "timing_start": COMPLETE_PAYLOAD_DELIVERED,
        "timing_end": POSITIONS_COLORS_READY,
        "environment_id": "js_worker_browser_windows_x64",
        "profile_implementation_confirmed": True,
        "network_time_included": False,
        "rendering_time_included": False,
        "provenance_complete": True,
        "validation_passed": True,
        "applicable_scope": {"dataset_id": "synthetic"},
    }


class MeasurementRecordsTest(unittest.TestCase):
    def test_core_microbenchmark_cannot_be_allocation_eligible(self) -> None:
        record = eligible_stage_record()
        record.update(
            measurement_kind=CORE_PARSE_MICROBENCHMARK,
            timing_start=BACKEND_CORE_ENTRY,
        )
        review = evaluate_allocation_eligibility(record, release_gate_passed=True)
        self.assertFalse(review["eligible_for_allocation"])
        self.assertEqual(review["allocation_integration_status"], INELIGIBLE_SCOPE)

    def test_path_loader_diagnostic_cannot_be_allocation_eligible(self) -> None:
        record = eligible_stage_record()
        record.update(
            measurement_kind=PATH_LOADER_DIAGNOSTIC,
            timing_start=PATH_DELIVERED,
        )
        review = evaluate_allocation_eligibility(record, release_gate_passed=True)
        self.assertFalse(review["eligible_for_allocation"])
        self.assertEqual(review["allocation_integration_status"], INELIGIBLE_SCOPE)

    def test_parse_stage_can_pass_allocation_gate(self) -> None:
        review = evaluate_allocation_eligibility(
            eligible_stage_record(), release_gate_passed=True
        )
        self.assertTrue(review["eligible_for_allocation"])
        self.assertEqual(review["allocation_integration_status"], READY)

    def test_legacy_schema_defaults_to_core_microbenchmark(self) -> None:
        contract = resolve_measurement_contract({"environment_id": "legacy"})
        self.assertEqual(contract["measurement_kind"], CORE_PARSE_MICROBENCHMARK)
        self.assertEqual(contract["timing_start"], BACKEND_CORE_ENTRY)

    def test_timing_end_must_be_positions_colors_ready(self) -> None:
        with self.assertRaisesRegex(MeasurementContractError, "positions_colors_ready"):
            resolve_measurement_contract({"timing_end": "geometry_ready"})

    def test_derived_handoff_inherits_parse_stage_contract(self) -> None:
        calibration = self._calibration(**eligible_stage_record())
        handoff = build_derived_handoff(
            self._inventory(),
            calibration,
            allocation_integration_status=READY,
        )
        self.assertEqual(handoff["measurement_kind"], PARSE_STAGE_END_TO_END)
        self.assertTrue(handoff["eligible_for_allocation"])
        self.assertEqual(handoff["allocation_integration_status"], READY)
        self.assertTrue(all(item["eligible_for_allocation"] for item in handoff["candidates"]))

    def test_core_handoff_is_downgraded_even_if_ready_is_requested(self) -> None:
        calibration = self._calibration()
        handoff = build_derived_handoff(
            self._inventory(),
            calibration,
            allocation_integration_status=READY,
        )
        self.assertEqual(handoff["measurement_kind"], CORE_PARSE_MICROBENCHMARK)
        self.assertFalse(handoff["eligible_for_allocation"])
        self.assertEqual(handoff["allocation_integration_status"], INELIGIBLE_SCOPE)

    def test_historical_json_remains_readable_and_unchanged(self) -> None:
        for relative_path, expected_hash in HISTORICAL_HASHES.items():
            path = ROOT / relative_path
            payload = path.read_bytes()
            self.assertIsInstance(json.loads(payload), dict)
            self.assertEqual(hashlib.sha256(payload).hexdigest().upper(), expected_hash)
            self.assertEqual(
                resolve_measurement_contract(json.loads(payload))["measurement_kind"],
                CORE_PARSE_MICROBENCHMARK,
            )

    @staticmethod
    def _inventory() -> dict:
        candidates = []
        for representation in ("ply", "drc"):
            candidates.append(
                {
                    "candidate_key": f"tile=one|repr={representation}",
                    "candidate_id": representation,
                    "dataset_id": "synthetic",
                    "frame_id": 1051,
                    "grid_profile_id": "grid-test",
                    "tile_id": f"tile-{representation}",
                    "representation": representation,
                    "pdl_ratio": 1.0,
                    "point_count": 100,
                    "file_size_bytes": 1000,
                    "codec_params": {"qp": 8, "cl": 10}
                    if representation == "drc"
                    else {},
                }
            )
        return {"candidates": candidates}

    @staticmethod
    def _calibration(**contract_fields: object) -> dict:
        model = {
            "selected_model": "P0",
            "fit_parameters": {"constant_median_ms": 1.0},
            "cross_validation_metrics": {"normalized_mae": 0.1},
            "recommended_for_allocation_pilot": True,
        }
        drc_model = {**model, "selected_model": "D0"}
        return {
            "calibration_id": "synthetic",
            "environment_id": "js_worker_browser_windows_x64",
            "dataset_id": "synthetic",
            "frame_id": 1051,
            "grid_profile_id": "grid-test",
            "target_statistic": "p50_ms",
            "representation_models": {"ply": model, "drc": drc_model},
            **contract_fields,
        }


if __name__ == "__main__":
    unittest.main()
