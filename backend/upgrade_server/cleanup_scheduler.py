from __future__ import annotations

import logging
import threading
from datetime import datetime, timedelta
from time import sleep
from zoneinfo import ZoneInfo

from .config import Settings
from .job_manager import JobManager


logger = logging.getLogger("upgrade_server.cleanup")
BEIJING_TZ = ZoneInfo("Asia/Shanghai")


def start_cleanup_scheduler(jobs: JobManager, settings: Settings) -> None:
    if not settings.cleanup_enabled:
        logger.info("cleanup scheduler disabled")
        return

    thread = threading.Thread(target=_cleanup_loop, args=(jobs, settings), daemon=True)
    thread.start()


def _cleanup_loop(jobs: JobManager, settings: Settings) -> None:
    logger.info(
        "cleanup scheduler started, retention_days=%s, time=%02d:%02d Asia/Shanghai",
        settings.cleanup_retention_days,
        settings.cleanup_hour,
        settings.cleanup_minute,
    )
    while True:
        next_run = _next_cleanup_time(settings)
        seconds = max(1, int((next_run - datetime.now(BEIJING_TZ)).total_seconds()))
        while seconds > 0:
            chunk = min(seconds, 3600)
            sleep(chunk)
            seconds -= chunk

        cutoff = datetime.now(BEIJING_TZ) - timedelta(days=settings.cleanup_retention_days)
        try:
            result = jobs.cleanup_before(cutoff)
            logger.info("cleanup finished, cutoff=%s, result=%s", cutoff.isoformat(), result)
        except Exception:
            logger.exception("cleanup failed")


def _next_cleanup_time(settings: Settings) -> datetime:
    now = datetime.now(BEIJING_TZ)
    next_run = now.replace(
        hour=settings.cleanup_hour,
        minute=settings.cleanup_minute,
        second=0,
        microsecond=0,
    )
    if next_run <= now:
        next_run += timedelta(days=1)
    return next_run
