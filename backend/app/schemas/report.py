"""Report schemas."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import EmailStr, Field, model_validator

from app.core.enums import TERMINAL_REPORT_STATUSES, ReportReason, ReportStatus
from app.schemas.common import ORMModel, StrictModel


class ReportCreate(StrictModel):
    """Public submission.

    `reporter_ip_hash` is absent by design — it is derived server-side from the
    connection. A client-supplied value would make rate limiting trivially
    bypassable.
    """

    job_id: UUID
    reason: ReportReason
    comment: str | None = Field(default=None, max_length=1000)
    reporter_email: EmailStr | None = None
    session_id: UUID | None = None

    @model_validator(mode="after")
    def other_requires_comment(self) -> ReportCreate:
        """Mirrors the database CHECK — "other" with no explanation is noise
        in the moderation queue."""
        if self.reason == ReportReason.OTHER and not (self.comment or "").strip():
            raise ValueError("comment is required when reason is 'other'")
        return self


class ReportUpdate(StrictModel):
    """Moderation action.

    Both fields are optional so the two real actions are both expressible: a
    transition (with a note, when the destination is terminal) and a correction
    to an existing note. An empty body is rejected rather than treated as a
    no-op, because it is always a client bug.
    """

    status: ReportStatus | None = None
    resolution_note: str | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def coherent_action(self) -> ReportUpdate:
        if self.status is None and self.resolution_note is None:
            raise ValueError("supply a status, a resolution_note, or both")

        note = (self.resolution_note or "").strip()
        if self.status in TERMINAL_REPORT_STATUSES and not note:
            raise ValueError("resolution_note is required when resolving or dismissing")

        # Reopening clears the resolution fields, so a note sent alongside a
        # non-terminal status would be written and immediately discarded.
        # Failing is honest; silently dropping it is not.
        if self.status is not None and self.status not in TERMINAL_REPORT_STATUSES and note:
            raise ValueError(
                "resolution_note cannot be set when moving a report out of a resolved state"
            )
        return self


class ReportJobRef(ORMModel):
    """Minimal job reference embedded in a moderation row, so the queue links
    straight to the offending listing."""

    id: UUID
    slug: str
    title: str
    company_name: str


class ReportCreated(ORMModel):
    """Deliberately minimal.

    The submission endpoint is anonymous and unauthenticated, so its response
    is kept to an acknowledgement. Echoing the stored row back would make it a
    read endpoint for anyone who can guess an identifier.
    """

    id: UUID
    status: ReportStatus


class ReportRead(ORMModel):
    """Admin view. Never exposes `reporter_ip_hash` or `session_id`."""

    id: UUID
    reason: ReportReason
    comment: str | None
    status: ReportStatus
    resolution_note: str | None
    resolved_by: UUID | None
    resolved_at: datetime | None
    created_at: datetime
    job: ReportJobRef


class ReportStats(ORMModel):
    open_count: int
    under_review_count: int
    by_reason: dict[str, int]
