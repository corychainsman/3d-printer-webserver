import math
import struct
from pathlib import Path


def _rotation_matrix(rx_deg: float, ry_deg: float, rz_deg: float) -> tuple[tuple[float, float, float], ...]:
    rx = math.radians(rx_deg)
    ry = math.radians(ry_deg)
    rz = math.radians(rz_deg)
    sx, cx = math.sin(rx), math.cos(rx)
    sy, cy = math.sin(ry), math.cos(ry)
    sz, cz = math.sin(rz), math.cos(rz)
    return (
        (cz * cy, cz * sy * sx - sz * cx, cz * sy * cx + sz * sx),
        (sz * cy, sz * sy * sx + cz * cx, sz * sy * cx - cz * sx),
        (-sy, cy * sx, cy * cx),
    )


def _apply(point: tuple[float, float, float], matrix: tuple[tuple[float, float, float], ...]) -> tuple[float, float, float]:
    x, y, z = point
    return (
        matrix[0][0] * x + matrix[0][1] * y + matrix[0][2] * z,
        matrix[1][0] * x + matrix[1][1] * y + matrix[1][2] * z,
        matrix[2][0] * x + matrix[2][1] * y + matrix[2][2] * z,
    )


def _normal(a: tuple[float, float, float], b: tuple[float, float, float], c: tuple[float, float, float]) -> tuple[float, float, float]:
    ux, uy, uz = b[0] - a[0], b[1] - a[1], b[2] - a[2]
    vx, vy, vz = c[0] - a[0], c[1] - a[1], c[2] - a[2]
    nx, ny, nz = uy * vz - uz * vy, uz * vx - ux * vz, ux * vy - uy * vx
    length = math.sqrt(nx * nx + ny * ny + nz * nz)
    if length == 0:
        return (0.0, 0.0, 0.0)
    return (nx / length, ny / length, nz / length)


def _is_binary_stl(data: bytes) -> bool:
    if len(data) < 84:
        return False
    count = struct.unpack_from("<I", data, 80)[0]
    return 84 + count * 50 == len(data)


def rotate_and_place_on_bed(source: Path, destination: Path, rx: float, ry: float, rz: float) -> None:
    data = source.read_bytes()
    matrix = _rotation_matrix(rx, ry, rz)
    if _is_binary_stl(data):
        _transform_binary(data, destination, matrix)
        return
    _transform_ascii(data, destination, matrix)


def _transform_binary(data: bytes, destination: Path, matrix: tuple[tuple[float, float, float], ...]) -> None:
    count = struct.unpack_from("<I", data, 80)[0]
    triangles: list[tuple[tuple[float, float, float], tuple[float, float, float], tuple[float, float, float], int]] = []
    min_z = float("inf")
    offset = 84
    for _ in range(count):
        vertices = []
        for vertex_index in range(3):
            point_offset = offset + 12 + vertex_index * 12
            point = struct.unpack_from("<fff", data, point_offset)
            transformed = _apply(point, matrix)
            min_z = min(min_z, transformed[2])
            vertices.append(transformed)
        attr = struct.unpack_from("<H", data, offset + 48)[0]
        triangles.append((vertices[0], vertices[1], vertices[2], attr))
        offset += 50

    z_shift = -min_z if min_z != float("inf") else 0.0
    header = data[:80]
    output = bytearray(header + struct.pack("<I", count))
    for a, b, c, attr in triangles:
        shifted = ((a[0], a[1], a[2] + z_shift), (b[0], b[1], b[2] + z_shift), (c[0], c[1], c[2] + z_shift))
        output += struct.pack("<fff", *_normal(*shifted))
        for point in shifted:
            output += struct.pack("<fff", *point)
        output += struct.pack("<H", attr)
    destination.write_bytes(output)


def _transform_ascii(data: bytes, destination: Path, matrix: tuple[tuple[float, float, float], ...]) -> None:
    text = data.decode("utf-8", errors="replace")
    points: list[tuple[float, float, float]] = []
    for line in text.splitlines():
        parts = line.strip().split()
        if len(parts) == 4 and parts[0].lower() == "vertex":
            points.append(_apply((float(parts[1]), float(parts[2]), float(parts[3])), matrix))

    min_z = min((point[2] for point in points), default=0.0)
    z_shift = -min_z
    output = ["solid transformed"]
    for index in range(0, len(points), 3):
        if index + 2 >= len(points):
            break
        tri = tuple((x, y, z + z_shift) for x, y, z in points[index : index + 3])
        output.append("  facet normal %.7g %.7g %.7g" % _normal(*tri))
        output.append("    outer loop")
        for point in tri:
            output.append("      vertex %.7g %.7g %.7g" % point)
        output.append("    endloop")
        output.append("  endfacet")
    output.append("endsolid transformed")
    destination.write_text("\n".join(output) + "\n", encoding="utf-8")
