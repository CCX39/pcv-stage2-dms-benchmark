from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Iterable

import numpy as np

from pcv_dms_benchmark.measurement_records import (
    INELIGIBLE_SCOPE,
    evaluate_allocation_eligibility,
    resolve_measurement_contract,
)


TARGET_STATISTIC = "p50_ms"
CALIBRATION_ID = "python_frame1051_p50_calibration_v1"
POINT_COUNT_SCALE = 1000.0
FILE_SIZE_SCALE = 1000.0


class CalibrationError(ValueError):
    """Raised when measured input or calibration output violates the contract."""


@dataclass(frozen=True)
class ModelSpec:
    model_id: str
    representation: str
    feature_set: tuple[str, ...]
    parameter_count_without_intercept: int
    formula: str


MODEL_SPECS = {
    "ply": (
        ModelSpec("P0", "ply", (), 0, "d_hat_ms = median(training p50_ms)"),
        ModelSpec(
            "P1",
            "ply",
            ("point_count",),
            1,
            "d_hat_ms = intercept + point_count_coef * (point_count / 1000)",
        ),
        ModelSpec(
            "P2",
            "ply",
            ("file_size_bytes",),
            1,
            "d_hat_ms = intercept + file_size_bytes_coef * (file_size_bytes / 1000)",
        ),
        ModelSpec(
            "P3",
            "ply",
            ("point_count",),
            1,
            "d_hat_ms = nonnegative_intercept + nonnegative_point_count_coef * "
            "(point_count / 1000)",
        ),
    ),
    "drc": (
        ModelSpec("D0", "drc", (), 0, "d_hat_ms = median(training p50_ms)"),
        ModelSpec(
            "D1",
            "drc",
            ("point_count",),
            1,
            "d_hat_ms = intercept + point_count_coef * (point_count / 1000)",
        ),
        ModelSpec(
            "D2",
            "drc",
            ("point_count", "file_size_bytes"),
            2,
            "d_hat_ms = intercept + point_count_coef * (point_count / 1000) + "
            "file_size_bytes_coef * (file_size_bytes / 1000)",
        ),
        ModelSpec(
            "D3",
            "drc",
            ("point_count", "file_size_bytes", "qp"),
            4,
            "d_hat_ms = intercept + point_count_coef * (point_count / 1000) + "
            "file_size_bytes_coef * (file_size_bytes / 1000) + "
            "qp10_effect * I(qp=10) + qp12_effect * I(qp=12); qp=8 is baseline",
        ),
        ModelSpec(
            "D4",
            "drc",
            ("point_count",),
            1,
            "d_hat_ms = nonnegative_intercept + nonnegative_point_count_coef * "
            "(point_count / 1000)",
        ),
    ),
}


def audit_pilot(
    pilot: dict[str, Any],
    inventory: dict[str, Any],
    *,
    expected_environment_id: str = "python_windows_x64",
    expected_measurement_scope: str = "longdress_frame1051_pilot",
) -> dict[str, Any]:
    errors: list[str] = []
    source_contract = resolve_measurement_contract(pilot)
    results = pilot.get("results")
    inventory_candidates = inventory.get("candidates")
    if not isinstance(results, list):
        raise CalibrationError("pilot.results must be a list")
    if not isinstance(inventory_candidates, list):
        raise CalibrationError("inventory.candidates must be a list")

    expected_top_level = {
        "status": "success",
        "environment_id": expected_environment_id,
        "candidate_count": 100,
        "success_count": 100,
        "failure_count": 0,
        "measurement_scope": expected_measurement_scope,
        "provenance": "measured",
        "eligible_for_final_model": False,
        "eligible_for_allocation": False,
    }
    for field, expected in expected_top_level.items():
        if pilot.get(field) != expected:
            errors.append(f"pilot.{field} must be {expected!r}, got {pilot.get(field)!r}")
    if len(results) != 100:
        errors.append(f"pilot.results must contain 100 records, got {len(results)}")

    inventory_keys = {
        item.get("candidate_key")
        for item in inventory_candidates
        if isinstance(item, dict) and item.get("candidate_key")
    }
    result_keys: list[str] = []
    representation_counts = {"ply": 0, "drc": 0}
    for index, record in enumerate(results):
        prefix = f"pilot.results[{index}]"
        if not isinstance(record, dict):
            errors.append(f"{prefix} must be an object")
            continue
        key = record.get("candidate_key")
        if not isinstance(key, str) or not key:
            errors.append(f"{prefix}.candidate_key is missing")
        else:
            result_keys.append(key)
            if key not in inventory_keys:
                errors.append(f"{prefix}.candidate_key is not present in inventory: {key}")
        representation = record.get("representation")
        if representation in representation_counts:
            representation_counts[representation] += 1
        else:
            errors.append(f"{prefix}.representation is unsupported: {representation!r}")
        if record.get("status") != "success":
            errors.append(f"{prefix}.status must be success")
        if record.get("provenance") != "measured":
            errors.append(f"{prefix}.provenance must be measured")
        if record.get("measurement_scope") != expected_measurement_scope:
            errors.append(f"{prefix}.measurement_scope is invalid")
        if record.get("eligible_for_final_model") is not False:
            errors.append(f"{prefix}.eligible_for_final_model must be false")
        if record.get("eligible_for_allocation") is not False:
            errors.append(f"{prefix}.eligible_for_allocation must be false")
        try:
            record_contract = resolve_measurement_contract(record)
        except ValueError as exc:
            errors.append(f"{prefix} has invalid timing contract: {exc}")
        else:
            if record_contract != source_contract:
                errors.append(f"{prefix} timing contract differs from pilot")
        for field in ("p50_ms", "mean_ms", "point_count", "file_size_bytes"):
            if not _is_positive_finite(record.get(field)):
                errors.append(f"{prefix}.{field} must be a finite positive number")
        if record.get("decoded_point_count") != record.get("point_count"):
            errors.append(f"{prefix}.decoded_point_count does not match point_count")

    if len(result_keys) != len(set(result_keys)):
        errors.append("pilot candidate_key values must be unique")
    if representation_counts != {"ply": 25, "drc": 75}:
        errors.append(f"pilot representation counts are invalid: {representation_counts}")
    if errors:
        raise CalibrationError("pilot audit failed:\n- " + "\n- ".join(errors))

    return {
        "status": "passed",
        "candidate_count": len(results),
        "representation_counts": representation_counts,
        "unique_candidate_key_count": len(set(result_keys)),
        "identity_error_count": 0,
        **source_contract,
    }


def calibrate_models(
    pilot: dict[str, Any],
    inventory: dict[str, Any],
    *,
    source_pilot_sha256: str,
    source_inventory_sha256: str,
    calibration_id: str = CALIBRATION_ID,
    expected_environment_id: str = "python_windows_x64",
    expected_measurement_scope: str = "longdress_frame1051_pilot",
    allocation_use_scope: str = "provisional_frame1051_python_pilot",
    profile_limitation: str = "specific to CPython 3.13.0 and the phase 1A Python backends",
    delivery_version: str | None = None,
) -> dict[str, Any]:
    audit = audit_pilot(
        pilot,
        inventory,
        expected_environment_id=expected_environment_id,
        expected_measurement_scope=expected_measurement_scope,
    )
    inventory_candidates = inventory["candidates"]
    measured_records = pilot["results"]
    identity = _inventory_identity(inventory_candidates)
    source_contract = resolve_measurement_contract(pilot)
    representation_models: dict[str, Any] = {}

    for representation in ("ply", "drc"):
        records = [item for item in measured_records if item["representation"] == representation]
        scope_candidates = [
            item for item in inventory_candidates if item.get("representation") == representation
        ]
        evaluations = [
            evaluate_model(spec, records, scope_candidates)
            for spec in MODEL_SPECS[representation]
        ]
        selected_evaluation = choose_model(evaluations)
        selected_spec = _model_spec(representation, selected_evaluation["model_id"])
        fit_parameters = fit_model(selected_spec, records)
        selected_predictions = predict_records(selected_spec, fit_parameters, scope_candidates)
        predictions_valid = _predictions_are_positive_finite(selected_predictions)
        normalized_mae = selected_evaluation["cross_validation_metrics"]["normalized_mae"]
        recommended = recommendation_status(
            predictions_valid=predictions_valid,
            normalized_mae=normalized_mae,
            identity_error_count=audit["identity_error_count"],
        )
        limitations = _representation_limitations(
            representation,
            recommended=recommended,
            predictions_valid=predictions_valid,
            normalized_mae=normalized_mae,
            profile_limitation=profile_limitation,
        )
        representation_models[representation] = {
            "representation": representation,
            "candidate_models": evaluations,
            "selected_model": selected_spec.model_id,
            "feature_set": list(selected_spec.feature_set),
            "formula": selected_spec.formula,
            "feature_scales": _feature_scales(selected_spec),
            "fit_parameters": fit_parameters,
            "cross_validation_metrics": selected_evaluation["cross_validation_metrics"],
            "training_candidate_count": len(records),
            "training_tile_count": len({item["tile_id"] for item in records}),
            "applicable_scope": {
                "dataset_id": identity["dataset_id"],
                "frame_id": identity["frame_id"],
                "grid_profile_id": identity["grid_profile_id"],
                "environment_id": pilot["environment_id"],
                "representation": representation,
            },
            "recommended_for_allocation_pilot": recommended,
            "allocation_use_scope": allocation_use_scope,
            "eligible_for_final_model": False,
            "cross_dataset_validated": False,
            "cross_frame_validated": False,
            "limitations": limitations,
            "provenance": "calibrated",
            **source_contract,
            "eligible_for_allocation": False,
        }

    validation_passed = all(
        model["recommended_for_allocation_pilot"] for model in representation_models.values()
    )
    applicable_scope = {
        "dataset_id": identity["dataset_id"],
        "frame_id": identity["frame_id"],
        "grid_profile_id": identity["grid_profile_id"],
        "environment_id": pilot["environment_id"],
    }
    eligibility_input = {
        **source_contract,
        "environment_id": pilot["environment_id"],
        "profile_implementation_confirmed": pilot.get(
            "profile_implementation_confirmed", False
        ),
        "network_time_included": pilot.get("network_time_included", False),
        "rendering_time_included": pilot.get("rendering_time_included", False),
        "provenance_complete": True,
        "validation_passed": validation_passed,
        "applicable_scope": applicable_scope,
    }
    eligibility = evaluate_allocation_eligibility(
        eligibility_input, release_gate_passed=False
    )
    artifact = {
        "calibration_schema_version": "1.0.0",
        "calibration_id": calibration_id,
        "environment_id": pilot["environment_id"],
        "dataset_id": identity["dataset_id"],
        "frame_id": identity["frame_id"],
        "grid_profile_id": identity["grid_profile_id"],
        "target_statistic": TARGET_STATISTIC,
        "source_pilot_sha256": source_pilot_sha256,
        "source_inventory_sha256": source_inventory_sha256,
        "pilot_audit": audit,
        "validation_protocol": {
            "protocol_id": "leave_one_tile_out",
            "group_field": "tile_id",
            "fold_count": 5,
            "selection_metric": "mean_fold_mae_ms",
            "selection_tolerance_relative": 0.05,
            "target_statistic": TARGET_STATISTIC,
        },
        "representation_models": representation_models,
        "provenance": "calibrated",
        **source_contract,
        "profile_implementation_confirmed": eligibility_input[
            "profile_implementation_confirmed"
        ],
        "network_time_included": eligibility_input["network_time_included"],
        "rendering_time_included": eligibility_input["rendering_time_included"],
        "provenance_complete": True,
        "validation_passed": validation_passed,
        "applicable_scope": applicable_scope,
        "eligible_for_allocation": False,
        "allocation_integration_status": eligibility.get(
            "allocation_integration_status", INELIGIBLE_SCOPE
        ),
    }
    if delivery_version is not None:
        artifact["delivery_version"] = delivery_version
    return artifact


def evaluate_model(
    spec: ModelSpec,
    measured_records: list[dict[str, Any]],
    inventory_candidates: list[dict[str, Any]],
) -> dict[str, Any]:
    cv_metrics = leave_one_tile_out(spec, measured_records)
    fit_parameters = fit_model(spec, measured_records)
    inventory_predictions = predict_records(spec, fit_parameters, inventory_candidates)
    predictions_valid = (
        cv_metrics["predictions_are_finite_positive"]
        and _predictions_are_positive_finite(inventory_predictions)
    )
    return {
        "model_id": spec.model_id,
        "feature_set": list(spec.feature_set),
        "parameter_count_without_intercept": spec.parameter_count_without_intercept,
        "formula": spec.formula,
        "feature_scales": _feature_scales(spec),
        "cross_validation_metrics": cv_metrics,
        "full_fit_parameters": fit_parameters,
        "all_scope_predictions_are_finite_positive": predictions_valid,
        "eligible_for_selection": predictions_valid,
    }


def leave_one_tile_out(
    spec: ModelSpec, records: list[dict[str, Any]]
) -> dict[str, Any]:
    tile_ids = sorted({str(item["tile_id"]) for item in records})
    if len(tile_ids) < 2:
        raise CalibrationError("leave-one-tile-out requires at least two tiles")

    all_targets: list[float] = []
    all_predictions: list[float] = []
    folds: list[dict[str, Any]] = []
    for validation_tile in tile_ids:
        training = [item for item in records if str(item["tile_id"]) != validation_tile]
        validation = [item for item in records if str(item["tile_id"]) == validation_tile]
        train_tiles = sorted({str(item["tile_id"]) for item in training})
        if validation_tile in train_tiles:
            raise CalibrationError("tile leakage detected in grouped validation")
        parameters = fit_model(spec, training)
        predictions = predict_records(spec, parameters, validation)
        targets = [float(item[TARGET_STATISTIC]) for item in validation]
        fold_metrics = error_metrics(targets, predictions)
        folds.append(
            {
                "validation_tile_id": validation_tile,
                "training_tile_ids": train_tiles,
                "training_candidate_count": len(training),
                "validation_candidate_count": len(validation),
                **fold_metrics,
            }
        )
        all_targets.extend(targets)
        all_predictions.extend(predictions)

    aggregate = error_metrics(all_targets, all_predictions)
    aggregate.update(
        {
            "mean_fold_mae_ms": float(np.mean([fold["mae_ms"] for fold in folds])),
            "fold_count": len(folds),
            "prediction_count": len(all_predictions),
            "predictions_are_finite_positive": _predictions_are_positive_finite(all_predictions),
            "folds": folds,
        }
    )
    return aggregate


def fit_model(spec: ModelSpec, records: list[dict[str, Any]]) -> dict[str, float]:
    if not records:
        raise CalibrationError(f"cannot fit {spec.model_id} without records")
    targets = np.asarray([float(item[TARGET_STATISTIC]) for item in records], dtype=np.float64)
    if spec.model_id in {"P0", "D0"}:
        return {"constant_median_ms": float(np.median(targets))}

    design, parameter_names = _design_matrix(spec, records)
    if spec.model_id in {"P3", "D4"}:
        coefficients = _fit_nonnegative_intercept_slope(design, targets)
        return {
            name: float(value)
            for name, value in zip(parameter_names, coefficients, strict=True)
        }
    coefficients, _, _, _ = np.linalg.lstsq(design, targets, rcond=None)
    return {name: float(value) for name, value in zip(parameter_names, coefficients, strict=True)}


def _fit_nonnegative_intercept_slope(
    design: np.ndarray, targets: np.ndarray
) -> np.ndarray:
    if design.shape[1] != 2:
        raise CalibrationError("nonnegative model requires intercept and one feature")
    feature = design[:, 1]
    candidates: list[np.ndarray] = []
    unconstrained, _, _, _ = np.linalg.lstsq(design, targets, rcond=None)
    if np.all(unconstrained >= 0):
        candidates.append(unconstrained)

    intercept_only = np.asarray([max(0.0, float(np.mean(targets))), 0.0])
    denominator = float(np.dot(feature, feature))
    slope = (
        0.0
        if denominator == 0
        else max(0.0, float(np.dot(feature, targets)) / denominator)
    )
    candidates.extend(
        (
            intercept_only,
            np.asarray([0.0, slope]),
            np.zeros(2, dtype=np.float64),
        )
    )
    return min(
        candidates,
        key=lambda coefficients: float(
            np.sum(np.square(targets - design @ coefficients))
        ),
    )


def predict_records(
    spec: ModelSpec,
    fit_parameters: dict[str, float],
    records: list[dict[str, Any]],
) -> list[float]:
    if spec.model_id in {"P0", "D0"}:
        value = float(fit_parameters["constant_median_ms"])
        return [value for _ in records]
    design, parameter_names = _design_matrix(spec, records)
    coefficients = np.asarray([fit_parameters[name] for name in parameter_names], dtype=np.float64)
    return [float(value) for value in design @ coefficients]


def error_metrics(targets: Iterable[float], predictions: Iterable[float]) -> dict[str, float]:
    target_values = np.asarray(list(targets), dtype=np.float64)
    prediction_values = np.asarray(list(predictions), dtype=np.float64)
    if target_values.size == 0 or target_values.shape != prediction_values.shape:
        raise CalibrationError("targets and predictions must be non-empty and have equal shape")
    absolute_errors = np.abs(prediction_values - target_values)
    mae = float(np.mean(absolute_errors))
    target_median = float(np.median(target_values))
    if target_median <= 0:
        raise CalibrationError("target median must be positive")
    return {
        "mae_ms": mae,
        "rmse_ms": float(np.sqrt(np.mean(np.square(prediction_values - target_values)))),
        "median_absolute_error_ms": float(np.median(absolute_errors)),
        "normalized_mae": mae / target_median,
    }


def choose_model(evaluations: list[dict[str, Any]]) -> dict[str, Any]:
    eligible = [item for item in evaluations if item.get("eligible_for_selection") is True]
    if not eligible:
        raise CalibrationError("no candidate model has finite positive predictions")
    best_mae = min(
        float(item["cross_validation_metrics"]["mean_fold_mae_ms"])
        for item in eligible
    )
    within_tolerance = [
        item
        for item in eligible
        if float(item["cross_validation_metrics"]["mean_fold_mae_ms"])
        <= best_mae * 1.05
    ]
    return min(
        within_tolerance,
        key=lambda item: (
            int(item["parameter_count_without_intercept"]),
            float(item["cross_validation_metrics"]["mean_fold_mae_ms"]),
            str(item["model_id"]),
        ),
    )


def recommendation_status(
    *, predictions_valid: bool, normalized_mae: float, identity_error_count: int
) -> bool:
    return (
        predictions_valid
        and math.isfinite(normalized_mae)
        and normalized_mae <= 0.30
        and identity_error_count == 0
    )


def model_spec(representation: str, model_id: str) -> ModelSpec:
    return _model_spec(representation, model_id)


def _design_matrix(
    spec: ModelSpec, records: list[dict[str, Any]]
) -> tuple[np.ndarray, tuple[str, ...]]:
    columns = [np.ones(len(records), dtype=np.float64)]
    names = ["intercept_ms"]
    if "point_count" in spec.feature_set:
        columns.append(
            np.asarray([float(item["point_count"]) for item in records]) / POINT_COUNT_SCALE
        )
        names.append("point_count_coef_ms_per_1000_points")
    if "file_size_bytes" in spec.feature_set:
        columns.append(
            np.asarray([float(item["file_size_bytes"]) for item in records]) / FILE_SIZE_SCALE
        )
        names.append("file_size_bytes_coef_ms_per_1000_bytes")
    if "qp" in spec.feature_set:
        qp_values = [int(_codec_value(item, "qp")) for item in records]
        unexpected = sorted(set(qp_values) - {8, 10, 12})
        if unexpected:
            raise CalibrationError(f"unsupported qp values for D3: {unexpected}")
        columns.append(np.asarray([value == 10 for value in qp_values], dtype=np.float64))
        columns.append(np.asarray([value == 12 for value in qp_values], dtype=np.float64))
        names.extend(("qp10_effect_ms", "qp12_effect_ms"))
    return np.column_stack(columns), tuple(names)


def _codec_value(record: dict[str, Any], field: str) -> Any:
    if record.get(field) is not None:
        return record[field]
    codec_params = record.get("codec_params") or {}
    if codec_params.get(field) is None:
        raise CalibrationError(f"record is missing {field}")
    return codec_params[field]


def _feature_scales(spec: ModelSpec) -> dict[str, float]:
    scales: dict[str, float] = {}
    if "point_count" in spec.feature_set:
        scales["point_count"] = POINT_COUNT_SCALE
    if "file_size_bytes" in spec.feature_set:
        scales["file_size_bytes"] = FILE_SIZE_SCALE
    return scales


def _model_spec(representation: str, model_id: str) -> ModelSpec:
    try:
        return next(spec for spec in MODEL_SPECS[representation] if spec.model_id == model_id)
    except (KeyError, StopIteration) as exc:
        raise CalibrationError(f"unknown model: {representation}/{model_id}") from exc


def _inventory_identity(candidates: list[dict[str, Any]]) -> dict[str, Any]:
    identity: dict[str, Any] = {}
    for field in ("dataset_id", "frame_id", "grid_profile_id"):
        values = {item.get(field) for item in candidates}
        if len(values) != 1 or None in values:
            raise CalibrationError(f"inventory must have one non-null {field}: {values}")
        identity[field] = values.pop()
    return identity


def _representation_limitations(
    representation: str,
    *,
    recommended: bool,
    predictions_valid: bool,
    normalized_mae: float,
    profile_limitation: str,
) -> list[str]:
    limitations = [
        "calibrated from one Longdress frame and five measured tiles",
        "not cross-frame or cross-dataset validated",
        profile_limitation,
        f"applies only to frame1051 {representation} candidates covered by the active metadata profile",
    ]
    if not predictions_valid:
        limitations.append("selected model did not produce finite positive predictions for all candidates")
    if normalized_mae > 0.30:
        limitations.append("leave-one-tile-out normalized_mae exceeds 0.30")
    if not recommended:
        limitations.append("not recommended for allocation pilot replacement")
    return limitations


def _predictions_are_positive_finite(values: Iterable[float]) -> bool:
    values_list = list(values)
    return bool(values_list) and all(math.isfinite(value) and value > 0 for value in values_list)


def _is_positive_finite(value: Any) -> bool:
    if isinstance(value, bool):
        return False
    try:
        number = float(value)
    except (TypeError, ValueError):
        return False
    return math.isfinite(number) and number > 0
