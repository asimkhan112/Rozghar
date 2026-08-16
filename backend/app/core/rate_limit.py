"""Redis-backed sliding-window rate limiting.

**Fails open.** When Redis is unreachable the limiter allows the request. That
is the right trade for this application: Redis is already optional everywhere
else, and a cache outage that locks every user out of login is a worse incident
than the abuse the limiter exists to stop. The one place that reasoning does
not hold is report submission, which keeps its own database-backed limiter from
Milestone 5 precisely so at least one control survives a Redis outage.

The window is a sorted set of request timestamps per key, trimmed on each
check. More memory than a fixed counter, and worth it: a fixed window lets
twice the limit through across a boundary, which for login is exactly the burst
an attacker wants.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass

import redis.asyncio as aioredis

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RateLimit:
    """One named bucket."""

    name: str
    limit: int
    window_seconds: int

    @property
    def retry_after(self) -> int:
        return self.window_seconds


#: The buckets. Login is tightest because it is the only endpoint where a
#: successful guess is a total compromise; the account lockout in
#: `AuthService` is the second layer behind it.
LOGIN = RateLimit(name="login", limit=10, window_seconds=300)
SEARCH = RateLimit(name="search", limit=120, window_seconds=60)
REPORTS = RateLimit(name="reports", limit=20, window_seconds=3600)
ANALYTICS = RateLimit(name="analytics", limit=240, window_seconds=60)
ADMIN_API = RateLimit(name="admin_api", limit=600, window_seconds=60)


@dataclass(frozen=True)
class Decision:
    allowed: bool
    remaining: int
    retry_after: int


class RateLimiter:
    def __init__(self, redis: aioredis.Redis | None) -> None:
        self.redis = redis

    async def check(self, bucket: RateLimit, identity: str) -> Decision:
        """Record this request and say whether it is allowed.

        One pipeline, four commands: drop everything older than the window, add
        this request, count what remains, and re-set the expiry so an idle key
        disappears on its own rather than waiting for eviction.
        """
        if self.redis is None or not identity:
            return Decision(allowed=True, remaining=bucket.limit, retry_after=0)

        key = f"ratelimit:{bucket.name}:{identity}"
        now = time.time()
        cutoff = now - bucket.window_seconds

        try:
            async with self.redis.pipeline(transaction=True) as pipe:
                pipe.zremrangebyscore(key, 0, cutoff)
                # Score and member both carry the timestamp; the member needs
                # only to be unique within the window.
                pipe.zadd(key, {f"{now}:{id(self)}": now})
                pipe.zcard(key)
                pipe.expire(key, bucket.window_seconds)
                results = await pipe.execute()
            used = int(results[2])
        except Exception:  # noqa: BLE001 - see the module docstring: fail open
            logger.warning(
                "rate limiter unavailable; allowing the request",
                extra={"event": "ratelimit.unavailable", "bucket": bucket.name},
                exc_info=True,
            )
            return Decision(allowed=True, remaining=bucket.limit, retry_after=0)

        if used > bucket.limit:
            return Decision(allowed=False, remaining=0, retry_after=bucket.retry_after)
        return Decision(allowed=True, remaining=bucket.limit - used, retry_after=0)


__all__ = [
    "ADMIN_API",
    "AI_DRAFT",
    "ANALYTICS",
    "LOGIN",
    "REPORTS",
    "SEARCH",
    "Decision",
    "RateLimit",
    "RateLimiter",
]


#: AI drafting. Far tighter than the other buckets because each call costs real
#: money and takes seconds — an editor needing more than this in an hour is
#: fighting the tool rather than using it.
AI_DRAFT = RateLimit(name="ai_draft", limit=40, window_seconds=3600)
