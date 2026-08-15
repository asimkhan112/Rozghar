"""Analytics ingest and reporting schemas."""

from __future__ import annotations

from datetime import date, datetime
from uuid import UUID

from pydantic import Field

from app.core.enums import EventType
from app.schemas.common import ORMModel, StrictModel


class EventIn(StrictModel):
    """One event in an ingest batch.

    Device, country and source attribution are deliberately absent: they are
    enriched server-side. Client-supplied attribution is trivially forgeable
    and must not be trusted for reporting that drives spend decisions.
    """

    type: EventType
    occurred_at: datetime | None = None
    job_id: UUID | None = None
    query: str | None = Field(default=None, max_length=200)
    filters: dict | None = None
    result_count: int | None = Field(default=None, ge=0)


class EventBatch(StrictModel):
    session_id: UUID
    events: list[EventIn] = Field(min_length=1, max_length=50)


class SearchLogRead(ORMModel):
    occurred_at: datetime
    normalised_query: str
    result_count: int
    was_degraded: bool
    click_position: int | None
    response_ms: int | None


class AnalyticsRange(ORMModel):
    from_date: date = Field(alias="from")
    to_date: date = Field(alias="to")


class AnalyticsTotals(ORMModel):
    job_views: int
    apply_clicks: int
    saves: int
    searches: int
    zero_result_searches: int
    reports: int


class AnalyticsRates(ORMModel):
    """Ratios are computed, never stored — storing a derived rate guarantees it
    will disagree with its inputs eventually."""

    view_to_apply: float
    zero_result_rate: float
    save_rate: float


class SeriesPoint(ORMModel):
    date: date
    job_views: int
    apply_clicks: int


class TopJob(ORMModel):
    job_id: UUID
    slug: str
    title: str
    views: int
    apply_clicks: int
    ctr: float


class TopQuery(ORMModel):
    query: str
    count: int
    zero_result_count: int


class SourcePerformance(ORMModel):
    source: str
    jobs: int
    apply_clicks: int
    ctr: float
    report_rate: float


class AnalyticsOverview(ORMModel):
    range: AnalyticsRange
    totals: AnalyticsTotals
    rates: AnalyticsRates
    series: list[SeriesPoint] = Field(default_factory=list)
    top_jobs: list[TopJob] = Field(default_factory=list)
    top_queries: list[TopQuery] = Field(default_factory=list)
    by_source: list[SourcePerformance] = Field(default_factory=list)
