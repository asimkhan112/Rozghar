"""Analytics dashboards.

Every endpoint takes the same optional `from`/`to` window, clamped in the
service. An unbounded range is not a feature — it is a table scan any client
can trigger by omitting a parameter.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.api.v1.deps import CacheDep, DbSession, require
from app.core.permissions import Permission
from app.schemas.analytics import (
    AnalyticsOverview,
    SearchAnalytics,
    SourcePerformance,
    TopJob,
    TrafficSummary,
    VisitorTrends,
)
from app.services.analytics_service import AnalyticsService, resolve_window
from app.services.auth_service import Principal
from app.services.cache_service import TTL_ANALYTICS

router = APIRouter(prefix="/admin/analytics", tags=["admin:analytics"])


def analytics_service(session: DbSession) -> AnalyticsService:
    return AnalyticsService(session)


ServiceDep = Annotated[AnalyticsService, Depends(analytics_service)]
ViewerDep = Annotated[Principal, Depends(require(Permission.ANALYTICS_VIEW))]

FromDate = Annotated[date | None, Query(alias="from")]
ToDate = Annotated[date | None, Query(alias="to")]


@router.get("/overview", response_model=AnalyticsOverview, summary="Dashboard headline metrics")
async def overview(
    service: ServiceDep,
    cache: CacheDep,
    _: ViewerDep,
    from_date: FromDate = None,
    to_date: ToDate = None,
) -> AnalyticsOverview:
    """Cached for ten minutes.

    Safe because the underlying rollups are only rebuilt every fifteen, so a
    cached answer is never more stale than an uncached one would have been.
    """
    window = resolve_window(from_date, to_date)
    key = f"{window.since}:{window.until}"
    data = await cache.get("analytics:overview", key)
    if data is None:
        data = await service.overview(window)
        await cache.set("analytics:overview", data, key, ttl=TTL_ANALYTICS)
    return AnalyticsOverview.model_validate(data)


@router.get("/traffic", response_model=TrafficSummary, summary="Audience and session shape")
async def traffic(
    service: ServiceDep,
    cache: CacheDep,
    _: ViewerDep,
    from_date: FromDate = None,
    to_date: ToDate = None,
) -> TrafficSummary:
    """Sessions, not listings.

    The only dashboard read that touches the raw event partitions: a session
    spans jobs and days, so the per-job daily rollup cannot describe one. Its
    `unique_sessions` column is per-day by construction and summing it would
    count a returning visitor once for every day they came back.

    Cached on the same terms as `/overview`. The events behind it are live
    rather than rebuilt on a schedule, so ten minutes is a real staleness
    budget here rather than a free one — spent deliberately, because this is
    the most expensive query on the dashboard and the tiles it feeds are read
    far more often than they change.
    """
    window = resolve_window(from_date, to_date)
    key = f"{window.since}:{window.until}"
    data = await cache.get("analytics:traffic", key)
    if data is None:
        data = await service.traffic(window)
        await cache.set("analytics:traffic", data, key, ttl=TTL_ANALYTICS)
    return TrafficSummary.model_validate(data)


@router.get("/visitors", response_model=VisitorTrends, summary="Visitors by period")
async def visitor_trends(
    service: ServiceDep,
    cache: CacheDep,
    _: ViewerDep,
) -> VisitorTrends:
    """Takes no window, unlike everything else here.

    Its periods are fixed — today, seven days, thirty days — and each is
    reported against the one before it. A caller-supplied range would make "vs
    last week" mean whatever the caller decided, which is not a comparison.

    Keyed on the date rather than on a window, so the first read after midnight
    UTC misses rather than serving yesterday's card under today's label.
    """
    data = await cache.get("analytics:visitors", str(datetime.now(UTC).date()))
    if data is None:
        data = await service.visitor_trends()
        await cache.set("analytics:visitors", data, str(data["as_of"]), ttl=TTL_ANALYTICS)
    return VisitorTrends.model_validate(data)


@router.get("/jobs", response_model=list[TopJob], summary="Per-listing performance")
async def job_performance(
    service: ServiceDep,
    cache: CacheDep,
    _: ViewerDep,
    from_date: FromDate = None,
    to_date: ToDate = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> list[TopJob]:
    window = resolve_window(from_date, to_date)
    key = f"{window.since}:{window.until}:{limit}"
    rows = await cache.get("analytics:jobs", key)
    if rows is None:
        rows = await service.job_performance(window, limit=limit)
        await cache.set("analytics:jobs", rows, key, ttl=TTL_ANALYTICS)
    return [TopJob.model_validate(row) for row in rows]


@router.get("/sources", response_model=list[SourcePerformance], summary="Per-source funnel")
async def source_performance(
    service: ServiceDep,
    _: ViewerDep,
    from_date: FromDate = None,
    to_date: ToDate = None,
) -> list[SourcePerformance]:
    """Includes sources with no activity in the window. A feed that published
    a thousand listings and earned two clicks has to be visible as such, and it
    would be absent from an inner join."""
    rows = await service.source_performance(resolve_window(from_date, to_date))
    return [SourcePerformance.model_validate(row) for row in rows]


@router.get("/search", response_model=SearchAnalytics, summary="Search health")
async def search_analytics(
    service: ServiceDep,
    _: ViewerDep,
    from_date: FromDate = None,
    to_date: ToDate = None,
) -> SearchAnalytics:
    """Reads `search_logs` rather than the rollups: result counts, degradation
    and latency exist only there."""
    data = await service.search_analytics(resolve_window(from_date, to_date))
    return SearchAnalytics.model_validate(data)
