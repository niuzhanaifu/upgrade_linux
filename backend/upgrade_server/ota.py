from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

from fastapi import HTTPException, Request
from fastapi.responses import FileResponse

from .config import Settings
from .ota_publish import SIGN_ALG, normalize_board, package_info, verify_manifest_signature
from .ota_upgrade_records import OtaUpgradeRecordStore


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


def client_ip(request: Request) -> str:
    forwarded_for = request.headers.get("x-forwarded-for", "")
    if forwarded_for:
        return forwarded_for.split(",", 1)[0].strip()
    real_ip = request.headers.get("x-real-ip", "")
    if real_ip:
        return real_ip.strip()
    return request.client.host if request.client else ""


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


def extract_board(body: Any, request: Request, settings: Settings) -> str:
    if isinstance(body, dict):
        board = _find_string_value(body, {"board", "board_type", "board_name", "boardType"})
        if board:
            return normalize_board(board)

    user_agent = request.headers.get("user-agent", "")
    if "/" in user_agent:
        candidate = user_agent.split("/", 1)[0].strip()
        if candidate:
            return normalize_board(candidate)

    return normalize_board(settings.ota_default_board)


def _find_string_value(value: Any, keys: set[str]) -> str:
    if isinstance(value, dict):
        for key, item in value.items():
            if key in keys and isinstance(item, str) and item.strip():
                return item.strip()
        for item in value.values():
            found = _find_string_value(item, keys)
            if found:
                return found
    elif isinstance(value, list):
        for item in value:
            found = _find_string_value(item, keys)
            if found:
                return found
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


async def build_ota_response(
    request: Request,
    settings: Settings,
    record_store: OtaUpgradeRecordStore | None = None,
) -> dict:
    body = await read_request_body(request)
    headers = selected_headers(request)
    ip = client_ip(request)
    current_version = extract_current_version(body)
    board = extract_board(body, request, settings)
    manifest = load_published_manifest(settings, board)
    latest_version = str(manifest.get("version") or "") if manifest else ""
    package_name = str(manifest.get("package_name") or "") if manifest else ""
    path = published_firmware_path(settings, board, package_name) if package_name else None
    file_exists = bool(path and path.is_file())
    force = bool(settings.ota_force or int(manifest.get("force", 0))) if manifest else settings.ota_force
    has_update = bool(manifest) and file_exists and (force or not current_version or is_newer_version(current_version, latest_version))
    signature_ok = bool(manifest and verify_manifest_signature(settings, manifest))

    log_payload: dict[str, Any] = {
        "headers": headers,
        "board": board,
        "current_version": current_version,
        "latest_version": latest_version,
        "firmware_file": str(path) if path else "",
        "firmware_exists": file_exists,
        "force": force,
        "signature_ok": signature_ok,
        "offer_update": has_update and signature_ok,
    }
    if settings.ota_log_body:
        log_payload["body"] = body
    logger.info("ota check: %s", log_payload)

    if not manifest or not has_update or not signature_ok:
        reason = "no_manifest"
        if manifest and not file_exists:
            reason = "firmware_missing"
        elif manifest and not signature_ok:
            reason = "signature_invalid"
        elif manifest and not has_update:
            reason = "no_new_version"
        _record_ota_check(
            record_store,
            {
                "ip": ip,
                "device_id": headers.get("device-id", ""),
                "client_id": headers.get("client-id", ""),
                "serial_number": headers.get("serial-number", ""),
                "user_agent": headers.get("user-agent", ""),
                "board": board,
                "current_version": current_version,
                "target_version": latest_version,
                "package_name": package_name,
                "status": "no_update",
                "success": False,
                "available": False,
                "reason": reason,
                "signature_ok": signature_ok,
            },
        )
        return {"firmware": {"available": False}}

    _record_ota_check(
        record_store,
        {
            "ip": ip,
            "device_id": headers.get("device-id", ""),
            "client_id": headers.get("client-id", ""),
            "serial_number": headers.get("serial-number", ""),
            "user_agent": headers.get("user-agent", ""),
            "board": board,
            "current_version": current_version,
            "target_version": latest_version,
            "package_name": package_name,
            "status": "offered",
            "success": True,
            "available": True,
            "reason": "available",
            "signature_ok": signature_ok,
        },
    )
    return {
        "firmware": {
            "available": True,
            "board": board,
            "version": latest_version,
            "url": manifest["url"],
            "size": int(manifest["size"]),
            "sha256": str(manifest["sha256"]).lower(),
            "sign_alg": SIGN_ALG,
            "signature": manifest["signature"],
            "force": 1 if force else 0,
        }
    }


def _record_ota_check(record_store: OtaUpgradeRecordStore | None, record: dict[str, Any]) -> None:
    if record_store is None:
        return
    try:
        record_store.add_record(record)
    except Exception as exc:
        logger.warning("failed to save OTA upgrade record: %s", exc)


def firmware_file_response(settings: Settings, firmware_name: str, board: str | None = None) -> FileResponse:
    if board:
        board_name = normalize_board(board)
        if Path(firmware_name).name != firmware_name:
            raise HTTPException(status_code=400, detail="invalid firmware filename")
        path = published_firmware_path(settings, board_name, firmware_name)
        root = (settings.ota_publish_dir / board_name).resolve()
        if path.parent != root:
            raise HTTPException(status_code=400, detail="invalid firmware path")
        if package_info(path) is None:
            raise HTTPException(status_code=400, detail="invalid OTA package filename")
        if not path.is_file():
            raise HTTPException(status_code=404, detail="firmware file not found")
        return FileResponse(
            path,
            media_type="application/octet-stream",
            filename=firmware_name,
        )

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


def load_published_manifest(settings: Settings, board: str) -> dict[str, object] | None:
    manifest_path = settings.ota_publish_dir / board / "manifest.json"
    if not manifest_path.is_file():
        return None
    try:
        with manifest_path.open("r", encoding="utf-8") as file:
            manifest = json.load(file)
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(manifest, dict):
        return None
    if not _manifest_has_required_fields(manifest):
        return None
    if str(manifest["board"]) != board:
        return None
    package_name = str(manifest["package_name"])
    path = published_firmware_path(settings, board, package_name)
    if not path.is_file():
        return None
    current_info = package_info(path)
    if current_info is None:
        return None
    if int(current_info["size"]) != int(manifest["size"]):
        return None
    if str(current_info["sha256"]).lower() != str(manifest["sha256"]).lower():
        return None
    return manifest


def published_firmware_path(settings: Settings, board: str, firmware_name: str) -> Path:
    return (settings.ota_publish_dir / normalize_board(board) / Path(firmware_name).name).resolve()


def _manifest_has_required_fields(manifest: dict[str, object]) -> bool:
    required = {"board", "version", "url", "size", "sha256", "sign_alg", "signature", "package_name"}
    if not required.issubset(manifest):
        return False
    if manifest.get("sign_alg") != SIGN_ALG:
        return False
    if not re.fullmatch(r"[0-9a-f]{64}", str(manifest.get("sha256", ""))):
        return False
    try:
        int(manifest["size"])
    except (TypeError, ValueError):
        return False
    return True
