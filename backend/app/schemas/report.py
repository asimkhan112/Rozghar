"""Report schemas."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import EmailStr, Field, model_validator

from app.core.enums import ReportReason, ReportStatus
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
    """Moderation action."""

    status: ReportStatus
    resolution_note: str | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def terminal_requires_note(self) -> ReportUpdate:
        if (
            self.status in {ReportStatus.RESOLVED, ReportStatus.DISMISSED}
            and not (self.resolution_note or "").strip()
        ):
            raise ValueError("resolution_note is required when resolving or dismissing")
        return self


class ReportJobRef(ORMModel):
    """Minimal job reference embedded in a moderation row, so the queue links
    straight to the offending listing."""

    id: UUID
    slug: str
    title: str
    company_name: str


class ReportCreated(ORMModel):
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
    in_review_count: int
    by_reason: dict[str, int]
