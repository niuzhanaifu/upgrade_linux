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
    ota_package_dir: Path = _path_from_env(
        "ESP_UPGRADE_OTA_PACKAGE_DIR",
        "/root/codebase/esp32/projects/release/ota",
    )
    ota_publish_dir: Path = _path_from_env(
        "ESP_UPGRADE_OTA_PUBLISH_DIR",
        "/root/codebase/esp32/projects/release/ota_publish",
    )
    ota_publish_history_path: Path = _path_from_env(
        "ESP_UPGRADE_OTA_PUBLISH_HISTORY_PATH",
        str(_path_from_env("ESP_UPGRADE_BASE_DIR", "./var") / "ota_publish_history.json"),
    )
    ota_upgrade_records_path: Path = _path_from_env(
        "ESP_UPGRADE_OTA_UPGRADE_RECORDS_PATH",
        str(_path_from_env("ESP_UPGRADE_BASE_DIR", "./var") / "ota_upgrade_records.json"),
    )
    ota_upgrade_records_limit: int = int(os.getenv("ESP_UPGRADE_OTA_UPGRADE_RECORDS_LIMIT", "1000"))
    ota_default_board: str = os.getenv("ESP_OTA_DEFAULT_BOARD", "fogseek-nano").strip()
    ota_sign_private_key_path: Path = _path_from_env(
        "ESP_OTA_SIGN_PRIVATE_KEY_PATH",
        "/root/codebase/esp32/projects/release/keys/ota_sign_private.pem",
    )
    ota_sign_public_key_path: Path = _path_from_env(
        "ESP_OTA_SIGN_PUBLIC_KEY_PATH",
        "/root/codebase/esp32/projects/release/keys/ota_sign_public.pem",
    )
    ota_auto_generate_test_keys: bool = _bool_from_env("ESP_OTA_AUTO_GENERATE_TEST_KEYS", "1")
    max_log_lines: int = int(os.getenv("ESP_UPGRADE_MAX_LOG_LINES", "3000"))
    build_records_path: Path = _path_from_env(
        "ESP_UPGRADE_BUILD_RECORDS_PATH",
        str(_path_from_env("ESP_UPGRADE_BASE_DIR", "./var") / "build_records.json"),
    )
    cleanup_enabled: bool = _bool_from_env("ESP_UPGRADE_CLEANUP_ENABLED", "1")
    cleanup_retention_days: int = int(os.getenv("ESP_UPGRADE_CLEANUP_RETENTION_DAYS", "14"))
    cleanup_hour: int = int(os.getenv("ESP_UPGRADE_CLEANUP_HOUR", "3"))
    cleanup_minute: int = int(os.getenv("ESP_UPGRADE_CLEANUP_MINUTE", "0"))
    ota_public_base_url: str = os.getenv("ESP_OTA_PUBLIC_BASE_URL", "http://14.103.183.47:8010").strip().rstrip("/")
    ota_latest_version: str = os.getenv("ESP_OTA_LATEST_VERSION", "").strip()
    ota_firmware_dir: Path = _path_from_env("ESP_OTA_FIRMWARE_DIR", "/codebase/upgrade_linux/firmwares")
    ota_firmware_file: str = os.getenv("ESP_OTA_FIRMWARE_FILE", "xiaozhi.bin").strip()
    ota_force: bool = _bool_from_env("ESP_OTA_FORCE", "0")
    ota_log_body: bool = _bool_from_env("ESP_OTA_LOG_BODY", "1")


settings = Settings()
