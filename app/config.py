from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    bambu_host: str = Field(alias="BAMBU_HOST")
    bambu_serial: str = Field(alias="BAMBU_SERIAL")
    bambu_access_code: str = Field(alias="BAMBU_ACCESS_CODE")
    bambu_mqtt_port: int = Field(default=8883, alias="BAMBU_MQTT_PORT")
    bambu_ftps_port: int = Field(default=990, alias="BAMBU_FTPS_PORT")
    bambu_connect_cmd: str | None = Field(default=None, alias="BAMBU_CONNECT_CMD")

    default_infill_density: int = Field(default=15, alias="DEFAULT_INFILL_DENSITY")
    default_wall_loops: int = Field(default=2, alias="DEFAULT_WALL_LOOPS")
    default_plate_index: int = Field(default=1, alias="DEFAULT_PLATE_INDEX")

    slicer_bin: Path = Field(default=Path("/slicer/BambuStudio.AppImage"), alias="SLICER_BIN")
    slicer_use_xvfb: bool = Field(default=True, alias="SLICER_USE_XVFB")
    slicer_plate_index: int = Field(default=0, alias="SLICER_PLATE_INDEX")
    slicer_timeout_seconds: int = Field(default=900, alias="SLICER_TIMEOUT_SECONDS")
    machine_profile: Path = Field(default=Path("/config/machine.json"), alias="MACHINE_PROFILE")
    process_profile: Path = Field(default=Path("/config/process.json"), alias="PROCESS_PROFILE")
    filament_profile_dir: Path = Field(default=Path("/config/filaments"), alias="FILAMENT_PROFILE_DIR")
    fallback_filament_profile: Path = Field(
        default=Path("/config/filaments/generic.json"),
        alias="FALLBACK_FILAMENT_PROFILE",
    )

    upload_dir: Path = Path("/data/uploads")
    job_dir: Path = Path("/data/jobs")


@lru_cache
def get_settings() -> Settings:
    return Settings()
