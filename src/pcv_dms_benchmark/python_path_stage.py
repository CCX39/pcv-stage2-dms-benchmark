from __future__ import annotations

import json
import math
import platform
import time
from datetime import datetime, timezone
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any, Callable

import numpy as np

from pcv_dms_benchmark.measurement_records import (
    PARSE_STAGE_END_TO_END,
    PATH_DELIVERED,
    POSITIONS_COLORS_READY,
)
from pcv_dms_benchmark.measurement_stats import summarize_samples
from pcv_dms_benchmark.python_benchmark import PythonBenchmarkError


ENVIRONMENT_ID = "python310_open3d019_dracopy200_path_stage_windows_x64"
MEASUREMENT_SCOPE = "longdress_frame1051_python_path_stage_pilot"
CALIBRATION_ID = "python310_path_stage_frame1051_p50_calibration_v1"
HANDOFF_ID = "python_path_stage_frame1051_candidate_dms_v1"
ALLOCATION_USE_SCOPE = "provisional_python_path_profile"
FILESYSTEM_CACHE_POLICY = "os_managed_repeated_path_load"
MEASUREMENT_BOUNDARY = (
    "path delivered to loader -> file open/read -> Open3D PLY load or DracoPy DRC decode "
    "-> owned positions float32[N,3] and colors uint8[N,3]"
)

PathProcessor = Callable[[Path], tuple[np.ndarray, np.ndarray]]
Clock = Callable[[], int]
StatSize = Callable[[Path], int]


class PythonPathStageError(PythonBenchmarkError):
    """Raised when the Python path-stage profile violates its contract."""


def load_ply_path(
    path: Path, *, loader: Callable[[str], Any] | None = None
) -> tuple[np.ndarray, np.ndarray]:
    if loader is None:
        try:
            import open3d as o3d
        except ImportError as exc:
            raise PythonPathStageError("Open3D is unavailable") from exc
        loader = o3d.t.io.read_point_cloud

    point_cloud = loader(str(path))
    point_map = getattr(point_cloud, "point", None)
    if point_map is None or "positions" not in point_map or "colors" not in point_map:
        raise PythonPathStageError("Open3D output must contain positions and colors")
    positions_source = _tensor_numpy(point_map["positions"])
    colors_source = _tensor_numpy(point_map["colors"])
    positions = np.array(
        np.asarray(positions_source).reshape(-1, 3),
        dtype=np.float32,
        order="C",
        copy=True,
    )
    colors = _canonical_colors(colors_source)
    return positions, colors


def decode_drc_path(
    path: Path,
    *,
    read_bytes: Callable[[Path], bytes] | None = None,
    decoder: Callable[[bytes], Any] | None = None,
) -> tuple[np.ndarray, np.ndarray]:
    payload = (read_bytes or Path.read_bytes)(path)
    if decoder is None:
        try:
            import DracoPy
        except ImportError as exc:
            raise PythonPathStageError("DracoPy is unavailable") from exc
        decoder = DracoPy.decode
    decoded = decoder(payload)
    points = getattr(decoded, "points", None)
    colors = getattr(decoded, "colors", None)
    if points is None or colors is None:
        raise PythonPathStageError("Draco output must contain points and colors")
    positions = np.array(
        np.asarray(points).reshape(-1, 3), dtype=np.float32, order="C", copy=True
    )
    canonical_colors = np.array(
        np.asarray(colors).reshape(-1, 3), dtype=np.uint8, order="C", copy=True
    )
    return positions, canonical_colors


def measure_path_candidate(
    candidate: dict[str, Any],
    *,
    data_prep_root: str | Path,
    processor: PathProcessor,
    warmup_count: int,
    sample_count: int,
    clock_ns: Clock = time.perf_counter_ns,
    stat_size: StatSize | None = None,
    backend_name: str,
    backend_version: str,
) -> dict[str, Any]:
    record = _base_record(
        candidate,
        warmup_count=warmup_count,
        sample_count=sample_count,
        backend_name=backend_name,
        backend_version=backend_version,
    )
    try:
        asset_path = _resolve_asset_path(data_prep_root, candidate.get("asset_ref"))
        actual_size = (stat_size or (lambda value: value.stat().st_size))(asset_path)
        expected_size = candidate.get("file_size_bytes")
        if expected_size is None or actual_size != int(expected_size):
            raise PythonPathStageError(
                f"file size mismatch: metadata={expected_size}, stat={actual_size}"
            )

        expected_points = candidate.get("point_count")
        for _ in range(warmup_count):
            _validate_output(processor(asset_path), expected_points)

        raw_samples_ms: list[float] = []
        decoded_point_count: int | None = None
        for _ in range(sample_count):
            start = clock_ns()
            output = processor(asset_path)
            end = clock_ns()
            positions, colors = _validate_output(output, expected_points)
            decoded_point_count = int(positions.shape[0])
            raw_samples_ms.append((end - start) / 1_000_000.0)
            del positions, colors, output
        record.update(summarize_samples(raw_samples_ms))
        record.update(
            {
                "decoded_point_count": decoded_point_count,
                "raw_samples_ms": raw_samples_ms,
                "status": "success",
                "error": None,
            }
        )
    except Exception as exc:
        record.update(
            {
                "decoded_point_count": None,
                "raw_samples_ms": [],
                "p50_ms": None,
                "mean_ms": None,
                "status": "failed",
                "error": f"{type(exc).__name__}: {exc}",
            }
        )
    return record


def run_python_path_stage_pilot(
    candidates: list[dict[str, Any]],
    *,
    data_prep_root: str | Path,
    warmup_count: int = 2,
    sample_count: int = 5,
    run_id: str | None = None,
    processor_overrides: dict[str, PathProcessor] | None = None,
    environment_snapshot_override: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if warmup_count < 0 or sample_count <= 0:
        raise PythonPathStageError("warmup must be non-negative and samples must be positive")
    snapshot = environment_snapshot_override or environment_snapshot()
    if environment_snapshot_override is None:
        _validate_environment(snapshot)
    processors = {"ply": load_ply_path, "drc": decode_drc_path}
    processors.update(processor_overrides or {})
    backend_info = {
        "ply": ("open3d.t.io.read_point_cloud+numpy", f"Open3D={snapshot['open3d_version']};numpy={snapshot['numpy_version']}"),
        "drc": ("Path.read_bytes+DracoPy+numpy", f"DracoPy={snapshot['dracopy_version']};numpy={snapshot['numpy_version']}"),
    }
    results = []
    for candidate in candidates:
        representation = str(candidate.get("representation"))
        if representation not in processors:
            raise PythonPathStageError(f"unsupported representation: {representation}")
        name, backend_version = backend_info[representation]
        results.append(
            measure_path_candidate(
                candidate,
                data_prep_root=data_prep_root,
                processor=processors[representation],
                warmup_count=warmup_count,
                sample_count=sample_count,
                backend_name=name,
                backend_version=backend_version,
            )
        )

    success_count = sum(item["status"] == "success" for item in results)
    failure_count = len(results) - success_count
    applicable_scope = _applicable_scope(candidates)
    return {
        "run_id": run_id or _default_run_id(),
        "environment_id": ENVIRONMENT_ID,
        "environment_snapshot": snapshot,
        "filesystem_cache_policy": FILESYSTEM_CACHE_POLICY,
        "timer_api": "time.perf_counter_ns",
        "measurement_boundary": MEASUREMENT_BOUNDARY,
        "measurement_scope": MEASUREMENT_SCOPE,
        "measurement_kind": PARSE_STAGE_END_TO_END,
        "timing_start": PATH_DELIVERED,
        "timing_end": POSITIONS_COLORS_READY,
        "profile_implementation_confirmed": True,
        "network_time_included": False,
        "rendering_time_included": False,
        "provenance_complete": True,
        "validation_passed": False,
        "applicable_scope": applicable_scope,
        "candidate_count": len(results),
        "success_count": success_count,
        "failure_count": failure_count,
        "status": "success" if failure_count == 0 else "failed" if success_count == 0 else "partial_failure",
        "provenance": "measured",
        "eligible_for_final_model": False,
        "eligible_for_allocation": False,
        "warmup_count": warmup_count,
        "sample_count": sample_count,
        "results": results,
    }


def audit_path_stage_smoke(smoke: dict[str, Any]) -> dict[str, Any]:
    results = smoke.get("results")
    counts = {
        representation: sum(
            isinstance(item, dict)
            and item.get("representation") == representation
            and item.get("status") == "success"
            for item in (results or [])
        )
        for representation in ("ply", "drc")
    }
    valid = (
        smoke.get("environment_id") == ENVIRONMENT_ID
        and smoke.get("measurement_kind") == PARSE_STAGE_END_TO_END
        and smoke.get("timing_start") == PATH_DELIVERED
        and smoke.get("timing_end") == POSITIONS_COLORS_READY
        and smoke.get("candidate_count") == 2
        and smoke.get("success_count") == 2
        and smoke.get("failure_count") == 0
        and counts == {"ply": 1, "drc": 1}
        and all(len(item.get("raw_samples_ms", [])) == 5 for item in results or [])
    )
    if not valid:
        raise PythonPathStageError("Python path-stage smoke gate failed")
    return {"status": "passed", "representation_counts": counts, "candidate_count": 2}


def environment_snapshot() -> dict[str, str]:
    return {
        "python_version": platform.python_version(),
        "python_implementation": platform.python_implementation(),
        "open3d_version": _package_version("open3d"),
        "dracopy_version": _package_version("DracoPy"),
        "numpy_version": np.__version__,
        "operating_system": platform.platform(),
        "timer_api": "time.perf_counter_ns",
    }


def write_pilot(path: str | Path, payload: dict[str, Any]) -> None:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _canonical_colors(value: Any) -> np.ndarray:
    colors = np.asarray(value)
    if colors.dtype == np.uint8:
        return np.array(
            colors.reshape(-1, 3), dtype=np.uint8, order="C", copy=True
        )
    if np.issubdtype(colors.dtype, np.floating):
        converted = np.rint(np.clip(colors, 0.0, 1.0) * 255.0).astype(np.uint8)
        return np.array(
            converted.reshape(-1, 3), dtype=np.uint8, order="C", copy=True
        )
    raise PythonPathStageError(f"unsupported Open3D color dtype: {colors.dtype}")


def _tensor_numpy(value: Any) -> np.ndarray:
    return np.asarray(value.numpy() if hasattr(value, "numpy") else value)


def _validate_output(
    output: tuple[np.ndarray, np.ndarray], expected_points: Any
) -> tuple[np.ndarray, np.ndarray]:
    if not isinstance(output, tuple) or len(output) != 2:
        raise PythonPathStageError("processor must return (positions, colors)")
    positions, colors = output
    if not isinstance(positions, np.ndarray) or positions.dtype != np.float32:
        raise PythonPathStageError("positions must be float32 numpy array")
    if not isinstance(colors, np.ndarray) or colors.dtype != np.uint8:
        raise PythonPathStageError("colors must be uint8 numpy array")
    if positions.ndim != 2 or positions.shape[1:] != (3,) or colors.shape != positions.shape:
        raise PythonPathStageError("positions/colors must have shape [N,3]")
    if positions.shape[0] <= 0 or not positions.flags.owndata or not colors.flags.owndata:
        raise PythonPathStageError("canonical arrays must be non-empty and own memory")
    if expected_points is not None and positions.shape[0] != int(expected_points):
        raise PythonPathStageError(
            f"decoded point count mismatch: metadata={expected_points}, decoded={positions.shape[0]}"
        )
    return positions, colors


def _base_record(
    candidate: dict[str, Any],
    *,
    warmup_count: int,
    sample_count: int,
    backend_name: str,
    backend_version: str,
) -> dict[str, Any]:
    codec_params = candidate.get("codec_params") or {}
    return {
        "candidate_key": candidate.get("candidate_key"),
        "candidate_id": candidate.get("candidate_id"),
        "representation": candidate.get("representation"),
        "dataset_id": candidate.get("dataset_id"),
        "frame_id": candidate.get("frame_id"),
        "tile_id": candidate.get("tile_id"),
        "pdl_ratio": candidate.get("pdl_ratio"),
        "qp": codec_params.get("qp"),
        "cl": codec_params.get("cl"),
        "point_count": candidate.get("point_count"),
        "file_size_bytes": candidate.get("file_size_bytes"),
        "python_version": platform.python_version(),
        "backend_name": backend_name,
        "backend_version": backend_version,
        "filesystem_cache_policy": FILESYSTEM_CACHE_POLICY,
        "warmup_count": warmup_count,
        "sample_count": sample_count,
        "provenance": "measured",
        "measurement_scope": MEASUREMENT_SCOPE,
        "measurement_kind": PARSE_STAGE_END_TO_END,
        "timing_start": PATH_DELIVERED,
        "timing_end": POSITIONS_COLORS_READY,
        "eligible_for_final_model": False,
        "eligible_for_allocation": False,
    }


def _resolve_asset_path(root_value: str | Path, asset_ref: Any) -> Path:
    if not isinstance(asset_ref, str) or not asset_ref:
        raise PythonPathStageError("asset_ref is missing")
    relative = Path(asset_ref)
    if relative.is_absolute():
        raise PythonPathStageError("asset_ref must be relative")
    root = Path(root_value).resolve()
    path = (root / relative).resolve()
    if root != path and root not in path.parents:
        raise PythonPathStageError("asset_ref resolves outside data-prep root")
    return path


def _applicable_scope(candidates: list[dict[str, Any]]) -> dict[str, Any]:
    scope: dict[str, Any] = {"environment_id": ENVIRONMENT_ID}
    for field in ("dataset_id", "frame_id", "grid_profile_id"):
        values = {item.get(field) for item in candidates}
        scope[field] = next(iter(values)) if len(values) == 1 else None
    return scope


def _validate_environment(snapshot: dict[str, Any]) -> None:
    expected = {
        "python_version": "3.10.20",
        "open3d_version": "0.19.0",
        "dracopy_version": "2.0.0",
        "numpy_version": "2.2.6",
    }
    mismatches = {
        field: (expected_value, snapshot.get(field))
        for field, expected_value in expected.items()
        if snapshot.get(field) != expected_value
    }
    if mismatches:
        raise PythonPathStageError(f"environment mismatch: {mismatches}")


def _package_version(package: str) -> str:
    try:
        return version(package)
    except PackageNotFoundError:
        return "unavailable"


def _default_run_id() -> str:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"python_path_stage_{timestamp}"


__all__ = [
    "ALLOCATION_USE_SCOPE",
    "CALIBRATION_ID",
    "ENVIRONMENT_ID",
    "FILESYSTEM_CACHE_POLICY",
    "HANDOFF_ID",
    "MEASUREMENT_SCOPE",
    "PythonPathStageError",
    "audit_path_stage_smoke",
    "decode_drc_path",
    "environment_snapshot",
    "load_ply_path",
    "measure_path_candidate",
    "run_python_path_stage_pilot",
    "write_pilot",
]
