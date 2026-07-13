from __future__ import annotations

import json
import platform
import time
from datetime import datetime, timezone
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any, Callable

import numpy as np

from pcv_dms_benchmark.measurement_stats import summarize_samples
from pcv_dms_benchmark.python_benchmark import PythonBenchmarkError, parse_binary_ply


ALIGNMENT_SCOPE = "longdress_frame1051_ply_backend_alignment"
CanonicalPointCloud = tuple[np.ndarray, np.ndarray]
PathReader = Callable[[str], Any]


class PlyBackendAlignmentError(PythonBenchmarkError):
    """Raised when alignment inputs or canonical outputs are inconsistent."""


def select_alignment_candidates(
    inventory: dict[str, Any], sample_plan: dict[str, Any]
) -> list[dict[str, Any]]:
    inventory_candidates = inventory.get("candidates")
    planned_candidates = sample_plan.get("selected_candidates")
    if not isinstance(inventory_candidates, list):
        raise PlyBackendAlignmentError("inventory.candidates must be a list")
    if not isinstance(planned_candidates, list):
        raise PlyBackendAlignmentError("sample_plan.selected_candidates must be a list")

    by_key: dict[str, dict[str, Any]] = {}
    for candidate in inventory_candidates:
        if not isinstance(candidate, dict) or not candidate.get("candidate_key"):
            raise PlyBackendAlignmentError("inventory candidate is missing candidate_key")
        key = str(candidate["candidate_key"])
        if key in by_key:
            raise PlyBackendAlignmentError(f"duplicate inventory candidate_key: {key}")
        by_key[key] = candidate

    planned_keys: set[str] = set()
    for planned in planned_candidates:
        if not isinstance(planned, dict) or not planned.get("candidate_key"):
            raise PlyBackendAlignmentError("planned candidate is missing candidate_key")
        key = str(planned["candidate_key"])
        if key in planned_keys:
            raise PlyBackendAlignmentError(f"duplicate planned candidate_key: {key}")
        if key not in by_key:
            raise PlyBackendAlignmentError(f"planned candidate_key not found: {key}")
        planned_keys.add(key)

    ply_candidates = [
        by_key[key]
        for key in planned_keys
        if by_key[key].get("representation") == "ply"
        and _is_target_pdl(by_key[key].get("pdl_ratio"))
    ]
    by_tile: dict[str, dict[float, dict[str, Any]]] = {}
    for candidate in ply_candidates:
        tile_id = str(candidate.get("tile_id") or "")
        if not tile_id:
            raise PlyBackendAlignmentError("PLY candidate is missing tile_id")
        pdl = float(candidate["pdl_ratio"])
        tile_candidates = by_tile.setdefault(tile_id, {})
        if pdl in tile_candidates:
            raise PlyBackendAlignmentError(
                f"duplicate planned PLY candidate for tile={tile_id}, pdl={pdl}"
            )
        tile_candidates[pdl] = candidate

    eligible_tiles = []
    for tile_id, candidates in by_tile.items():
        if set(candidates) != {0.2, 1.0}:
            continue
        point_count = candidates[1.0].get("point_count")
        if not isinstance(point_count, int) or point_count <= 0:
            raise PlyBackendAlignmentError(
                f"invalid full-PDL point_count for tile={tile_id}: {point_count}"
            )
        eligible_tiles.append((point_count, tile_id))

    eligible_tiles.sort(key=lambda item: (item[0], item[1]))
    if len(eligible_tiles) < 2:
        raise PlyBackendAlignmentError("at least two eligible planned tiles are required")

    selected_tile_ids = [eligible_tiles[0][1], eligible_tiles[-1][1]]
    selected = [
        by_tile[tile_id][pdl]
        for tile_id in selected_tile_ids
        for pdl in (0.2, 1.0)
    ]
    keys = [str(candidate["candidate_key"]) for candidate in selected]
    if len(set(keys)) != 4:
        raise PlyBackendAlignmentError("alignment selection must contain four unique candidates")
    return selected


def parse_open3d_ply_path(
    path: str | Path, *, reader: PathReader | None = None
) -> CanonicalPointCloud:
    if reader is None:
        try:
            import open3d as o3d
        except ImportError as exc:
            raise PlyBackendAlignmentError("Open3D is not installed") from exc
        reader = o3d.io.read_point_cloud

    point_cloud = reader(str(path))
    points_value = getattr(point_cloud, "points", None)
    colors_value = getattr(point_cloud, "colors", None)
    if points_value is None or colors_value is None:
        raise PlyBackendAlignmentError("Open3D output has no points or colors")

    positions = np.array(points_value, dtype=np.float32, order="C", copy=True)
    colors_float = np.asarray(colors_value, dtype=np.float64)
    if not np.all(np.isfinite(colors_float)):
        raise PlyBackendAlignmentError("Open3D colors contain non-finite values")
    if colors_float.size and (colors_float.min() < 0.0 or colors_float.max() > 1.0):
        raise PlyBackendAlignmentError("Open3D colors must be normalized to [0, 1]")
    colors = np.array(
        np.rint(np.clip(colors_float, 0.0, 1.0) * 255.0),
        dtype=np.uint8,
        order="C",
        copy=True,
    )
    validate_canonical_arrays(positions, colors)
    return positions, colors


def measure_processor(
    processor: Callable[[], CanonicalPointCloud],
    *,
    warmup_count: int,
    sample_count: int,
    expected_point_count: int,
    clock_ns: Callable[[], int] = time.perf_counter_ns,
) -> tuple[dict[str, Any], CanonicalPointCloud]:
    if warmup_count < 0:
        raise PlyBackendAlignmentError("warmup_count must be non-negative")
    if sample_count <= 0:
        raise PlyBackendAlignmentError("sample_count must be positive")

    for _ in range(warmup_count):
        output = processor()
        validate_canonical_arrays(*output, expected_point_count=expected_point_count)

    samples_ms = []
    last_output: CanonicalPointCloud | None = None
    for _ in range(sample_count):
        start = clock_ns()
        output = processor()
        end = clock_ns()
        validate_canonical_arrays(*output, expected_point_count=expected_point_count)
        samples_ms.append((end - start) / 1_000_000.0)
        last_output = output

    assert last_output is not None
    summary: dict[str, Any] = {"raw_samples_ms": samples_ms}
    summary.update(summarize_samples(samples_ms))
    return summary, last_output


def validate_canonical_arrays(
    positions: Any, colors: Any, *, expected_point_count: int | None = None
) -> None:
    if not isinstance(positions, np.ndarray) or positions.dtype != np.float32:
        raise PlyBackendAlignmentError("positions must be a float32 numpy array")
    if not isinstance(colors, np.ndarray) or colors.dtype != np.uint8:
        raise PlyBackendAlignmentError("colors must be a uint8 numpy array")
    if positions.ndim != 2 or positions.shape[1:] != (3,):
        raise PlyBackendAlignmentError("positions must have shape [N, 3]")
    if colors.shape != positions.shape:
        raise PlyBackendAlignmentError("colors must have shape [N, 3]")
    if positions.shape[0] <= 0:
        raise PlyBackendAlignmentError("point cloud must contain at least one point")
    if not positions.flags.owndata or not colors.flags.owndata:
        raise PlyBackendAlignmentError("positions and colors must own their memory")
    if expected_point_count is not None and positions.shape[0] != expected_point_count:
        raise PlyBackendAlignmentError(
            "decoded point count mismatch: "
            f"expected={expected_point_count}, actual={positions.shape[0]}"
        )


def validate_backend_equivalence(
    plyfile_output: CanonicalPointCloud,
    open3d_output: CanonicalPointCloud,
    *,
    position_atol: float = 1e-5,
    color_atol: int = 1,
) -> None:
    ply_positions, ply_colors = plyfile_output
    open3d_positions, open3d_colors = open3d_output
    validate_canonical_arrays(ply_positions, ply_colors)
    validate_canonical_arrays(
        open3d_positions, open3d_colors, expected_point_count=ply_positions.shape[0]
    )
    if not np.allclose(ply_positions, open3d_positions, rtol=1e-6, atol=position_atol):
        max_error = float(np.max(np.abs(ply_positions - open3d_positions)))
        raise PlyBackendAlignmentError(
            f"backend positions differ beyond tolerance: max_abs_error={max_error}"
        )
    color_error = np.abs(ply_colors.astype(np.int16) - open3d_colors.astype(np.int16))
    if int(color_error.max(initial=0)) > color_atol:
        raise PlyBackendAlignmentError(
            f"backend colors differ beyond tolerance: max_level_error={int(color_error.max())}"
        )


def run_ply_backend_alignment(
    candidates: list[dict[str, Any]],
    pilot: dict[str, Any],
    *,
    data_prep_root: str | Path,
    warmup_count: int = 2,
    sample_count: int = 5,
    open3d_reader: PathReader | None = None,
    run_id: str | None = None,
) -> dict[str, Any]:
    if len(candidates) != 4:
        raise PlyBackendAlignmentError("alignment requires exactly four PLY candidates")
    drc_reference = _index_existing_drc_qp10(pilot)
    root = Path(data_prep_root).resolve()
    records = []

    for candidate in candidates:
        record = _base_record(candidate)
        try:
            asset_path = _resolve_asset_path(root, candidate.get("asset_ref"))
            expected_size = candidate.get("file_size_bytes")
            actual_size = asset_path.stat().st_size
            if not isinstance(expected_size, int) or actual_size != expected_size:
                raise PlyBackendAlignmentError(
                    f"file size mismatch: metadata={expected_size}, stat={actual_size}"
                )
            payload = asset_path.read_bytes()
            expected_points = int(candidate["point_count"])

            plyfile_timing, plyfile_output = measure_processor(
                lambda: parse_binary_ply(payload),
                warmup_count=warmup_count,
                sample_count=sample_count,
                expected_point_count=expected_points,
            )
            open3d_timing, open3d_output = measure_processor(
                lambda: parse_open3d_ply_path(asset_path, reader=open3d_reader),
                warmup_count=warmup_count,
                sample_count=sample_count,
                expected_point_count=expected_points,
            )
            validate_backend_equivalence(plyfile_output, open3d_output)

            reference_key = (str(candidate["tile_id"]), float(candidate["pdl_ratio"]))
            if reference_key not in drc_reference:
                raise PlyBackendAlignmentError(
                    "existing phase1A DRC qp=10 reference not found for "
                    f"tile={reference_key[0]}, pdl={reference_key[1]}"
                )
            reference = drc_reference[reference_key]
            ratio = open3d_timing["p50_ms"] / plyfile_timing["p50_ms"]
            record.update(
                {
                    "plyfile_current_boundary_ms": plyfile_timing,
                    "open3d_legacy_total_ms": open3d_timing,
                    "open3d_over_plyfile_p50_ratio": ratio,
                    "existing_drc_qp10": reference,
                    "correctness_status": "passed",
                    "status": "success",
                    "error": None,
                }
            )
        except Exception as exc:
            record.update(
                {
                    "plyfile_current_boundary_ms": None,
                    "open3d_legacy_total_ms": None,
                    "open3d_over_plyfile_p50_ratio": None,
                    "existing_drc_qp10": None,
                    "correctness_status": "failed",
                    "status": "failed",
                    "error": f"{type(exc).__name__}: {exc}",
                }
            )
        records.append(record)

    conclusion = classify_alignment(records)
    success_count = sum(record["status"] == "success" for record in records)
    return {
        "alignment_schema_version": "1.0",
        "run_id": run_id or _default_run_id(),
        "measurement_scope": ALIGNMENT_SCOPE,
        "environment_id": "python_open3d_alignment_windows_x64",
        "python_version": platform.python_version(),
        "numpy_version": np.__version__,
        "plyfile_version": _package_version("plyfile"),
        "open3d_version": _package_version("open3d"),
        "timer_api": "time.perf_counter_ns",
        "warmup_count": warmup_count,
        "sample_count": sample_count,
        "candidate_count": len(records),
        "success_count": success_count,
        "failure_count": len(records) - success_count,
        "plyfile_boundary": (
            "payload resident in memory -> plyfile+BytesIO -> owned canonical arrays"
        ),
        "open3d_boundary": (
            "Open3D path API including disk read -> owned canonical arrays"
        ),
        "open3d_boundary_is_formal_d_ms": False,
        "eligible_for_allocation": False,
        "conclusion": conclusion,
        "records": records,
    }


def classify_alignment(records: list[dict[str, Any]]) -> str:
    if len(records) != 4 or any(record.get("correctness_status") != "passed" for record in records):
        return "inconclusive"
    ratios = [float(record["open3d_over_plyfile_p50_ratio"]) for record in records]
    if sum(ratio <= 0.5 for ratio in ratios) >= 3:
        return "strong_support_for_open3d_backend"
    if sum(ratio < 1.0 for ratio in ratios) >= 3:
        return "partial_support_for_open3d_backend"
    return "no_support_or_inconclusive"


def write_alignment_result(path: str | Path, result: dict[str, Any]) -> None:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _index_existing_drc_qp10(pilot: dict[str, Any]) -> dict[tuple[str, float], dict[str, Any]]:
    results = pilot.get("results")
    if not isinstance(results, list):
        raise PlyBackendAlignmentError("pilot.results must be a list")
    index: dict[tuple[str, float], dict[str, Any]] = {}
    for result in results:
        if (
            isinstance(result, dict)
            and result.get("representation") == "drc"
            and result.get("qp") == 10
            and result.get("status") == "success"
        ):
            key = (str(result.get("tile_id")), float(result.get("pdl_ratio")))
            if key in index:
                raise PlyBackendAlignmentError(
                    f"duplicate phase1A DRC qp=10 reference: tile={key[0]}, pdl={key[1]}"
                )
            index[key] = {
                "candidate_key": result.get("candidate_key"),
                "p50_ms": result.get("p50_ms"),
                "source": "existing_phase1a_measured",
            }
    return index


def _base_record(candidate: dict[str, Any]) -> dict[str, Any]:
    return {
        "candidate_key": candidate.get("candidate_key"),
        "candidate_id": candidate.get("candidate_id"),
        "tile_id": candidate.get("tile_id"),
        "pdl_ratio": candidate.get("pdl_ratio"),
        "point_count": candidate.get("point_count"),
        "file_size_bytes": candidate.get("file_size_bytes"),
    }


def _resolve_asset_path(root: Path, asset_ref: Any) -> Path:
    if not isinstance(asset_ref, str) or not asset_ref:
        raise PlyBackendAlignmentError("candidate asset_ref is missing")
    relative = Path(asset_ref)
    if relative.is_absolute():
        raise PlyBackendAlignmentError("candidate asset_ref must be relative")
    resolved = (root / relative).resolve()
    if root != resolved and root not in resolved.parents:
        raise PlyBackendAlignmentError("candidate asset_ref resolves outside data-prep root")
    return resolved


def _is_target_pdl(value: Any) -> bool:
    try:
        return float(value) in {0.2, 1.0}
    except (TypeError, ValueError):
        return False


def _package_version(package_name: str) -> str:
    try:
        return version(package_name)
    except PackageNotFoundError:
        return "unavailable"


def _default_run_id() -> str:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"ply_backend_alignment_{timestamp}"
