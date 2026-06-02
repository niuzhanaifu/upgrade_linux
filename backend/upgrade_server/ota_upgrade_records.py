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
            **record,
        }
        with self._lock:
            records = self._load_unlocked()
            records.insert(0, data)
            self._save_unlocked(records[: self.limit])
        return data

    def list_records(self, limit: int = 100) -> list[dict[str, Any]]:
        with self._lock:
            return self._load_unlocked()[:limit]

    def stats(self) -> dict[str, int]:
        with self._lock:
            records = self._load_unlocked()
        total = len(records)
        offered = sum(1 for item in records if item.get("status") == "offered")
        no_update = sum(1 for item in records if item.get("status") == "no_update")
        failed = sum(1 for item in records if item.get("status") == "failed")
        unique_ips = len({str(item.get("ip", "")) for item in records if item.get("ip")})
        return {
            "total": total,
            "offered": offered,
            "no_update": no_update,
            "failed": failed,
            "unique_ips": unique_ips,
        }

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
