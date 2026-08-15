"""Public analytics ingest.

Returns 202, never 4xx for a persistence problem, and never blocks on
anything that is not the insert itself. A dropped event costs a decimal place
in a report; a 500 here costs a reader the page they were looking at.
"""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, Header, Request, status

from app.api.v1.deps import DbSession
from app.schemas.analytics import EventBatch, IngestAccepted
from app.services.analytics_service import AnalyticsService
from app.services.metrics_service import MetricsService

logger = logging.getLogger(__name__)

router = APIRouter(tags=["analytics"])


def analytics_service(session: DbSession) -> AnalyticsService:
    return AnalyticsService(session)


ServiceDep = Annotated[AnalyticsService, Depends(analytics_service)]


@router.post(
    "/analytics/events",
    response_model=IngestAccepted,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Record a batch of behavioural events",
)
async def ingest_events(
    payload: EventBatch,
    request: Request,
    service: ServiceDep,
    user_agent: Annotated[str | None, Header(alias="User-Agent")] = None,
    referer: Annotated[str | None, Header(alias="Referer")] = None,
) -> IngestAccepted:
    """Anonymous and batched. Device, referrer host and job attribution are all
    derived server-side — the client reports what happened, never what it
    should be attributed to, because this endpoint needs no credentials and
    attribution decides where acquisition budget goes.

    A batch containing bad rows still writes the good ones, and the response
    says how many of each. Rejecting the whole batch would let one stale client
    build silently zero a day of data.
    """
    try:
        result = await service.ingest(
            session_id=payload.session_id,
            events=payload.events,
            user_agent=user_agent,
            referrer=referer,
            country=request.headers.get("cf-ipcountry"),
        )
        await service.session.commit()
        MetricsService.observe_ingest(accepted=result.accepted, rejected=result.rejected)
        return IngestAccepted(accepted=result.accepted, rejected=result.rejected)
    except Exception:  # noqa: BLE001 - measurement must not break the product
        await service.session.rollback()
        logger.warning(
            "analytics ingest failed",
            extra={"event": "analytics.ingest_failed", "batch_size": len(payload.events)},
            exc_info=True,
        )
        MetricsService.observe_ingest(accepted=0, rejected=len(payload.events))
        return IngestAccepted(accepted=0, rejected=len(payload.events))
