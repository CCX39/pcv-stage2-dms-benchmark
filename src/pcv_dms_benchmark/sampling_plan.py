from __future__ import annotations

import json
from pathlib import Path
from typing import Any


SAMPLING_PLAN_SCHEMA_VERSION = "0.1.0"
PLANNING_PROVENANCE = "metadata_planning"


class SamplingPlanError(ValueError):
    """Raised when an inventory cannot be sampled safely."""


def load_inventory(path: str | Path) -> dict[str, Any]:
    inventory_path = Path(path)
    try:
        payload = json.loads(inventory_path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise SamplingPlanError(f"Inventory file not found: {inventory_path}") from exc
    except json.JSONDecodeError as exc:
        raise SamplingPlanError(
            f"Invalid inventory JSON in {inventory_path}: line {exc.lineno}, column {exc.colno}: {exc.msg}"
        ) from exc
    if not isinstance(payload, dict):
        raise SamplingPlanError(f"Expected inventory JSON object in {inventory_path}")
    return payload


def build_sampling_plan(
    inventory: dict[str, Any],
    *,
    max_tiles: int = 5,
    include_all_pdl: bool = True,
    include_all_qp: bool = True,
    plan_id: str = "longdress_frame1051_metadata_plan_v1",
    source_inventory: str | None = None,
) -> dict[str, Any]:
    if max_tiles <= 0:
        raise SamplingPlanError("max_tiles must be positive")

    candidates = inventory.get("candidates")
    if not isinstance(candidates, list):
        raise SamplingPlanError("inventory.candidates must be a list")

    warnings: list[str] = []
    by_tile: dict[str, list[dict[str, Any]]] = {}
    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        tile_id = candidate.get("tile_id")
        if not tile_id:
            warnings.append("candidate_missing_tile_id")
            continue
        by_tile.setdefault(str(tile_id), []).append(candidate)

    selected_tiles = _select_tiles(by_tile, max_tiles=max_tiles, warnings=warnings)
    selected_candidates = []
    selected_keys: set[str] = set()
    for tile_id in selected_tiles:
        for candidate in _select_candidates_for_tile(
            by_tile[tile_id],
            include_all_pdl=include_all_pdl,
            include_all_qp=include_all_qp,
        ):
            candidate_key = candidate.get("candidate_key")
            if not candidate_key or candidate_key in selected_keys:
                continue
            selected_keys.add(candidate_key)
            selected_candidates.append(_candidate_summary(candidate))

    selected_candidates.sort(key=lambda item: item["candidate_key"])

    coverage_summary = _coverage_summary(selected_candidates)
    return {
        "sampling_plan_schema_version": SAMPLING_PLAN_SCHEMA_VERSION,
        "plan_kind": PLANNING_PROVENANCE,
        "plan_id": plan_id,
        "source_inventory": source_inventory,
        "selection_policy": {
            "policy_id": "tile_bucket_all_pdl_all_qp_v1",
            "max_tiles": max_tiles,
            "include_all_pdl": include_all_pdl,
            "include_all_qp": include_all_qp,
            "tile_selection": "bucket_by_max_point_count_then_midpoint",
            "fallback": "tile_id_sort_when_point_count_missing",
        },
        "selected_tiles": selected_tiles,
        "selected_candidates": selected_candidates,
        "coverage_summary": coverage_summary,
        "warnings": sorted(set(warnings)),
    }


def write_sampling_plan(path: str | Path, plan: dict[str, Any]) -> None:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(plan, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _select_tiles(
    by_tile: dict[str, list[dict[str, Any]]],
    *,
    max_tiles: int,
    warnings: list[str],
) -> list[str]:
    if not by_tile:
        warnings.append("no_tiles_available")
        return []

    tile_scores = []
    missing_count = False
    for tile_id, candidates in by_tile.items():
        point_counts = [
            item.get("point_count")
            for item in candidates
            if isinstance(item.get("point_count"), int)
        ]
        if point_counts:
            tile_scores.append((tile_id, max(point_counts)))
        else:
            missing_count = True
            tile_scores.append((tile_id, None))

    if missing_count:
        warnings.append("tile_point_count_missing_or_partial")

    if all(score is None for _, score in tile_scores):
        return sorted(by_tile)[:max_tiles]

    sortable = sorted(
        tile_scores,
        key=lambda item: (
            item[1] is None,
            item[1] if item[1] is not None else 0,
            item[0],
        ),
    )
    if len(sortable) <= max_tiles:
        return [tile_id for tile_id, _ in sortable]

    selected: list[str] = []
    n = len(sortable)
    for bucket_index in range(max_tiles):
        start = bucket_index * n // max_tiles
        end = ((bucket_index + 1) * n // max_tiles) - 1
        midpoint = (start + end) // 2
        tile_id = sortable[midpoint][0]
        if tile_id not in selected:
            selected.append(tile_id)
    return selected


def _select_candidates_for_tile(
    candidates: list[dict[str, Any]],
    *,
    include_all_pdl: bool,
    include_all_qp: bool,
) -> list[dict[str, Any]]:
    if include_all_pdl and include_all_qp:
        return list(candidates)

    selected: list[dict[str, Any]] = []
    seen: set[tuple[Any, ...]] = set()
    for candidate in sorted(candidates, key=lambda item: item.get("candidate_key", "")):
        if include_all_pdl:
            key = (candidate.get("representation"), candidate.get("pdl_ratio"))
        elif include_all_qp:
            key = (
                candidate.get("representation"),
                candidate.get("codec_params", {}).get("qp"),
            )
        else:
            key = (candidate.get("representation"),)
        if key in seen:
            continue
        seen.add(key)
        selected.append(candidate)
    return selected


def _candidate_summary(candidate: dict[str, Any]) -> dict[str, Any]:
    codec_params = candidate.get("codec_params") or {}
    return {
        "candidate_key": candidate.get("candidate_key"),
        "candidate_id": candidate.get("candidate_id"),
        "tile_id": candidate.get("tile_id"),
        "representation": candidate.get("representation"),
        "pdl_ratio": candidate.get("pdl_ratio"),
        "qp": codec_params.get("qp"),
        "cl": codec_params.get("cl"),
        "point_count": candidate.get("point_count"),
        "file_size_bytes": candidate.get("file_size_bytes"),
        "status": "planned_metadata_only",
    }


def _coverage_summary(selected_candidates: list[dict[str, Any]]) -> dict[str, Any]:
    representations = sorted(
        {item["representation"] for item in selected_candidates if item.get("representation") is not None}
    )
    pdl_values = sorted(
        {item["pdl_ratio"] for item in selected_candidates if item.get("pdl_ratio") is not None}
    )
    qp_values = sorted(
        {
            item["qp"]
            for item in selected_candidates
            if item.get("representation") == "drc" and item.get("qp") is not None
        }
    )
    tile_ids = sorted({item["tile_id"] for item in selected_candidates if item.get("tile_id")})
    return {
        "selected_tile_count": len(tile_ids),
        "selected_candidate_count": len(selected_candidates),
        "representations": representations,
        "pdl_values": pdl_values,
        "drc_qp_values": qp_values,
        "ply_candidate_count": sum(1 for item in selected_candidates if item.get("representation") == "ply"),
        "drc_candidate_count": sum(1 for item in selected_candidates if item.get("representation") == "drc"),
    }
