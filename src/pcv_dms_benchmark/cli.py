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
        description="Stage2 d_ms inventory, Python pilot, and calibration utilities.",
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

    pilot_parser = subparsers.add_parser(
        "python-pilot", help="Measure selected PLY/DRC candidates in the Python environment."
    )
    pilot_parser.add_argument("--inventory", required=True, help="Input inventory JSON path.")
    pilot_parser.add_argument("--sample-plan", required=True, help="Input sampling plan JSON path.")
    pilot_parser.add_argument("--data-prep-root", required=True, help="Root of pcv-stage2-data-prep.")
    pilot_parser.add_argument("--out", required=True, help="Output measured pilot JSON path.")
    pilot_parser.add_argument("--warmup", type=int, default=2, help="Warmup calls per candidate.")
    pilot_parser.add_argument("--samples", type=int, default=5, help="Measured calls per candidate.")
    pilot_parser.add_argument(
        "--smoke",
        action="store_true",
        help="Measure only the first planned PLY and DRC candidate.",
    )

    calibration_parser = subparsers.add_parser(
        "python-calibrate", help="Calibrate Python pilot models and export frame1051 handoff."
    )
    calibration_parser.add_argument("--pilot", required=True, help="Input measured pilot JSON.")
    calibration_parser.add_argument("--inventory", required=True, help="Input inventory JSON.")
    calibration_parser.add_argument(
        "--measured-summary-out", required=True, help="Output measured summary JSON."
    )
    calibration_parser.add_argument(
        "--calibration-out", required=True, help="Output calibrated model JSON."
    )
    calibration_parser.add_argument(
        "--handoff-out", required=True, help="Output derived candidate handoff JSON."
    )

    alignment_parser = subparsers.add_parser(
        "ply-backend-align", help="Compare plyfile and Open3D on four planned PLY candidates."
    )
    alignment_parser.add_argument("--inventory", required=True, help="Input inventory JSON.")
    alignment_parser.add_argument("--sample-plan", required=True, help="Input sample plan JSON.")
    alignment_parser.add_argument("--pilot", required=True, help="Existing phase1A pilot JSON.")
    alignment_parser.add_argument(
        "--data-prep-root", required=True, help="Root of pcv-stage2-data-prep."
    )
    alignment_parser.add_argument("--out", required=True, help="Output alignment JSON.")
    alignment_parser.add_argument("--warmup", type=int, default=2, help="Warmup calls per path.")
    alignment_parser.add_argument("--samples", type=int, default=5, help="Measured calls per path.")

    v2_pilot_parser = subparsers.add_parser(
        "python-v2-pilot",
        help="Measure Open3D memory PLY and DracoPy DRC in the Python 3.10 v2 profile.",
    )
    v2_pilot_parser.add_argument("--inventory", required=True, help="Input inventory JSON.")
    v2_pilot_parser.add_argument("--sample-plan", required=True, help="Input sample plan JSON.")
    v2_pilot_parser.add_argument(
        "--data-prep-root", required=True, help="Root of pcv-stage2-data-prep."
    )
    v2_pilot_parser.add_argument("--out", required=True, help="Output v2 measured pilot JSON.")
    v2_pilot_parser.add_argument("--warmup", type=int, default=2, help="Warmup calls per candidate.")
    v2_pilot_parser.add_argument("--samples", type=int, default=5, help="Measured calls per candidate.")
    v2_pilot_parser.add_argument(
        "--smoke", action="store_true", help="Measure one PLY and one DRC candidate."
    )

    v2_calibration_parser = subparsers.add_parser(
        "python-v2-calibrate",
        help="Calibrate the Python 3.10 Open3D/DracoPy v2 pilot and export handoff.",
    )
    v2_calibration_parser.add_argument("--smoke", required=True, help="Input v2 smoke JSON.")
    v2_calibration_parser.add_argument("--pilot", required=True, help="Input v2 pilot JSON.")
    v2_calibration_parser.add_argument(
        "--alignment", required=True, help="Input phase1B.2 alignment JSON."
    )
    v2_calibration_parser.add_argument("--inventory", required=True, help="Input inventory JSON.")
    v2_calibration_parser.add_argument(
        "--measured-summary-out", required=True, help="Output v2 measured summary JSON."
    )
    v2_calibration_parser.add_argument(
        "--calibration-out", required=True, help="Output v2 calibration JSON."
    )
    v2_calibration_parser.add_argument(
        "--handoff-out", required=True, help="Output v2 derived handoff JSON."
    )

    numpy_alignment_parser = subparsers.add_parser(
        "numpy-ply-align", help="Run the four-candidate NumPy PLY correctness/performance gate."
    )
    numpy_alignment_parser.add_argument("--inventory", required=True, help="Input inventory JSON.")
    numpy_alignment_parser.add_argument(
        "--sample-plan", required=True, help="Input sample plan JSON."
    )
    numpy_alignment_parser.add_argument(
        "--phase1b2-alignment", required=True, help="Existing phase1B.2 alignment JSON."
    )
    numpy_alignment_parser.add_argument(
        "--data-prep-root", required=True, help="Root of pcv-stage2-data-prep."
    )
    numpy_alignment_parser.add_argument("--out", required=True, help="Output gate JSON.")
    numpy_alignment_parser.add_argument("--warmup", type=int, default=2)
    numpy_alignment_parser.add_argument("--samples", type=int, default=5)

    numpy_pilot_parser = subparsers.add_parser(
        "python-numpy-v2-pilot",
        help="Measure NumPy PLY and DracoPy DRC in one Python 3.13 v2 profile.",
    )
    numpy_pilot_parser.add_argument("--inventory", required=True, help="Input inventory JSON.")
    numpy_pilot_parser.add_argument("--sample-plan", required=True, help="Input sample plan JSON.")
    numpy_pilot_parser.add_argument(
        "--alignment-gate", required=True, help="Passed NumPy PLY alignment gate JSON."
    )
    numpy_pilot_parser.add_argument(
        "--data-prep-root", required=True, help="Root of pcv-stage2-data-prep."
    )
    numpy_pilot_parser.add_argument("--out", required=True, help="Output v2 pilot JSON.")
    numpy_pilot_parser.add_argument("--warmup", type=int, default=2)
    numpy_pilot_parser.add_argument("--samples", type=int, default=5)
    numpy_pilot_parser.add_argument("--smoke", action="store_true")

    numpy_calibration_parser = subparsers.add_parser(
        "python-numpy-v2-calibrate",
        help="Calibrate and export the Python 3.13 NumPy PLY v2 handoff.",
    )
    numpy_calibration_parser.add_argument("--alignment-gate", required=True)
    numpy_calibration_parser.add_argument("--smoke", required=True)
    numpy_calibration_parser.add_argument("--pilot", required=True)
    numpy_calibration_parser.add_argument("--inventory", required=True)
    numpy_calibration_parser.add_argument("--measured-summary-out", required=True)
    numpy_calibration_parser.add_argument("--calibration-out", required=True)
    numpy_calibration_parser.add_argument("--handoff-out", required=True)

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
    if args.command == "python-pilot":
        return _run_python_pilot(args)
    if args.command == "python-calibrate":
        return _run_python_calibration(args)
    if args.command == "ply-backend-align":
        return _run_ply_backend_alignment(args)
    if args.command == "python-v2-pilot":
        return _run_python_v2_pilot(args)
    if args.command == "python-v2-calibrate":
        return _run_python_v2_calibration(args)
    if args.command == "numpy-ply-align":
        return _run_numpy_ply_alignment(args)
    if args.command == "python-numpy-v2-pilot":
        return _run_python_numpy_v2_pilot(args)
    if args.command == "python-numpy-v2-calibrate":
        return _run_python_numpy_v2_calibration(args)
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


def _run_python_pilot(args: argparse.Namespace) -> int:
    from pcv_dms_benchmark.python_benchmark import (
        load_json_object,
        run_python_pilot,
        select_candidates,
        write_pilot_result,
    )

    inventory = load_json_object(args.inventory)
    sample_plan = load_json_object(args.sample_plan)
    candidates = select_candidates(inventory, sample_plan, smoke=args.smoke)
    result = run_python_pilot(
        candidates,
        data_prep_root=args.data_prep_root,
        warmup_count=args.warmup,
        sample_count=args.samples,
    )
    write_pilot_result(args.out, result)
    print(f"pilot_out={Path(args.out)}")
    print(f"candidate_count={result['candidate_count']}")
    print(f"success_count={result['success_count']}")
    print(f"failure_count={result['failure_count']}")
    print(f"status={result['status']}")
    return 0 if result["failure_count"] == 0 else 1


def _run_python_calibration(args: argparse.Namespace) -> int:
    from pcv_dms_benchmark.calibration import calibrate_models
    from pcv_dms_benchmark.derived_export import (
        build_derived_handoff,
        build_measured_summary,
        sha256_file,
        write_json,
    )
    from pcv_dms_benchmark.python_benchmark import load_json_object

    pilot = load_json_object(args.pilot)
    inventory = load_json_object(args.inventory)
    pilot_sha256 = sha256_file(args.pilot)
    inventory_sha256 = sha256_file(args.inventory)
    calibration = calibrate_models(
        pilot,
        inventory,
        source_pilot_sha256=pilot_sha256,
        source_inventory_sha256=inventory_sha256,
    )
    measured_summary = build_measured_summary(pilot, source_pilot_sha256=pilot_sha256)
    handoff = build_derived_handoff(
        inventory,
        calibration,
        expected_representation_counts={"ply": 200, "drc": 600},
    )
    write_json(args.measured_summary_out, measured_summary)
    write_json(args.calibration_out, calibration)
    write_json(args.handoff_out, handoff)

    for representation in ("ply", "drc"):
        model = calibration["representation_models"][representation]
        print(f"{representation}_selected_model={model['selected_model']}")
        print(
            f"{representation}_normalized_mae="
            f"{model['cross_validation_metrics']['normalized_mae']:.9f}"
        )
        print(
            f"{representation}_recommended_for_allocation_pilot="
            f"{str(model['recommended_for_allocation_pilot']).lower()}"
        )
    print(f"candidate_count={handoff['candidate_count']}")
    return 0


def _run_ply_backend_alignment(args: argparse.Namespace) -> int:
    from pcv_dms_benchmark.ply_backend_alignment import (
        run_ply_backend_alignment,
        select_alignment_candidates,
        write_alignment_result,
    )
    from pcv_dms_benchmark.python_benchmark import load_json_object

    inventory = load_json_object(args.inventory)
    sample_plan = load_json_object(args.sample_plan)
    pilot = load_json_object(args.pilot)
    candidates = select_alignment_candidates(inventory, sample_plan)
    result = run_ply_backend_alignment(
        candidates,
        pilot,
        data_prep_root=args.data_prep_root,
        warmup_count=args.warmup,
        sample_count=args.samples,
    )
    write_alignment_result(args.out, result)
    print(f"alignment_out={Path(args.out)}")
    print(f"candidate_count={result['candidate_count']}")
    print(f"success_count={result['success_count']}")
    print(f"failure_count={result['failure_count']}")
    print(f"conclusion={result['conclusion']}")
    return 0 if result["failure_count"] == 0 else 1


def _run_python_v2_pilot(args: argparse.Namespace) -> int:
    from pcv_dms_benchmark.open3d_python_backend import (
        run_python_v2_pilot,
        verify_ply_candidate_against_legacy,
    )
    from pcv_dms_benchmark.python_benchmark import (
        load_json_object,
        select_candidates,
        write_pilot_result,
    )

    inventory = load_json_object(args.inventory)
    sample_plan = load_json_object(args.sample_plan)
    candidates = select_candidates(inventory, sample_plan, smoke=args.smoke)
    result = run_python_v2_pilot(
        candidates,
        data_prep_root=args.data_prep_root,
        warmup_count=args.warmup,
        sample_count=args.samples,
    )
    if args.smoke and result["failure_count"] == 0:
        ply_candidate = next(
            candidate for candidate in candidates if candidate.get("representation") == "ply"
        )
        result["ply_smoke_equivalence"] = verify_ply_candidate_against_legacy(
            ply_candidate, data_prep_root=args.data_prep_root
        )
    write_pilot_result(args.out, result)
    print(f"pilot_out={Path(args.out)}")
    print(f"environment_id={result['environment_id']}")
    print(f"candidate_count={result['candidate_count']}")
    print(f"success_count={result['success_count']}")
    print(f"failure_count={result['failure_count']}")
    print(f"status={result['status']}")
    return 0 if result["failure_count"] == 0 else 1


def _run_python_v2_calibration(args: argparse.Namespace) -> int:
    from pcv_dms_benchmark.calibration import calibrate_models
    from pcv_dms_benchmark.derived_export import (
        build_derived_handoff,
        build_measured_summary,
        sha256_file,
        write_json,
    )
    from pcv_dms_benchmark.open3d_python_backend import (
        ALLOCATION_USE_SCOPE,
        CALIBRATION_ID,
        ENVIRONMENT_ID,
        HANDOFF_ID,
        MEASUREMENT_SCOPE,
        allocation_release_status,
        audit_alignment_consistency,
        audit_v2_smoke,
    )
    from pcv_dms_benchmark.python_benchmark import load_json_object

    smoke = load_json_object(args.smoke)
    pilot = load_json_object(args.pilot)
    alignment = load_json_object(args.alignment)
    inventory = load_json_object(args.inventory)
    smoke_audit = audit_v2_smoke(smoke)
    alignment_audit = audit_alignment_consistency(pilot, alignment)
    pilot_sha256 = sha256_file(args.pilot)
    inventory_sha256 = sha256_file(args.inventory)
    calibration = calibrate_models(
        pilot,
        inventory,
        source_pilot_sha256=pilot_sha256,
        source_inventory_sha256=inventory_sha256,
        calibration_id=CALIBRATION_ID,
        expected_environment_id=ENVIRONMENT_ID,
        expected_measurement_scope=MEASUREMENT_SCOPE,
        allocation_use_scope=ALLOCATION_USE_SCOPE,
        profile_limitation=(
            "specific to Python 3.10.20, Open3D 0.19.0, DracoPy 2.0.0, "
            "and numpy 2.2.6 on Windows x64"
        ),
        delivery_version="v2",
    )
    integration_status = allocation_release_status(
        calibration,
        smoke_audit=smoke_audit,
        alignment_audit=alignment_audit,
    )
    release_gate = {
        "smoke": smoke_audit,
        "phase1b2_alignment_consistency": alignment_audit,
        "all_models_recommended": all(
            calibration["representation_models"][representation][
                "recommended_for_allocation_pilot"
            ]
            for representation in ("ply", "drc")
        ),
        "status": "passed"
        if integration_status == "ready_for_provisional_integration"
        else "failed",
    }
    calibration.update(
        {
            "environment_snapshot": pilot.get("environment_snapshot"),
            "source_smoke_sha256": sha256_file(args.smoke),
            "source_alignment_sha256": sha256_file(args.alignment),
            "release_gate": release_gate,
            "allocation_integration_status": integration_status,
            "v1_relationship": {
                "v1_profile_status": "historical_plyfile_profile",
                "allocation_status": "superseded_for_allocation_pilot",
                "retention_status": "retained_for_audit",
                "v1_values_used_for_v2_calibration": False,
            },
        }
    )
    measured_summary = build_measured_summary(
        pilot, source_pilot_sha256=pilot_sha256, delivery_version="v2"
    )
    measured_summary["execution_profile"] = ENVIRONMENT_ID
    handoff = build_derived_handoff(
        inventory,
        calibration,
        expected_representation_counts={"ply": 200, "drc": 600},
        handoff_id=HANDOFF_ID,
        allocation_use_scope=ALLOCATION_USE_SCOPE,
        delivery_version="v2",
        allocation_integration_status=integration_status,
        limitations=[
            "derived from one Longdress frame and five measured tiles",
            "not cross-frame or cross-dataset validated",
            "specific to the Python 3.10 Open3D 0.19.0 and DracoPy 2.0.0 profile",
            "allocation must join by candidate_key and verify tile_id plus candidate_id",
        ],
    )
    handoff["release_gate"] = release_gate
    handoff["v1_relationship"] = calibration["v1_relationship"]

    write_json(args.measured_summary_out, measured_summary)
    write_json(args.calibration_out, calibration)
    write_json(args.handoff_out, handoff)
    for representation in ("ply", "drc"):
        model = calibration["representation_models"][representation]
        print(f"{representation}_selected_model={model['selected_model']}")
        print(
            f"{representation}_normalized_mae="
            f"{model['cross_validation_metrics']['normalized_mae']:.9f}"
        )
        print(
            f"{representation}_recommended_for_allocation_pilot="
            f"{str(model['recommended_for_allocation_pilot']).lower()}"
        )
    print(f"candidate_count={handoff['candidate_count']}")
    print(f"allocation_integration_status={integration_status}")
    return 0 if integration_status == "ready_for_provisional_integration" else 1


def _run_numpy_ply_alignment(args: argparse.Namespace) -> int:
    from pcv_dms_benchmark.numpy_ply_backend import (
        run_numpy_ply_alignment,
        select_alignment_candidates,
        write_numpy_alignment,
    )
    from pcv_dms_benchmark.python_benchmark import load_json_object

    inventory = load_json_object(args.inventory)
    sample_plan = load_json_object(args.sample_plan)
    phase1b2_alignment = load_json_object(args.phase1b2_alignment)
    candidates = select_alignment_candidates(inventory, sample_plan)
    result = run_numpy_ply_alignment(
        candidates,
        phase1b2_alignment,
        data_prep_root=args.data_prep_root,
        warmup_count=args.warmup,
        sample_count=args.samples,
    )
    write_numpy_alignment(args.out, result)
    print(f"alignment_out={Path(args.out)}")
    print(f"candidate_count={result['candidate_count']}")
    print(f"success_count={result['success_count']}")
    print(f"failure_count={result['failure_count']}")
    print(f"gate_status={result['gate']['status']}")
    return 0 if result["gate"]["status"] == "passed" else 1


def _run_python_numpy_v2_pilot(args: argparse.Namespace) -> int:
    from pcv_dms_benchmark.numpy_ply_backend import (
        audit_numpy_alignment_gate,
        run_python_numpy_v2_pilot,
    )
    from pcv_dms_benchmark.python_benchmark import (
        load_json_object,
        select_candidates,
        write_pilot_result,
    )

    alignment = load_json_object(args.alignment_gate)
    audit_numpy_alignment_gate(alignment)
    inventory = load_json_object(args.inventory)
    sample_plan = load_json_object(args.sample_plan)
    candidates = select_candidates(inventory, sample_plan, smoke=args.smoke)
    result = run_python_numpy_v2_pilot(
        candidates,
        data_prep_root=args.data_prep_root,
        warmup_count=args.warmup,
        sample_count=args.samples,
    )
    result["source_alignment_gate"] = Path(args.alignment_gate).as_posix()
    write_pilot_result(args.out, result)
    print(f"pilot_out={Path(args.out)}")
    print(f"environment_id={result['environment_id']}")
    print(f"candidate_count={result['candidate_count']}")
    print(f"success_count={result['success_count']}")
    print(f"failure_count={result['failure_count']}")
    print(f"status={result['status']}")
    return 0 if result["failure_count"] == 0 else 1


def _run_python_numpy_v2_calibration(args: argparse.Namespace) -> int:
    from pcv_dms_benchmark.calibration import calibrate_models
    from pcv_dms_benchmark.derived_export import (
        build_derived_handoff,
        build_measured_summary,
        sha256_file,
        write_json,
    )
    from pcv_dms_benchmark.numpy_ply_backend import (
        ALLOCATION_USE_SCOPE,
        CALIBRATION_ID,
        ENVIRONMENT_ID,
        HANDOFF_ID,
        MEASUREMENT_SCOPE,
        allocation_release_status,
        audit_numpy_alignment_gate,
        audit_numpy_v2_smoke,
    )
    from pcv_dms_benchmark.python_benchmark import load_json_object

    alignment = load_json_object(args.alignment_gate)
    smoke = load_json_object(args.smoke)
    pilot = load_json_object(args.pilot)
    inventory = load_json_object(args.inventory)
    alignment_gate = audit_numpy_alignment_gate(alignment)
    smoke_audit = audit_numpy_v2_smoke(smoke)
    pilot_sha256 = sha256_file(args.pilot)
    inventory_sha256 = sha256_file(args.inventory)
    calibration = calibrate_models(
        pilot,
        inventory,
        source_pilot_sha256=pilot_sha256,
        source_inventory_sha256=inventory_sha256,
        calibration_id=CALIBRATION_ID,
        expected_environment_id=ENVIRONMENT_ID,
        expected_measurement_scope=MEASUREMENT_SCOPE,
        allocation_use_scope=ALLOCATION_USE_SCOPE,
        profile_limitation=(
            "specific to CPython 3.13.0, numpy 2.5.1 structured PLY parsing, "
            "and DracoPy 2.0.0 on Windows x64"
        ),
        delivery_version="v2",
    )
    integration_status = allocation_release_status(
        calibration,
        alignment_gate=alignment_gate,
        smoke_audit=smoke_audit,
    )
    release_gate = {
        "numpy_ply_alignment": alignment_gate,
        "smoke": smoke_audit,
        "pilot_audit": calibration["pilot_audit"],
        "all_models_recommended": all(
            calibration["representation_models"][representation][
                "recommended_for_allocation_pilot"
            ]
            for representation in ("ply", "drc")
        ),
        "status": "passed"
        if integration_status == "ready_for_provisional_integration"
        else "failed",
    }
    historical_profiles = {
        "v1": {
            "profile_status": "historical_plyfile_profile",
            "allocation_status": "superseded_for_allocation_pilot",
            "retention_status": "retained_for_audit",
            "v1_values_used_for_v2_calibration": False,
        },
        "open3d_from_bytes": {
            "profile_status": "blocked_open3d_windows_from_bytes_profile",
            "retention_status": "retained_for_audit",
        },
    }
    calibration.update(
        {
            "environment_snapshot": pilot.get("environment_snapshot"),
            "source_alignment_gate_sha256": sha256_file(args.alignment_gate),
            "source_smoke_sha256": sha256_file(args.smoke),
            "release_gate": release_gate,
            "allocation_integration_status": integration_status,
            "historical_profiles": historical_profiles,
        }
    )
    measured_summary = build_measured_summary(
        pilot, source_pilot_sha256=pilot_sha256, delivery_version="v2"
    )
    measured_summary["execution_profile"] = ENVIRONMENT_ID
    measured_summary["historical_profiles"] = historical_profiles
    handoff = build_derived_handoff(
        inventory,
        calibration,
        expected_representation_counts={"ply": 200, "drc": 600},
        handoff_id=HANDOFF_ID,
        allocation_use_scope=ALLOCATION_USE_SCOPE,
        delivery_version="v2",
        allocation_integration_status=integration_status,
        limitations=[
            "derived from one Longdress frame and five measured tiles",
            "not cross-frame or cross-dataset validated",
            "specific to the Python 3.13 NumPy PLY and DracoPy 2.0.0 profile",
            "NumPy PLY parser supports only the controlled Stage2 scalar vertex corpus",
            "allocation must join by candidate_key and verify tile_id plus candidate_id",
        ],
    )
    handoff["release_gate"] = release_gate
    handoff["historical_profiles"] = historical_profiles

    write_json(args.measured_summary_out, measured_summary)
    write_json(args.calibration_out, calibration)
    write_json(args.handoff_out, handoff)
    for representation in ("ply", "drc"):
        model = calibration["representation_models"][representation]
        print(f"{representation}_selected_model={model['selected_model']}")
        print(
            f"{representation}_normalized_mae="
            f"{model['cross_validation_metrics']['normalized_mae']:.9f}"
        )
        print(
            f"{representation}_recommended_for_allocation_pilot="
            f"{str(model['recommended_for_allocation_pilot']).lower()}"
        )
    print(f"candidate_count={handoff['candidate_count']}")
    print(f"allocation_integration_status={integration_status}")
    return 0 if integration_status == "ready_for_provisional_integration" else 1


if __name__ == "__main__":
    raise SystemExit(main())
