from __future__ import annotations

from typing import Any, Mapping


CORE_PARSE_MICROBENCHMARK = "core_parse_microbenchmark"
PARSE_STAGE_END_TO_END = "parse_stage_end_to_end"
PATH_LOADER_DIAGNOSTIC = "path_loader_diagnostic"
CAPABILITY_PROBE = "capability_probe"

COMPLETE_PAYLOAD_DELIVERED = "complete_payload_delivered_to_parser"
PATH_DELIVERED = "path_delivered_to_loader"
BACKEND_CORE_ENTRY = "backend_core_entry"
POSITIONS_COLORS_READY = "positions_colors_ready"

READY = "ready_for_provisional_integration"
REVIEW_PENDING = "review_pending"
INELIGIBLE_SCOPE = "ineligible_measurement_scope"

MEASUREMENT_KINDS = frozenset(
    {
        CORE_PARSE_MICROBENCHMARK,
        PARSE_STAGE_END_TO_END,
        PATH_LOADER_DIAGNOSTIC,
        CAPABILITY_PROBE,
    }
)
TIMING_STARTS = frozenset(
    {COMPLETE_PAYLOAD_DELIVERED, PATH_DELIVERED, BACKEND_CORE_ENTRY}
)


class MeasurementContractError(ValueError):
    """Raised when timing metadata violates the frozen measurement contract."""


def resolve_measurement_contract(record: Mapping[str, Any]) -> dict[str, str]:
    """Resolve contract fields, conservatively classifying legacy artifacts as core."""
    kind = record.get("measurement_kind", CORE_PARSE_MICROBENCHMARK)
    timing_start = record.get("timing_start", BACKEND_CORE_ENTRY)
    timing_end = record.get("timing_end", POSITIONS_COLORS_READY)
    if kind not in MEASUREMENT_KINDS:
        raise MeasurementContractError(f"unsupported measurement_kind: {kind!r}")
    if timing_start not in TIMING_STARTS:
        raise MeasurementContractError(f"unsupported timing_start: {timing_start!r}")
    if timing_end != POSITIONS_COLORS_READY:
        raise MeasurementContractError(
            f"timing_end must be {POSITIONS_COLORS_READY!r}, got {timing_end!r}"
        )
    return {
        "measurement_kind": str(kind),
        "timing_start": str(timing_start),
        "timing_end": str(timing_end),
    }


def evaluate_allocation_eligibility(
    record: Mapping[str, Any], *, release_gate_passed: bool
) -> dict[str, Any]:
    contract = resolve_measurement_contract(record)
    unmet: list[str] = []
    if contract["measurement_kind"] != PARSE_STAGE_END_TO_END:
        unmet.append("measurement_kind must be parse_stage_end_to_end")
    if contract["timing_start"] not in {COMPLETE_PAYLOAD_DELIVERED, PATH_DELIVERED}:
        unmet.append("timing_start must represent candidate delivery to the actual parser/loader")
    if not str(record.get("environment_id") or "").strip():
        unmet.append("environment_id must identify the target environment")
    if record.get("profile_implementation_confirmed") is not True:
        unmet.append("parser/loader/decoder must be the confirmed target implementation")
    if record.get("network_time_included") is not False:
        unmet.append("network transfer must be excluded")
    if record.get("rendering_time_included") is not False:
        unmet.append("rendering work must be excluded")
    if record.get("provenance_complete") is not True:
        unmet.append("measured/calibrated/derived provenance must be complete")
    if record.get("validation_passed") is not True:
        unmet.append("sample and model validation must pass")
    if not record.get("applicable_scope"):
        unmet.append("applicable_scope must be explicit")
    if not release_gate_passed:
        unmet.append("allocation release gate must pass")

    eligible = not unmet
    if eligible:
        status = READY
    elif contract["measurement_kind"] != PARSE_STAGE_END_TO_END:
        status = INELIGIBLE_SCOPE
    else:
        status = REVIEW_PENDING
    return {
        **contract,
        "eligible_for_allocation": eligible,
        "allocation_integration_status": status,
        "unmet_requirements": unmet,
    }


__all__ = [
    "BACKEND_CORE_ENTRY",
    "CAPABILITY_PROBE",
    "COMPLETE_PAYLOAD_DELIVERED",
    "CORE_PARSE_MICROBENCHMARK",
    "INELIGIBLE_SCOPE",
    "MEASUREMENT_KINDS",
    "PARSE_STAGE_END_TO_END",
    "PATH_DELIVERED",
    "PATH_LOADER_DIAGNOSTIC",
    "POSITIONS_COLORS_READY",
    "READY",
    "REVIEW_PENDING",
    "MeasurementContractError",
    "evaluate_allocation_eligibility",
    "resolve_measurement_contract",
]
