"""Request dependencies: database session, principal, permission gate.

Routers declare what a caller must be able to *do*, never what they must *be*:

    @router.post("/jobs", dependencies=[Depends(require(Permission.JOB_CREATE))])

Checking permissions rather than roles is what makes a fifth role a
configuration change instead of a search through conditionals.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator, Callable, Coroutine
from typing import Annotated, Any

import redis.asyncio as aioredis
from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import InvalidToken, PermissionDenied
from app.core.permissions import Permission
from app.core.security import decode_access_token
from app.db.database import get_db
from app.services.auth_service import AuthService, Principal
from app.services.permission_service import PermissionService

#: `auto_error=False` so a missing header raises our own domain error and
#: produces an RFC 7807 body like every other failure, rather than FastAPI's
#: default shape.
bearer_scheme = HTTPBearer(auto_error=False)

DbSession = Annotated[AsyncSession, Depends(get_db)]


async def get_redis(request: Request) -> aioredis.Redis | None:
    """Shared Redis client created once in the application lifespan."""
    return getattr(request.app.state, "redis", None)


async def get_permission_service(
    session: DbSession,
    redis: Annotated[aioredis.Redis | None, Depends(get_redis)],
) -> PermissionService:
    return PermissionService(session, redis)


async def get_auth_service(
    session: DbSession,
    permissions: Annotated[PermissionService, Depends(get_permission_service)],
) -> AuthService:
    return AuthService(session, permissions=permissions)


AuthServiceDep = Annotated[AuthService, Depends(get_auth_service)]


async def get_principal(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    auth: AuthServiceDep,
) -> Principal:
    """Resolve the caller from a bearer access token.

    Two steps, deliberately: the JWT is verified locally (signature, expiry,
    type), then the principal is loaded from the database so deactivation and
    password changes take effect immediately rather than at token expiry.
    """
    if credentials is None or not credentials.credentials:
        raise InvalidToken("Authorization header is missing.")

    claims = decode_access_token(credentials.credentials)
    return await auth.resolve_principal(claims.admin_id, claims.issued_at)


CurrentPrincipal = Annotated[Principal, Depends(get_principal)]


async def get_optional_principal(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    auth: AuthServiceDep,
) -> Principal | None:
    """For endpoints that behave differently when signed in but do not require
    it. A malformed token is ignored rather than rejected."""
    if credentials is None or not credentials.credentials:
        return None
    try:
        claims = decode_access_token(credentials.credentials)
        return await auth.resolve_principal(claims.admin_id, claims.issued_at)
    except Exception:  # noqa: BLE001 - anonymous is a valid outcome here
        return None


def require(
    *permissions: Permission,
    require_all: bool = True,
) -> Callable[[Principal], Coroutine[Any, Any, Principal]]:
    """Build a dependency asserting the caller holds the given permissions.

    Defaults to requiring all of them; pass `require_all=False` when any one
    will do. Returns the principal so a handler can depend on it directly
    instead of declaring it twice.
    """
    required = tuple(permissions)

    async def dependency(principal: CurrentPrincipal) -> Principal:
        held = principal.permissions
        satisfied = (
            all(p.value in held for p in required)
            if require_all
            else any(p.value in held for p in required)
        )
        if not satisfied:
            missing = [p.value for p in required if p.value not in held]
            raise PermissionDenied(missing[0] if missing else None)
        return principal

    return dependency


def client_ip(request: Request) -> str | None:
    """Best-effort client address.

    `X-Forwarded-For` is only trusted when the app is deployed behind a proxy
    that sets it; a client can otherwise forge the header and defeat per-IP
    controls. Configure the proxy to overwrite, not append.
    """
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else None


async def db_session() -> AsyncGenerator[AsyncSession, None]:
    async for session in get_db():
        yield session
