from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Any

from pcv_dms_benchmark.calibration import model_spec, predict_records
from pcv_dms_benchmark.measurement_records import (
    READY,
    evaluate_allocation_eligibility,
    resolve_measurement_contract,
)


class DerivedExportError(ValueError):
    """Raised when a versioned handoff cannot be generated safely."""


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as input_file:
        for chunk in iter(lambda: input_file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def build_measured_summary(
    pilot: dict[str, Any],
    *,
    source_pilot_sha256: str,
    delivery_version: str | None = None,
) -> dict[str, Any]:
    contract = resolve_measurement_contract(pilot)
    records = []
    for result in pilot["results"]:
        records.append(
            {
                "candidate_key": result["candidate_key"],
                "candidate_id": result["candidate_id"],
                "tile_id": result["tile_id"],
                "representation": result["representation"],
                "pdl_ratio": result["pdl_ratio"],
                "qp": result.get("qp"),
                "cl": result.get("cl"),
                "point_count": result["point_count"],
                "file_size_bytes": result["file_size_bytes"],
                "p50_ms": result["p50_ms"],
                "mean_ms": result["mean_ms"],
                "provenance": "measured",
                "measurement_scope": result["measurement_scope"],
                **contract,
                "eligible_for_allocation": False,
            }
        )
    summary = {
        "measured_summary_schema_version": "1.0.0",
        "source_pilot_sha256": source_pilot_sha256,
        "environment_id": pilot["environment_id"],
        "target_statistic": "p50_ms",
        "candidate_count": len(records),
        "provenance": "measured",
        **contract,
        "eligible_for_allocation": False,
        "records": records,
    }
    if delivery_version is not None:
        summary["delivery_version"] = delivery_version
    if pilot.get("environment_snapshot") is not None:
        summary["environment_snapshot"] = pilot["environment_snapshot"]
    return summary


def build_derived_handoff(
    inventory: dict[str, Any],
    calibration: dict[str, Any],
    *,
    expected_representation_counts: dict[str, int] | None = None,
    handoff_id: str = "python_frame1051_candidate_dms_v1",
    allocation_use_scope: str = "provisional_frame1051_python_pilot",
    limitations: list[str] | None = None,
    delivery_version: str | None = None,
    allocation_integration_status: str | None = None,
) -> dict[str, Any]:
    candidates = inventory.get("candidates")
    if not isinstance(candidates, list):
        raise DerivedExportError("inventory.candidates must be a list")
    models = calibration["representation_models"]
    contract = resolve_measurement_contract(calibration)
    requested_ready = allocation_integration_status == READY
    eligibility = evaluate_allocation_eligibility(
        calibration, release_gate_passed=requested_ready
    )
    derived_candidates: list[dict[str, Any]] = []
    representation_status: dict[str, Any] = {}

    for representation in ("ply", "drc"):
        scope = [item for item in candidates if item.get("representation") == representation]
        model = models[representation]
        spec = model_spec(representation, model["selected_model"])
        predictions = predict_records(spec, model["fit_parameters"], scope)
        if not predictions or not all(math.isfinite(value) and value > 0 for value in predictions):
            raise DerivedExportError(
                f"{representation} selected model produced invalid derived predictions"
            )
        recommended = bool(model["recommended_for_allocation_pilot"])
        representation_status[representation] = {
            "candidate_count": len(scope),
            "selected_model": model["selected_model"],
            "normalized_mae": model["cross_validation_metrics"]["normalized_mae"],
            "recommended_for_allocation_pilot": recommended,
            "measurement_kind": contract["measurement_kind"],
            "eligible_for_allocation": eligibility["eligible_for_allocation"],
        }
        for candidate, prediction in zip(scope, predictions, strict=True):
            codec_params = candidate.get("codec_params") or {}
            derived_candidates.append(
                {
                    "candidate_key": candidate["candidate_key"],
                    "candidate_id": candidate["candidate_id"],
                    "dataset_id": candidate["dataset_id"],
                    "frame_id": candidate["frame_id"],
                    "grid_profile_id": candidate["grid_profile_id"],
                    "tile_id": candidate["tile_id"],
                    "representation": representation,
                    "pdl_ratio": candidate["pdl_ratio"],
                    "qp": codec_params.get("qp"),
                    "cl": codec_params.get("cl"),
                    "point_count": candidate["point_count"],
                    "file_size_bytes": candidate["file_size_bytes"],
                    "d_hat_ms": prediction,
                    "calibration_id": calibration["calibration_id"],
                    "provenance": "derived",
                    "recommended_for_allocation_pilot": recommended,
                    **contract,
                    "eligible_for_allocation": eligibility[
                        "eligible_for_allocation"
                    ],
                }
            )

    if expected_representation_counts is not None:
        actual_counts = {
            representation: representation_status[representation]["candidate_count"]
            for representation in ("ply", "drc")
        }
        if actual_counts != expected_representation_counts:
            raise DerivedExportError(
                "handoff representation counts mismatch: "
                f"expected={expected_representation_counts}, actual={actual_counts}"
            )

    derived_candidates.sort(key=lambda item: item["candidate_key"])
    _validate_candidate_identity(derived_candidates, expected_count=len(candidates))
    artifact = {
        "handoff_schema_version": "1.0.0",
        "handoff_id": handoff_id,
        "environment_id": calibration["environment_id"],
        "dataset_id": calibration["dataset_id"],
        "frame_id": calibration["frame_id"],
        "grid_profile_id": calibration["grid_profile_id"],
        "calibration_id": calibration["calibration_id"],
        "target_statistic": calibration["target_statistic"],
        "candidate_count": len(derived_candidates),
        "representation_status": representation_status,
        "provenance": "derived",
        **contract,
        "eligible_for_allocation": eligibility["eligible_for_allocation"],
        "allocation_integration_status": eligibility[
            "allocation_integration_status"
        ],
        "allocation_eligibility_review": eligibility,
        "allocation_use_scope": allocation_use_scope,
        "eligible_for_final_model": False,
        "cross_dataset_validated": False,
        "cross_frame_validated": False,
        "limitations": limitations
        or [
            "derived from one Longdress frame and five measured tiles",
            "not cross-frame or cross-dataset validated",
            "environment-specific to the phase 1A Python runtime and backends",
            "allocation must join by candidate_key and verify tile_id plus candidate_id",
        ],
        "candidates": derived_candidates,
    }
    if delivery_version is not None:
        artifact["delivery_version"] = delivery_version
    return artifact


def write_json(path: str | Path, payload: dict[str, Any]) -> None:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _validate_candidate_identity(
    candidates: list[dict[str, Any]], *, expected_count: int
) -> None:
    if len(candidates) != expected_count:
        raise DerivedExportError(
            f"handoff candidate count mismatch: expected={expected_count}, actual={len(candidates)}"
        )
    candidate_keys = [item["candidate_key"] for item in candidates]
    if len(candidate_keys) != len(set(candidate_keys)):
        raise DerivedExportError("handoff candidate_key values must be unique")
    join_keys = [(item["tile_id"], item["candidate_id"]) for item in candidates]
    if len(join_keys) != len(set(join_keys)):
        raise DerivedExportError("tile_id + candidate_id values must be unique")
    if any(item["provenance"] != "derived" for item in candidates):
        raise DerivedExportError("handoff candidate provenance must be derived")
    if any("raw_samples_ms" in item for item in candidates):
        raise DerivedExportError("handoff must not contain raw_samples_ms")
