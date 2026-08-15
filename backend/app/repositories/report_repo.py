"""Report persistence and the moderation queue.

The queue is the only list in the application where the joined entity is
rendered as four fields rather than in full. `Report.job` is `selectin` and
`Job` in turn eager-loads four relations of its own, so the obvious
`select(Report)` costs six queries to populate a job reference the response
truncates to id, slug, title and company. Every read here therefore joins
explicitly and calls `raiseload("*")` on the job, which both collapses that to
one query and makes any future lazy access fail loudly instead of quietly
costing a round trip per row.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import Select, func, select
from sqlalchemy.orm import contains_eager, noload

from app.core.enums import ReportReason, ReportStatus
from app.models.job import Job
from app.models.report import Report
from app.repositories.base import BaseRepository


@dataclass(frozen=True)
class ReportFilters:
    """Moderation queue filters. All optional; absent means "no constraint"."""

    status: ReportStatus | None = None
    reason: ReportReason | None = None
    job_id: UUID | None = None
    created_from: datetime | None = None
    created_to: datetime | None = None


def _job_reference():
    """Load only the columns `ReportJobRef` renders, and nothing beyond it."""
    return (
        contains_eager(Report.job)
        .load_only(Job.id, Job.slug, Job.title, Job.company_name)
        .raiseload("*")
    )


class ReportRepository(BaseRepository[Report]):
    model = Report

    # --- queue ------------------------------------------------------------

    def _apply(self, stmt: Select, filters: ReportFilters) -> Select:
        if filters.status is not None:
            stmt = stmt.where(Report.status == filters.status)
        if filters.reason is not None:
            stmt = stmt.where(Report.reason == filters.reason)
        if filters.job_id is not None:
            stmt = stmt.where(Report.job_id == filters.job_id)
        if filters.created_from is not None:
            stmt = stmt.where(Report.created_at >= filters.created_from)
        if filters.created_to is not None:
            stmt = stmt.where(Report.created_at <= filters.created_to)
        return stmt

    async def count(self, filters: ReportFilters) -> int:
        """No join: counting does not render the job reference."""
        stmt = self._apply(select(func.count()).select_from(Report), filters)
        return (await self.session.execute(stmt)).scalar_one()

    async def list(self, filters: ReportFilters, *, limit: int, offset: int) -> list[Report]:
        """Newest first, served by `ix_reports_status_created_at`.

        `id` breaks ties. Two reports filed in the same millisecond would
        otherwise order arbitrarily and could appear on two pages or neither —
        the classic keyset-free pagination bug. UUIDv7 is time-ordered, so the
        tiebreak agrees with the primary sort rather than fighting it.
        """
        stmt = (
            self._apply(select(Report).join(Report.job), filters)
            .options(_job_reference())
            .order_by(Report.created_at.desc(), Report.id.desc())
            .limit(limit)
            .offset(offset)
        )
        return list((await self.session.execute(stmt)).scalars().unique().all())

    async def get_with_job(self, report_id: UUID) -> Report | None:
        """`populate_existing` because this is also the read-back after a
        moderation write. The row is already in the identity map with its job
        reference unloaded, and without this the loaded-attribute rules would
        keep the stale instance rather than take the freshly joined one."""
        stmt = (
            select(Report)
            .join(Report.job)
            .where(Report.id == report_id)
            .options(_job_reference())
            .execution_options(populate_existing=True)
        )
        return (await self.session.execute(stmt)).scalars().unique().one_or_none()

    async def get_for_update(self, report_id: UUID) -> Report | None:
        """Row-locked read for the moderation PATCH.

        `reports` carries no version column, so there is no optimistic-locking
        path as there is on jobs. Two moderators acting on the same row at the
        same moment are serialised here instead: the second waits, re-reads the
        committed state, and either applies a legal transition or is rejected.
        Without this the loser would write an audit entry describing a
        transition that never happened.

        `of=Report` keeps the lock off `jobs` — a moderator resolving a report
        has no business blocking edits to the listing.

        `noload` on the job because nothing in a transition needs it, and
        `Report.job` is `selectin` — leaving the default would fire five
        further queries to hydrate a listing this method never reads.
        """
        stmt = (
            select(Report)
            .where(Report.id == report_id)
            .options(noload(Report.job))
            .with_for_update(of=Report)
        )
        return (await self.session.execute(stmt)).scalars().one_or_none()

    # --- abuse control ----------------------------------------------------

    async def open_report_exists(
        self, *, job_id: UUID, session_id: UUID | None, ip_hash: str | None
    ) -> bool:
        """Has this reporter already got an open report on this listing?

        The partial unique index covers the session case in the database, but
        only `WHERE session_id IS NOT NULL`. A client that sends no session id
        would otherwise be able to file the same report indefinitely, so the
        address hash is checked here as well.
        """
        stmt = select(Report.id).where(
            Report.job_id == job_id,
            Report.status == ReportStatus.OPEN,
        )
        if session_id is not None:
            stmt = stmt.where(Report.session_id == session_id)
        elif ip_hash is not None:
            stmt = stmt.where(Report.reporter_ip_hash == ip_hash)
        else:  # pragma: no cover - hash_ip only returns None without a client
            return False
        return (await self.session.execute(stmt.limit(1))).first() is not None

    async def count_recent_from(self, ip_hash: str, *, window_minutes: int) -> int:
        """Submissions from one address inside the window.

        Reads `ix_reports_reporter_ip_hash_created_at`, which was built for
        exactly this: the hash narrows to a handful of rows and the descending
        timestamp is already in the index, so the window bound is satisfied
        without touching the heap.
        """
        since = datetime.now(UTC) - timedelta(minutes=window_minutes)
        stmt = select(func.count()).where(
            Report.reporter_ip_hash == ip_hash,
            Report.created_at >= since,
        )
        return (await self.session.execute(stmt)).scalar_one()


__all__ = ["ReportFilters", "ReportRepository"]
