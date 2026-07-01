import math
import struct

import pytest

from app.stl_transform import rotate_and_place_on_bed
from tests.conftest import ascii_stl, binary_stl, binary_vertices


def _ascii_vertices(path):
    vertices = []
    for line in path.read_text(encoding="utf-8").splitlines():
        parts = line.strip().split()
        if len(parts) == 4 and parts[0] == "vertex":
            vertices.append(tuple(float(value) for value in parts[1:]))
    return vertices


def test_rotate_and_place_on_bed_ascii_shifts_lowest_point_to_zero(tmp_path):
    source = tmp_path / "source.stl"
    destination = tmp_path / "transformed.stl"
    source.write_text(ascii_stl(), encoding="utf-8")

    rotate_and_place_on_bed(source, destination, rx=0, ry=0, rz=0)

    vertices = _ascii_vertices(destination)
    assert min(point[2] for point in vertices) == pytest.approx(0)
    assert destination.read_text(encoding="utf-8").startswith("solid transformed")


def test_rotate_and_place_on_bed_ascii_applies_rotation_before_bed_shift(tmp_path):
    source = tmp_path / "source.stl"
    destination = tmp_path / "transformed.stl"
    source.write_text(ascii_stl([(0, 0, 0), (0, 1, 0), (0, 0, 1)]), encoding="utf-8")

    rotate_and_place_on_bed(source, destination, rx=90, ry=0, rz=0)

    vertices = _ascii_vertices(destination)
    assert min(point[2] for point in vertices) == pytest.approx(0)
    assert min(point[1] for point in vertices) == pytest.approx(-1)


def test_rotate_and_place_on_bed_binary_shifts_lowest_point_and_preserves_attr(tmp_path):
    source = tmp_path / "source.stl"
    destination = tmp_path / "transformed.stl"
    source.write_bytes(binary_stl(attr=42))

    rotate_and_place_on_bed(source, destination, rx=0, ry=0, rz=0)

    data = destination.read_bytes()
    vertices, attrs = binary_vertices(data)
    assert struct.unpack_from("<I", data, 80)[0] == 1
    assert min(point[2] for point in vertices) == pytest.approx(0)
    assert attrs == [42]


def test_rotate_and_place_on_bed_binary_handles_degenerate_triangle(tmp_path):
    source = tmp_path / "source.stl"
    destination = tmp_path / "transformed.stl"
    source.write_bytes(binary_stl(vertices=((1, 1, -1), (1, 1, -1), (1, 1, -1))))

    rotate_and_place_on_bed(source, destination, rx=0, ry=0, rz=0)

    vertices, _attrs = binary_vertices(destination.read_bytes())
    normal = struct.unpack_from("<fff", destination.read_bytes(), 84)
    assert min(point[2] for point in vertices) == pytest.approx(0)
    assert all(math.isfinite(component) for component in normal)
    assert normal == pytest.approx((0, 0, 0))
