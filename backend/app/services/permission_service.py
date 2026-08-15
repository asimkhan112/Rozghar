"""Role → permission resolution, with a shared cache.

Every authenticated request needs the caller's permission set. Resolving it
from the database each time is three queries on the hottest path in the API, so
the resolved set is cached in Redis and shared across processes.

Correctness comes from a **version key**: changing any role bumps one integer,
which makes every cached entry for every role unreachable at once. That avoids
having to enumerate and delete keys, and it means a stale entry can never be
served after a permission change.
"""

from __future__ import annotations

import logging
from uuid import UUID

import redis.asyncio as aioredis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.repositories.rbac_repo import RoleRepository

logger = logging.getLogger(__name__)

_VERSION_KEY = "rbac:version"
_CACHE_TTL_SECONDS = 300


def _cache_key(version: int, role_id: UUID) -> str:
    return f"rbac:v{version}:role:{role_id}"


class PermissionService:
    """Resolves and caches the permission set for a role.

    Degrades to direct database reads when Redis is unavailable. A cache outage
    should slow the API down, never lock everyone out.
    """

    def __init__(self, session: AsyncSession, redis: aioredis.Redis | None = None) -> None:
        self.session = session
        self.redis = redis
        self.roles = RoleRepository(session)

    async def _version(self) -> int:
        if self.redis is None:
            return 0
        try:
            raw = await self.redis.get(_VERSION_KEY)
            return int(raw) if raw is not None else 0
        except Exception:  # noqa: BLE001 - cache must never break authorisation
            logger.warning("redis unavailable while reading the rbac version", exc_info=True)
            return 0

    async def resolve(self, role_id: UUID) -> frozenset[str]:
        """Permission keys granted to a role."""
        version = await self._version()
        key = _cache_key(version, role_id)

        if self.redis is not None:
            try:
                cached = await self.redis.smembers(key)
                if cached:
                    return frozenset(m.decode() if isinstance(m, bytes) else m for m in cached)
            except Exception:  # noqa: BLE001
                logger.warning("redis unavailable while reading permissions", exc_info=True)

        permissions = await self.roles.permission_keys_for(role_id)

        if self.redis is not None and permissions:
            try:
                async with self.redis.pipeline(transaction=True) as pipe:
                    pipe.sadd(key, *permissions)
                    pipe.expire(key, _CACHE_TTL_SECONDS)
                    await pipe.execute()
            except Exception:  # noqa: BLE001
                logger.warning("redis unavailable while caching permissions", exc_info=True)

        return permissions

    async def invalidate(self) -> None:
        """Bump the version so every cached role set becomes unreachable.

        Called whenever a role's grants change. One INCR is cheaper and safer
        than deleting keys one by one, and it cannot leave a straggler behind.
        """
        if self.redis is None:
            return
        try:
            await self.redis.incr(_VERSION_KEY)
        except Exception:  # noqa: BLE001
            logger.warning("redis unavailable while invalidating permissions", exc_info=True)


async def create_redis() -> aioredis.Redis | None:
    """Connect to Redis, or return None if it is not reachable.

    Returning None rather than raising keeps the API serving when the cache is
    down — every call site treats it as optional.
    """
    try:
        client = aioredis.from_url(settings.redis_url, decode_responses=True)
        await client.ping()
        return client
    except Exception:  # noqa: BLE001
        logger.warning("redis is not reachable; permission caching is disabled")
        return None
