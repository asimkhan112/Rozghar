"""The scheduled tasks themselves.

Every task obeys three rules, and each is enforced structurally rather than by
convention:

**Idempotent.** Running a task twice produces the same state as running it
once. Auto-expiry re-reads what is actually overdue; the rollup replaces rather
than increments; partition creation returns early when the partition exists.

**Serialised across instances.** APScheduler runs in-process, so N uvicorn
workers means N schedulers and N firings of every trigger. Each task takes a
Postgres advisory lock keyed on its own name and returns immediately if another
instance holds it. Without this, `rebuild_rollups` alone would be running four
times concurrently over the same rows.

**Never fatal.** A task that raises must not take the scheduler down with it.
`run_task` converts any exception into a logged, structured failure, because a
scheduler that dies silently at 3am is worse than a task that fails loudly.

Tasks are plain async functions taking a session. The scheduler is one caller;
the test suite and the CLI are others.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.enums import JobStatus, ReportStatus
from app.db.database import SessionFactory
from app.repositories.analytics_repo import AnalyticsRepository
from app.repositories.job_repo import JobRepository
from app.repositories.session_repo import SessionRepository
from app.repositories.suggest_repo import SuggestRepository
from app.services.analytics_service import AnalyticsService
from app.services.metrics_service import MetricsService

logger = logging.getLogger("rozgar.tasks")

#: Namespace for the advisory locks, so a key collision with anything else
#: using `pg_try_advisory_lock` on this database is not possible by accident.
LOCK_NAMESPACE = 0x524F5A47  # "ROZG"

PARTITIONED_TABLES = ("analytics_events", "search_logs")


@dataclass
class TaskResult:
    """What a task did, in a shape that logs and tests can both read."""

    name: str
    ran: bool
    duration_ms: int = 0
    details: dict[str, Any] = field(default_factory=dict)
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.error is None


def _lock_key(name: str) -> int:
    """Stable 32-bit key from the task name.

    Deliberately not `hash()` — that is salted per process in Python 3, so two
    workers would compute different keys for the same task and both would take
    "the" lock.
    """
    return sum((i + 1) * ord(c) for i, c in enumerate(name)) % 2_000_000_000


async def _try_lock(session: AsyncSession, name: str) -> bool:
    """Session-scoped advisory lock. Released when the connection closes, so a
    crashed worker cannot leave a task wedged."""
    return bool(
        (
            await session.execute(
                text("SELECT pg_try_advisory_lock(:ns, :key)"),
                {"ns": LOCK_NAMESPACE, "key": _lock_key(name)},
            )
        ).scalar_one()
    )


async def _unlock(session: AsyncSession, name: str) -> None:
    await session.execute(
        text("SELECT pg_advisory_unlock(:ns, :key)"),
        {"ns": LOCK_NAMESPACE, "key": _lock_key(name)},
    )


async def run_task(
    name: str,
    fn: Callable[[AsyncSession], Awaitable[dict[str, Any]]],
) -> TaskResult:
    """Execute one task under a lock, with structured logging either way.

    Owns its own session rather than taking one: a scheduled task has no
    request to borrow a session from, and holding a request-scoped session
    across a trigger interval would pin a pool connection for minutes.
    """
    started = time.perf_counter()
    async with SessionFactory() as session:
        if not await _try_lock(session, name):
            logger.info(
                "task skipped: another instance holds the lock",
                extra={"task": name, "event": "task.skipped"},
            )
            MetricsService.observe_task(task=name, outcome="skipped", duration_ms=0)
            return TaskResult(name=name, ran=False)

        try:
            details = await fn(session)
            await session.commit()
            duration = int((time.perf_counter() - started) * 1000)
            logger.info(
                "task completed",
                extra={
                    "task": name,
                    "event": "task.completed",
                    "duration_ms": duration,
                    # Nested, never splatted. A task is free to return any key
                    # it likes, and `logging.makeRecord` raises KeyError if one
                    # collides with a reserved LogRecord attribute — `created`,
                    # `name`, `module`, `filename`. `ensure_partitions` returns
                    # exactly such a key, so splatting turned the most
                    # consequential task in the system into a hard failure at
                    # INFO level, which is to say in production only.
                    "details": details,
                },
            )
            MetricsService.observe_task(task=name, outcome="ok", duration_ms=duration)
            return TaskResult(name=name, ran=True, duration_ms=duration, details=details)
        except Exception as exc:  # noqa: BLE001 - a task must not kill the scheduler
            await session.rollback()
            duration = int((time.perf_counter() - started) * 1000)
            logger.exception(
                "task failed",
                extra={"task": name, "event": "task.failed", "duration_ms": duration},
            )
            MetricsService.observe_task(task=name, outcome="failed", duration_ms=duration)
            return TaskResult(name=name, ran=True, duration_ms=duration, error=str(exc))
        finally:
            await _unlock(session, name)


# --- 1. auto-expire -------------------------------------------------------


async def expire_jobs(session: AsyncSession) -> dict[str, Any]:
    """Move published listings past their expiry date to `expired`.

    Idempotent because the query asks what is *currently* overdue and
    published. A second run finds nothing, having already moved them.

    Deliberately not a bulk UPDATE: the status machine, the audit entry and the
    category counters all live in `JobService`, and reimplementing them in SQL
    here is how the two versions drift apart.
    """
    from app.services.job_service import JobService

    jobs = JobRepository(session)
    service = JobService(session)
    today = datetime.now(UTC).date()

    due = await jobs.list_expiring(on_or_before=today)
    expired: list[str] = []
    for job in due:
        job.status = JobStatus.EXPIRED
        await service.audit.record(
            admin_id=None,
            action="job.expire",
            entity_type="job",
            entity_id=job.id,
            before={"status": JobStatus.PUBLISHED.value},
            after={"status": JobStatus.EXPIRED.value, "reason": "expiry_date_passed"},
        )
        expired.append(job.slug)

    await session.flush()
    return {"expired": len(expired), "slugs": expired[:20]}


# --- 2. analytics rollups -------------------------------------------------


async def rebuild_rollups(session: AsyncSession) -> dict[str, Any]:
    """Recompute today and yesterday.

    Today is always incomplete, so it is rebuilt rather than finalised.
    Yesterday is included because an event can arrive slightly late — a batch
    queued while the browser was offline — and would otherwise be missing from
    a day nobody ever recomputes.
    """
    service = AnalyticsService(session)
    written = await service.rebuild_rollups(days=2)
    return {"days": len(written), "rows": sum(written.values()), "detail": written}


# --- 3. session cleanup ---------------------------------------------------


async def purge_sessions(session: AsyncSession) -> dict[str, Any]:
    """Delete refresh sessions that expired.

    An expired session cannot authenticate anything, so the row carries no
    security value and only grows the table. Revoked-but-unexpired rows stay:
    they are the evidence for "when was I signed out, and why".
    """
    repo = SessionRepository(session)
    removed = await repo.purge_expired()
    return {"removed": removed}


# --- 4. search log cleanup ------------------------------------------------


async def prune_telemetry(session: AsyncSession) -> dict[str, Any]:
    """Retention by partition, not by DELETE.

    Dropping a partition is a catalogue update. Deleting six months of rows is
    a long transaction, a table lock, and a vacuum problem afterwards — which
    is the entire reason both tables were partitioned in the first place.
    """
    repo = AnalyticsRepository(session)
    now = datetime.now(UTC).date()
    dropped: dict[str, list[str]] = {}

    dropped["analytics_events"] = await repo.drop_partitions_before(
        "analytics_events", now - timedelta(days=settings.analytics_retention_days)
    )
    dropped["search_logs"] = await repo.drop_partitions_before(
        "search_logs", now - timedelta(days=settings.search_log_retention_days)
    )
    rollups_removed = await repo.delete_rollups_before(
        now - timedelta(days=settings.rollup_retention_days)
    )
    return {
        "partitions_dropped": sum(len(v) for v in dropped.values()),
        "detail": dropped,
        "rollup_rows_removed": rollups_removed,
    }


# --- 5. partition window --------------------------------------------------


async def ensure_partitions(session: AsyncSession) -> dict[str, Any]:
    """Keep the partition window ahead of now.

    The single most consequential task here. A partitioned table with no
    partition covering the incoming row **rejects the insert** — analytics
    ingest and search logging both stop, at midnight on the first of a month,
    with no warning beforehand. Runs hourly because the cost is a catalogue
    lookup and the cost of it not having run is an outage.
    """
    repo = AnalyticsRepository(session)
    today = datetime.now(UTC).date().replace(day=1)
    created: list[str] = []

    for parent in PARTITIONED_TABLES:
        existing = set(await repo.partition_months(parent))
        month = today
        for _ in range(settings.partition_months_ahead + 1):
            name = await repo.ensure_month_partition(parent, month)
            if name not in existing:
                created.append(name)
            # First of next month, without needing calendar arithmetic.
            month = (month + timedelta(days=32)).replace(day=1)

    if created:
        logger.info(
            "created partitions", extra={"event": "partition.created", "partitions": created}
        )
    return {"created": len(created), "partitions": created}


# --- 6. report escalation -------------------------------------------------


async def alert_on_reports(session: AsyncSession) -> dict[str, Any]:
    """Surface listings that have accumulated open reports.

    Emits a structured log line rather than sending mail: there is no mail
    infrastructure, and inventing one here would be the wrong place for it. The
    log line carries everything an alerting rule needs, so the routing decision
    stays with whoever operates the platform.

    Idempotent in the sense that matters — it reads and reports, changing
    nothing. Running it twice produces two identical alerts, which is what an
    alerting system is built to deduplicate.
    """
    threshold = settings.report_alert_threshold
    rows = await session.execute(
        text(
            """
            SELECT r.job_id, j.slug, j.title, count(*) AS open_reports,
                   array_agg(DISTINCT CAST(r.reason AS text)) AS reasons
              FROM reports r
              JOIN jobs j ON j.id = r.job_id
             WHERE r.status = :open_status
               AND j.deleted_at IS NULL
             GROUP BY r.job_id, j.slug, j.title
            HAVING count(*) >= :threshold
             ORDER BY count(*) DESC
             LIMIT 50
            """
        ),
        {"open_status": ReportStatus.OPEN.value, "threshold": threshold},
    )
    flagged = [
        {"job_id": str(r[0]), "slug": r[1], "title": r[2], "open_reports": r[3], "reasons": r[4]}
        for r in rows.all()
    ]

    for entry in flagged:
        logger.warning(
            "listing has reached the report threshold",
            extra={
                "event": "report.threshold_reached",
                "threshold": threshold,
                **entry,
            },
        )
    return {"flagged": len(flagged), "threshold": threshold, "jobs": flagged[:20]}


# --- 7. autocomplete vocabulary -------------------------------------------


async def refresh_suggestions(session: AsyncSession) -> dict[str, Any]:
    """Rebuild the two materialised vocabularies the typeahead reads.

    Neither can be queried live inside the endpoint's 100ms budget. Skills are
    a JSONB array on `jobs` with no index a per-keystroke unnest could use;
    query popularity is an aggregate over a table partitioned by month. Both
    change on the scale of hours, not keystrokes, so they are rebuilt here and
    read as plain indexed tables on the request path.

    A rebuild rather than an incremental update, because both sources can lose
    rows: a skill nobody lists any more, and a query nobody runs any more, must
    both stop being suggested.
    """
    repo = SuggestRepository(session)
    skills = await repo.rebuild_skill_terms()
    queries = await repo.rebuild_popular_queries()
    await session.commit()
    return {"skill_terms": skills, "popular_queries": queries}


#: Every task, by name. The scheduler registers from this and the CLI runs
#: from it, so there is exactly one list to keep current.
TASKS: dict[str, Callable[[AsyncSession], Awaitable[dict[str, Any]]]] = {
    "expire_jobs": expire_jobs,
    "rebuild_rollups": rebuild_rollups,
    "purge_sessions": purge_sessions,
    "prune_telemetry": prune_telemetry,
    "ensure_partitions": ensure_partitions,
    "alert_on_reports": alert_on_reports,
    "refresh_suggestions": refresh_suggestions,
}


__all__ = ["TASKS", "TaskResult", "run_task"] + list(TASKS)
