from __future__ import annotations

import json
import threading
import uuid
from datetime import datetime, timezone
from typing import Any

from .config import Settings


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class OtaUpgradeRecordStore:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.path = settings.ota_upgrade_records_path
        self.limit = settings.ota_upgrade_records_limit
        self._lock = threading.Lock()

    def add_record(self, record: dict[str, Any]) -> dict[str, Any]:
        data = {
            "id": str(uuid.uuid4()),
            "requested_at": utc_now(),
            "reported_at": None,
            **record,
        }
        with self._lock:
            records = self._load_unlocked()
            records.insert(0, data)
            self._save_unlocked(records[: self.limit])
        return data

    def update_result(
        self,
        *,
        record_id: str = "",
        device_id: str = "",
        client_id: str = "",
        board: str = "",
        package_name: str = "",
        target_version: str = "",
        success: bool,
        error: str = "",
        ip: str = "",
    ) -> dict[str, Any]:
        with self._lock:
            records = self._load_unlocked()
            record = self._find_record_unlocked(
                records,
                record_id=record_id,
                device_id=device_id,
                client_id=client_id,
                board=board,
                package_name=package_name,
                target_version=target_version,
            )
            if record is None:
                record = {
                    "id": str(uuid.uuid4()),
                    "requested_at": utc_now(),
                    "ip": ip,
                    "device_id": device_id,
                    "client_id": client_id,
                    "serial_number": "",
                    "user_agent": "",
                    "board": board,
                    "current_version": "",
                    "target_version": target_version,
                    "package_name": package_name,
                    "available": True,
                    "reason": "device_report_without_offer_record",
                    "signature_ok": None,
                }
                records.insert(0, record)

            record["status"] = "success" if success else "failed"
            record["success"] = success
            record["result_source"] = "device"
            record["reported_at"] = utc_now()
            record["report_error"] = error
            if ip:
                record["report_ip"] = ip
            self._save_unlocked(records[: self.limit])
            return dict(record)

    def list_records(self, limit: int = 100) -> list[dict[str, Any]]:
        with self._lock:
            return self._load_unlocked()[:limit]

    def stats(self) -> dict[str, int]:
        with self._lock:
            records = self._load_unlocked()
        total = len(records)
        success = sum(1 for item in records if item.get("status") == "success")
        failed = sum(1 for item in records if item.get("status") == "failed")
        reported = sum(1 for item in records if item.get("result_source") == "device")
        unique_ips = len({str(item.get("ip", "")) for item in records if item.get("ip")})
        return {
            "total": total,
            "success": success,
            "failed": failed,
            "reported": reported,
            "unique_ips": unique_ips,
        }

    def _find_record_unlocked(
        self,
        records: list[dict[str, Any]],
        *,
        record_id: str,
        device_id: str,
        client_id: str,
        board: str,
        package_name: str,
        target_version: str,
    ) -> dict[str, Any] | None:
        if record_id:
            for record in records:
                if record.get("id") == record_id:
                    return record

        for record in records:
            if record.get("status") not in {"success", "failed"}:
                continue
            if device_id and record.get("device_id") != device_id:
                continue
            if client_id and record.get("client_id") != client_id:
                continue
            if board and record.get("board") != board:
                continue
            if package_name and record.get("package_name") != package_name:
                continue
            if target_version and record.get("target_version") != target_version:
                continue
            return record
        return None

    def _load_unlocked(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        try:
            with self.path.open("r", encoding="utf-8") as file:
                data = json.load(file)
        except (OSError, json.JSONDecodeError):
            return []
        if not isinstance(data, list):
            return []
        return [item for item in data if isinstance(item, dict)]

    def _save_unlocked(self, records: list[dict[str, Any]]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("w", encoding="utf-8") as file:
            json.dump(records, file, ensure_ascii=False, indent=2)
