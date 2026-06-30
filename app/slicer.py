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
        str(settings.machine_profile),
        "--load-settings",
        str(settings.process_profile),
        "--load-filaments",
        str(filament_profile),
        f"--sparse_infill_density={infill_density}%",
        f"--wall_loops={wall_loops}",
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
