"""Analytics dashboards.

Every endpoint takes the same optional `from`/`to` window, clamped in the
service. An unbounded range is not a feature — it is a table scan any client
can trigger by omitting a parameter.
"""

from __future__ import annotations

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.api.v1.deps import CacheDep, DbSession, require
from app.core.permissions import Permission
from app.schemas.analytics import (
    AnalyticsOverview,
    SearchAnalytics,
    SourcePerformance,
    TopJob,
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
