from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _path_from_env(name: str, default: str) -> Path:
    return Path(os.getenv(name, default)).expanduser()


def _bool_from_env(name: str, default: str = "0") -> bool:
    return os.getenv(name, default).strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    host: str = os.getenv("ESP_UPGRADE_HOST", "0.0.0.0")
    port: int = int(os.getenv("ESP_UPGRADE_PORT", "8010"))
    base_dir: Path = _path_from_env("ESP_UPGRADE_BASE_DIR", "./var")
    repo_url: str = os.getenv("ESP_UPGRADE_REPO_URL", "").strip()
    repo_branch: str = os.getenv("ESP_UPGRADE_REPO_BRANCH", "").strip()
    source_dir: Path = _path_from_env(
        "ESP_UPGRADE_SOURCE_DIR",
        str(_path_from_env("ESP_UPGRADE_BASE_DIR", "./var") / "source"),
    )
    build_command: str = os.getenv("ESP_UPGRADE_BUILD_COMMAND", "").strip()
    build_workdir: Path = _path_from_env(
        "ESP_UPGRADE_BUILD_WORKDIR",
        str(_path_from_env("ESP_UPGRADE_SOURCE_DIR", str(_path_from_env("ESP_UPGRADE_BASE_DIR", "./var") / "source"))),
    )
    build_script: Path = _path_from_env(
        "ESP_UPGRADE_BUILD_SCRIPT",
        "/root/codebase/esp32/projects/fetch_build_lula_esp32.sh",
    )
    build_script_workdir: Path = _path_from_env(
        "ESP_UPGRADE_BUILD_SCRIPT_WORKDIR",
        "/root/codebase/esp32/projects",
    )
    build_incremental_arg: str = os.getenv("ESP_UPGRADE_BUILD_INCREMENTAL_ARG", "--incremental").strip()
    build_full_arg: str = os.getenv("ESP_UPGRADE_BUILD_FULL_ARG", "--full").strip()
    firmware_path: str = os.getenv("ESP_UPGRADE_FIRMWARE_PATH", "").strip()
    upgrade_command: str = os.getenv("ESP_UPGRADE_UPGRADE_COMMAND", "").strip()
    max_log_lines: int = int(os.getenv("ESP_UPGRADE_MAX_LOG_LINES", "3000"))
    ota_public_base_url: str = os.getenv("ESP_OTA_PUBLIC_BASE_URL", "http://14.103.183.47:8010").strip().rstrip("/")
    ota_latest_version: str = os.getenv("ESP_OTA_LATEST_VERSION", "").strip()
    ota_firmware_dir: Path = _path_from_env("ESP_OTA_FIRMWARE_DIR", "/codebase/upgrade_linux/firmwares")
    ota_firmware_file: str = os.getenv("ESP_OTA_FIRMWARE_FILE", "xiaozhi.bin").strip()
    ota_force: bool = _bool_from_env("ESP_OTA_FORCE", "0")
    ota_log_body: bool = _bool_from_env("ESP_OTA_LOG_BODY", "1")


settings = Settings()
