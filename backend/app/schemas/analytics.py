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
    shares: int
    source_clicks: int
    saves: int
    reports: int
    #: From `search_logs`, not from the rollups — that table knows result
    #: counts and latency, which no event row does.
    searches: int
    zero_result_searches: int


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
    company_name: str
    views: int
    apply_clicks: int
    ctr: float


class TopQuery(ORMModel):
    query: str
    count: int
    zero_result_count: int


class SourcePerformance(ORMModel):
    source_id: UUID
    name: str
    slug: str
    jobs: int
    views: int
    apply_clicks: int
    source_clicks: int
    reports: int
    ctr: float
    #: Applies per listing published. A feed with ten thousand listings and no
    #: applies looks healthy on totals and terrible here, which is the point.
    apply_rate_per_job: float
    report_rate: float


class AnalyticsOverview(ORMModel):
    range: AnalyticsRange
    totals: AnalyticsTotals
    rates: AnalyticsRates
    series: list[SeriesPoint] = Field(default_factory=list)
    top_jobs: list[TopJob] = Field(default_factory=list)
    top_queries: list[TopQuery] = Field(default_factory=list)


class ZeroResultQuery(ORMModel):
    query: str
    count: int


class SearchAnalytics(ORMModel):
    range: AnalyticsRange
    total_searches: int
    zero_result_searches: int
    zero_result_rate: float
    latency_p50_ms: float
    latency_p95_ms: float
    top_queries: list[TopQuery] = Field(default_factory=list)
    zero_result_queries: list[ZeroResultQuery] = Field(default_factory=list)


class IngestAccepted(ORMModel):
    """Counts rather than an empty 202.

    A client that is silently having every event rejected — a stale build
    sending a retired event name, a clock that is days out — otherwise has no
    way to find out.
    """

    accepted: int
    rejected: int
