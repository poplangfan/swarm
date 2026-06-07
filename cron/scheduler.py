"""Cron scheduler — APScheduler wrapper for background tasks."""

from __future__ import annotations

from typing import Any, Callable

import structlog
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

logger = structlog.get_logger(__name__)


class CronScheduler:
    """Async cron scheduler wrapping APScheduler with structured logging."""

    def __init__(self):
        self._scheduler = AsyncIOScheduler()
        self._jobs: dict[str, dict[str, Any]] = {}
        self._started = False

    def start(self) -> None:
        if self._started:
            logger.warning("cron_scheduler_already_started")
            return
        self._scheduler.start()
        self._started = True
        logger.info("cron_scheduler_started")

    def stop(self) -> None:
        self._scheduler.shutdown(wait=False)
        logger.info("cron_scheduler_stopped")

    def add_interval_job(
        self,
        job_id: str,
        func: Callable,
        minutes: int = 30,
        **kwargs,
    ) -> None:
        """Add a recurring job that runs every N minutes."""
        self._scheduler.add_job(
            func=func,
            trigger=IntervalTrigger(minutes=minutes),
            id=job_id,
            name=job_id,
            replace_existing=True,
            **kwargs,
        )
        self._jobs[job_id] = {"type": "interval", "minutes": minutes}
        logger.info("cron_job_added", job_id=job_id, interval_minutes=minutes)

    def add_cron_job(
        self,
        job_id: str,
        func: Callable,
        cron_expr: str,
        **kwargs,
    ) -> None:
        """Add a job with a cron expression (e.g. '0 9 * * *' for 9am daily)."""
        parts = cron_expr.strip().split()
        if len(parts) != 5:
            raise ValueError(f"Invalid cron expression: {cron_expr}")
        self._scheduler.add_job(
            func=func,
            trigger=CronTrigger(
                minute=parts[0],
                hour=parts[1],
                day=parts[2],
                month=parts[3],
                day_of_week=parts[4],
            ),
            id=job_id,
            name=job_id,
            replace_existing=True,
            **kwargs,
        )
        self._jobs[job_id] = {"type": "cron", "expression": cron_expr}
        logger.info("cron_job_added", job_id=job_id, cron=cron_expr)

    def remove_job(self, job_id: str) -> bool:
        """Remove a scheduled job. Returns False if not found."""
        from apscheduler.jobstores.base import JobLookupError

        try:
            self._scheduler.remove_job(job_id)
            self._jobs.pop(job_id, None)
            logger.info("cron_job_removed", job_id=job_id)
            return True
        except JobLookupError:
            logger.debug("cron_job_not_found", job_id=job_id)
            return False
        except Exception as e:
            logger.warning("cron_job_remove_error", job_id=job_id, error=str(e))
            return False

    def list_jobs(self) -> list[dict[str, Any]]:
        """List all scheduled jobs."""
        return [{"id": jid, **info} for jid, info in self._jobs.items()]

    def get_job_count(self) -> int:
        return len(self._jobs)
