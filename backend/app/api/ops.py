"""Operational endpoints: health, readiness, metrics.

Mounted outside the versioned prefix on purpose. `/health` is wired into an
orchestrator's config and a load balancer's target group; moving it when the
API version changes would mean a coordinated change across infrastructure that
has nothing to do with the API contract.
"""

from __future__ import annotations

import secrets
from typing import Annotated

from fastapi import APIRouter, Depends, Header, Request, Response

from app.api.v1.deps import DbSession, get_redis
from app.core.config import settings
from app.core.exceptions import DomainError
from app.services.health_service import HealthService
from app.services.metrics_service import MetricsService
from app.tasks.scheduler import scheduler_handle

router = APIRouter(tags=["ops"])


class MetricsForbidden(DomainError):
    status = 403
    code = "metrics_forbidden"
    title = "Metrics access denied"


@router.get("/health", summary="Liveness — is this process alive?")
async def health() -> dict[str, str]:
    """Deliberately touches nothing.

    Liveness answers "should this process be restarted?". A check that queries
    Postgres turns a slow database into a restart loop across every instance,
    converting a degradation into an outage. Dependencies belong in `/ready`.
    """
    return {
        "status": "ok",
        "environment": settings.environment,
        "version": settings.app_version,
    }


@router.get("/ready", summary="Readiness — should this instance receive traffic?")
async def ready(
    session: DbSession,
    redis: Annotated[object | None, Depends(get_redis)],
    response: Response,
) -> dict:
    """Checks dependencies, and grades them.

    Postgres is required — an instance that cannot reach it should leave the
    pool. Redis and the scheduler are not: permissions, caching and rate
    limiting all degrade gracefully without Redis by design, and background work
    is protected by an advisory lock so any other instance picks it up. Failing
    readiness on either would remove healthy servers from rotation over
    something they do not need to serve a request.
    """
    report = await HealthService(session, redis, scheduler_handle).readiness()  # type: ignore[arg-type]
    if not report.ready:
        response.status_code = 503
    return report.as_dict()


@router.get("/metrics", summary="Prometheus exposition")
async def metrics(
    request: Request,
    authorization: Annotated[str | None, Header()] = None,
) -> Response:
    """Token-gated when `METRICS_TOKEN` is set.

    The payload reveals route names, traffic shape and error rates — enough to
    fingerprint the application and to watch the effect of an attack in real
    time. `compare_digest` because a naive `==` on a secret leaks its prefix
    through response timing.
    """
    expected = settings.metrics_token
    if expected:
        supplied = (authorization or "").removeprefix("Bearer ").strip()
        if not secrets.compare_digest(supplied, expected):
            raise MetricsForbidden("A valid metrics token is required.")

    payload, content_type = MetricsService.render()
    return Response(content=payload, media_type=content_type)
