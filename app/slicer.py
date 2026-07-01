import json
import os
import re
import shlex
import subprocess
import uuid
from dataclasses import dataclass
from pathlib import Path

from .config import Settings


class SlicerError(RuntimeError):
    pass


@dataclass(frozen=True)
class StlInput:
    path: Path
    original_filename: str
    copy_count: int


def _safe_stem(name: str) -> str:
    stem = Path(name).stem
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "-", stem).strip(".-")
    return cleaned or "model"


def filament_profile_for(settings: Settings, filament_type: str) -> Path:
    candidates = [
        settings.filament_profile_dir / f"{filament_type}.json",
        settings.filament_profile_dir / f"{filament_type.lower()}.json",
        settings.filament_profile_dir / f"{filament_type.replace(' ', '_')}.json",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return settings.fallback_filament_profile


def validate_slicer_inputs(settings: Settings, filament_profile: Path) -> None:
    missing = [
        path
        for path in [
            settings.slicer_bin,
            settings.machine_profile,
            settings.process_profile,
            filament_profile,
        ]
        if not path.exists()
    ]
    if missing:
        joined = ", ".join(str(path) for path in missing)
        raise SlicerError(f"Missing slicer input(s): {joined}")


def _first_config_value(config: dict, key: str, default: str) -> str:
    value = config.get(key)
    if isinstance(value, list) and value:
        return str(value[0])
    if value not in (None, ""):
        return str(value)
    return default


def _format_point(value: float) -> str:
    return f"{value:g}"


def _parse_points(area: str) -> list[tuple[float, float]]:
    points = []
    for token in area.split(","):
        x_text, separator, y_text = token.strip().partition("x")
        if not separator:
            return []
        try:
            points.append((float(x_text), float(y_text)))
        except ValueError:
            return []
    return points


def _area_from_printable_area(config: dict) -> str:
    printable_area = config.get("printable_area")
    if isinstance(printable_area, list) and printable_area:
        return ",".join(str(point) for point in printable_area)
    if printable_area:
        return str(printable_area)
    return "0x0,350x0,350x320,0x320"


def _shared_extruder_area(config: dict) -> str:
    areas = config.get("extruder_printable_area")
    if not isinstance(areas, list) or len(areas) < 2:
        return _area_from_printable_area(config)

    rectangles = []
    for area in areas:
        points = _parse_points(str(area))
        if len(points) < 4:
            return _area_from_printable_area(config)
        xs = [point[0] for point in points]
        ys = [point[1] for point in points]
        rectangles.append((min(xs), min(ys), max(xs), max(ys)))

    min_x = max(rectangle[0] for rectangle in rectangles)
    min_y = max(rectangle[1] for rectangle in rectangles)
    max_x = min(rectangle[2] for rectangle in rectangles)
    max_y = min(rectangle[3] for rectangle in rectangles)
    if min_x >= max_x or min_y >= max_y:
        return _area_from_printable_area(config)
    return ",".join(
        [
            f"{_format_point(min_x)}x{_format_point(min_y)}",
            f"{_format_point(max_x)}x{_format_point(min_y)}",
            f"{_format_point(max_x)}x{_format_point(max_y)}",
            f"{_format_point(min_x)}x{_format_point(max_y)}",
        ]
    )


def _merge_local_machine_includes(machine_profile: Path, config: dict) -> dict:
    merged = dict(config)
    includes = config.get("include")
    if not isinstance(includes, list):
        return merged

    for include in includes:
        include_path = machine_profile.parent / f"{include}.json"
        if not include_path.exists():
            continue
        try:
            include_config = json.loads(include_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        for key, value in include_config.items():
            if key not in {"name", "instantiation"}:
                merged.setdefault(key, value)
    return merged


def runtime_machine_profile_for(settings: Settings, output_dir: Path) -> Path:
    try:
        config = json.loads(settings.machine_profile.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SlicerError(f"Invalid machine profile JSON: {settings.machine_profile}") from exc

    printer_model = str(config.get("printer_model") or config.get("name") or "")
    nozzle_count = len(config.get("nozzle_diameter") or [])
    if "H2D" not in printer_model or nozzle_count <= 1:
        return settings.machine_profile

    runtime_config = _merge_local_machine_includes(settings.machine_profile, config)
    extruder_variant = _first_config_value(runtime_config, "printer_extruder_variant", "Direct Drive Standard")
    extruder_variant = extruder_variant.split(",", 1)[0].strip() or "Direct Drive Standard"
    runtime_config.update(
        {
            "nozzle_diameter": [_first_config_value(runtime_config, "nozzle_diameter", "0.4")],
            "default_nozzle_volume_type": [
                _first_config_value(runtime_config, "default_nozzle_volume_type", "Standard")
            ],
            "nozzle_volume_type": [_first_config_value(runtime_config, "nozzle_volume_type", "Standard")],
            "extruder_type": [_first_config_value(runtime_config, "extruder_type", "Direct Drive")],
            "extruder_offset": [_first_config_value(runtime_config, "extruder_offset", "0x0")],
            "extruder_printable_area": [_shared_extruder_area(runtime_config)],
            "extruder_printable_height": [
                _first_config_value(runtime_config, "extruder_printable_height", runtime_config.get("printable_height", "325"))
            ],
            "extruder_variant_list": [extruder_variant],
            "printer_extruder_id": ["1"],
            "printer_extruder_variant": [extruder_variant],
            "physical_extruder_map": ["0"],
            "master_extruder_id": "1",
            "extruder_max_nozzle_count": ["1"],
        }
    )
    runtime_profile = output_dir / "machine-runtime.json"
    runtime_profile.write_text(json.dumps(runtime_config, indent=2) + "\n", encoding="utf-8")
    return runtime_profile


def slice_stls(
    settings: Settings,
    stls: list[StlInput],
    filament_type: str,
    infill_density: int,
    wall_loops: int,
) -> Path:
    if not stls:
        raise SlicerError("At least one STL is required")

    filament_profile = filament_profile_for(settings, filament_type)
    validate_slicer_inputs(settings, filament_profile)

    job_id = uuid.uuid4().hex[:12]
    output_dir = settings.job_dir / job_id
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "arranged-plate.3mf"
    machine_profile = runtime_machine_profile_for(settings, output_dir)
    process_profile = output_dir / "process-overrides.json"
    process_settings = json.loads(settings.process_profile.read_text(encoding="utf-8"))
    process_settings["sparse_infill_density"] = f"{infill_density}%"
    process_settings["wall_loops"] = str(wall_loops)
    process_profile.write_text(json.dumps(process_settings, indent=2) + "\n", encoding="utf-8")
    duplicate_dir = output_dir / "inputs"
    duplicate_dir.mkdir()
    input_paths: list[Path] = []
    for stl_index, stl in enumerate(stls, start=1):
        source_bytes = stl.path.read_bytes()
        safe_name = _safe_stem(stl.original_filename)
        for copy_index in range(1, stl.copy_count + 1):
            duplicate_path = duplicate_dir / f"{stl_index:02d}-{safe_name}-copy-{copy_index:02d}.stl"
            duplicate_path.write_bytes(source_bytes)
            input_paths.append(duplicate_path)

    command = [
        str(settings.slicer_bin),
        "--arrange",
        "1",
        "--load-settings",
        f"{machine_profile};{process_profile}",
        "--load-filaments",
        str(filament_profile),
        "--slice",
        str(settings.slicer_plate_index),
        "--export-3mf",
        str(output_path),
        *[str(path) for path in input_paths],
    ]
    if settings.slicer_use_xvfb:
        command = ["xvfb-run", "-a", *command]

    result = subprocess.run(
        command,
        cwd=output_dir,
        env={**os.environ, "APPIMAGE_EXTRACT_AND_RUN": "1"},
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=settings.slicer_timeout_seconds,
        check=False,
    )
    if result.returncode != 0 or not output_path.exists():
        redacted = " ".join(shlex.quote(part) for part in command)
        raise SlicerError(f"Slicer failed with exit {result.returncode}: {redacted}\n{result.stdout[-4000:]}")
    return output_path


def slice_stl(
    settings: Settings,
    stl_path: Path,
    original_filename: str,
    filament_type: str,
    infill_density: int,
    wall_loops: int,
    copy_count: int,
) -> Path:
    return slice_stls(
        settings=settings,
        stls=[
            StlInput(
                path=stl_path,
                original_filename=original_filename,
                copy_count=copy_count,
            )
        ],
        filament_type=filament_type,
        infill_density=infill_density,
        wall_loops=wall_loops,
    )
