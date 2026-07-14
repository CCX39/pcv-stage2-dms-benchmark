from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import pcv_dms_benchmark.numpy_ply_backend as numpy_backend
from pcv_dms_benchmark.calibration import calibrate_models
from pcv_dms_benchmark.derived_export import build_derived_handoff
from pcv_dms_benchmark.numpy_ply_backend import (
    ALLOCATION_USE_SCOPE,
    CALIBRATION_ID,
    ENVIRONMENT_ID,
    HANDOFF_ID,
    MEASUREMENT_SCOPE,
    NumpyPlyError,
    parse_binary_ply_numpy,
)
from tests.test_open3d_python_backend import _v2_pilot_and_inventory


TYPE_DTYPES = {
    "uchar": "u1",
    "ushort": "<u2",
    "float": "<f4",
    "double": "<f8",
}


def synthetic_ply(
    *,
    line_ending: str = "\n",
    properties: list[tuple[str, str]] | None = None,
    ascii_format: bool = False,
) -> bytes:
    properties = properties or [
        ("float", "x"),
        ("float", "y"),
        ("float", "z"),
        ("uchar", "red"),
        ("uchar", "green"),
        ("uchar", "blue"),
    ]
    lines = [
        "ply",
        "format ascii 1.0" if ascii_format else "format binary_little_endian 1.0",
        "element vertex 2",
        *(f"property {scalar_type} {name}" for scalar_type, name in properties),
        "end_header",
        "",
    ]
    header = line_ending.join(lines).encode("ascii")
    if ascii_format:
        return header + b"1 2 3 10 20 30\n4 5 6 40 50 60\n"
    dtype = np.dtype([(name, TYPE_DTYPES[scalar_type]) for scalar_type, name in properties])
    rows = np.zeros(2, dtype=dtype)
    values = {
        "x": [1.0, 4.0],
        "y": [2.0, 5.0],
        "z": [3.0, 6.0],
        "red": [10, 40],
        "green": [20, 50],
        "blue": [30, 60],
    }
    for name in rows.dtype.names or ():
        rows[name] = values.get(name, [0, 0])
    return header + rows.tobytes()


class NumpyPlyBackendTest(unittest.TestCase):
    def test_binary_little_endian_bytes_produce_canonical_arrays(self) -> None:
        positions, colors = parse_binary_ply_numpy(synthetic_ply())
        self.assertEqual(positions.dtype, np.float32)
        self.assertEqual(colors.dtype, np.uint8)
        self.assertEqual(positions.shape, (2, 3))
        self.assertEqual(colors.shape, (2, 3))
        self.assertTrue(positions.flags.owndata)
        self.assertTrue(colors.flags.owndata)
        np.testing.assert_array_equal(colors, [[10, 20, 30], [40, 50, 60]])

    def test_lf_and_crlf_headers(self) -> None:
        lf = parse_binary_ply_numpy(synthetic_ply(line_ending="\n"))
        crlf = parse_binary_ply_numpy(synthetic_ply(line_ending="\r\n"))
        np.testing.assert_array_equal(lf[0], crlf[0])
        np.testing.assert_array_equal(lf[1], crlf[1])

    def test_property_order_is_dynamic(self) -> None:
        properties = [
            ("uchar", "blue"),
            ("double", "z"),
            ("uchar", "red"),
            ("float", "x"),
            ("uchar", "green"),
            ("double", "y"),
        ]
        positions, colors = parse_binary_ply_numpy(synthetic_ply(properties=properties))
        np.testing.assert_allclose(positions, [[1, 2, 3], [4, 5, 6]])
        np.testing.assert_array_equal(colors, [[10, 20, 30], [40, 50, 60]])

    def test_float64_xyz_converts_to_float32(self) -> None:
        properties = [
            ("double", "x"),
            ("double", "y"),
            ("double", "z"),
            ("uchar", "red"),
            ("uchar", "green"),
            ("uchar", "blue"),
        ]
        positions, _ = parse_binary_ply_numpy(synthetic_ply(properties=properties))
        self.assertEqual(positions.dtype, np.float32)
        np.testing.assert_allclose(positions, [[1, 2, 3], [4, 5, 6]])

    def test_ascii_is_rejected(self) -> None:
        with self.assertRaisesRegex(NumpyPlyError, "UNSUPPORTED_PLY_FORMAT"):
            parse_binary_ply_numpy(synthetic_ply(ascii_format=True))

    def test_end_header_text_in_comment_is_not_body_boundary(self) -> None:
        payload = synthetic_ply().replace(
            b"format binary_little_endian 1.0\n",
            b"format binary_little_endian 1.0\ncomment end_header is only text\n",
        )
        positions, colors = parse_binary_ply_numpy(payload)
        self.assertEqual(positions.shape, colors.shape)

    def test_missing_required_property_is_rejected(self) -> None:
        properties = [
            ("float", "x"),
            ("float", "y"),
            ("float", "z"),
            ("uchar", "red"),
            ("uchar", "green"),
        ]
        with self.assertRaisesRegex(NumpyPlyError, "REQUIRED_PROPERTY_MISSING"):
            parse_binary_ply_numpy(synthetic_ply(properties=properties))

    def test_vertex_list_property_is_rejected(self) -> None:
        payload = synthetic_ply()
        payload = payload.replace(
            b"property float x\n", b"property list uchar int weights\nproperty float x\n"
        )
        with self.assertRaisesRegex(NumpyPlyError, "VERTEX_LIST_PROPERTY_UNSUPPORTED"):
            parse_binary_ply_numpy(payload)

    def test_non_uint8_rgb_is_rejected(self) -> None:
        properties = [
            ("float", "x"),
            ("float", "y"),
            ("float", "z"),
            ("ushort", "red"),
            ("uchar", "green"),
            ("uchar", "blue"),
        ]
        with self.assertRaisesRegex(NumpyPlyError, "INVALID_RGB_TYPE"):
            parse_binary_ply_numpy(synthetic_ply(properties=properties))

    def test_elements_after_vertex_are_not_read_as_vertices(self) -> None:
        payload = synthetic_ply()
        marker = b"end_header\n"
        payload = payload.replace(
            marker,
            b"element face 1\nproperty list uchar int vertex_indices\n" + marker,
        )
        payload += b"\x03\x00\x00\x00\x00\x01\x00\x00\x00\x02\x00\x00\x00"
        positions, colors = parse_binary_ply_numpy(payload)
        self.assertEqual(positions.shape, (2, 3))
        np.testing.assert_array_equal(colors, [[10, 20, 30], [40, 50, 60]])

    def test_truncated_payload_is_rejected(self) -> None:
        with self.assertRaisesRegex(NumpyPlyError, "TRUNCATED_VERTEX_PAYLOAD"):
            parse_binary_ply_numpy(synthetic_ply()[:-1])

    def test_processor_does_not_read_files(self) -> None:
        with patch.object(Path, "read_bytes", side_effect=AssertionError("file read forbidden")):
            positions, colors = parse_binary_ply_numpy(memoryview(synthetic_ply()))
        self.assertEqual(positions.shape, colors.shape)

    def test_four_candidate_gate_requires_three_five_x_speedups(self) -> None:
        records = [
            {
                "status": "success",
                "correctness": {"status": "passed"},
                "numpy_over_plyfile_p50_ratio": ratio,
            }
            for ratio in (0.10, 0.15, 0.20, 0.30)
        ]
        self.assertEqual(numpy_backend._classify_alignment_gate(records)["status"], "passed")
        records[2]["numpy_over_plyfile_p50_ratio"] = 0.21
        self.assertEqual(numpy_backend._classify_alignment_gate(records)["status"], "failed")

    def test_numpy_v2_handoff_covers_800_without_touching_v1(self) -> None:
        pilot, inventory = _v2_pilot_and_inventory()
        pilot["environment_id"] = ENVIRONMENT_ID
        pilot["measurement_scope"] = MEASUREMENT_SCOPE
        for record in pilot["results"]:
            record["measurement_scope"] = MEASUREMENT_SCOPE
        with tempfile.TemporaryDirectory() as directory:
            v1 = Path(directory) / "python_frame1051_measured_summary_v1.json"
            v1.write_bytes(b"v1-sentinel")
            calibration = calibrate_models(
                pilot,
                inventory,
                source_pilot_sha256="NUMPY-V2",
                source_inventory_sha256="INVENTORY",
                calibration_id=CALIBRATION_ID,
                expected_environment_id=ENVIRONMENT_ID,
                expected_measurement_scope=MEASUREMENT_SCOPE,
                allocation_use_scope=ALLOCATION_USE_SCOPE,
                profile_limitation="synthetic NumPy v2 profile",
                delivery_version="v2",
            )
            handoff = build_derived_handoff(
                inventory,
                calibration,
                expected_representation_counts={"ply": 200, "drc": 600},
                handoff_id=HANDOFF_ID,
                allocation_use_scope=ALLOCATION_USE_SCOPE,
                delivery_version="v2",
            )
            self.assertEqual(v1.read_bytes(), b"v1-sentinel")
        self.assertEqual(handoff["candidate_count"], 800)
        self.assertEqual(len({item["candidate_key"] for item in handoff["candidates"]}), 800)
        self.assertTrue(all(item["provenance"] == "derived" for item in handoff["candidates"]))


if __name__ == "__main__":
    unittest.main()
