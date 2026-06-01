from __future__ import annotations

import os
import shlex
import subprocess
import threading
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from .build_records import BuildRecordStore
from .config import Settings


Status = str


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class Job:
    id: str
    kind: str
    status: Status = "queued"
    created_at: str = field(default_factory=utc_now)
    started_at: str | None = None
    finished_at: str | None = None
    exit_code: int | None = None
    result: dict[str, object] = field(default_factory=dict)
    logs: list[str] = field(default_factory=list)

    def public(self) -> dict:
        data = asdict(self)
        data["log_count"] = len(self.logs)
        data.pop("logs")
        return data


class JobManager:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.records = BuildRecordStore(settings)
        self._jobs: dict[str, Job] = {}
        self._lock = threading.Lock()

    def list_jobs(self) -> list[dict]:
        with self._lock:
            return [job.public() for job in sorted(self._jobs.values(), key=lambda item: item.created_at, reverse=True)]

    def get_job(self, job_id: str) -> Job | None:
        with self._lock:
            return self._jobs.get(job_id)

    def get_logs(self, job_id: str, offset: int = 0) -> dict | None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return None
            return {
                "job": job.public(),
                "offset": offset,
                "next_offset": len(job.logs),
                "lines": job.logs[offset:],
            }

    def list_build_records(self) -> list[dict[str, object]]:
        return self.records.list_records()

    def list_firmwares(self) -> list[dict[str, object]]:
        return self.records.list_firmwares()

    def get_firmware_path(self, record_id: str) -> Path | None:
        return self.records.get_firmware_path(record_id)

    def start_build(self, full: bool = False) -> Job:
        kind = "build_full" if full else "build_incremental"
        return self._start(kind, lambda job: self._run_build(job, full=full))

    def start_upgrade(self) -> Job:
        return self._start("upgrade", self._run_upgrade)

    def _start(self, kind: str, worker: Callable[[Job], None]) -> Job:
        with self._lock:
            running = [job for job in self._jobs.values() if job.status in {"queued", "running"}]
            running_build = [job for job in running if job.kind.startswith("build")]
            if kind.startswith("build") and running_build:
                raise RuntimeError("已有编译任务正在运行")
            if running:
                raise RuntimeError("another job is already running")
            job = Job(id=str(uuid.uuid4()), kind=kind)
            self._jobs[job.id] = job

        thread = threading.Thread(target=worker, args=(job,), daemon=True)
        thread.start()
        return job

    def _append(self, job: Job, line: str) -> None:
        with self._lock:
            job.logs.append(line.rstrip())
            if len(job.logs) > self.settings.max_log_lines:
                job.logs = job.logs[-self.settings.max_log_lines :]

    def _set_status(self, job: Job, status: Status, exit_code: int | None = None) -> None:
        with self._lock:
            job.status = status
            if status == "running":
                job.started_at = utc_now()
            if status in {"succeeded", "failed"}:
                job.finished_at = utc_now()
                job.exit_code = exit_code

    def _set_job_result(self, job: Job, result: dict[str, object]) -> None:
        with self._lock:
            job.result = result

    def _run_build(self, job: Job, full: bool = False) -> None:
        self._set_status(job, "running")
        try:
            self.settings.base_dir.mkdir(parents=True, exist_ok=True)
            mode = "full" if full else "incremental"
            self._append(job, f"{mode.capitalize()} build started.")
            result = self._run_build_script(job, full=full)
            self._set_job_result(job, result)
            if result["success"]:
                self._set_status(job, "succeeded", int(result["returncode"]))
                self._append(job, "Build finished successfully.")
            else:
                self._set_status(job, "failed", int(result["returncode"]))
                self._append(job, f"ERROR: build failed with exit code {result['returncode']}")
            self._try_save_build_record(job)
        except Exception as exc:
            self._append(job, f"ERROR: {exc}")
            self._set_status(job, "failed", 1)
            self._try_save_build_record(job)

    def _run_upgrade(self, job: Job) -> None:
        self._set_status(job, "running")
        try:
            self.settings.base_dir.mkdir(parents=True, exist_ok=True)
            self._append(job, "Upgrade started.")
            if not self.settings.upgrade_command:
                raise RuntimeError("ESP_UPGRADE_UPGRADE_COMMAND is empty. Configure it before running upgrade.")
            firmware = self.settings.firmware_path
            if not firmware:
                raise RuntimeError("ESP_UPGRADE_FIRMWARE_PATH is empty. Configure it before running upgrade.")
            if not Path(firmware).expanduser().exists():
                self._append(job, f"WARNING: firmware path does not exist yet: {firmware}")
            command = self.settings.upgrade_command.format(
                firmware=shlex.quote(firmware),
                source_dir=shlex.quote(str(self.settings.source_dir)),
            )
            self._run_shell(job, command, self.settings.build_workdir)
            self._set_status(job, "succeeded", 0)
            self._append(job, "Upgrade finished successfully.")
        except Exception as exc:
            self._append(job, f"ERROR: {exc}")
            self._set_status(job, "failed", 1)

    def _pull_source(self, job: Job) -> None:
        if not self.settings.repo_url:
            raise RuntimeError("ESP_UPGRADE_REPO_URL is empty. Configure it before running build.")

        source_dir = self.settings.source_dir
        if (source_dir / ".git").exists():
            self._append(job, f"Updating repository in {source_dir}")
            self._run_process(job, ["git", "fetch", "--all", "--prune"], source_dir)
            if self.settings.repo_branch:
                self._run_process(job, ["git", "checkout", self.settings.repo_branch], source_dir)
            self._run_process(job, ["git", "pull", "--ff-only"], source_dir)
            return

        if source_dir.exists() and any(source_dir.iterdir()):
            raise RuntimeError(f"{source_dir} exists but is not a git repository.")

        source_dir.parent.mkdir(parents=True, exist_ok=True)
        command = ["git", "clone"]
        if self.settings.repo_branch:
            command.extend(["--branch", self.settings.repo_branch])
        command.extend([self.settings.repo_url, str(source_dir)])
        self._append(job, f"Cloning repository into {source_dir}")
        self._run_process(job, command, source_dir.parent)

    def _run_build_command(self, job: Job) -> None:
        if not self.settings.build_command:
            raise RuntimeError("ESP_UPGRADE_BUILD_COMMAND is empty. Configure it before running build.")
        self._run_shell(job, self.settings.build_command, self.settings.build_workdir)
        if self.settings.firmware_path:
            self._append(job, f"Configured firmware path: {self.settings.firmware_path}")

    def _run_build_script(self, job: Job, full: bool) -> dict[str, object]:
        script = self.settings.build_script
        workdir = self.settings.build_script_workdir
        mode_arg = self.settings.build_full_arg if full else self.settings.build_incremental_arg

        if not str(script):
            raise RuntimeError("ESP_UPGRADE_BUILD_SCRIPT is empty. Configure it before running build.")
        if not script.exists():
            raise RuntimeError(f"build script does not exist: {script}")

        command = [str(script)]
        if mode_arg:
            command.append(mode_arg)

        result: dict[str, object] = {
            "success": False,
            "returncode": None,
            "output_dir": None,
            "merged_bin": None,
            "firmware_version": None,
            "mode": "full" if full else "incremental",
        }

        def parse_build_line(line: str) -> None:
            if line.startswith("OUTPUT_DIR="):
                result["output_dir"] = line.split("=", 1)[1]
            elif line.startswith("MERGED_BIN="):
                result["merged_bin"] = line.split("=", 1)[1]
            elif line.startswith("FIRMWARE_VERSION="):
                result["firmware_version"] = line.split("=", 1)[1]

        self._append(job, f"$ {' '.join(shlex.quote(part) for part in command)}")
        returncode = self._run_process(job, command, workdir, on_line=parse_build_line, check=False)
        result["returncode"] = returncode
        result["success"] = returncode == 0
        return result

    def _save_build_record(self, job: Job) -> None:
        if not job.kind.startswith("build"):
            return

        result = job.result or {}
        merged_bin = result.get("merged_bin")
        path = Path(str(merged_bin)).expanduser() if merged_bin else None
        record: dict[str, object] = {
            "id": job.id,
            "kind": job.kind,
            "mode": result.get("mode") or ("full" if job.kind == "build_full" else "incremental"),
            "status": job.status,
            "created_at": job.created_at,
            "started_at": job.started_at,
            "finished_at": job.finished_at,
            "exit_code": job.exit_code,
            "success": job.status == "succeeded",
            "output_dir": result.get("output_dir"),
            "merged_bin": merged_bin,
            "firmware_name": path.name if path is not None else None,
            "firmware_exists": path.is_file() if path is not None else False,
            "firmware_size": path.stat().st_size if path is not None and path.is_file() else 0,
            "firmware_version": result.get("firmware_version"),
        }
        self.records.save_record(record)

    def _try_save_build_record(self, job: Job) -> None:
        try:
            self._save_build_record(job)
        except Exception as exc:
            self._append(job, f"WARNING: failed to save build record: {exc}")

    def _run_shell(self, job: Job, command: str, cwd: Path) -> None:
        self._append(job, f"$ {command}")
        self._run_process(job, command, cwd, shell=True)

    def _run_process(
        self,
        job: Job,
        command: list[str] | str,
        cwd: Path,
        shell: bool = False,
        on_line: Callable[[str], None] | None = None,
        check: bool = True,
    ) -> int:
        cwd.mkdir(parents=True, exist_ok=True)
        env = os.environ.copy()
        process = subprocess.Popen(
            command,
            cwd=str(cwd),
            env=env,
            shell=shell,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        assert process.stdout is not None
        for line in process.stdout:
            clean_line = line.rstrip()
            if on_line is not None:
                on_line(clean_line)
            self._append(job, clean_line)
        exit_code = process.wait()
        if check and exit_code != 0:
            raise RuntimeError(f"command failed with exit code {exit_code}")
        return exit_code
