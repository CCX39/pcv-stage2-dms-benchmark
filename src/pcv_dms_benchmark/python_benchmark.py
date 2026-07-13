from __future__ import annotations

import io
import json
import platform
import time
from datetime import datetime, timezone
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any, Callable

import numpy as np
from plyfile import PlyData

from pcv_dms_benchmark.measurement_stats import summarize_samples


ENVIRONMENT_ID = "python_windows_x64"
MEASUREMENT_BOUNDARY = (
    "payload bytes resident in memory -> parse/decode -> owned positions float32[N,3] "
    "and colors uint8[N,3]"
)
Processor = Callable[[bytes], tuple[np.ndarray, np.ndarray]]


class PythonBenchmarkError(ValueError):
    """Raised when a pilot input or decoded point cloud violates the contract."""


class BackendUnavailableError(RuntimeError):
    """Raised when an in-process parser or decoder is unavailable."""


def parse_binary_ply(payload: bytes) -> tuple[np.ndarray, np.ndarray]:
    ply = PlyData.read(io.BytesIO(payload))
    if ply.text or ply.byte_order != "<":
        raise PythonBenchmarkError("only binary little-endian PLY is supported")

    try:
        vertices = ply["vertex"].data
    except KeyError as exc:
        raise PythonBenchmarkError("PLY has no vertex element") from exc
    _require_fields(vertices.dtype.names, ("x", "y", "z", "red", "green", "blue"), "PLY")

    positions = np.array(
        np.column_stack((vertices["x"], vertices["y"], vertices["z"])),
        dtype=np.float32,
        order="C",
        copy=True,
    )
    colors = np.array(
        np.column_stack((vertices["red"], vertices["green"], vertices["blue"])),
        dtype=np.uint8,
        order="C",
        copy=True,
    )
    return positions, colors


def decode_drc(
    payload: bytes,
    *,
    decoder: Callable[[bytes], Any] | None = None,
) -> tuple[np.ndarray, np.ndarray]:
    if decoder is None:
        try:
            import DracoPy
        except ImportError as exc:
            raise BackendUnavailableError("DracoPy is not installed") from exc
        decoder = DracoPy.decode

    decoded = decoder(payload)
    points = getattr(decoded, "points", None)
    colors_value = getattr(decoded, "colors", None)
    if points is None:
        raise PythonBenchmarkError("Draco output has no points")
    if colors_value is None:
        raise PythonBenchmarkError("Draco output has no colors")

    positions = np.array(points, dtype=np.float32, order="C", copy=True)
    colors = np.array(colors_value, dtype=np.uint8, order="C", copy=True)
    return positions, colors


def load_json_object(path: str | Path) -> dict[str, Any]:
    input_path = Path(path)
    try:
        payload = json.loads(input_path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise PythonBenchmarkError(f"JSON file not found: {input_path}") from exc
    except json.JSONDecodeError as exc:
        raise PythonBenchmarkError(
            f"invalid JSON in {input_path}: line {exc.lineno}, column {exc.colno}: {exc.msg}"
        ) from exc
    if not isinstance(payload, dict):
        raise PythonBenchmarkError(f"expected JSON object in {input_path}")
    return payload


def select_candidates(
    inventory: dict[str, Any],
    sample_plan: dict[str, Any],
    *,
    smoke: bool = False,
) -> list[dict[str, Any]]:
    inventory_candidates = inventory.get("candidates")
    planned_candidates = sample_plan.get("selected_candidates")
    if not isinstance(inventory_candidates, list):
        raise PythonBenchmarkError("inventory.candidates must be a list")
    if not isinstance(planned_candidates, list):
        raise PythonBenchmarkError("sample_plan.selected_candidates must be a list")

    by_key: dict[str, dict[str, Any]] = {}
    for candidate in inventory_candidates:
        if not isinstance(candidate, dict) or not candidate.get("candidate_key"):
            raise PythonBenchmarkError("inventory candidate is missing candidate_key")
        key = str(candidate["candidate_key"])
        if key in by_key:
            raise PythonBenchmarkError(f"duplicate inventory candidate_key: {key}")
        by_key[key] = candidate

    selected: list[dict[str, Any]] = []
    seen: set[str] = set()
    for planned in planned_candidates:
        if not isinstance(planned, dict) or not planned.get("candidate_key"):
            raise PythonBenchmarkError("planned candidate is missing candidate_key")
        key = str(planned["candidate_key"])
        if key in seen:
            raise PythonBenchmarkError(f"duplicate planned candidate_key: {key}")
        seen.add(key)
        if key not in by_key:
            raise PythonBenchmarkError(f"planned candidate_key not found in inventory: {key}")
        selected.append(by_key[key])

    if not smoke:
        return selected

    smoke_candidates = []
    for representation in ("ply", "drc"):
        match = next(
            (item for item in selected if item.get("representation") == representation),
            None,
        )
        if match is None:
            raise PythonBenchmarkError(f"smoke plan has no {representation} candidate")
        smoke_candidates.append(match)
    return smoke_candidates


def run_python_pilot(
    candidates: list[dict[str, Any]],
    *,
    data_prep_root: str | Path,
    warmup_count: int = 2,
    sample_count: int = 5,
    run_id: str | None = None,
    processor_overrides: dict[str, Processor] | None = None,
) -> dict[str, Any]:
    if warmup_count < 0:
        raise PythonBenchmarkError("warmup_count must be non-negative")
    if sample_count <= 0:
        raise PythonBenchmarkError("sample_count must be positive")

    processors = processor_overrides or {}
    drc_backend_error: str | None = None
    if any(item.get("representation") == "drc" for item in candidates) and "drc" not in processors:
        try:
            import DracoPy  # noqa: F401
        except ImportError as exc:
            drc_backend_error = f"DRC backend unavailable: {exc}"

    results = []
    for candidate in candidates:
        representation = candidate.get("representation")
        if representation == "drc" and drc_backend_error:
            results.append(
                _failure_record(candidate, warmup_count, sample_count, drc_backend_error)
            )
            continue
        processor = processors.get(str(representation)) or _processor_for(str(representation))
        results.append(
            measure_candidate(
                candidate,
                data_prep_root=data_prep_root,
                warmup_count=warmup_count,
                sample_count=sample_count,
                processor=processor,
            )
        )

    success_count = sum(item["status"] == "success" for item in results)
    failure_count = len(results) - success_count
    return {
        "run_id": run_id or _default_run_id(),
        "environment_id": ENVIRONMENT_ID,
        "timer_api": "time.perf_counter_ns",
        "measurement_boundary": MEASUREMENT_BOUNDARY,
        "candidate_count": len(results),
        "success_count": success_count,
        "failure_count": failure_count,
        "status": (
            "success"
            if failure_count == 0
            else "failed"
            if success_count == 0
            else "partial_failure"
        ),
        "provenance": "measured",
        "measurement_scope": "longdress_frame1051_pilot",
        "eligible_for_final_model": False,
        "eligible_for_allocation": False,
        "results": results,
    }


def measure_candidate(
    candidate: dict[str, Any],
    *,
    data_prep_root: str | Path,
    warmup_count: int,
    sample_count: int,
    processor: Processor,
    read_bytes: Callable[[Path], bytes] | None = None,
    clock_ns: Callable[[], int] = time.perf_counter_ns,
) -> dict[str, Any]:
    record = _base_record(candidate, warmup_count, sample_count)
    try:
        asset_path = _resolve_asset_path(data_prep_root, candidate.get("asset_ref"))
        actual_size = asset_path.stat().st_size
        expected_size = candidate.get("file_size_bytes")
        if expected_size is None:
            raise PythonBenchmarkError("candidate file_size_bytes is missing")
        if actual_size != expected_size:
            raise PythonBenchmarkError(
                f"file size mismatch: metadata={expected_size}, stat={actual_size}"
            )
        payload = (read_bytes or Path.read_bytes)(asset_path)

        expected_points = candidate.get("point_count")
        for _ in range(warmup_count):
            output = processor(payload)
            _validate_output(output, expected_points)

        samples_ms = []
        decoded_point_count = None
        for _ in range(sample_count):
            start = clock_ns()
            output = processor(payload)
            end = clock_ns()
            positions, colors = _validate_output(output, expected_points)
            decoded_point_count = int(positions.shape[0])
            samples_ms.append((end - start) / 1_000_000.0)
            del positions, colors, output

        record.update(summarize_samples(samples_ms))
        record.update(
            {
                "decoded_point_count": decoded_point_count,
                "raw_samples_ms": samples_ms,
                "status": "success",
                "error": None,
            }
        )
    except Exception as exc:  # A failed candidate must not abort the rest of the pilot.
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


def write_pilot_result(path: str | Path, result: dict[str, Any]) -> None:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _processor_for(representation: str) -> Processor:
    if representation == "ply":
        return parse_binary_ply
    if representation == "drc":
        return decode_drc
    raise PythonBenchmarkError(f"unsupported representation: {representation}")


def _resolve_asset_path(data_prep_root: str | Path, asset_ref: Any) -> Path:
    if not isinstance(asset_ref, str) or not asset_ref:
        raise PythonBenchmarkError("candidate asset_ref is missing")
    relative_path = Path(asset_ref)
    if relative_path.is_absolute():
        raise PythonBenchmarkError("candidate asset_ref must be relative to data-prep root")
    root = Path(data_prep_root).resolve()
    asset_path = (root / relative_path).resolve()
    if root != asset_path and root not in asset_path.parents:
        raise PythonBenchmarkError("candidate asset_ref resolves outside data-prep root")
    return asset_path


def _validate_output(
    output: tuple[np.ndarray, np.ndarray],
    expected_point_count: Any,
) -> tuple[np.ndarray, np.ndarray]:
    if not isinstance(output, tuple) or len(output) != 2:
        raise PythonBenchmarkError("processor must return (positions, colors)")
    positions, colors = output
    _validate_point_cloud(positions, colors, expected_point_count)
    return positions, colors


def _validate_point_cloud(
    positions: Any,
    colors: Any,
    expected_point_count: Any,
) -> None:
    if not isinstance(positions, np.ndarray) or positions.dtype != np.float32:
        raise PythonBenchmarkError("positions must be a float32 numpy array")
    if not isinstance(colors, np.ndarray) or colors.dtype != np.uint8:
        raise PythonBenchmarkError("colors must be a uint8 numpy array")
    if positions.ndim != 2 or positions.shape[1:] != (3,):
        raise PythonBenchmarkError("positions must have shape [N, 3]")
    if colors.shape != positions.shape:
        raise PythonBenchmarkError("colors must have shape [N, 3]")
    if not positions.flags.owndata or not colors.flags.owndata:
        raise PythonBenchmarkError("positions and colors must own their memory")
    if expected_point_count is not None and positions.shape[0] != int(expected_point_count):
        raise PythonBenchmarkError(
            f"decoded point count mismatch: metadata={expected_point_count}, decoded={positions.shape[0]}"
        )


def _base_record(
    candidate: dict[str, Any], warmup_count: int, sample_count: int
) -> dict[str, Any]:
    representation = candidate.get("representation")
    codec_params = candidate.get("codec_params") or {}
    backend_name, backend_version = _backend_info(str(representation))
    return {
        "candidate_key": candidate.get("candidate_key"),
        "candidate_id": candidate.get("candidate_id"),
        "representation": representation,
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
        "warmup_count": warmup_count,
        "sample_count": sample_count,
        "provenance": "measured",
        "measurement_scope": "longdress_frame1051_pilot",
        "eligible_for_final_model": False,
        "eligible_for_allocation": False,
    }


def _failure_record(
    candidate: dict[str, Any], warmup_count: int, sample_count: int, error: str
) -> dict[str, Any]:
    record = _base_record(candidate, warmup_count, sample_count)
    record.update(
        {
            "decoded_point_count": None,
            "raw_samples_ms": [],
            "p50_ms": None,
            "mean_ms": None,
            "status": "failed",
            "error": error,
        }
    )
    return record


def _backend_info(representation: str) -> tuple[str, str]:
    if representation == "ply":
        return "plyfile+numpy", f"plyfile={_package_version('plyfile')};numpy={np.__version__}"
    if representation == "drc":
        return "DracoPy+numpy", f"DracoPy={_package_version('DracoPy')};numpy={np.__version__}"
    return "unsupported", "unknown"


def _package_version(package_name: str) -> str:
    try:
        return version(package_name)
    except PackageNotFoundError:
        return "unavailable"


def _require_fields(
    available: tuple[str, ...] | None,
    required: tuple[str, ...],
    source: str,
) -> None:
    names = set(available or ())
    missing = [name for name in required if name not in names]
    if missing:
        raise PythonBenchmarkError(f"{source} is missing fields: {', '.join(missing)}")


def _default_run_id() -> str:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"python_longdress_frame1051_pilot_{timestamp}"
