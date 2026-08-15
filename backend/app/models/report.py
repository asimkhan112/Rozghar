"""User-submitted reports about a listing.

The primary quality signal for an aggregator: broken apply links and expired
posts are found by readers long before they are found by staff.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import CITEXT
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.enums import ReportReason, ReportStatus, pg_enum
from app.db.base import Base, CreatedAtMixin, UUIDPkMixin

if TYPE_CHECKING:
    from app.models.job import Job


class Report(UUIDPkMixin, CreatedAtMixin, Base):
    __tablename__ = "reports"

    #: CASCADE: a report about a hard-deleted job has no meaning. Soft deletion
    #: keeps both, which is the normal path.
    job_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False
    )

    reason: Mapped[ReportReason] = mapped_column(
        pg_enum(ReportReason, "report_reason"), nullable=False
    )
    comment: Mapped[str | None] = mapped_column(Text(), nullable=True)

    #: Optional — enables follow-up without requiring an account, which the
    #: product deliberately does not have.
    reporter_email: Mapped[str | None] = mapped_column(CITEXT(), nullable=True)
    #: Hashed, never raw. Enough for rate limiting, not enough to identify.
    reporter_ip_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    #: Anonymous browser session, used to stop one visitor filing the same
    #: report repeatedly.
    session_id: Mapped[UUID | None] = mapped_column(PgUUID(as_uuid=True), nullable=True)

    status: Mapped[ReportStatus] = mapped_column(
        pg_enum(ReportStatus, "report_status"),
        nullable=False,
        server_default=text("'open'"),
    )
    resolution_note: Mapped[str | None] = mapped_column(String(500), nullable=True)
    resolved_by: Mapped[UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("admins.id", ondelete="SET NULL"), nullable=True
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    job: Mapped[Job] = relationship(back_populates="reports", lazy="selectin")

    __table_args__ = (
        CheckConstraint("comment IS NULL OR length(comment) <= 1000", name="comment_length"),
        # A resolved report with no reason recorded is worthless a month later.
        CheckConstraint(
            "status NOT IN ('resolved', 'dismissed') "
            "OR (resolved_by IS NOT NULL AND resolution_note IS NOT NULL)",
            name="terminal_requires_resolution",
        ),
        CheckConstraint(
            "reason <> 'other' OR comment IS NOT NULL",
            name="other_requires_comment",
        ),
        # The moderation queue.
        Index("ix_reports_status_created_at", "status", text("created_at DESC")),
        Index("ix_reports_job_id_status", "job_id", "status"),
        Index(
            "ix_reports_reporter_ip_hash_created_at", "reporter_ip_hash", text("created_at DESC")
        ),
        # One open report per browser session per job.
        Index(
            "uq_reports_job_session_open",
            "job_id",
            "session_id",
            unique=True,
            postgresql_where=text("status = 'open' AND session_id IS NOT NULL"),
        ),
    )


__all__ = ["Report"]
