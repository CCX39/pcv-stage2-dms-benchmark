from __future__ import annotations

import json
from pathlib import Path
from typing import Any


INVENTORY_SCHEMA_VERSION = "0.1.0"
PLANNING_PROVENANCE = "metadata_planning"

DEFAULT_PLY_INDEX = (
    Path("artifacts")
    / "pilot_1051_g128_tilelocal_pdl5_v1"
    / "frame_1051_tile_index.json"
)
DEFAULT_DRC_MANIFEST = (
    Path("artifacts")
    / "pilot_1051_g128_drc_pdl5_qp3_cl10_v1"
    / "generation_manifest.json"
)


class MetadataInventoryError(ValueError):
    """Raised when metadata cannot be safely normalized."""


def load_json(path: str | Path) -> dict[str, Any]:
    json_path = Path(path)
    try:
        payload = json.loads(json_path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise MetadataInventoryError(f"JSON file not found: {json_path}") from exc
    except json.JSONDecodeError as exc:
        raise MetadataInventoryError(
            f"Invalid JSON in {json_path}: line {exc.lineno}, column {exc.colno}: {exc.msg}"
        ) from exc
    if not isinstance(payload, dict):
        raise MetadataInventoryError(f"Expected JSON object in {json_path}")
    return payload


def build_inventory_from_data_prep_root(data_prep_root: str | Path) -> dict[str, Any]:
    root = Path(data_prep_root)
    return build_inventory_from_paths(
        ply_index_path=root / DEFAULT_PLY_INDEX,
        drc_manifest_path=root / DEFAULT_DRC_MANIFEST,
        source_label=root.as_posix(),
        ply_source_manifest=DEFAULT_PLY_INDEX.as_posix(),
        drc_source_manifest=DEFAULT_DRC_MANIFEST.as_posix(),
    )


def build_inventory_from_paths(
    *,
    ply_index_path: str | Path,
    drc_manifest_path: str | Path,
    source_label: str | None = None,
    ply_source_manifest: str | None = None,
    drc_source_manifest: str | None = None,
) -> dict[str, Any]:
    ply_index = load_json(ply_index_path)
    drc_manifest = load_json(drc_manifest_path)
    return build_inventory_from_metadata(
        ply_index=ply_index,
        drc_manifest=drc_manifest,
        source_label=source_label,
        ply_source_manifest=ply_source_manifest or Path(ply_index_path).as_posix(),
        drc_source_manifest=drc_source_manifest or Path(drc_manifest_path).as_posix(),
    )


def build_inventory_from_metadata(
    *,
    ply_index: dict[str, Any],
    drc_manifest: dict[str, Any],
    source_label: str | None = None,
    ply_source_manifest: str = "ply_tile_index",
    drc_source_manifest: str = "drc_generation_manifest",
) -> dict[str, Any]:
    warnings: list[str] = []
    candidates: list[dict[str, Any]] = []

    candidates.extend(_ply_candidates(ply_index, ply_source_manifest, warnings))
    candidates.extend(_drc_candidates(drc_manifest, drc_source_manifest, warnings))

    duplicate_keys = _duplicates(candidate["candidate_key"] for candidate in candidates)
    if duplicate_keys:
        raise MetadataInventoryError(
            "Duplicate candidate_key values: " + ", ".join(sorted(duplicate_keys))
        )

    summary = {
        "candidate_count": len(candidates),
        "ply_candidate_count": sum(1 for item in candidates if item["representation"] == "ply"),
        "drc_candidate_count": sum(1 for item in candidates if item["representation"] == "drc"),
        "tile_count": len({item["tile_id"] for item in candidates if item.get("tile_id") is not None}),
        "pdl_values": sorted(
            {item["pdl_ratio"] for item in candidates if item.get("pdl_ratio") is not None}
        ),
        "drc_qp_values": sorted(
            {
                item.get("codec_params", {}).get("qp")
                for item in candidates
                if item["representation"] == "drc"
                and item.get("codec_params", {}).get("qp") is not None
            }
        ),
    }

    return {
        "inventory_schema_version": INVENTORY_SCHEMA_VERSION,
        "inventory_kind": PLANNING_PROVENANCE,
        "source": source_label,
        "source_manifests": {
            "ply_tile_index": ply_source_manifest,
            "drc_generation_manifest": drc_source_manifest,
        },
        "summary": summary,
        "candidates": sorted(candidates, key=lambda item: item["candidate_key"]),
        "warnings": sorted(set(warnings)),
    }


def _ply_candidates(
    ply_index: dict[str, Any],
    source_manifest: str,
    inventory_warnings: list[str],
) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    dataset_id = ply_index.get("dataset_id")
    frame_id = ply_index.get("frame_id")
    grid_profile_id = ply_index.get("grid_profile_id")
    artifact_root = _artifact_root_from_manifest(source_manifest)

    for tile in ply_index.get("tiles", []):
        if not isinstance(tile, dict) or tile.get("is_empty") is True:
            continue
        tile_id = tile.get("tile_id")
        for asset in tile.get("quality_assets", []) or []:
            if not isinstance(asset, dict):
                continue
            warnings: list[str] = []
            source_pdl = _optional_float(asset.get("target_pdl"), "target_pdl", warnings)
            point_count = _optional_int(
                asset.get("retained_point_count", asset.get("point_count")),
                "point_count",
                warnings,
            )
            file_size_bytes = _optional_int(asset.get("file_size_bytes"), "file_size_bytes", warnings)
            asset_ref = _join_ref(artifact_root, asset.get("relative_path"))
            asset_sha256 = asset.get("sha256")
            if asset_sha256 is None:
                warnings.append("missing_asset_sha256")

            identity = {
                "dataset_id": asset.get("dataset_id", dataset_id),
                "frame_id": asset.get("frame_id", frame_id),
                "grid_profile_id": asset.get("grid_profile_id", grid_profile_id),
                "tile_id": asset.get("tile_id", tile_id),
                "representation": "ply",
                "pdl_ratio": source_pdl,
                "codec": None,
                "qp": None,
                "cl": None,
                "point_cloud_mode": None,
            }
            candidate_key = make_candidate_key(identity)
            candidate_id = f"ply__pdl_{_pdl_token(source_pdl)}" if source_pdl is not None else None
            candidates.append(
                {
                    "inventory_schema_version": INVENTORY_SCHEMA_VERSION,
                    "dataset_id": identity["dataset_id"],
                    "frame_id": identity["frame_id"],
                    "grid_profile_id": identity["grid_profile_id"],
                    "tile_id": identity["tile_id"],
                    "candidate_id": candidate_id,
                    "candidate_key": candidate_key,
                    "representation": "ply",
                    "file_format": "ply",
                    "source_pdl": source_pdl,
                    "pdl_ratio": source_pdl,
                    "codec": None,
                    "codec_profile": "binary_little_endian_ply",
                    "codec_params": {
                        "source_pdl": source_pdl,
                        "sampling_scope": asset.get("sampling_scope"),
                        "sampling_method": asset.get("sampling_method"),
                    },
                    "point_count": point_count,
                    "file_size_bytes": file_size_bytes,
                    "asset_ref": asset_ref,
                    "asset_sha256": asset_sha256,
                    "source_manifest": source_manifest,
                    "provenance": {
                        "record_kind": PLANNING_PROVENANCE,
                        "source_metadata": "tile_binary_ply_index",
                    },
                    "status": "planned_metadata_only",
                    "warning_codes": sorted(set(warnings)),
                }
            )
            inventory_warnings.extend(f"{candidate_key}:{warning}" for warning in warnings)
    return candidates


def _drc_candidates(
    drc_manifest: dict[str, Any],
    source_manifest: str,
    inventory_warnings: list[str],
) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    dataset_id = drc_manifest.get("dataset_id")
    frame_id = drc_manifest.get("frame_id")
    grid_profile_id = drc_manifest.get("grid_profile_id")
    artifact_root = _artifact_root_from_manifest(source_manifest)

    for variant in drc_manifest.get("variants", []) or []:
        if not isinstance(variant, dict):
            continue
        warnings: list[str] = []
        source_pdl = _optional_float(variant.get("source_pdl"), "source_pdl", warnings)
        qp = _optional_int(variant.get("qp"), "qp", warnings)
        cl = _optional_int(variant.get("compression_level"), "compression_level", warnings)
        point_cloud_mode = _point_cloud_mode(variant)
        point_count = _optional_int(
            variant.get("source_point_count", variant.get("decoded_vertex_count")),
            "point_count",
            warnings,
        )
        file_size_bytes = _optional_int(
            variant.get("drc_file_size_bytes"), "drc_file_size_bytes", warnings
        )
        asset_ref = _join_ref(artifact_root, variant.get("drc_relpath"))
        asset_sha256 = variant.get("drc_sha256")
        if asset_sha256 is None:
            warnings.append("missing_asset_sha256")

        identity = {
            "dataset_id": variant.get("dataset_id", dataset_id),
            "frame_id": variant.get("frame_id", frame_id),
            "grid_profile_id": variant.get("grid_profile_id", grid_profile_id),
            "tile_id": variant.get("tile_id"),
            "representation": "drc",
            "pdl_ratio": source_pdl,
            "codec": variant.get("codec_id", "draco"),
            "qp": qp,
            "cl": cl,
            "point_cloud_mode": point_cloud_mode,
        }
        candidate_key = make_candidate_key(identity)
        candidate_id = (
            f"drc__pdl_{_pdl_token(source_pdl)}__qp_{qp}__cl_{cl}"
            if source_pdl is not None and qp is not None and cl is not None
            else variant.get("variant_id")
        )
        candidates.append(
            {
                "inventory_schema_version": INVENTORY_SCHEMA_VERSION,
                "dataset_id": identity["dataset_id"],
                "frame_id": identity["frame_id"],
                "grid_profile_id": identity["grid_profile_id"],
                "tile_id": identity["tile_id"],
                "candidate_id": candidate_id,
                "candidate_key": candidate_key,
                "representation": "drc",
                "file_format": "drc",
                "source_pdl": source_pdl,
                "pdl_ratio": source_pdl,
                "codec": identity["codec"],
                "codec_profile": _drc_codec_profile(cl=cl, qp=qp, point_cloud_mode=point_cloud_mode),
                "codec_params": {
                    "source_pdl": source_pdl,
                    "qp": qp,
                    "cl": cl,
                    "point_cloud_mode": point_cloud_mode,
                },
                "point_count": point_count,
                "file_size_bytes": file_size_bytes,
                "asset_ref": asset_ref,
                "asset_sha256": asset_sha256,
                "source_manifest": source_manifest,
                "provenance": {
                    "record_kind": PLANNING_PROVENANCE,
                    "source_metadata": "drc_generation_manifest",
                },
                "status": "planned_metadata_only",
                "warning_codes": sorted(set(warnings)),
            }
        )
        inventory_warnings.extend(f"{candidate_key}:{warning}" for warning in warnings)
    return candidates


def make_candidate_key(identity: dict[str, Any]) -> str:
    parts = [
        ("dataset", identity.get("dataset_id")),
        ("frame", identity.get("frame_id")),
        ("grid", identity.get("grid_profile_id")),
        ("tile", identity.get("tile_id")),
        ("repr", identity.get("representation")),
        ("pdl", _pdl_token(identity.get("pdl_ratio"))),
        ("codec", identity.get("codec") or "none"),
    ]
    if identity.get("representation") == "drc":
        parts.extend(
            [
                ("pc", "1" if identity.get("point_cloud_mode") is True else "0"),
                ("cl", identity.get("cl")),
                ("qp", identity.get("qp")),
            ]
        )
    return "|".join(f"{key}={_stable_value(value)}" for key, value in parts)


def write_inventory(path: str | Path, inventory: dict[str, Any]) -> None:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(inventory, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _artifact_root_from_manifest(source_manifest: str) -> str | None:
    path = Path(source_manifest)
    parts = path.parts
    if "artifacts" not in parts:
        return None
    artifact_index = parts.index("artifacts")
    if len(parts) <= artifact_index + 1:
        return None
    return Path(*parts[artifact_index : artifact_index + 2]).as_posix()


def _join_ref(root: str | None, relative_path: Any) -> str | None:
    if not isinstance(relative_path, str) or not relative_path:
        return None
    normalized = relative_path.replace("\\", "/")
    if root is None:
        return normalized
    return f"{root.rstrip('/')}/{normalized.lstrip('/')}"


def _optional_float(value: Any, field_name: str, warnings: list[str]) -> float | None:
    if value is None:
        warnings.append(f"missing_{field_name}")
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        warnings.append(f"invalid_{field_name}")
        return None


def _optional_int(value: Any, field_name: str, warnings: list[str]) -> int | None:
    if value is None:
        warnings.append(f"missing_{field_name}")
        return None
    if isinstance(value, bool):
        warnings.append(f"invalid_{field_name}")
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        warnings.append(f"invalid_{field_name}")
        return None


def _point_cloud_mode(variant: dict[str, Any]) -> bool | None:
    if variant.get("point_cloud_mode") is True:
        return True
    if variant.get("point_cloud_flag") == "-point_cloud":
        return True
    return None


def _drc_codec_profile(*, cl: int | None, qp: int | None, point_cloud_mode: bool | None) -> str:
    pc = "point_cloud" if point_cloud_mode else "point_cloud_pending"
    cl_part = f"cl{cl}" if cl is not None else "cl_pending"
    qp_part = f"qp{qp}" if qp is not None else "qp_pending"
    return f"draco_{pc}_{cl_part}_{qp_part}"


def _pdl_token(value: Any) -> str:
    if value is None:
        return "pending"
    try:
        return f"{float(value):.1f}".replace(".", "p")
    except (TypeError, ValueError):
        return "pending"


def _stable_value(value: Any) -> str:
    if value is None:
        return "pending"
    return str(value).replace("|", "_").replace("=", "_")


def _duplicates(values: Any) -> set[str]:
    seen: set[str] = set()
    duplicates: set[str] = set()
    for value in values:
        if value in seen:
            duplicates.add(value)
        seen.add(value)
    return duplicates
