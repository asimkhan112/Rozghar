"""Redis caching for expensive reads.

Three rules, all learned the hard way by people who did the opposite:

**A cache miss is not an error.** Every method degrades to `None` when Redis is
unreachable, and every caller treats that as "compute it". The API stays
correct without Redis; it is only slower. This mirrors `PermissionService`,
which made the same choice for the same reason.

**Namespaced by version.** Invalidation bumps one integer instead of deleting
keys. `KEYS`/`SCAN` over a production Redis to find what to delete is how a
cache invalidation takes the site down, and a delete loop can always leave a
straggler.

**Nothing user-specific.** Everything cached here is either public or
platform-wide aggregate. A per-admin cache keyed carelessly is how one user's
data ends up on another user's screen, so the shape of this class makes it
awkward to do by accident.
"""

from __future__ import annotations

import json
import logging
from datetime import date, datetime
from typing import Any
from uuid import UUID

import redis.asyncio as aioredis

logger = logging.getLogger(__name__)

#: Namespace version. Bumped by `invalidate`, which makes every key in the
#: previous generation unreachable at once.
_VERSION_KEY = "cache:version"

#: TTLs, chosen from how stale each answer may acceptably be.
TTL_SEARCH = 120  # popular queries: a new listing should surface within minutes
TTL_TOP_JOBS = 300  # homepage rails: five minutes of staleness is invisible
TTL_ANALYTICS = 600  # dashboards: rebuilt every fifteen minutes anyway


def _default(value: Any) -> Any:
    """JSON encoder for the types that reach a cache payload."""
    if isinstance(value, datetime | date):
        return value.isoformat()
    if isinstance(value, UUID):
        return str(value)
    raise TypeError(f"cannot serialise {type(value).__name__} into the cache")


class CacheService:
    def __init__(self, redis: aioredis.Redis | None) -> None:
        self.redis = redis

    @property
    def enabled(self) -> bool:
        return self.redis is not None

    async def _version(self) -> int:
        if self.redis is None:
            return 0
        try:
            raw = await self.redis.get(_VERSION_KEY)
            return int(raw) if raw is not None else 0
        except Exception:  # noqa: BLE001 - a cache outage must not break a read
            logger.warning("redis unavailable while reading the cache version", exc_info=True)
            return 0

    async def _key(self, namespace: str, *parts: Any) -> str:
        version = await self._version()
        suffix = ":".join(str(p) for p in parts if p is not None)
        return (
            f"cache:v{version}:{namespace}:{suffix}" if suffix else f"cache:v{version}:{namespace}"
        )

    async def get(self, namespace: str, *parts: Any) -> Any | None:
        if self.redis is None:
            return None
        try:
            raw = await self.redis.get(await self._key(namespace, *parts))
        except Exception:  # noqa: BLE001
            logger.warning("redis unavailable while reading the cache", exc_info=True)
            return None
        if raw is None:
            return None
        try:
            return json.loads(raw)
        except ValueError:
            # A payload written by an older, incompatible version of the code.
            # Treated as a miss rather than an error.
            return None

    async def set(self, namespace: str, value: Any, *parts: Any, ttl: int) -> None:
        if self.redis is None:
            return
        try:
            await self.redis.set(
                await self._key(namespace, *parts),
                json.dumps(value, default=_default),
                ex=ttl,
            )
        except TypeError:
            # Never let an unserialisable value propagate — the caller asked
            # for a cache write, not for its request to fail.
            logger.warning("cache payload is not serialisable", exc_info=True)
        except Exception:  # noqa: BLE001
            logger.warning("redis unavailable while writing the cache", exc_info=True)

    async def invalidate(self) -> None:
        """Make every cached entry unreachable in one operation."""
        if self.redis is None:
            return
        try:
            await self.redis.incr(_VERSION_KEY)
        except Exception:  # noqa: BLE001
            logger.warning("redis unavailable while invalidating the cache", exc_info=True)

    async def stats(self) -> dict[str, Any]:
        """Hit rate and memory, for `/metrics` and the ops dashboard."""
        if self.redis is None:
            return {"enabled": False}
        try:
            info = await self.redis.info()
        except Exception:  # noqa: BLE001
            return {"enabled": False}
        hits = int(info.get("keyspace_hits", 0))
        misses = int(info.get("keyspace_misses", 0))
        total = hits + misses
        return {
            "enabled": True,
            "hits": hits,
            "misses": misses,
            "hit_rate": round(hits / total, 4) if total else 0.0,
            "used_memory_bytes": int(info.get("used_memory", 0)),
        }


__all__ = ["CacheService", "TTL_ANALYTICS", "TTL_SEARCH", "TTL_TOP_JOBS"]
