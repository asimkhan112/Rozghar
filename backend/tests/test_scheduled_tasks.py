"""Milestone 7 behavioural tests.

Scheduled work fails differently from request work: nobody is watching, and a
task that silently does its job twice looks identical to one that does it once.
These tests therefore lean on the two properties that make that survivable —
idempotency and the advisory lock — rather than on happy paths.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, date, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import delete, select, text

from app.core.enums import JobStatus, ReportStatus
from app.core.permissions import SystemRole
from app.core.security import hash_password
from app.db.database import SessionFactory
from app.models.admin import Admin, AdminSession
from app.models.audit import AuditLog
from app.models.job import Job
from app.models.rbac import Role
from app.models.report import Report
from app.models.taxonomy import Category, Location, Source
from app.tasks.scheduled_tasks import (
    TASKS,
    _lock_key,
    alert_on_reports,
    ensure_partitions,
    expire_jobs,
    purge_sessions,
    run_task,
)
from app.tasks.scheduler import SCHEDULE, SchedulerHandle

ADMIN_EMAIL = "m7-admin@plenilo.com"
PASSWORD = "milestone-seven-pass"


async def _seed() -> dict:
    async with SessionFactory() as s:
        existing = (
            await s.execute(select(Admin).where(Admin.email == ADMIN_EMAIL))
        ).scalar_one_or_none()
        if existing:
            await s.execute(delete(AdminSession).where(AdminSession.admin_id == existing.id))
            await s.execute(delete(AuditLog).where(AuditLog.admin_id == existing.id))
            await s.execute(
                delete(Report).where(
                    Report.job_id.in_(select(Job.id).where(Job.created_by == existing.id))
                )
            )
            await s.execute(delete(Job).where(Job.created_by == existing.id))
            await s.delete(existing)
        await s.commit()

        role = (
            await s.execute(select(Role).where(Role.key == SystemRole.ADMIN.value))
        ).scalar_one()
        admin = Admin(
            email=ADMIN_EMAIL,
            full_name="M7 Admin",
            password_hash=hash_password(PASSWORD),
            role_id=role.id,
            is_active=True,
        )
        s.add(admin)

        category = (
            await s.execute(select(Category).where(Category.slug == "m7-tech"))
        ).scalar_one_or_none() or Category(name="M7 Tech", slug="m7-tech", job_count=0)
        location = (
            await s.execute(select(Location).where(Location.slug == "m7-multan"))
        ).scalar_one_or_none() or Location(
            city="Multan", country="PK", slug="m7-multan", display_name="Multan, PK", job_count=0
        )
        s.add_all([category, location])
        source = (await s.execute(select(Source).where(Source.slug == "manual"))).scalar_one()
        await s.flush()

        def job(slug: str, **extra) -> Job:
            return Job(
                slug=slug,
                title=f"Task Role {slug}",
                company_name="Scheduler Co",
                category_id=category.id,
                location_id=location.id,
                source_id=source.id,
                work_type="remote",
                employment_type="full_time",
                experience_level="mid",
                description=(
                    "A listing used by the Milestone 7 scheduler tests. It needs at "
                    "least fifty characters to satisfy the description constraint."
                ),
                apply_url="https://example.com/apply",
                status=JobStatus.PUBLISHED,
                published_at=datetime.now(UTC),
                created_by=admin.id,
                **extra,
            )

        overdue = job("m7-overdue", expiry_date=date.today() - timedelta(days=1))
        current = job("m7-current", expiry_date=date.today() + timedelta(days=30))
        reported = job("m7-reported")
        s.add_all([overdue, current, reported])
        await s.flush()

        # Three open reports — the escalation threshold.
        for _ in range(3):
            s.add(
                Report(
                    job_id=reported.id,
                    reason="broken_link",
                    reporter_ip_hash="x" * 64,
                    session_id=uuid4(),
                    status=ReportStatus.OPEN,
                )
            )

        # An expired session, and a live one that must survive the purge.
        # `issued_at` has to be set explicitly: it server-defaults to now(),
        # and ck_admin_sessions_expiry_after_issue would reject a row that
        # expired before it was issued.
        s.add(
            AdminSession(
                admin_id=admin.id,
                token_hash="a" * 64,
                family_id=uuid4(),
                issued_at=datetime.now(UTC) - timedelta(days=2),
                expires_at=datetime.now(UTC) - timedelta(days=1),
            )
        )
        s.add(
            AdminSession(
                admin_id=admin.id,
                token_hash="b" * 64,
                family_id=uuid4(),
                expires_at=datetime.now(UTC) + timedelta(days=1),
            )
        )
        await s.commit()

        return {
            "admin_id": str(admin.id),
            "overdue": str(overdue.id),
            "current": str(current.id),
            "reported": str(reported.id),
        }


@pytest.fixture
def world():
    return asyncio.run(_seed())


def run(name: str, fn) -> object:
    return asyncio.run(run_task(name, fn))


def job_status(job_id: str) -> str:
    async def read():
        async with SessionFactory() as s:
            return (
                await s.execute(text("SELECT status FROM jobs WHERE id = :i"), {"i": job_id})
            ).scalar_one()

    return asyncio.run(read())


# --- auto-expire ----------------------------------------------------------


def test_expire_jobs_only_touches_overdue_listings(world):
    result = run("expire_jobs", expire_jobs)
    assert result.ok, result.error
    assert job_status(world["overdue"]) == "expired"
    assert job_status(world["current"]) == "published"


def test_expire_jobs_is_idempotent(world):
    first = run("expire_jobs", expire_jobs)
    second = run("expire_jobs", expire_jobs)
    assert first.details["expired"] >= 1
    assert second.details["expired"] == 0, "a second run must find nothing left to do"


def test_expiry_is_audited_without_an_admin(world):
    """No human took this action, so `admin_id` is null — but the trail still
    has to record that it happened and why."""
    run("expire_jobs", expire_jobs)

    async def read():
        async with SessionFactory() as s:
            return (
                (
                    await s.execute(
                        select(AuditLog).where(
                            AuditLog.entity_id == world["overdue"], AuditLog.action == "job.expire"
                        )
                    )
                )
                .scalars()
                .all()
            )

    rows = asyncio.run(read())
    assert len(rows) == 1
    assert rows[0].admin_id is None
    assert rows[0].after["reason"] == "expiry_date_passed"


# --- session cleanup ------------------------------------------------------


def test_purge_removes_expired_sessions_and_keeps_live_ones(world):
    result = run("purge_sessions", purge_sessions)
    assert result.details["removed"] >= 1

    async def read():
        async with SessionFactory() as s:
            return (
                (
                    await s.execute(
                        select(AdminSession.token_hash).where(
                            AdminSession.admin_id == world["admin_id"]
                        )
                    )
                )
                .scalars()
                .all()
            )

    remaining = asyncio.run(read())
    assert "b" * 64 in remaining, "an unexpired session must survive"
    assert "a" * 64 not in remaining


# --- partitions -----------------------------------------------------------


def test_ensure_partitions_keeps_the_window_ahead(world):
    """The most consequential task here: a partitioned table with no matching
    partition rejects the insert outright, so ingest stops dead at midnight on
    the first of a month."""
    result = run("ensure_partitions", ensure_partitions)
    assert result.ok, result.error

    async def read():
        async with SessionFactory() as s:
            return (
                (
                    await s.execute(
                        text(
                            "SELECT c.relname FROM pg_inherits i "
                            "JOIN pg_class c ON c.oid = i.inhrelid "
                            "JOIN pg_class p ON p.oid = i.inhparent "
                            "WHERE p.relname = 'analytics_events'"
                        )
                    )
                )
                .scalars()
                .all()
            )

    names = asyncio.run(read())
    future = (date.today().replace(day=1) + timedelta(days=95)).strftime("%Y_%m")
    assert f"analytics_events_{future}" in names


def test_ensure_partitions_is_idempotent(world):
    run("ensure_partitions", ensure_partitions)
    second = run("ensure_partitions", ensure_partitions)
    assert second.details["created"] == 0


# --- report escalation ----------------------------------------------------


def test_report_threshold_flags_the_listing(world):
    result = run("alert_on_reports", alert_on_reports)
    assert result.ok, result.error
    flagged = {j["job_id"] for j in result.details["jobs"]}
    assert world["reported"] in flagged


# --- the lock -------------------------------------------------------------


def test_concurrent_runs_are_serialised_by_the_advisory_lock():
    """APScheduler runs in-process, so N uvicorn workers means N firings of
    every trigger. Without this, `rebuild_rollups` would run four times
    concurrently over the same rows."""

    async def slow(_session):
        await asyncio.sleep(1.0)
        return {"worked": True}

    async def race():
        return await asyncio.gather(
            run_task("lock_test", slow),
            run_task("lock_test", slow),
            run_task("lock_test", slow),
        )

    results = asyncio.run(race())
    assert sum(1 for r in results if r.ran) == 1, "exactly one instance should do the work"


def test_lock_key_is_stable_across_processes():
    """Not `hash()` — that is salted per process, so two workers would compute
    different keys for the same task and both would take "the" lock."""
    assert _lock_key("rebuild_rollups") == _lock_key("rebuild_rollups")
    assert _lock_key("rebuild_rollups") != _lock_key("expire_jobs")


# --- failure handling -----------------------------------------------------


def test_a_failing_task_is_contained():
    """A task that raises must not take the scheduler down with it."""

    async def broken(_session):
        raise RuntimeError("deliberate")

    result = asyncio.run(run_task("broken_task", broken))
    assert result.ran is True
    assert result.ok is False
    assert "deliberate" in result.error


def test_a_failing_task_rolls_back_its_writes(world):
    async def write_then_fail(session):
        await session.execute(
            text("UPDATE jobs SET title = 'should not persist' WHERE id = :i"),
            {"i": world["current"]},
        )
        raise RuntimeError("after the write")

    asyncio.run(run_task("rollback_probe", write_then_fail))

    async def read():
        async with SessionFactory() as s:
            return (
                await s.execute(
                    text("SELECT title FROM jobs WHERE id = :i"), {"i": world["current"]}
                )
            ).scalar_one()

    assert asyncio.run(read()) != "should not persist"


# --- registration ---------------------------------------------------------


def test_every_scheduled_name_resolves_to_a_task():
    """A typo in the schedule would otherwise be a KeyError at startup, in
    production, on a deploy nobody associates with the scheduler."""
    for name, _, description in SCHEDULE:
        assert name in TASKS, f"{name} is scheduled but not defined"
        assert description, f"{name} has no description"


def test_scheduler_handle_reports_state_without_starting():
    handle = SchedulerHandle()
    assert handle.running is False
    assert handle.jobs() == []
