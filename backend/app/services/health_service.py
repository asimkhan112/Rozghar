"""Liveness and readiness.

The distinction matters more than it looks. **Liveness** answers "should this
process be restarted?" and must not touch a dependency — a slow database would
otherwise cause an orchestrator to kill every healthy instance, turning a
degradation into an outage. **Readiness** answers "should traffic be routed
here?" and does check dependencies, because an instance that cannot reach
Postgres should be taken out of the pool rather than restarted.

Getting these the wrong way round is one of the most common ways a Kubernetes
deployment amplifies a small problem into a total one.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any

import redis.asyncio as aioredis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings

logger = logging.getLogger(__name__)

#: A dependency slower than this is treated as down. Generous enough to absorb
#: a GC pause, tight enough that a readiness probe cannot hang the probe itself.
PROBE_TIMEOUT_SECONDS = 2.0


@dataclass
class Check:
    name: str
    ok: bool
    latency_ms: float = 0.0
    detail: str | None = None
    #: A check that is allowed to fail without failing readiness.
    required: bool = True


@dataclass
class HealthReport:
    checks: list[Check] = field(default_factory=list)

    @property
    def ready(self) -> bool:
        return all(c.ok for c in self.checks if c.required)

    def as_dict(self) -> dict[str, Any]:
        return {
            "status": "ready" if self.ready else "degraded",
            "environment": settings.environment,
            "checks": {
                c.name: {
                    "status": "ok" if c.ok else ("degraded" if not c.required else "down"),
                    "latency_ms": round(c.latency_ms, 2),
                    **({"detail": c.detail} if c.detail else {}),
                }
                for c in self.checks
            },
        }


class HealthService:
    def __init__(
        self,
        session: AsyncSession,
        redis: aioredis.Redis | None = None,
        scheduler: Any | None = None,
    ) -> None:
        self.session = session
        self.redis = redis
        self.scheduler = scheduler

    async def check_database(self) -> Check:
        """`SELECT 1`, and nothing more.

        A readiness probe that runs a real query measures that query, not the
        connection — and a probe that gets slower as the catalogue grows will
        eventually take the whole deployment out during a traffic peak.
        """
        started = time.perf_counter()
        try:
            await self.session.execute(text("SELECT 1"))
            return Check(
                name="postgres", ok=True, latency_ms=(time.perf_counter() - started) * 1000
            )
        except Exception as exc:  # noqa: BLE001
            return Check(
                name="postgres",
                ok=False,
                latency_ms=(time.perf_counter() - started) * 1000,
                detail=str(exc)[:200],
            )

    async def check_redis(self) -> Check:
        """Not required for readiness.

        Permissions, caching and rate limiting all degrade gracefully without
        Redis — that was designed in deliberately — so a Redis outage must not
        remove every instance from the load balancer. It is reported as
        degraded so it is still visible.
        """
        if self.redis is None:
            return Check(
                name="redis", ok=False, detail="not configured or unreachable", required=False
            )
        started = time.perf_counter()
        try:
            await self.redis.ping()
            return Check(
                name="redis",
                ok=True,
                latency_ms=(time.perf_counter() - started) * 1000,
                required=False,
            )
        except Exception as exc:  # noqa: BLE001
            return Check(
                name="redis",
                ok=False,
                latency_ms=(time.perf_counter() - started) * 1000,
                detail=str(exc)[:200],
                required=False,
            )

    def check_scheduler(self) -> Check:
        """Also not required.

        An instance with a stopped scheduler still serves requests perfectly
        well, and the work is protected by an advisory lock so any other
        instance picks it up. Failing readiness here would remove a healthy
        server from rotation over background work it does not need to be doing.
        """
        if not settings.scheduler_enabled:
            return Check(
                name="scheduler", ok=True, detail="disabled by configuration", required=False
            )
        if self.scheduler is None:
            return Check(name="scheduler", ok=False, detail="not started", required=False)
        running = bool(getattr(self.scheduler, "running", False))
        jobs = self.scheduler.jobs() if running else []
        return Check(
            name="scheduler",
            ok=running,
            detail=f"{len(jobs)} jobs registered" if running else "not running",
            required=False,
        )

    async def readiness(self) -> HealthReport:
        return HealthReport(
            checks=[
                await self.check_database(),
                await self.check_redis(),
                self.check_scheduler(),
            ]
        )


__all__ = ["Check", "HealthReport", "HealthService"]
