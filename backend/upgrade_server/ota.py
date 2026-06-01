from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

from fastapi import HTTPException, Request
from fastapi.responses import FileResponse

from .config import Settings


logger = logging.getLogger("upgrade_server.ota")

OTA_HEADER_NAMES = (
    "device-id",
    "client-id",
    "user-agent",
    "activation-version",
    "accept-language",
    "content-type",
    "serial-number",
)


def selected_headers(request: Request) -> dict[str, str]:
    return {name: request.headers[name] for name in OTA_HEADER_NAMES if name in request.headers}


async def read_request_body(request: Request) -> Any:
    try:
        return await request.json()
    except Exception:
        body = await request.body()
        return body.decode("utf-8", errors="replace")


def extract_current_version(body: Any) -> str:
    if not isinstance(body, dict):
        return ""

    application = body.get("application")
    if isinstance(application, dict):
        version = application.get("version")
        if isinstance(version, str):
            return version.strip()

    version = body.get("version")
    if isinstance(version, str):
        return version.strip()

    firmware = body.get("firmware")
    if isinstance(firmware, dict):
        version = firmware.get("version")
        if isinstance(version, str):
            return version.strip()

    return ""


def parse_version(version: str) -> list[int]:
    parts = re.findall(r"\d+", version)
    return [int(part) for part in parts]


def is_newer_version(current_version: str, latest_version: str) -> bool:
    current = parse_version(current_version)
    latest = parse_version(latest_version)
    if not current or not latest:
        return False

    for index in range(max(len(current), len(latest))):
        current_part = current[index] if index < len(current) else 0
        latest_part = latest[index] if index < len(latest) else 0
        if latest_part > current_part:
            return True
        if latest_part < current_part:
            return False
    return False


def firmware_path(settings: Settings, firmware_name: str | None = None) -> Path:
    name = firmware_name or settings.ota_firmware_file
    if not name or Path(name).name != name:
        raise HTTPException(status_code=400, detail="invalid firmware filename")
    return (settings.ota_firmware_dir / name).resolve()


def build_firmware_url(request: Request, settings: Settings) -> str:
    base_url = settings.ota_public_base_url or str(request.base_url).rstrip("/")
    return f"{base_url}/firmwares/{settings.ota_firmware_file}"


async def build_ota_response(request: Request, settings: Settings) -> dict:
    body = await read_request_body(request)
    headers = selected_headers(request)
    current_version = extract_current_version(body)
    latest_version = settings.ota_latest_version or current_version
    path = firmware_path(settings)
    file_exists = path.is_file()
    has_update = settings.ota_force or not current_version or is_newer_version(current_version, latest_version)
    url = build_firmware_url(request, settings) if latest_version and file_exists and has_update else ""

    log_payload: dict[str, Any] = {
        "headers": headers,
        "current_version": current_version,
        "latest_version": latest_version,
        "firmware_file": str(path),
        "firmware_exists": file_exists,
        "force": settings.ota_force,
        "offer_url": bool(url),
    }
    if settings.ota_log_body:
        log_payload["body"] = body
    logger.info("ota check: %s", log_payload)

    return {
        "firmware": {
            "version": latest_version,
            "url": url,
            "force": 1 if settings.ota_force else 0,
        }
    }


def firmware_file_response(settings: Settings, firmware_name: str) -> FileResponse:
    root = settings.ota_firmware_dir.resolve()
    path = firmware_path(settings, firmware_name)

    if path.parent != root:
        raise HTTPException(status_code=400, detail="invalid firmware path")
    if firmware_name != settings.ota_firmware_file:
        raise HTTPException(status_code=404, detail="firmware not published")
    if not path.is_file():
        raise HTTPException(status_code=404, detail="firmware file not found")

    return FileResponse(
        path,
        media_type="application/octet-stream",
        filename=firmware_name,
    )
