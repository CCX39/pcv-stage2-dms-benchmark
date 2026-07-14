from __future__ import annotations

import platform
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any, Callable

import numpy as np

from pcv_dms_benchmark.python_benchmark import (
    Processor,
    PythonBenchmarkError,
    decode_drc,
    parse_binary_ply,
    run_python_pilot,
)


ENVIRONMENT_ID = "python310_open3d019_dracopy200_windows_x64"
MEASUREMENT_SCOPE = "longdress_frame1051_python_open3d_v2_pilot"
MEASUREMENT_BOUNDARY = (
    "payload bytes resident in memory -> Open3D PLY parse or DracoPy DRC decode -> "
    "owned positions float32[N,3] and colors uint8[N,3]"
)
CALIBRATION_ID = "python310_open3d019_dracopy200_frame1051_p50_calibration_v2"
HANDOFF_ID = "python_open3d_frame1051_candidate_dms_v2"
ALLOCATION_USE_SCOPE = "provisional_frame1051_python310_open3d019_dracopy200_v2"
ReadPointCloudFromBytes = Callable[..., Any]


class Open3DPythonBackendError(PythonBenchmarkError):
    """Raised when the v2 Open3D memory profile violates its contract."""


def parse_binary_ply_open3d(
    payload: bytes,
    *,
    reader: ReadPointCloudFromBytes | None = None,
) -> tuple[np.ndarray, np.ndarray]:
    _validate_binary_ply_header(payload)
    if reader is None:
        try:
            import open3d as o3d
        except ImportError as exc:
            raise Open3DPythonBackendError("Open3D is not installed") from exc
        reader = getattr(o3d.io, "read_point_cloud_from_bytes", None)
        if reader is None:
            raise Open3DPythonBackendError(
                "Open3D read_point_cloud_from_bytes is unavailable"
            )

    point_cloud = reader(payload, format="ply")
    points_value = getattr(point_cloud, "points", None)
    colors_value = getattr(point_cloud, "colors", None)
    if points_value is None or colors_value is None:
        raise Open3DPythonBackendError("Open3D output has no points or colors")

    positions = np.array(points_value, dtype=np.float32, order="C", copy=True)
    colors_float = np.asarray(colors_value, dtype=np.float64)
    if not np.all(np.isfinite(colors_float)):
        raise Open3DPythonBackendError("Open3D colors contain non-finite values")
    if colors_float.size and (colors_float.min() < 0.0 or colors_float.max() > 1.0):
        raise Open3DPythonBackendError("Open3D colors must be normalized to [0, 1]")
    colors = np.array(
        np.rint(np.clip(colors_float, 0.0, 1.0) * 255.0),
        dtype=np.uint8,
        order="C",
        copy=True,
    )
    return positions, colors


def environment_snapshot() -> dict[str, str]:
    return {
        "python_version": platform.python_version(),
        "python_implementation": platform.python_implementation(),
        "operating_system": platform.platform(),
        "open3d_version": _package_version("open3d"),
        "dracopy_version": _package_version("DracoPy"),
        "numpy_version": np.__version__,
        "timer_api": "time.perf_counter_ns",
    }


def run_python_v2_pilot(
    candidates: list[dict[str, Any]],
    *,
    data_prep_root: str | Path,
    warmup_count: int = 2,
    sample_count: int = 5,
    run_id: str | None = None,
    processor_overrides: dict[str, Processor] | None = None,
) -> dict[str, Any]:
    snapshot = environment_snapshot()
    _validate_environment(snapshot)
    processors: dict[str, Processor] = {
        "ply": parse_binary_ply_open3d,
        "drc": decode_drc,
    }
    processors.update(processor_overrides or {})
    return run_python_pilot(
        candidates,
        data_prep_root=data_prep_root,
        warmup_count=warmup_count,
        sample_count=sample_count,
        run_id=run_id,
        processor_overrides=processors,
        backend_info_overrides={
            "ply": (
                "Open3D.from_bytes+numpy",
                f"Open3D={snapshot['open3d_version']};numpy={snapshot['numpy_version']}",
            ),
            "drc": (
                "DracoPy+numpy",
                f"DracoPy={snapshot['dracopy_version']};numpy={snapshot['numpy_version']}",
            ),
        },
        environment_id=ENVIRONMENT_ID,
        measurement_boundary=MEASUREMENT_BOUNDARY,
        measurement_scope=MEASUREMENT_SCOPE,
        environment_snapshot=snapshot,
    )


def verify_ply_candidate_against_legacy(
    candidate: dict[str, Any], *, data_prep_root: str | Path
) -> dict[str, Any]:
    asset_path = _resolve_asset_path(data_prep_root, candidate.get("asset_ref"))
    payload = asset_path.read_bytes()
    open3d_positions, open3d_colors = parse_binary_ply_open3d(payload)
    legacy_positions, legacy_colors = parse_binary_ply(payload)
    if open3d_positions.shape != legacy_positions.shape:
        raise Open3DPythonBackendError(
            "Open3D/plyfile point count mismatch during smoke verification"
        )
    position_error = float(np.max(np.abs(open3d_positions - legacy_positions)))
    if not np.allclose(open3d_positions, legacy_positions, rtol=1e-6, atol=1e-5):
        raise Open3DPythonBackendError(
            f"Open3D/plyfile coordinates differ: max_abs_error={position_error}"
        )
    color_error = np.abs(
        open3d_colors.astype(np.int16) - legacy_colors.astype(np.int16)
    )
    max_color_error = int(color_error.max(initial=0))
    if max_color_error > 1:
        raise Open3DPythonBackendError(
            f"Open3D/plyfile colors differ: max_level_error={max_color_error}"
        )
    return {
        "candidate_key": candidate.get("candidate_key"),
        "status": "passed",
        "point_count": int(open3d_positions.shape[0]),
        "max_position_abs_error": position_error,
        "max_color_level_error": max_color_error,
        "reference_backend": "plyfile_diagnostic_only",
    }


def audit_v2_smoke(smoke: dict[str, Any]) -> dict[str, Any]:
    results = smoke.get("results")
    if not isinstance(results, list):
        raise Open3DPythonBackendError("smoke.results must be a list")
    representation_counts = {
        representation: sum(
            item.get("representation") == representation and item.get("status") == "success"
            for item in results
            if isinstance(item, dict)
        )
        for representation in ("ply", "drc")
    }
    passed = (
        smoke.get("environment_id") == ENVIRONMENT_ID
        and smoke.get("candidate_count") == 2
        and smoke.get("success_count") == 2
        and smoke.get("failure_count") == 0
        and representation_counts == {"ply": 1, "drc": 1}
        and (smoke.get("ply_smoke_equivalence") or {}).get("status") == "passed"
    )
    if not passed:
        raise Open3DPythonBackendError("v2 smoke release gate failed")
    return {
        "status": "passed",
        "environment_id": ENVIRONMENT_ID,
        "candidate_count": 2,
        "representation_counts": representation_counts,
        "ply_smoke_equivalence": smoke["ply_smoke_equivalence"],
    }


def audit_alignment_consistency(
    pilot: dict[str, Any], alignment: dict[str, Any]
) -> dict[str, Any]:
    if alignment.get("conclusion") != "strong_support_for_open3d_backend":
        raise Open3DPythonBackendError("phase1B.2 alignment conclusion is not strong support")
    pilot_by_key = {
        item.get("candidate_key"): item
        for item in pilot.get("results", [])
        if isinstance(item, dict) and item.get("representation") == "ply"
    }
    comparisons = []
    for alignment_record in alignment.get("records", []):
        if alignment_record.get("correctness_status") != "passed":
            raise Open3DPythonBackendError("phase1B.2 alignment correctness did not pass")
        key = alignment_record.get("candidate_key")
        pilot_record = pilot_by_key.get(key)
        if not pilot_record or pilot_record.get("status") != "success":
            raise Open3DPythonBackendError(
                f"v2 pilot is missing alignment PLY candidate: {key}"
            )
        v2_p50 = float(pilot_record["p50_ms"])
        plyfile_p50 = float(
            alignment_record["plyfile_current_boundary_ms"]["p50_ms"]
        )
        if not 0 < v2_p50 < plyfile_p50:
            raise Open3DPythonBackendError(
                f"v2 PLY direction conflicts with phase1B.2 for candidate: {key}"
            )
        comparisons.append(
            {
                "candidate_key": key,
                "v2_open3d_memory_p50_ms": v2_p50,
                "phase1b2_plyfile_p50_ms": plyfile_p50,
                "v2_over_plyfile_ratio": v2_p50 / plyfile_p50,
            }
        )
    if len(comparisons) != 4:
        raise Open3DPythonBackendError(
            f"expected four phase1B.2 alignment comparisons, got {len(comparisons)}"
        )
    return {
        "status": "passed",
        "comparison_count": len(comparisons),
        "rule": "v2 Open3D memory p50 must be below phase1B.2 plyfile p50",
        "comparisons": comparisons,
    }


def allocation_release_status(
    calibration: dict[str, Any],
    *,
    smoke_audit: dict[str, Any],
    alignment_audit: dict[str, Any],
) -> str:
    models = calibration.get("representation_models") or {}
    ready = (
        smoke_audit.get("status") == "passed"
        and alignment_audit.get("status") == "passed"
        and all(
            (models.get(representation) or {}).get("recommended_for_allocation_pilot") is True
            for representation in ("ply", "drc")
        )
    )
    return "ready_for_provisional_integration" if ready else "review_pending"


def _validate_binary_ply_header(payload: bytes) -> None:
    if not isinstance(payload, bytes):
        raise Open3DPythonBackendError("Open3D PLY processor requires bytes payload")
    marker = b"end_header"
    marker_index = payload.find(marker)
    if marker_index < 0:
        raise Open3DPythonBackendError("PLY end_header is missing")
    try:
        header = payload[: marker_index + len(marker)].decode("ascii")
    except UnicodeDecodeError as exc:
        raise Open3DPythonBackendError("PLY header must be ASCII") from exc
    lines = [line.strip() for line in header.replace("\r", "").split("\n")]
    if not lines or lines[0] != "ply":
        raise Open3DPythonBackendError("invalid PLY magic")
    if "format binary_little_endian 1.0" not in lines:
        raise Open3DPythonBackendError("only binary little-endian PLY is supported")
    properties: set[str] = set()
    current_element: str | None = None
    for line in lines:
        parts = line.split()
        if len(parts) >= 2 and parts[0] == "element":
            current_element = parts[1]
        elif len(parts) >= 3 and parts[0] == "property" and current_element == "vertex":
            properties.add(parts[-1])
    required = {"x", "y", "z", "red", "green", "blue"}
    missing = sorted(required - properties)
    if missing:
        raise Open3DPythonBackendError(
            f"PLY is missing required vertex properties: {', '.join(missing)}"
        )


def _validate_environment(snapshot: dict[str, str]) -> None:
    expected = {
        "python_version": "3.10.",
        "open3d_version": "0.19.0",
        "dracopy_version": "2.0.0",
    }
    for field, value in expected.items():
        actual = snapshot.get(field, "")
        if field == "python_version":
            valid = actual.startswith(value)
        else:
            valid = actual == value
        if not valid:
            raise Open3DPythonBackendError(
                f"v2 environment mismatch for {field}: expected={value}, actual={actual}"
            )


def _resolve_asset_path(data_prep_root: str | Path, asset_ref: Any) -> Path:
    if not isinstance(asset_ref, str) or not asset_ref:
        raise Open3DPythonBackendError("candidate asset_ref is missing")
    relative = Path(asset_ref)
    if relative.is_absolute():
        raise Open3DPythonBackendError("candidate asset_ref must be relative")
    root = Path(data_prep_root).resolve()
    resolved = (root / relative).resolve()
    if root != resolved and root not in resolved.parents:
        raise Open3DPythonBackendError("candidate asset_ref resolves outside data-prep root")
    return resolved


def _package_version(package_name: str) -> str:
    try:
        return version(package_name)
    except PackageNotFoundError:
        return "unavailable"
