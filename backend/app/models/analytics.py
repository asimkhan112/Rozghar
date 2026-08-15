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

from datetime import date, datetime
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
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
    location_id: Mapped[UUID | None] = mapped_column(PgUUID(as_uuid=True), nullable=True)

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


class AnalyticsDailyRollup(Base):
    """Pre-aggregated daily counters, one row per job per day.

    Raw events answer every question but answer none of them quickly: a ninety
    day dashboard over `analytics_events` scans three partitions and millions
    of rows to produce twenty numbers. This table is that scan, done once by a
    scheduled task.

    **Grain is `(day, job_id)` with `job_id` NOT NULL.** Attribution columns are
    copied down from the events rather than joined from `jobs`, for the same
    reason the events carry them: a job that is re-categorised next month must
    not silently rewrite last month's reporting.

    Search is deliberately absent. `search_logs` already holds result counts,
    degradation flags and latency that no event row has, so search metrics
    aggregate from there. Rolling them in here would create a second source of
    truth for one number, and two sources of truth for one number eventually
    disagree.

    Not partitioned: one row per active job per day is thousands per day, not
    millions, and a plain table with a BRIN-friendly date index stays fast for
    years. Partitioning it would be ceremony.
    """

    __tablename__ = "analytics_daily_rollups"

    day: Mapped[date] = mapped_column(Date(), primary_key=True, nullable=False)
    job_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("jobs.id", ondelete="CASCADE"),
        primary_key=True,
        nullable=False,
    )

    #: Attribution as it stood when the events happened.
    source_id: Mapped[UUID | None] = mapped_column(PgUUID(as_uuid=True), nullable=True)
    category_id: Mapped[UUID | None] = mapped_column(PgUUID(as_uuid=True), nullable=True)
    location_id: Mapped[UUID | None] = mapped_column(PgUUID(as_uuid=True), nullable=True)

    views: Mapped[int] = mapped_column(Integer(), nullable=False, server_default=text("0"))
    apply_clicks: Mapped[int] = mapped_column(Integer(), nullable=False, server_default=text("0"))
    shares: Mapped[int] = mapped_column(Integer(), nullable=False, server_default=text("0"))
    source_clicks: Mapped[int] = mapped_column(Integer(), nullable=False, server_default=text("0"))
    saves: Mapped[int] = mapped_column(Integer(), nullable=False, server_default=text("0"))
    reports: Mapped[int] = mapped_column(Integer(), nullable=False, server_default=text("0"))

    #: Unique sessions that saw this job. Cannot be summed across days without
    #: overcounting a returning visitor — the column is per-day only, and the
    #: reporting layer never adds it up.
    unique_sessions: Mapped[int] = mapped_column(
        Integer(), nullable=False, server_default=text("0")
    )

    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        CheckConstraint(
            "views >= 0 AND apply_clicks >= 0 AND shares >= 0 AND source_clicks >= 0 "
            "AND saves >= 0 AND reports >= 0 AND unique_sessions >= 0",
            name="counts_non_negative",
        ),
        # Every dashboard query is "this date window, ordered by a counter".
        Index("ix_analytics_daily_rollups_day", text("day DESC")),
        Index("ix_analytics_daily_rollups_source_day", "source_id", text("day DESC")),
        Index("ix_analytics_daily_rollups_category_day", "category_id", text("day DESC")),
    )


__all__ = ["AnalyticsDailyRollup", "AnalyticsEvent", "SearchLog"]
