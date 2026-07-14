from __future__ import annotations

import json
import platform
from dataclasses import dataclass
from datetime import datetime, timezone
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any

import numpy as np

from pcv_dms_benchmark.measurement_records import evaluate_allocation_eligibility
from pcv_dms_benchmark.ply_backend_alignment import (
    measure_processor,
    select_alignment_candidates,
)
from pcv_dms_benchmark.python_benchmark import (
    Processor,
    PythonBenchmarkError,
    decode_drc,
    parse_binary_ply,
    run_python_pilot,
)


ENVIRONMENT_ID = "python313_numpy_ply_dracopy200_windows_x64"
MEASUREMENT_SCOPE = "longdress_frame1051_python_numpy_ply_v2_pilot"
MEASUREMENT_BOUNDARY = (
    "payload bytes resident in memory -> NumPy structured PLY parse or DracoPy DRC decode -> "
    "owned positions float32[N,3] and colors uint8[N,3]"
)
CALIBRATION_ID = "python313_numpy_ply_dracopy200_frame1051_p50_calibration_v2"
HANDOFF_ID = "python_numpy_frame1051_candidate_dms_v2"
ALLOCATION_USE_SCOPE = "provisional_frame1051_python313_numpy_ply_dracopy200_v2"
ALIGNMENT_SCOPE = "longdress_frame1051_numpy_ply_alignment"
MAX_HEADER_BYTES = 1024 * 1024


SCALAR_TYPES = {
    "char": "i1",
    "int8": "i1",
    "uchar": "u1",
    "uint8": "u1",
    "short": "<i2",
    "int16": "<i2",
    "ushort": "<u2",
    "uint16": "<u2",
    "int": "<i4",
    "int32": "<i4",
    "uint": "<u4",
    "uint32": "<u4",
    "float": "<f4",
    "float32": "<f4",
    "double": "<f8",
    "float64": "<f8",
}


class NumpyPlyError(PythonBenchmarkError):
    """Raised when a Stage2 PLY violates the controlled NumPy profile."""

    def __init__(self, code: str, detail: str) -> None:
        self.code = code
        super().__init__(f"{code}: {detail}")


@dataclass(frozen=True)
class ElementSpec:
    name: str
    count: int
    properties: tuple[tuple[str, np.dtype[Any]], ...]
    has_list_property: bool


def parse_binary_ply_numpy(
    payload: bytes | memoryview,
) -> tuple[np.ndarray, np.ndarray]:
    buffer = _readonly_buffer(payload)
    body_offset, elements = _parse_header(buffer)
    vertex_index = next(
        (index for index, element in enumerate(elements) if element.name == "vertex"), None
    )
    if vertex_index is None:
        raise NumpyPlyError("VERTEX_ELEMENT_MISSING", "element vertex is required")
    vertex = elements[vertex_index]
    if vertex.count <= 0:
        raise NumpyPlyError("INVALID_VERTEX_COUNT", f"vertex count must be positive: {vertex.count}")
    if vertex.has_list_property:
        raise NumpyPlyError(
            "VERTEX_LIST_PROPERTY_UNSUPPORTED", "vertex list properties are not supported"
        )

    vertex_offset = body_offset
    for element in elements[:vertex_index]:
        if element.has_list_property:
            raise NumpyPlyError(
                "UNSUPPORTED_PLY_FORMAT",
                f"cannot skip list property before vertex element: {element.name}",
            )
        element_dtype = np.dtype(list(element.properties))
        vertex_offset += element.count * element_dtype.itemsize

    names = [name for name, _ in vertex.properties]
    required = ("x", "y", "z", "red", "green", "blue")
    missing = [name for name in required if name not in names]
    if missing:
        raise NumpyPlyError(
            "REQUIRED_PROPERTY_MISSING", f"missing vertex properties: {', '.join(missing)}"
        )
    property_types = dict(vertex.properties)
    if any(property_types[name] != np.dtype("u1") for name in ("red", "green", "blue")):
        raise NumpyPlyError(
            "INVALID_RGB_TYPE", "red, green, and blue must be uchar/uint8"
        )

    structured_dtype = np.dtype(list(vertex.properties))
    required_end = vertex_offset + vertex.count * structured_dtype.itemsize
    if required_end > buffer.nbytes:
        raise NumpyPlyError(
            "TRUNCATED_VERTEX_PAYLOAD",
            f"need {required_end} bytes, payload has {buffer.nbytes}",
        )
    vertices = np.frombuffer(
        buffer,
        dtype=structured_dtype,
        count=vertex.count,
        offset=vertex_offset,
    )
    positions = np.empty((vertex.count, 3), dtype=np.float32)
    colors = np.empty((vertex.count, 3), dtype=np.uint8)
    positions[:, 0] = vertices["x"]
    positions[:, 1] = vertices["y"]
    positions[:, 2] = vertices["z"]
    colors[:, 0] = vertices["red"]
    colors[:, 1] = vertices["green"]
    colors[:, 2] = vertices["blue"]
    return positions, colors


def environment_snapshot() -> dict[str, str]:
    return {
        "python_version": platform.python_version(),
        "python_implementation": platform.python_implementation(),
        "operating_system": platform.platform(),
        "numpy_version": np.__version__,
        "dracopy_version": _package_version("DracoPy"),
        "plyfile_version": _package_version("plyfile"),
        "timer_api": "time.perf_counter_ns",
    }


def run_python_numpy_v2_pilot(
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
        "ply": parse_binary_ply_numpy,
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
                "numpy.frombuffer+structured-dtype",
                f"numpy={snapshot['numpy_version']}",
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


def run_numpy_ply_alignment(
    candidates: list[dict[str, Any]],
    phase1b2_alignment: dict[str, Any],
    *,
    data_prep_root: str | Path,
    warmup_count: int = 2,
    sample_count: int = 5,
    run_id: str | None = None,
) -> dict[str, Any]:
    if len(candidates) != 4:
        raise NumpyPlyError("UNSUPPORTED_PLY_FORMAT", "alignment requires four candidates")
    reference_by_key = {
        record.get("candidate_key"): record
        for record in phase1b2_alignment.get("records", [])
        if isinstance(record, dict)
    }
    records = []
    root = Path(data_prep_root).resolve()
    for candidate in candidates:
        record = _alignment_base_record(candidate)
        try:
            asset_path = _resolve_asset_path(root, candidate.get("asset_ref"))
            actual_size = asset_path.stat().st_size
            expected_size = int(candidate["file_size_bytes"])
            if actual_size != expected_size:
                raise NumpyPlyError(
                    "TRUNCATED_VERTEX_PAYLOAD",
                    f"file size mismatch: metadata={expected_size}, stat={actual_size}",
                )
            payload = asset_path.read_bytes()
            expected_points = int(candidate["point_count"])
            fast_timing, fast_output = measure_processor(
                lambda: parse_binary_ply_numpy(payload),
                warmup_count=warmup_count,
                sample_count=sample_count,
                expected_point_count=expected_points,
            )
            plyfile_timing, plyfile_output = measure_processor(
                lambda: parse_binary_ply(payload),
                warmup_count=warmup_count,
                sample_count=sample_count,
                expected_point_count=expected_points,
            )
            correctness = _validate_exact_equivalence(fast_output, plyfile_output)
            reference = reference_by_key.get(candidate["candidate_key"])
            if not reference:
                raise NumpyPlyError(
                    "UNSUPPORTED_PLY_FORMAT", "phase1B.2 reference candidate is missing"
                )
            ratio = fast_timing["p50_ms"] / plyfile_timing["p50_ms"]
            record.update(
                {
                    "numpy_fast_memory_ms": fast_timing,
                    "plyfile_memory_ms": plyfile_timing,
                    "numpy_over_plyfile_p50_ratio": ratio,
                    "phase1b2_open3d_path_p50_ms": reference["open3d_legacy_total_ms"][
                        "p50_ms"
                    ],
                    "correctness": correctness,
                    "status": "success",
                    "error": None,
                }
            )
        except Exception as exc:
            record.update(
                {
                    "numpy_fast_memory_ms": None,
                    "plyfile_memory_ms": None,
                    "numpy_over_plyfile_p50_ratio": None,
                    "phase1b2_open3d_path_p50_ms": None,
                    "correctness": {"status": "failed"},
                    "status": "failed",
                    "error": f"{type(exc).__name__}: {exc}",
                }
            )
        records.append(record)

    gate = _classify_alignment_gate(records)
    success_count = sum(record["status"] == "success" for record in records)
    return {
        "alignment_schema_version": "1.0",
        "run_id": run_id or _default_run_id("numpy_ply_alignment"),
        "measurement_scope": ALIGNMENT_SCOPE,
        "environment_id": ENVIRONMENT_ID,
        "environment_snapshot": environment_snapshot(),
        "timer_api": "time.perf_counter_ns",
        "warmup_count": warmup_count,
        "sample_count": sample_count,
        "candidate_count": len(records),
        "success_count": success_count,
        "failure_count": len(records) - success_count,
        "gate": gate,
        "records": records,
    }


def audit_numpy_alignment_gate(alignment: dict[str, Any]) -> dict[str, Any]:
    gate = alignment.get("gate") or {}
    if (
        alignment.get("environment_id") != ENVIRONMENT_ID
        or alignment.get("candidate_count") != 4
        or alignment.get("success_count") != 4
        or alignment.get("failure_count") != 0
        or gate.get("status") != "passed"
    ):
        raise NumpyPlyError("UNSUPPORTED_PLY_FORMAT", "NumPy PLY alignment gate failed")
    return gate


def audit_numpy_v2_smoke(smoke: dict[str, Any]) -> dict[str, Any]:
    results = smoke.get("results")
    if not isinstance(results, list):
        raise NumpyPlyError("UNSUPPORTED_PLY_FORMAT", "smoke.results must be a list")
    counts = {
        representation: sum(
            item.get("representation") == representation and item.get("status") == "success"
            for item in results
            if isinstance(item, dict)
        )
        for representation in ("ply", "drc")
    }
    if not (
        smoke.get("environment_id") == ENVIRONMENT_ID
        and smoke.get("candidate_count") == 2
        and smoke.get("success_count") == 2
        and smoke.get("failure_count") == 0
        and counts == {"ply": 1, "drc": 1}
    ):
        raise NumpyPlyError("UNSUPPORTED_PLY_FORMAT", "NumPy v2 smoke gate failed")
    return {
        "status": "passed",
        "environment_id": ENVIRONMENT_ID,
        "candidate_count": 2,
        "representation_counts": counts,
    }


def allocation_release_status(
    calibration: dict[str, Any],
    *,
    alignment_gate: dict[str, Any],
    smoke_audit: dict[str, Any],
) -> str:
    models = calibration.get("representation_models") or {}
    ready = (
        alignment_gate.get("status") == "passed"
        and smoke_audit.get("status") == "passed"
        and all(
            (models.get(representation) or {}).get("recommended_for_allocation_pilot") is True
            for representation in ("ply", "drc")
        )
    )
    return evaluate_allocation_eligibility(
        calibration, release_gate_passed=ready
    )["allocation_integration_status"]


def write_numpy_alignment(path: str | Path, result: dict[str, Any]) -> None:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _readonly_buffer(payload: bytes | memoryview) -> memoryview:
    if isinstance(payload, bytes):
        return memoryview(payload)
    if isinstance(payload, memoryview) and payload.readonly:
        return payload.cast("B")
    raise NumpyPlyError(
        "UNSUPPORTED_PLY_FORMAT", "processor requires bytes or a read-only memoryview"
    )


def _parse_header(buffer: memoryview) -> tuple[int, tuple[ElementSpec, ...]]:
    header_bytes = buffer[: min(buffer.nbytes, MAX_HEADER_BYTES)].tobytes()
    body_offset: int | None = None
    line_start = 0
    while line_start < len(header_bytes):
        newline_index = header_bytes.find(b"\n", line_start)
        if newline_index < 0:
            break
        line = header_bytes[line_start:newline_index].removesuffix(b"\r")
        if line == b"end_header":
            body_offset = newline_index + 1
            break
        line_start = newline_index + 1
    if body_offset is None:
        raise NumpyPlyError(
            "UNSUPPORTED_PLY_FORMAT", "PLY end_header line with LF or CRLF is missing"
        )
    try:
        header = header_bytes[:body_offset].decode("ascii")
    except UnicodeDecodeError as exc:
        raise NumpyPlyError("UNSUPPORTED_PLY_FORMAT", "PLY header must be ASCII") from exc
    lines = [line.strip() for line in header.replace("\r", "").split("\n")]
    if not lines or lines[0] != "ply":
        raise NumpyPlyError("UNSUPPORTED_PLY_FORMAT", "invalid PLY magic")
    if "format binary_little_endian 1.0" not in lines:
        raise NumpyPlyError(
            "UNSUPPORTED_PLY_FORMAT", "only binary little-endian PLY is supported"
        )

    elements: list[ElementSpec] = []
    current_name: str | None = None
    current_count = 0
    current_properties: list[tuple[str, np.dtype[Any]]] = []
    current_has_list = False

    def finish_element() -> None:
        nonlocal current_name, current_count, current_properties, current_has_list
        if current_name is not None:
            elements.append(
                ElementSpec(
                    current_name,
                    current_count,
                    tuple(current_properties),
                    current_has_list,
                )
            )
        current_name = None
        current_count = 0
        current_properties = []
        current_has_list = False

    for line in lines[1:]:
        parts = line.split()
        if not parts or parts[0] in {"comment", "obj_info", "format", "end_header"}:
            continue
        if parts[0] == "element":
            finish_element()
            if len(parts) != 3:
                raise NumpyPlyError("UNSUPPORTED_PLY_FORMAT", f"invalid element line: {line}")
            current_name = parts[1]
            try:
                current_count = int(parts[2])
            except ValueError as exc:
                raise NumpyPlyError(
                    "INVALID_VERTEX_COUNT" if current_name == "vertex" else "UNSUPPORTED_PLY_FORMAT",
                    f"invalid element count: {parts[2]}",
                ) from exc
            if current_count < 0:
                raise NumpyPlyError(
                    "INVALID_VERTEX_COUNT" if current_name == "vertex" else "UNSUPPORTED_PLY_FORMAT",
                    f"negative element count: {current_count}",
                )
        elif parts[0] == "property":
            if current_name is None:
                raise NumpyPlyError("UNSUPPORTED_PLY_FORMAT", "property appears before element")
            if len(parts) >= 2 and parts[1] == "list":
                current_has_list = True
                continue
            if len(parts) != 3:
                raise NumpyPlyError("UNSUPPORTED_PLY_FORMAT", f"invalid property line: {line}")
            scalar_type, property_name = parts[1], parts[2]
            if scalar_type not in SCALAR_TYPES:
                if current_name != "vertex" and any(
                    element.name == "vertex" for element in elements
                ):
                    continue
                raise NumpyPlyError(
                    "UNSUPPORTED_SCALAR_TYPE", f"unsupported scalar type: {scalar_type}"
                )
            if property_name in {name for name, _ in current_properties}:
                raise NumpyPlyError(
                    "UNSUPPORTED_PLY_FORMAT", f"duplicate property name: {property_name}"
                )
            current_properties.append((property_name, np.dtype(SCALAR_TYPES[scalar_type])))
    finish_element()
    return body_offset, tuple(elements)


def _validate_exact_equivalence(
    fast_output: tuple[np.ndarray, np.ndarray],
    plyfile_output: tuple[np.ndarray, np.ndarray],
) -> dict[str, Any]:
    fast_positions, fast_colors = fast_output
    reference_positions, reference_colors = plyfile_output
    if fast_positions.shape != reference_positions.shape:
        raise NumpyPlyError("UNSUPPORTED_PLY_FORMAT", "point count mismatch")
    if fast_positions.dtype != np.float32 or fast_colors.dtype != np.uint8:
        raise NumpyPlyError("UNSUPPORTED_PLY_FORMAT", "canonical dtype mismatch")
    if not fast_positions.flags.owndata or not fast_colors.flags.owndata:
        raise NumpyPlyError("UNSUPPORTED_PLY_FORMAT", "canonical arrays must own memory")
    if not np.allclose(fast_positions, reference_positions, rtol=1e-6, atol=1e-5):
        raise NumpyPlyError("UNSUPPORTED_PLY_FORMAT", "coordinate mismatch")
    if not np.array_equal(fast_colors, reference_colors):
        raise NumpyPlyError("UNSUPPORTED_PLY_FORMAT", "RGB mismatch")
    return {
        "status": "passed",
        "point_count": int(fast_positions.shape[0]),
        "positions_dtype": str(fast_positions.dtype),
        "colors_dtype": str(fast_colors.dtype),
        "rgb_exact": True,
        "arrays_own_memory": True,
    }


def _classify_alignment_gate(records: list[dict[str, Any]]) -> dict[str, Any]:
    correctness_pass_count = sum(
        (record.get("correctness") or {}).get("status") == "passed" for record in records
    )
    speedup_pass_count = sum(
        record.get("numpy_over_plyfile_p50_ratio") is not None
        and float(record["numpy_over_plyfile_p50_ratio"]) <= 0.2
        for record in records
    )
    passed = (
        len(records) == 4
        and correctness_pass_count == 4
        and speedup_pass_count >= 3
        and all(record.get("status") == "success" for record in records)
    )
    return {
        "status": "passed" if passed else "failed",
        "correctness_pass_count": correctness_pass_count,
        "speedup_threshold": "numpy p50 <= plyfile p50 / 5",
        "speedup_pass_count": speedup_pass_count,
        "required_speedup_pass_count": 3,
        "formal_processor_uses_bytes_only": True,
        "formal_processor_performs_file_io": False,
        "formal_processor_uses_path_api": False,
    }


def _alignment_base_record(candidate: dict[str, Any]) -> dict[str, Any]:
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
        raise NumpyPlyError("UNSUPPORTED_PLY_FORMAT", "candidate asset_ref is missing")
    relative = Path(asset_ref)
    if relative.is_absolute():
        raise NumpyPlyError("UNSUPPORTED_PLY_FORMAT", "candidate asset_ref must be relative")
    resolved = (root / relative).resolve()
    if root != resolved and root not in resolved.parents:
        raise NumpyPlyError("UNSUPPORTED_PLY_FORMAT", "asset_ref resolves outside data-prep root")
    return resolved


def _validate_environment(snapshot: dict[str, str]) -> None:
    expected = {
        "python_version": "3.13.",
        "numpy_version": "2.5.1",
        "dracopy_version": "2.0.0",
        "plyfile_version": "1.1.4",
    }
    for field, expected_value in expected.items():
        actual = snapshot.get(field, "")
        valid = actual.startswith(expected_value) if field == "python_version" else actual == expected_value
        if not valid:
            raise NumpyPlyError(
                "UNSUPPORTED_PLY_FORMAT",
                f"environment mismatch for {field}: expected={expected_value}, actual={actual}",
            )


def _package_version(package_name: str) -> str:
    try:
        return version(package_name)
    except PackageNotFoundError:
        return "unavailable"


def _default_run_id(prefix: str) -> str:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"{prefix}_{timestamp}"


__all__ = [
    "ALLOCATION_USE_SCOPE",
    "CALIBRATION_ID",
    "ENVIRONMENT_ID",
    "HANDOFF_ID",
    "MEASUREMENT_SCOPE",
    "NumpyPlyError",
    "allocation_release_status",
    "audit_numpy_alignment_gate",
    "audit_numpy_v2_smoke",
    "parse_binary_ply_numpy",
    "run_numpy_ply_alignment",
    "run_python_numpy_v2_pilot",
    "select_alignment_candidates",
    "write_numpy_alignment",
]
