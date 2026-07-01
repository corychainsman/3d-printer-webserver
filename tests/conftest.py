import io
import struct
from pathlib import Path

import pytest
from fastapi import UploadFile

from app.config import Settings


@pytest.fixture
def settings_factory(tmp_path):
    def factory(**overrides):
        root = tmp_path / f"settings-{len(list(tmp_path.glob('settings-*')))}"
        root.mkdir()
        config_dir = root / "config"
        filament_dir = config_dir / "filaments"
        data_dir = root / "data"
        slicer_dir = root / "slicer"
        for directory in (config_dir, filament_dir, data_dir, slicer_dir):
            directory.mkdir(parents=True, exist_ok=True)

        slicer_bin = slicer_dir / "BambuStudio.AppImage"
        machine_profile = config_dir / "machine.json"
        process_profile = config_dir / "process.json"
        fallback_filament = filament_dir / "generic.json"
        for path in (slicer_bin, machine_profile, process_profile, fallback_filament):
            path.write_text("{}", encoding="utf-8")

        values = {
            "BAMBU_HOST": "printer.local",
            "BAMBU_SERIAL": "SERIAL123",
            "BAMBU_ACCESS_CODE": "LAN-CODE",
            "SLICER_BIN": slicer_bin,
            "SLICER_USE_XVFB": False,
            "SLICER_PLATE_INDEX": 0,
            "SLICER_TIMEOUT_SECONDS": 60,
            "MACHINE_PROFILE": machine_profile,
            "PROCESS_PROFILE": process_profile,
            "FILAMENT_PROFILE_DIR": filament_dir,
            "FALLBACK_FILAMENT_PROFILE": fallback_filament,
            "upload_dir": data_dir / "uploads",
            "job_dir": data_dir / "jobs",
        }
        values.update(overrides)
        return Settings(**values)

    return factory


@pytest.fixture
def settings(settings_factory):
    return settings_factory()


def upload_file(filename: str, content: bytes = b"solid test\nendsolid test\n") -> UploadFile:
    return UploadFile(filename=filename, file=io.BytesIO(content))


def ascii_stl(vertices=None) -> str:
    vertices = vertices or [(0.0, 0.0, -2.0), (10.0, 0.0, 1.0), (0.0, 10.0, 3.0)]
    lines = ["solid test", "  facet normal 0 0 1", "    outer loop"]
    for x, y, z in vertices:
        lines.append(f"      vertex {x} {y} {z}")
    lines += ["    endloop", "  endfacet", "endsolid test"]
    return "\n".join(lines) + "\n"


def binary_stl(
    vertices=((0.0, 0.0, -3.0), (10.0, 0.0, 1.0), (0.0, 10.0, 2.0)),
    attr: int = 7,
) -> bytes:
    header = b"unit-test".ljust(80, b"\0")
    output = bytearray(header + struct.pack("<I", 1))
    output += struct.pack("<fff", 0.0, 0.0, 1.0)
    for point in vertices:
        output += struct.pack("<fff", *point)
    output += struct.pack("<H", attr)
    return bytes(output)


def binary_vertices(data: bytes):
    count = struct.unpack_from("<I", data, 80)[0]
    vertices = []
    offset = 84
    attrs = []
    for _ in range(count):
        for vertex_index in range(3):
            vertices.append(struct.unpack_from("<fff", data, offset + 12 + vertex_index * 12))
        attrs.append(struct.unpack_from("<H", data, offset + 48)[0])
        offset += 50
    return vertices, attrs


def status_payload(state: str = "IDLE", units=None):
    units = units if units is not None else [
        {
            "id": "0",
            "tray": [
                {"id": "0", "tray_type": "PLA", "tray_color": "F7D959FF"},
                {"id": "1", "tray_type": "", "tray_sub_brands": "PETG", "tray_color": "FFFFFFFF"},
            ],
        },
        {
            "id": "1",
            "tray": [
                {"id": "0", "tray_type": "ABS", "tray_color": None},
            ],
        },
    ]
    return {"print": {"gcode_state": state, "ams": {"ams": units}}}
