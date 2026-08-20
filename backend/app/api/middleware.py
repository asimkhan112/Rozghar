"""Cross-cutting request handling: request ids, metrics, rate limiting.

Middleware rather than dependencies because all three have to apply to every
route including the ones that fail before a dependency runs — a 422 from
request validation is still a request worth counting and still consumes a rate
limit slot.
"""

from __future__ import annotations

import logging
import time
import uuid
from collections.abc import Awaitable, Callable

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse

from app.core.config import settings
from app.core.rate_limit import (
    ADMIN_API,
    ANALYTICS,
    LOGIN,
    REPORTS,
    SEARCH,
    RateLimit,
    RateLimiter,
)
from app.services.metrics_service import MetricsService

logger = logging.getLogger("plenilo.request")

#: Endpoints outside the metrics and rate-limit paths. Instrumenting the
#: probes means the health check appears in the latency histogram, which
#: flatters every percentile it touches.
_EXEMPT = frozenset({"/health", "/ready", "/metrics"})


def _route_template(request: Request) -> str:
    """The registered path, never the concrete URL.

    `/api/v1/jobs/{slug}` is one time series; `/api/v1/jobs/senior-engineer-lahore`
    is a new one for every listing ever viewed. Labelling metrics by URL is the
    standard way to make a Prometheus instance unqueryable.

    This FastAPI version keeps included routers nested rather than flattening
    them, so the matched route's `path` is router-relative — `/jobs/{slug}`,
    not `/api/v1/jobs/{slug}` — and the mount prefix appears in neither the
    route nor `root_path`. It is recovered by segment count: the template's
    trailing segments are dropped from the real path and whatever remains is
    the prefix. Without this every versioned route is labelled by its bare
    suffix, and two routers that share one would silently merge into a single
    series.
    """
    route = request.scope.get("route")
    path = getattr(route, "path", None)
    if not path:
        # No match: a 404 on an unrouted URL. One bucket for all of them,
        # deliberately — labelling by the requested path would let anyone
        # mint unbounded series by making up URLs.
        return "unmatched"

    template_segments = [s for s in path.split("/") if s]
    actual_segments = [s for s in request.url.path.split("/") if s]
    prefix_length = len(actual_segments) - len(template_segments)
    if prefix_length <= 0:
        return path
    return "/" + "/".join(actual_segments[:prefix_length]) + path


def _bucket_for(request: Request) -> RateLimit | None:
    """Which limiter applies, by path prefix.

    Login is tightest: it is the one endpoint where a successful guess is a
    total compromise. Admin APIs are limited generously — the point there is to
    bound a compromised token's blast radius, not to inconvenience staff.
    """
    path = request.url.path
    if path.endswith("/auth/login"):
        return LOGIN
    if path.endswith("/analytics/events"):
        return ANALYTICS
    if path.endswith("/reports") and request.method == "POST":
        return REPORTS
    if "/admin/" in path:
        return ADMIN_API
    if path.endswith("/jobs") and request.query_params.get("q"):
        return SEARCH
    return None


def _client_identity(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else ""


def register_middleware(app: FastAPI) -> None:
    @app.middleware("http")
    async def observe(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        # A correlation id, echoed back so a user reporting "it failed at
        # 14:32" hands over something greppable. Honours an upstream one if the
        # proxy already assigned it.
        request_id = request.headers.get("x-request-id") or uuid.uuid4().hex[:16]
        request.state.request_id = request_id

        path = request.url.path
        if path in _EXEMPT:
            response = await call_next(request)
            response.headers["X-Request-ID"] = request_id
            return response

        # --- rate limit ---------------------------------------------------
        bucket = _bucket_for(request)
        if settings.rate_limit_enabled and bucket is not None:
            limiter = RateLimiter(getattr(app.state, "redis", None))
            decision = await limiter.check(bucket, _client_identity(request))
            if not decision.allowed:
                MetricsService.observe_rate_limit(bucket.name)
                logger.warning(
                    "rate limit exceeded",
                    extra={
                        "event": "ratelimit.rejected",
                        "bucket": bucket.name,
                        "path": path,
                        "request_id": request_id,
                    },
                )
                # Same RFC 7807 shape as every other failure in this API.
                return JSONResponse(
                    status_code=429,
                    content={
                        "type": "https://plenilo.com/errors/rate_limited",
                        "title": "Too many requests",
                        "status": 429,
                        "detail": (
                            f"Too many requests. Try again in {decision.retry_after} seconds."
                        ),
                        "instance": path,
                    },
                    headers={
                        "Retry-After": str(decision.retry_after),
                        "X-Request-ID": request_id,
                    },
                )

        # --- serve and measure ---------------------------------------------
        started = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            duration = time.perf_counter() - started
            MetricsService.observe_request(
                method=request.method,
                route=_route_template(request),
                status_code=500,
                duration=duration,
            )
            logger.exception(
                "unhandled error",
                extra={
                    "event": "request.failed",
                    "request_id": request_id,
                    "path": path,
                    "method": request.method,
                    "duration_ms": round(duration * 1000, 2),
                },
            )
            raise

        duration = time.perf_counter() - started
        MetricsService.observe_request(
            method=request.method,
            route=_route_template(request),
            status_code=response.status_code,
            duration=duration,
        )
        response.headers["X-Request-ID"] = request_id

        # One structured line per request. Access logs are the first thing
        # anyone reaches for and the last thing anyone remembers to add.
        logger.info(
            "request",
            extra={
                "event": "request.completed",
                "request_id": request_id,
                "method": request.method,
                "path": path,
                "route": _route_template(request),
                "status": response.status_code,
                "duration_ms": round(duration * 1000, 2),
            },
        )
        return response


__all__ = ["register_middleware"]
