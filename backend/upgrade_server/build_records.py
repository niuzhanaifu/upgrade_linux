from __future__ import annotations

import json
import threading
from datetime import datetime
from pathlib import Path
from typing import Any

from .config import Settings


class BuildRecordStore:
    def __init__(self, settings: Settings):
        self.path = settings.build_records_path
        self._lock = threading.Lock()

    def list_records(self) -> list[dict[str, Any]]:
        with self._lock:
            return self._read_records()

    def list_firmwares(self) -> list[dict[str, Any]]:
        records = self.list_records()
        firmwares = []
        for record in records:
            merged_bin = record.get("merged_bin")
            if record.get("status") != "succeeded" or not merged_bin:
                continue

            path = Path(str(merged_bin)).expanduser()
            firmwares.append(
                {
                    "id": record["id"],
                    "name": path.name,
                    "path": str(path),
                    "exists": path.is_file(),
                    "size": path.stat().st_size if path.is_file() else 0,
                    "firmware_version": record.get("firmware_version"),
                    "output_dir": record.get("output_dir"),
                    "finished_at": record.get("finished_at"),
                    "mode": record.get("mode"),
                }
            )
        return firmwares

    def get_firmware_path(self, record_id: str) -> Path | None:
        for firmware in self.list_firmwares():
            if firmware["id"] == record_id:
                path = Path(str(firmware["path"])).expanduser()
                return path if path.is_file() else None
        return None

    def cleanup_before(self, cutoff: datetime) -> dict[str, int]:
        with self._lock:
            kept_records = []
            removed_records = 0
            removed_firmwares = 0
            removed_empty_dirs = 0

            for record in self._read_records():
                finished_at = _parse_time(record.get("finished_at") or record.get("created_at"))
                if finished_at is None or finished_at >= cutoff:
                    kept_records.append(record)
                    continue

                removed_records += 1
                merged_bin = record.get("merged_bin")
                if merged_bin:
                    firmware_path = Path(str(merged_bin)).expanduser()
                    if firmware_path.is_file():
                        try:
                            firmware_path.unlink()
                            removed_firmwares += 1
                        except OSError:
                            pass
                    try:
                        firmware_path.parent.rmdir()
                        removed_empty_dirs += 1
                    except OSError:
                        pass

            self._write_records(kept_records)
            return {
                "removed_records": removed_records,
                "removed_firmwares": removed_firmwares,
                "removed_empty_dirs": removed_empty_dirs,
            }

    def save_record(self, record: dict[str, Any]) -> None:
        with self._lock:
            records = [item for item in self._read_records() if item.get("id") != record.get("id")]
            records.insert(0, record)
            self._write_records(records[:200])

    def _read_records(self) -> list[dict[str, Any]]:
        if not self.path.is_file():
            return []
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return []
        if isinstance(data, list):
            return [item for item in data if isinstance(item, dict)]
        return []

    def _write_records(self, records: list[dict[str, Any]]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        content = json.dumps(records, ensure_ascii=False, indent=2)
        tmp_path = self.path.with_suffix(f"{self.path.suffix}.tmp")
        tmp_path.write_text(content, encoding="utf-8")
        try:
            tmp_path.replace(self.path)
        except PermissionError:
            self.path.write_text(content, encoding="utf-8")
            try:
                tmp_path.unlink()
            except OSError:
                pass


def _parse_time(value: object) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.astimezone()
    return parsed
