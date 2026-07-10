from __future__ import annotations

import argparse
from pathlib import Path

from pcv_dms_benchmark.metadata_inventory import (
    build_inventory_from_data_prep_root,
    build_inventory_from_paths,
    write_inventory,
)
from pcv_dms_benchmark.sampling_plan import (
    build_sampling_plan,
    load_inventory,
    write_sampling_plan,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="pcv-dms-benchmark",
        description="Metadata-only inventory and sampling-plan utilities.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    inventory_parser = subparsers.add_parser("inventory", help="Build candidate inventory JSON.")
    inventory_source = inventory_parser.add_mutually_exclusive_group(required=True)
    inventory_source.add_argument("--data-prep-root", help="Root of pcv-stage2-data-prep.")
    inventory_source.add_argument("--ply-index", help="Path to frame_1051_tile_index.json.")
    inventory_parser.add_argument("--drc-manifest", help="Path to DRC generation_manifest.json.")
    inventory_parser.add_argument("--out", required=True, help="Output inventory JSON path.")

    sample_parser = subparsers.add_parser("sample-plan", help="Build sampling plan JSON.")
    sample_parser.add_argument("--inventory", required=True, help="Input inventory JSON path.")
    sample_parser.add_argument("--out", required=True, help="Output sampling plan JSON path.")
    sample_parser.add_argument("--max-tiles", type=int, default=5, help="Maximum tile count to select.")
    sample_parser.add_argument(
        "--plan-id",
        default="longdress_frame1051_metadata_plan_v1",
        help="Plan identifier to store in output JSON.",
    )

    args = parser.parse_args(argv)
    if args.command == "inventory":
        inventory = _run_inventory(args)
        write_inventory(args.out, inventory)
        _print_inventory_summary(inventory, Path(args.out))
        return 0
    if args.command == "sample-plan":
        plan = _run_sample_plan(args)
        write_sampling_plan(args.out, plan)
        _print_plan_summary(plan, Path(args.out))
        return 0
    parser.error(f"Unsupported command: {args.command}")
    return 2


def _run_inventory(args: argparse.Namespace) -> dict:
    if args.data_prep_root:
        return build_inventory_from_data_prep_root(args.data_prep_root)
    if not args.drc_manifest:
        raise SystemExit("--drc-manifest is required when --ply-index is used")
    return build_inventory_from_paths(
        ply_index_path=args.ply_index,
        drc_manifest_path=args.drc_manifest,
        ply_source_manifest=Path(args.ply_index).as_posix(),
        drc_source_manifest=Path(args.drc_manifest).as_posix(),
    )


def _run_sample_plan(args: argparse.Namespace) -> dict:
    inventory = load_inventory(args.inventory)
    return build_sampling_plan(
        inventory,
        max_tiles=args.max_tiles,
        plan_id=args.plan_id,
        source_inventory=Path(args.inventory).as_posix(),
    )


def _print_inventory_summary(inventory: dict, out_path: Path) -> None:
    summary = inventory.get("summary", {})
    print(f"inventory_out={out_path}")
    print(f"candidate_count={summary.get('candidate_count', 0)}")
    print(f"ply_candidate_count={summary.get('ply_candidate_count', 0)}")
    print(f"drc_candidate_count={summary.get('drc_candidate_count', 0)}")
    print(f"tile_count={summary.get('tile_count', 0)}")


def _print_plan_summary(plan: dict, out_path: Path) -> None:
    summary = plan.get("coverage_summary", {})
    print(f"sample_plan_out={out_path}")
    print(f"selected_tile_count={summary.get('selected_tile_count', 0)}")
    print(f"selected_candidate_count={summary.get('selected_candidate_count', 0)}")
    print(f"ply_candidate_count={summary.get('ply_candidate_count', 0)}")
    print(f"drc_candidate_count={summary.get('drc_candidate_count', 0)}")


if __name__ == "__main__":
    raise SystemExit(main())
