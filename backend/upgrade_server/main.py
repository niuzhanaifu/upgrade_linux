from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import __version__
from .cleanup_scheduler import start_cleanup_scheduler
from .config import settings
from .job_manager import JobManager
from .ota import build_ota_response, firmware_file_response
from .ota_publish import OtaPublishStore, PublishError, publish_ota_package, scan_ota_packages
from .ota_upgrade_records import OtaUpgradeRecordStore


ROOT_DIR = Path(__file__).resolve().parents[2]
FRONTEND_DIR = ROOT_DIR / "frontend"

app = FastAPI(title="ESP32 Upgrade Server", version=__version__)
jobs = JobManager(settings)
ota_publish_store = OtaPublishStore(settings)
ota_upgrade_record_store = OtaUpgradeRecordStore(settings)


class BuildRequest(BaseModel):
    full: bool = False


class OtaPublishRequest(BaseModel):
    package_name: str
    password: str
    board: str | None = None


@app.on_event("startup")
def startup() -> None:
    start_cleanup_scheduler(jobs, settings)


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "version": __version__}


@app.get("/api/v1/config")
def config() -> dict:
    return {
        "host": settings.host,
        "port": settings.port,
        "base_dir": str(settings.base_dir),
        "source_dir": str(settings.source_dir),
        "build_workdir": str(settings.build_workdir),
        "repo_configured": bool(settings.repo_url),
        "repo_branch": settings.repo_branch,
        "build_command_configured": bool(settings.build_command),
        "build_script": str(settings.build_script),
        "build_script_workdir": str(settings.build_script_workdir),
        "build_script_configured": bool(settings.build_script),
        "build_incremental_arg": settings.build_incremental_arg,
        "build_full_arg": settings.build_full_arg,
        "cleanup_enabled": settings.cleanup_enabled,
        "cleanup_retention_days": settings.cleanup_retention_days,
        "cleanup_hour": settings.cleanup_hour,
        "cleanup_minute": settings.cleanup_minute,
        "firmware_path": settings.firmware_path,
        "upgrade_command_configured": bool(settings.upgrade_command),
        "ota_package_dir": str(settings.ota_package_dir),
        "ota_package_dir_configured": bool(settings.ota_package_dir),
        "ota_publish_dir": str(settings.ota_publish_dir),
        "ota_upgrade_records_path": str(settings.ota_upgrade_records_path),
        "ota_default_board": settings.ota_default_board,
        "ota_sign_public_key_path": str(settings.ota_sign_public_key_path),
        "ota_sign_private_key_configured": settings.ota_sign_private_key_path.is_file(),
        "ota_auto_generate_test_keys": settings.ota_auto_generate_test_keys,
        "ota_public_base_url": settings.ota_public_base_url,
        "ota_latest_version": settings.ota_latest_version,
        "ota_firmware_dir": str(settings.ota_firmware_dir),
        "ota_firmware_file": settings.ota_firmware_file,
        "ota_force": settings.ota_force,
        "ota_firmware_configured": bool(settings.ota_latest_version and settings.ota_firmware_file),
    }


@app.get("/api/v1/jobs")
def list_jobs() -> dict:
    return {"jobs": jobs.list_jobs()}


@app.post("/api/v1/build")
def start_build(request: BuildRequest | None = None) -> dict:
    try:
        job = jobs.start_build(full=request.full if request is not None else False)
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"job": job.public()}


@app.post("/api/v1/build/incremental")
def start_incremental_build() -> dict:
    try:
        job = jobs.start_build(full=False)
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"job": job.public()}


@app.post("/api/v1/build/full")
def start_full_build() -> dict:
    try:
        job = jobs.start_build(full=True)
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"job": job.public()}


@app.post("/api/v1/upgrade")
def start_upgrade() -> dict:
    try:
        job = jobs.start_upgrade()
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"job": job.public()}


@app.get("/api/v1/jobs/{job_id}")
def get_job(job_id: str) -> dict:
    job = jobs.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    return {"job": job.public()}


@app.get("/api/v1/jobs/{job_id}/logs")
def get_job_logs(job_id: str, offset: int = 0) -> dict:
    data = jobs.get_logs(job_id, offset)
    if data is None:
        raise HTTPException(status_code=404, detail="job not found")
    return data


@app.get("/api/v1/build-records")
def list_build_records() -> dict:
    return {"records": jobs.list_build_records()}


@app.get("/api/v1/firmwares")
def list_built_firmwares() -> dict:
    return {"firmwares": jobs.list_firmwares()}


@app.get("/api/v1/firmwares/{record_id}/download")
def download_built_firmware(record_id: str) -> FileResponse:
    path = jobs.get_firmware_path(record_id)
    if path is None:
        raise HTTPException(status_code=404, detail="firmware not found")
    return FileResponse(path, media_type="application/octet-stream", filename=path.name)


@app.get("/api/v1/ota-packages")
def list_ota_packages() -> dict:
    try:
        packages = scan_ota_packages(settings.ota_package_dir)
    except PublishError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    return {"directory": str(settings.ota_package_dir), "packages": packages}


@app.get("/api/v1/ota-publish/history")
def list_ota_publish_history() -> dict:
    return {"records": ota_publish_store.list_records()}


@app.post("/api/v1/ota-publish")
def publish_ota(request: OtaPublishRequest) -> dict:
    try:
        record = publish_ota_package(settings, ota_publish_store, request.package_name, request.password, request.board)
    except PublishError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    return {"record": record}


@app.get("/api/v1/ota-upgrade-records")
def list_ota_upgrade_records() -> dict:
    return {
        "records": ota_upgrade_record_store.list_records(),
        "stats": ota_upgrade_record_store.stats(),
    }


@app.post("/v1/firmware/ota/")
async def check_firmware_ota(request: Request) -> dict:
    return await build_ota_response(request, settings, ota_upgrade_record_store)


@app.get("/firmwares/{board}/{firmware_name}")
def download_board_firmware(board: str, firmware_name: str) -> FileResponse:
    return firmware_file_response(settings, firmware_name, board)


@app.get("/firmwares/{firmware_name}")
def download_firmware(firmware_name: str) -> FileResponse:
    return firmware_file_response(settings, firmware_name)


app.mount("/assets", StaticFiles(directory=str(FRONTEND_DIR)), name="assets")


@app.get("/")
def index() -> FileResponse:
    return FileResponse(FRONTEND_DIR / "index.html")
