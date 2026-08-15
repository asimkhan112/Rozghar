"""Behavioural events and search telemetry.

Both tables are append-only and range-partitioned by month. Partitioning is
what makes retention cheap: dropping a partition is instant, where deleting
ninety days of rows is a long transaction and a vacuum problem.

Neither carries `updated_at` — nothing ever updates these rows.

A partitioned table requires the partition key in every unique constraint, so
the primary key is `(occurred_at, id)` rather than `id` alone. The partitions
themselves are created by migration and by the monthly worker; SQLAlchemy only
describes the parent.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Identity,
    Index,
    Integer,
    SmallInteger,
    String,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.enums import DeviceType, EventType, pg_enum
from app.db.base import Base


class AnalyticsEvent(Base):
    """One user interaction.

    Written in batches off the request path — a failed analytics insert must
    never fail a page view.
    """

    __tablename__ = "analytics_events"

    id: Mapped[int] = mapped_column(BigInteger(), Identity(), primary_key=True)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), primary_key=True, nullable=False, server_default=func.now()
    )

    event_type: Mapped[EventType] = mapped_column(pg_enum(EventType, "event_type"), nullable=False)
    #: Anonymous, client-generated, rotates when the browser is cleared.
    session_id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), nullable=False)

    job_id: Mapped[UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("jobs.id", ondelete="SET NULL"), nullable=True
    )
    #: Copied at write time rather than joined at read time — attribution has
    #: to survive a later re-categorisation of the job.
    source_id: Mapped[UUID | None] = mapped_column(PgUUID(as_uuid=True), nullable=True)
    category_id: Mapped[UUID | None] = mapped_column(PgUUID(as_uuid=True), nullable=True)

    filters: Mapped[dict | None] = mapped_column(JSONB(), nullable=True)
    referrer_host: Mapped[str | None] = mapped_column(String(255), nullable=True)
    device_type: Mapped[DeviceType | None] = mapped_column(
        pg_enum(DeviceType, "device_type"), nullable=True
    )
    country: Mapped[str | None] = mapped_column(String(2), nullable=True)

    __table_args__ = (
        Index(
            "ix_analytics_events_job_type_time", "job_id", "event_type", text("occurred_at DESC")
        ),
        Index("ix_analytics_events_type_time", "event_type", text("occurred_at DESC")),
        Index("ix_analytics_events_session_time", "session_id", "occurred_at"),
        {"postgresql_partition_by": "RANGE (occurred_at)"},
    )


class SearchLog(Base):
    """One search execution.

    Kept out of `analytics_events` on purpose: these rows carry fields no other
    event has — result count, degradation flag, clicked position, latency — and
    folding them in would produce a mostly-null wide table needing a partial
    index on every query. `click_position` is what makes relevance tuning
    measurable later instead of a matter of opinion.
    """

    __tablename__ = "search_logs"

    id: Mapped[int] = mapped_column(BigInteger(), Identity(), primary_key=True)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), primary_key=True, nullable=False, server_default=func.now()
    )

    session_id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), nullable=False)
    raw_query: Mapped[str] = mapped_column(String(200), nullable=False)
    #: Lowercased, trimmed, whitespace-collapsed — the grouping key for the
    #: "top queries" and "zero result queries" reports.
    normalised_query: Mapped[str] = mapped_column(String(200), nullable=False)
    filters: Mapped[dict] = mapped_column(
        JSONB(), nullable=False, server_default=text("'{}'::jsonb")
    )

    result_count: Mapped[int] = mapped_column(Integer(), nullable=False)
    #: True when the trigram or relaxed-filter fallback produced the results.
    was_degraded: Mapped[bool] = mapped_column(
        Boolean(), nullable=False, server_default=text("false")
    )

    #: Set by a later click event — relevance feedback.
    clicked_job_id: Mapped[UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("jobs.id", ondelete="SET NULL"), nullable=True
    )
    click_position: Mapped[int | None] = mapped_column(SmallInteger(), nullable=True)
    response_ms: Mapped[int | None] = mapped_column(Integer(), nullable=True)

    __table_args__ = (
        CheckConstraint("result_count >= 0", name="result_count_non_negative"),
        CheckConstraint(
            "click_position IS NULL OR click_position > 0", name="click_position_positive"
        ),
        Index("ix_search_logs_normalised_query_time", "normalised_query", text("occurred_at DESC")),
        # Partial index dedicated to the zero-result report, which is the
        # single most actionable search metric.
        Index(
            "ix_search_logs_zero_results",
            text("occurred_at DESC"),
            postgresql_where=text("result_count = 0"),
        ),
        {"postgresql_partition_by": "RANGE (occurred_at)"},
    )


__all__ = ["AnalyticsEvent", "SearchLog"]
