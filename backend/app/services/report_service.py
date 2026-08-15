"""Report business rules: submission gating, the moderation workflow, audit.

Two audiences share one table and have almost nothing else in common. A
reporter is anonymous, untrusted, and rate limited; a moderator is
authenticated, permissioned, and every action they take is recorded. The split
runs through this file: `submit` guards the public write, everything else
serves the queue.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.enums import TERMINAL_REPORT_STATUSES, JobStatus, ReportStatus
from app.core.exceptions import Conflict, DomainError, NotFound, RateLimited
from app.models.job import Job
from app.models.report import Report
from app.repositories.report_repo import ReportFilters, ReportRepository
from app.services.audit_service import AuditService
from app.services.auth_service import Principal

logger = logging.getLogger(__name__)

#: Which workflow transitions are legal. Anything absent is rejected.
#:
#: Both terminal states can return to review, and deliberately do not lead
#: straight back to `open`. A listing whose apply link was fixed can break
#: again a week later, so a resolved report has to be reopenable — but it
#: reopens onto the desk of whoever reopened it, not back into the anonymous
#: queue where the earlier investigation would be repeated from scratch.
ALLOWED_TRANSITIONS: dict[ReportStatus, frozenset[ReportStatus]] = {
    ReportStatus.OPEN: frozenset(
        {ReportStatus.UNDER_REVIEW, ReportStatus.RESOLVED, ReportStatus.DISMISSED}
    ),
    ReportStatus.UNDER_REVIEW: frozenset(
        {ReportStatus.OPEN, ReportStatus.RESOLVED, ReportStatus.DISMISSED}
    ),
    ReportStatus.RESOLVED: frozenset({ReportStatus.UNDER_REVIEW}),
    ReportStatus.DISMISSED: frozenset({ReportStatus.UNDER_REVIEW}),
}

#: A report edited without a status change. Recorded because a resolution note
#: is the institutional memory of why a listing was left alone.
_AUDIT_NOTE_EDIT = "report.note_edit"


def _audit_action(current: ReportStatus, target: ReportStatus) -> str:
    """The verb for a transition — distinct per event, not per destination.

    Keyed on the pair rather than the destination alone because two arrivals at
    `under_review` mean different things: picking a new report off the queue is
    routine, while reopening one that was already decided says the earlier
    decision was wrong. An audit trail that calls both "review" cannot answer
    the second question at all, and that is the question worth asking.

    Distinct verbs rather than one `report.update` because `action` is indexed:
    "how many did we dismiss last month?" stays a filter instead of becoming a
    scan through JSONB diffs.
    """
    if target is ReportStatus.RESOLVED:
        return "report.resolve"
    if target is ReportStatus.DISMISSED:
        return "report.dismiss"
    if current in TERMINAL_REPORT_STATUSES:
        return "report.reopen"
    if target is ReportStatus.UNDER_REVIEW:
        return "report.review"
    # under_review -> open: handed back to the unclaimed queue.
    return "report.release"


#: The fields worth auditing. `reporter_ip_hash` and `session_id` are excluded
#: deliberately — copying a reporter's identifiers into a second table that
#: admins can browse would undo the point of hashing them.
_AUDITED_FIELDS = ("status", "resolution_note", "resolved_by", "resolved_at")


class InvalidTransition(DomainError):
    status = 422
    code = "invalid_report_transition"
    title = "Report status transition is not allowed"


class DuplicateReport(Conflict):
    code = "duplicate_report"
    title = "This listing has already been reported"


@dataclass(frozen=True)
class ReportPage:
    items: list[Report]
    total: int
    page: int
    per_page: int

    @property
    def total_pages(self) -> int:
        return (self.total + self.per_page - 1) // self.per_page if self.per_page else 0

    @property
    def has_more(self) -> bool:
        return self.page * self.per_page < self.total


def _snapshot(report: Report) -> dict[str, Any]:
    return {field: getattr(report, field) for field in _AUDITED_FIELDS}


class ReportService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.reports = ReportRepository(session)
        self.audit = AuditService(session)

    # --- public submission ------------------------------------------------

    async def submit(
        self,
        data: dict[str, Any],
        *,
        ip_hash: str | None,
    ) -> Report:
        """Accept a public report, or explain why not.

        Deliberately no audit entry. The audit trail exists so privileged
        actions can be attributed to the person who took them; a submission
        already *is* its own record, with a timestamp and an address hash, in a
        table admins read directly. Mirroring every one of them into
        `audit_logs` would bury the moderator actions the trail is for.
        """
        job_id: UUID = data["job_id"]
        session_id: UUID | None = data.get("session_id")

        await self._assert_reportable(job_id)
        await self._assert_within_rate_limit(ip_hash)

        if await self.reports.open_report_exists(
            job_id=job_id, session_id=session_id, ip_hash=ip_hash
        ):
            # Phrased for both cases. With a session id this really is the
            # same reporter; without one it may be a colleague behind the same
            # office NAT — and either way the listing already has an open
            # report saying the same thing, so nothing is lost by declining.
            raise DuplicateReport(
                "There is already an open report on this listing from this "
                "connection. Our team has it."
            )

        report = Report(
            job_id=job_id,
            reason=data["reason"],
            comment=data.get("comment"),
            reporter_email=data.get("reporter_email"),
            reporter_ip_hash=ip_hash or "",
            session_id=session_id,
            status=ReportStatus.OPEN,
        )
        self.reports.add(report)
        try:
            await self.session.flush()
        except IntegrityError as exc:
            await self.session.rollback()
            # The partial unique index is the authoritative duplicate check;
            # the query above is an optimisation that loses a race.
            if "uq_reports_job_session_open" in str(exc.orig):
                raise DuplicateReport("There is already an open report on this listing.") from exc
            raise
        return report

    async def _assert_reportable(self, job_id: UUID) -> None:
        """The listing must exist, be live, and have been public.

        Drafts and scheduled listings are indistinguishable from unknown IDs
        here on purpose: a 422 saying "that job is not published yet" turns
        this endpoint into an oracle for the editorial pipeline. Expired
        listings *are* reportable — "this job has expired" is the second most
        common report there is.
        """
        reportable = (
            await self.session.execute(
                select(Job.id).where(
                    Job.id == job_id,
                    Job.deleted_at.is_(None),
                    Job.status.in_((JobStatus.PUBLISHED, JobStatus.EXPIRED)),
                    Job.published_at.is_not(None),
                )
            )
        ).first()
        if reportable is None:
            raise NotFound("That listing does not exist.")

    async def _assert_within_rate_limit(self, ip_hash: str | None) -> None:
        """Sliding window per address hash.

        Backed by the database rather than Redis on purpose: Redis is optional
        in this application and degrades to "off" when unreachable. An abuse
        control that silently stops working when the cache is down is not one.
        """
        if not ip_hash:
            return
        window = settings.report_rate_limit_window_minutes
        recent = await self.reports.count_recent_from(ip_hash, window_minutes=window)
        if recent >= settings.report_rate_limit_per_window:
            raise RateLimited(
                window * 60,
                f"Too many reports from this connection. Try again in {window} minutes.",
            )

    # --- moderation reads -------------------------------------------------

    async def list_queue(self, filters: ReportFilters, *, page: int, per_page: int) -> ReportPage:
        offset = (page - 1) * per_page
        total = await self.reports.count(filters)
        items = await self.reports.list(filters, limit=per_page, offset=offset)
        return ReportPage(items=items, total=total, page=page, per_page=per_page)

    async def get(self, report_id: UUID) -> Report:
        report = await self.reports.get_with_job(report_id)
        if report is None:
            raise NotFound("Report not found.")
        return report

    # --- moderation writes ------------------------------------------------

    async def moderate(
        self,
        report_id: UUID,
        changes: dict[str, Any],
        *,
        principal: Principal,
        ip_hash: str | None = None,
    ) -> Report:
        """Apply a moderation decision.

        The row is locked for the duration, so concurrent decisions serialise
        rather than racing. Returns the updated report; the caller commits.
        """
        report = await self.reports.get_for_update(report_id)
        if report is None:
            raise NotFound("Report not found.")

        before = _snapshot(report)
        # Coerced rather than assumed. Through the API Pydantic has already
        # produced an enum, but this method is also the entry point for the
        # CLI and for background sweeps, and a bare string would slip past the
        # `is` comparisons in `_audit_action` and be filed under the wrong verb
        # — a silent wrong answer, which is worse than the crash.
        raw_status = changes.get("status")
        target = ReportStatus(raw_status) if raw_status is not None else None
        note_supplied = "resolution_note" in changes

        status_changed = target is not None and target != report.status
        if status_changed:
            self._assert_transition(report.status, target)

        if note_supplied:
            report.resolution_note = changes["resolution_note"]

        if status_changed:
            self._apply_transition(report, target, principal=principal)

        after = _snapshot(report)
        if before == after:
            # A PATCH that changes nothing is not an event. Recording it would
            # put noise in the one table that has to stay readable.
            return await self.get(report_id)

        action = _audit_action(before["status"], target) if status_changed else _AUDIT_NOTE_EDIT
        await self.audit.record_change(
            admin_id=principal.admin_id,
            action=action,
            entity_type="report",
            entity_id=report.id,
            before=before,
            after=after,
            ip_hash=ip_hash,
        )
        await self.session.flush()
        return await self.get(report_id)

    def _assert_transition(self, current: ReportStatus, target: ReportStatus) -> None:
        allowed = ALLOWED_TRANSITIONS.get(current, frozenset())
        if target not in allowed:
            raise InvalidTransition(
                f"A report that is {current.value} cannot become {target.value}. "
                f"Allowed from here: {', '.join(sorted(s.value for s in allowed)) or 'none'}."
            )

    def _apply_transition(
        self, report: Report, target: ReportStatus, *, principal: Principal
    ) -> None:
        """Move the report, keeping the resolution fields honest.

        Entering a terminal state stamps who decided and when. Leaving one
        clears all three: a resolution note left on a reopened report reads as
        current guidance, and the next moderator acts on it. Nothing is lost —
        the previous values are in the audit `before` payload, which is where
        superseded state belongs.
        """
        if target in TERMINAL_REPORT_STATUSES:
            report.status = target
            report.resolved_by = principal.admin_id
            report.resolved_at = datetime.now(UTC)
            return

        # Order matters: the CHECK constraint requires a resolver and a note
        # while the status is terminal, so the status has to move first.
        report.status = target
        report.resolved_by = None
        report.resolved_at = None
        report.resolution_note = None


__all__ = ["ReportPage", "ReportService", "ALLOWED_TRANSITIONS"]
