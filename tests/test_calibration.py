from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from pcv_dms_benchmark.calibration import (
    MODEL_SPECS,
    calibrate_models,
    choose_model,
    fit_model,
    leave_one_tile_out,
    model_spec,
    predict_records,
    recommendation_status,
)


def record(
    tile_id: str,
    point_count: int,
    file_size_bytes: int,
    p50_ms: float,
    *,
    qp: int | None = None,
) -> dict:
    return {
        "tile_id": tile_id,
        "point_count": point_count,
        "file_size_bytes": file_size_bytes,
        "p50_ms": p50_ms,
        "qp": qp,
    }


class CalibrationTest(unittest.TestCase):
    def test_leave_one_tile_out_has_no_tile_leakage(self) -> None:
        records = [
            record(f"tile-{tile}", point_count, point_count * 12, 1.0 + point_count / 1000)
            for tile, point_count in enumerate((100, 200, 300, 400, 500), start=1)
        ]
        metrics = leave_one_tile_out(model_spec("ply", "P1"), records)
        self.assertEqual(metrics["fold_count"], 5)
        for fold in metrics["folds"]:
            self.assertNotIn(fold["validation_tile_id"], fold["training_tile_ids"])
            self.assertEqual(len(fold["training_tile_ids"]), 4)

    def test_ply_linear_model_recovers_point_count_relation(self) -> None:
        records = [
            record("tile-a", count, count * 12, 0.75 + 2.5 * count / 1000)
            for count in (100, 300, 600, 900)
        ]
        spec = model_spec("ply", "P1")
        parameters = fit_model(spec, records)
        prediction = predict_records(spec, parameters, [record("x", 500, 6000, 0.0)])[0]
        self.assertAlmostEqual(parameters["intercept_ms"], 0.75, places=10)
        self.assertAlmostEqual(parameters["point_count_coef_ms_per_1000_points"], 2.5, places=10)
        self.assertAlmostEqual(prediction, 2.0, places=10)

    def test_drc_multifeature_model_fits_and_predicts(self) -> None:
        records = [
            record("tile-a", 100, 1000, 0.5 + 1.2 * 0.1 + 0.3 * 1.0, qp=8),
            record("tile-a", 200, 1400, 0.5 + 1.2 * 0.2 + 0.3 * 1.4, qp=8),
            record("tile-b", 500, 2200, 0.5 + 1.2 * 0.5 + 0.3 * 2.2, qp=10),
            record("tile-c", 800, 3000, 0.5 + 1.2 * 0.8 + 0.3 * 3.0, qp=12),
        ]
        spec = model_spec("drc", "D2")
        parameters = fit_model(spec, records)
        prediction = predict_records(
            spec, parameters, [record("x", 400, 1800, 0.0, qp=8)]
        )[0]
        self.assertAlmostEqual(prediction, 0.5 + 1.2 * 0.4 + 0.3 * 1.8, places=10)

    def test_within_five_percent_prefers_simpler_model(self) -> None:
        evaluations = [
            self._evaluation("complex", mae=1.0, parameter_count=2, valid=True),
            self._evaluation("simple", mae=1.04, parameter_count=1, valid=True),
        ]
        self.assertEqual(choose_model(evaluations)["model_id"], "simple")

    def test_invalid_prediction_model_cannot_be_selected(self) -> None:
        evaluations = [
            self._evaluation("invalid-best", mae=0.1, parameter_count=1, valid=False),
            self._evaluation("valid-baseline", mae=2.0, parameter_count=0, valid=True),
        ]
        self.assertEqual(choose_model(evaluations)["model_id"], "valid-baseline")

    def test_nonnegative_models_fit_nonnegative_parameters_and_predictions(self) -> None:
        records = [
            record("tile-a", 100, 1000, 0.1),
            record("tile-b", 200, 2000, 0.2),
            record("tile-c", 300, 3000, 0.3),
        ]
        for representation, model_id in (("ply", "P3"), ("drc", "D4")):
            spec = model_spec(representation, model_id)
            parameters = fit_model(spec, records)
            self.assertTrue(all(value >= 0 for value in parameters.values()))
            predictions = predict_records(spec, parameters, records)
            self.assertTrue(all(value >= 0 for value in predictions))

    def test_recommendation_threshold(self) -> None:
        self.assertTrue(
            recommendation_status(
                predictions_valid=True, normalized_mae=0.30, identity_error_count=0
            )
        )
        self.assertFalse(
            recommendation_status(
                predictions_valid=True, normalized_mae=0.300001, identity_error_count=0
            )
        )
        self.assertFalse(
            recommendation_status(
                predictions_valid=False, normalized_mae=0.1, identity_error_count=0
            )
        )

    def test_identity_fields_are_not_model_features(self) -> None:
        for specs in MODEL_SPECS.values():
            for spec in specs:
                self.assertNotIn("tile_id", spec.feature_set)
                self.assertNotIn("candidate_id", spec.feature_set)
                self.assertNotIn("candidate_key", spec.feature_set)

    def test_calibration_artifact_uses_calibrated_provenance(self) -> None:
        pilot, inventory = self._synthetic_pilot_and_inventory()
        artifact = calibrate_models(
            pilot,
            inventory,
            source_pilot_sha256="PILOT",
            source_inventory_sha256="INVENTORY",
        )
        self.assertEqual(artifact["provenance"], "calibrated")
        self.assertEqual(artifact["representation_models"]["ply"]["provenance"], "calibrated")
        self.assertEqual(artifact["representation_models"]["drc"]["provenance"], "calibrated")
        self.assertNotEqual(artifact["provenance"], "measured")
        self.assertNotEqual(artifact["provenance"], "derived")
        self.assertEqual(artifact["measurement_kind"], "core_parse_microbenchmark")
        self.assertFalse(artifact["eligible_for_allocation"])
        self.assertEqual(
            artifact["allocation_integration_status"], "ineligible_measurement_scope"
        )

    @staticmethod
    def _evaluation(model_id: str, *, mae: float, parameter_count: int, valid: bool) -> dict:
        return {
            "model_id": model_id,
            "parameter_count_without_intercept": parameter_count,
            "cross_validation_metrics": {"mean_fold_mae_ms": mae},
            "eligible_for_selection": valid,
        }

    @staticmethod
    def _synthetic_pilot_and_inventory() -> tuple[dict, dict]:
        results = []
        candidates = []
        for tile_index in range(5):
            tile_id = f"tile-{tile_index}"
            for pdl_index in range(5):
                point_count = 100 + tile_index * 100 + pdl_index * 20
                key = f"{tile_id}|ply|{pdl_index}"
                results.append(
                    CalibrationTest._measured_record(
                        key, tile_id, "ply", point_count, point_count * 12, 0.5 + point_count / 1000
                    )
                )
                candidates.append(
                    CalibrationTest._inventory_record(
                        key, tile_id, "ply", point_count, point_count * 12, qp=None
                    )
                )
            for pdl_index in range(5):
                for qp in (8, 10, 12):
                    point_count = 100 + tile_index * 100 + pdl_index * 20
                    file_size = point_count * 4 + qp * 3
                    key = f"{tile_id}|drc|{pdl_index}|{qp}"
                    results.append(
                        CalibrationTest._measured_record(
                            key,
                            tile_id,
                            "drc",
                            point_count,
                            file_size,
                            0.2 + 0.3 * point_count / 1000,
                            qp=qp,
                        )
                    )
                    candidates.append(
                        CalibrationTest._inventory_record(
                            key, tile_id, "drc", point_count, file_size, qp=qp
                        )
                    )
        pilot = {
            "status": "success",
            "candidate_count": 100,
            "success_count": 100,
            "failure_count": 0,
            "environment_id": "python_windows_x64",
            "measurement_scope": "longdress_frame1051_pilot",
            "provenance": "measured",
            "eligible_for_final_model": False,
            "eligible_for_allocation": False,
            "results": results,
        }
        return pilot, {"candidates": candidates}

    @staticmethod
    def _measured_record(
        key: str,
        tile_id: str,
        representation: str,
        point_count: int,
        file_size_bytes: int,
        p50_ms: float,
        *,
        qp: int | None = None,
    ) -> dict:
        return {
            "candidate_key": key,
            "tile_id": tile_id,
            "representation": representation,
            "status": "success",
            "provenance": "measured",
            "measurement_scope": "longdress_frame1051_pilot",
            "eligible_for_final_model": False,
            "eligible_for_allocation": False,
            "p50_ms": p50_ms,
            "mean_ms": p50_ms,
            "point_count": point_count,
            "decoded_point_count": point_count,
            "file_size_bytes": file_size_bytes,
            "qp": qp,
        }

    @staticmethod
    def _inventory_record(
        key: str,
        tile_id: str,
        representation: str,
        point_count: int,
        file_size_bytes: int,
        *,
        qp: int | None,
    ) -> dict:
        return {
            "candidate_key": key,
            "dataset_id": "synthetic",
            "frame_id": 1051,
            "grid_profile_id": "grid-test",
            "tile_id": tile_id,
            "representation": representation,
            "point_count": point_count,
            "file_size_bytes": file_size_bytes,
            "codec_params": {"qp": qp, "cl": 10} if representation == "drc" else {},
        }


if __name__ == "__main__":
    unittest.main()
