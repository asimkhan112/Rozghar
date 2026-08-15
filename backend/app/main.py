"""Application entrypoint."""

from __future__ import annotations

import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.api import ops as ops_router
from app.api.middleware import register_middleware
from app.api.v1.routers import admin_admins as admin_admins_router
from app.api.v1.routers import admin_analytics as admin_analytics_router
from app.api.v1.routers import admin_jobs as admin_jobs_router
from app.api.v1.routers import admin_reports as admin_reports_router
from app.api.v1.routers import analytics as analytics_router
from app.api.v1.routers import auth as auth_router
from app.api.v1.routers import jobs as jobs_router
from app.api.v1.routers import reports as reports_router
from app.api.v1.routers import taxonomy as taxonomy_router
from app.core.config import assert_secret_key_is_strong, settings
from app.core.exceptions import DomainError
from app.core.logging import configure_logging
from app.db.database import SessionFactory, dispose_engine
from app.db.validate import assert_permissions_in_sync
from app.services.metrics_service import MetricsService
from app.services.permission_service import create_redis
from app.tasks.scheduler import scheduler_handle

configure_logging(json_logs=settings.json_logs, debug=settings.debug)
logger = logging.getLogger("rozgar")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    logger.info(
        "starting",
        extra={
            "event": "app.starting",
            "app": settings.app_name,
            "version": settings.app_version,
            "environment": settings.environment,
        },
    )

    # Before anything can mint a token with it. A weak signing key outside
    # local development is not a warning, it is forgeable authentication.
    assert_secret_key_is_strong(settings)
    MetricsService.set_build_info(version=settings.app_version, environment=settings.environment)

    if settings.validate_permissions_on_startup:
        async with SessionFactory() as session:
            # Aborts startup on drift between the Permission enum and the
            # database. Serving requests with an authorisation model nobody can
            # reason about is worse than not serving them.
            await assert_permissions_in_sync(session)
        logger.info("permission model verified against the database")

    # Optional: authorisation still works without it, just without caching.
    app.state.redis = await create_redis()
    if app.state.redis is not None:
        logger.info("redis connected; permission caching enabled")

    # In-process, and every worker starts one. Each task takes a Postgres
    # advisory lock, so N schedulers do not mean N times the work — see
    # `app.tasks.scheduled_tasks`. Disable per-instance with SCHEDULER_ENABLED.
    if settings.scheduler_enabled:
        scheduler_handle.start()

    yield

    scheduler_handle.shutdown()
    if app.state.redis is not None:
        await app.state.redis.aclose()
    await dispose_engine()
    logger.info("shutdown complete")


def _problem(
    request: Request,
    *,
    status: int,
    code: str,
    title: str,
    detail: str,
    errors: dict | None = None,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    """RFC 7807 problem response — one shape for every failure."""
    body = {
        "type": f"https://rozgar.pk/errors/{code}",
        "title": title,
        "status": status,
        "detail": detail,
        "instance": str(request.url.path),
    }
    if errors:
        body["errors"] = errors
    return JSONResponse(status_code=status, content=body, headers=headers or {})


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        docs_url="/docs" if not settings.is_production else None,
        redoc_url=None,
        openapi_url="/openapi.json" if not settings.is_production else None,
        lifespan=lifespan,
    )

    @app.exception_handler(DomainError)
    async def handle_domain_error(request: Request, exc: DomainError) -> JSONResponse:
        headers = dict(exc.headers)
        # Signals to the client that a bearer token is expected, per RFC 6750.
        if exc.status == 401:
            headers.setdefault("WWW-Authenticate", 'Bearer realm="rozgar"')
        return _problem(
            request,
            status=exc.status,
            code=exc.code,
            title=exc.title,
            detail=exc.detail,
            errors=exc.errors,
            headers=headers,
        )

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        """Collapse Pydantic's error list into field → messages."""
        errors: dict[str, list[str]] = {}
        for error in exc.errors():
            location = [str(part) for part in error["loc"] if part not in ("body", "query")]
            field = ".".join(location) or "body"
            errors.setdefault(field, []).append(error["msg"])
        return _problem(
            request,
            status=422,
            code="validation_error",
            title="Request validation failed",
            detail="One or more fields are invalid.",
            errors=errors,
        )

    register_middleware(app)

    # Unversioned: /health and /ready are wired into orchestrator config
    # and load-balancer target groups, which must not move when the API
    # version does.
    app.include_router(ops_router.router)

    app.include_router(auth_router.router, prefix=settings.api_v1_prefix)
    app.include_router(jobs_router.router, prefix=settings.api_v1_prefix)
    app.include_router(reports_router.router, prefix=settings.api_v1_prefix)
    app.include_router(analytics_router.router, prefix=settings.api_v1_prefix)
    app.include_router(taxonomy_router.public, prefix=settings.api_v1_prefix)
    app.include_router(admin_jobs_router.router, prefix=settings.api_v1_prefix)
    app.include_router(admin_reports_router.router, prefix=settings.api_v1_prefix)
    app.include_router(admin_analytics_router.router, prefix=settings.api_v1_prefix)
    app.include_router(admin_admins_router.router, prefix=settings.api_v1_prefix)
    app.include_router(taxonomy_router.admin, prefix=settings.api_v1_prefix)

    return app


app = create_app()
