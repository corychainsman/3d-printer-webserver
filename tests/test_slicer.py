import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from app import slicer
from app.slicer import SlicerError, StlInput, filament_profile_for, slice_stls, validate_slicer_inputs


def test_filament_profile_for_checks_exact_lowercase_underscore_then_fallback(settings):
    (settings.filament_profile_dir / "PLA.json").write_text("{}", encoding="utf-8")
    (settings.filament_profile_dir / "petg.json").write_text("{}", encoding="utf-8")
    (settings.filament_profile_dir / "Carbon_Fiber.json").write_text("{}", encoding="utf-8")

    assert filament_profile_for(settings, "PLA") == settings.filament_profile_dir / "PLA.json"
    assert filament_profile_for(settings, "PETG") == settings.filament_profile_dir / "petg.json"
    assert filament_profile_for(settings, "Carbon Fiber") == settings.filament_profile_dir / "Carbon_Fiber.json"
    assert filament_profile_for(settings, "TPU") == settings.fallback_filament_profile


def test_validate_slicer_inputs_reports_missing_paths(settings):
    settings.slicer_bin.unlink()

    with pytest.raises(SlicerError) as exc:
        validate_slicer_inputs(settings, settings.fallback_filament_profile)

    assert str(settings.slicer_bin) in str(exc.value)


def test_slice_stls_rejects_empty_input(settings):
    with pytest.raises(SlicerError, match="At least one STL"):
        slice_stls(settings, [], "PLA", infill_density=15, wall_loops=2)


def test_slice_stls_duplicates_inputs_and_builds_expected_command(settings, monkeypatch, tmp_path):
    stl_a = tmp_path / "weird name.stl"
    stl_b = tmp_path / "part.stl"
    stl_a.write_bytes(b"aaa")
    stl_b.write_bytes(b"bbb")
    calls = []

    def fake_run(command, cwd, env, text, stdout, stderr, timeout, check):
        calls.append(
            {
                "command": command,
                "cwd": cwd,
                "env": env,
                "text": text,
                "stdout": stdout,
                "stderr": stderr,
                "timeout": timeout,
                "check": check,
            }
        )
        output_path = Path(command[command.index("--export-3mf") + 1])
        output_path.write_bytes(b"3mf")
        return SimpleNamespace(returncode=0, stdout="ok")

    monkeypatch.setattr(slicer.subprocess, "run", fake_run)

    project = slice_stls(
        settings,
        [
            StlInput(path=stl_a, original_filename="weird name.stl", copy_count=2),
            StlInput(path=stl_b, original_filename="../part.stl", copy_count=1),
        ],
        "missing-profile",
        infill_density=23,
        wall_loops=4,
    )

    command = calls[0]["command"]
    input_paths = command[command.index(str(project)) + 1 :]
    assert project.name == "arranged-plate.3mf"
    assert calls[0]["cwd"] == project.parent
    assert calls[0]["env"]["APPIMAGE_EXTRACT_AND_RUN"] == "1"
    assert calls[0]["timeout"] == settings.slicer_timeout_seconds
    assert "--arrange" in command
    load_settings = command[command.index("--load-settings") + 1]
    machine_profile, process_profile = load_settings.split(";")
    assert machine_profile == str(settings.machine_profile)
    assert Path(process_profile).name == "process-overrides.json"
    process_settings = json.loads(Path(process_profile).read_text(encoding="utf-8"))
    assert process_settings["sparse_infill_density"] == "23%"
    assert process_settings["wall_loops"] == "4"
    assert str(settings.fallback_filament_profile) in command
    assert "--slice" in command
    assert "--export-3mf" in command
    assert len(input_paths) == 3
    assert [Path(path).name for path in input_paths] == [
        "01-weird-name-copy-01.stl",
        "01-weird-name-copy-02.stl",
        "02-part-copy-01.stl",
    ]
    assert [Path(path).read_bytes() for path in input_paths] == [b"aaa", b"aaa", b"bbb"]


def test_slice_stls_writes_h2d_single_material_runtime_machine_profile(settings, monkeypatch, tmp_path):
    settings.machine_profile.write_text(
        json.dumps(
            {
                "type": "machine",
                "name": "Bambu Lab H2D 0.4 nozzle",
                "printer_model": "Bambu Lab H2D",
                "printer_variant": "0.4",
                "nozzle_diameter": ["0.4", "0.4"],
                "printable_area": ["0x0", "350x0", "350x320", "0x320"],
                "extruder_printable_area": [
                    "0x0,325x0,325x320,0x320",
                    "25x0,350x0,350x320,25x320",
                ],
                "extruder_printable_height": ["320", "325"],
                "printer_extruder_variant": ["Direct Drive Standard", "Direct Drive High Flow"],
                "include": ["Bambu Lab H2D 0.4 nozzle template machine_start_gcode"],
            }
        ),
        encoding="utf-8",
    )
    (settings.machine_profile.parent / "Bambu Lab H2D 0.4 nozzle template machine_start_gcode.json").write_text(
        json.dumps(
            {
                "name": "Bambu Lab H2D 0.4 nozzle template machine_start_gcode",
                "machine_start_gcode": "H2D start",
            }
        ),
        encoding="utf-8",
    )
    stl = tmp_path / "part.stl"
    stl.write_bytes(b"part")
    calls = []

    def fake_run(command, cwd, env, text, stdout, stderr, timeout, check):
        calls.append(command)
        Path(command[command.index("--export-3mf") + 1]).write_bytes(b"3mf")
        return SimpleNamespace(returncode=0, stdout="ok")

    monkeypatch.setattr(slicer.subprocess, "run", fake_run)

    slice_stls(settings, [StlInput(stl, "part.stl", 1)], "PLA", 15, 2)

    load_settings = calls[0][calls[0].index("--load-settings") + 1]
    machine_profile, _process_profile = load_settings.split(";")
    machine_settings = json.loads(Path(machine_profile).read_text(encoding="utf-8"))
    assert Path(machine_profile).name == "machine-runtime.json"
    assert machine_settings["name"] == "Bambu Lab H2D 0.4 nozzle"
    assert machine_settings["machine_start_gcode"] == "H2D start"
    assert machine_settings["nozzle_diameter"] == ["0.4"]
    assert machine_settings["extruder_printable_area"] == ["25x0,325x0,325x320,25x320"]
    assert machine_settings["printer_extruder_id"] == ["1"]
    assert machine_settings["physical_extruder_map"] == ["0"]
    assert machine_settings["master_extruder_id"] == "1"


def test_slice_stls_prepends_xvfb_when_enabled(settings, monkeypatch, tmp_path):
    settings.slicer_use_xvfb = True
    stl = tmp_path / "part.stl"
    stl.write_bytes(b"part")
    commands = []

    def fake_run(command, cwd, env, text, stdout, stderr, timeout, check):
        commands.append(command)
        Path(command[command.index("--export-3mf") + 1]).write_bytes(b"3mf")
        return SimpleNamespace(returncode=0, stdout="ok")

    monkeypatch.setattr(slicer.subprocess, "run", fake_run)

    slice_stls(settings, [StlInput(stl, "part.stl", 1)], "PLA", 15, 2)

    assert commands[0][:2] == ["xvfb-run", "-a"]


def test_slice_stls_raises_with_command_and_tail_output_on_failure(settings, monkeypatch, tmp_path):
    stl = tmp_path / "part.stl"
    stl.write_bytes(b"part")

    def fake_run(command, cwd, env, text, stdout, stderr, timeout, check):
        return SimpleNamespace(returncode=2, stdout="failure output")

    monkeypatch.setattr(slicer.subprocess, "run", fake_run)

    with pytest.raises(SlicerError) as exc:
        slice_stls(settings, [StlInput(stl, "part.stl", 1)], "PLA", 15, 2)

    message = str(exc.value)
    assert "Slicer failed with exit 2" in message
    assert "process-overrides.json" in message
    assert "failure output" in message
