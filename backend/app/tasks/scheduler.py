"""Scheduler lifecycle and trigger registration.

APScheduler runs in-process, inside the API. That is a deliberate choice for a
platform this size: a separate worker deployment is another process to build,
deploy, monitor and page someone about, and the work here is six periodic
queries. The cost of the choice is that every uvicorn worker starts a
scheduler, so every trigger fires N times — which is why each task takes a
Postgres advisory lock and returns immediately if it loses. Correctness does
not depend on there being exactly one scheduler.

`coalesce=True` and `max_instances=1` are the other half of that. If the
process was paused, a task with three missed firings runs once rather than
three times in a row; and a slow run is never overlapped by the next trigger.
"""

from __future__ import annotations

import logging
from typing import Any

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from app.core.config import settings
from app.tasks.scheduled_tasks import TASKS, run_task

logger = logging.getLogger("rozgar.scheduler")

#: (task name, trigger, description). Times are in `settings.scheduler_timezone`
#: — Asia/Karachi — so "runs overnight" means overnight for the people who
#: operate this, not overnight in UTC.
SCHEDULE: list[tuple[str, Any, str]] = [
    (
        "ensure_partitions",
        IntervalTrigger(hours=1),
        "keep the partition window ahead of now",
    ),
    (
        "rebuild_rollups",
        IntervalTrigger(minutes=15),
        "recompute today and yesterday's analytics rollups",
    ),
    (
        "expire_jobs",
        CronTrigger(hour=0, minute=5),
        "expire published listings past their expiry date",
    ),
    (
        "purge_sessions",
        CronTrigger(hour=3, minute=0),
        "delete refresh sessions that have expired",
    ),
    (
        "prune_telemetry",
        CronTrigger(day=1, hour=4, minute=0),
        "drop analytics and search-log partitions past retention",
    ),
    (
        "alert_on_reports",
        IntervalTrigger(minutes=30),
        "flag listings that have reached the open-report threshold",
    ),
]


class SchedulerHandle:
    """Wraps the APScheduler instance.

    Exists so the health check can ask whether the scheduler is actually
    running without importing APScheduler, and so tests can construct the
    schedule without starting it.
    """

    def __init__(self) -> None:
        self.scheduler: AsyncIOScheduler | None = None

    @property
    def running(self) -> bool:
        return self.scheduler is not None and self.scheduler.running

    def jobs(self) -> list[dict[str, Any]]:
        if self.scheduler is None:
            return []
        return [
            {
                "id": job.id,
                "next_run": job.next_run_time.isoformat() if job.next_run_time else None,
            }
            for job in self.scheduler.get_jobs()
        ]

    def start(self) -> None:
        if self.running:
            return

        scheduler = AsyncIOScheduler(
            timezone=settings.scheduler_timezone,
            job_defaults={
                # A paused process must not stampede on resume.
                "coalesce": True,
                # Never overlap a task with itself.
                "max_instances": 1,
                # Tolerate the event loop being busy at the trigger instant.
                "misfire_grace_time": 300,
            },
        )

        for name, trigger, description in SCHEDULE:
            task = TASKS[name]
            scheduler.add_job(
                _make_runner(name, task),
                trigger=trigger,
                id=name,
                name=description,
                replace_existing=True,
            )

        scheduler.start()
        self.scheduler = scheduler
        logger.info(
            "scheduler started",
            extra={
                "event": "scheduler.started",
                "timezone": settings.scheduler_timezone,
                "jobs": [name for name, _, _ in SCHEDULE],
            },
        )

    def shutdown(self) -> None:
        if self.scheduler is None:
            return
        # `wait=False`: shutdown happens during application teardown, and
        # blocking on a fifteen-minute rollup would hold the process open past
        # any sensible termination grace period. The advisory lock is released
        # by the connection closing either way.
        self.scheduler.shutdown(wait=False)
        logger.info("scheduler stopped", extra={"event": "scheduler.stopped"})
        self.scheduler = None


def _make_runner(name, task):  # type: ignore[no-untyped-def]
    async def runner() -> None:
        await run_task(name, task)

    runner.__name__ = f"run_{name}"
    return runner


#: One handle per process, created at import so the health check can reach it.
scheduler_handle = SchedulerHandle()


__all__ = ["SCHEDULE", "SchedulerHandle", "scheduler_handle"]
