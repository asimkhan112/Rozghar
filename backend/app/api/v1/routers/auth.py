"""Authentication endpoints.

Four routes, per the milestone scope: login, refresh, logout, me.

The refresh token is never in a response body. It is set as an httpOnly cookie,
which means JavaScript cannot read it and a cross-site request cannot mint
tokens with it (`SameSite=Strict`). The access token, by contrast, is returned
in the body and expected to live in memory only — never in localStorage.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Cookie, Request, Response, status

from app.api.v1.deps import AuthServiceDep, CurrentPrincipal, client_ip
from app.core.config import settings
from app.core.exceptions import InvalidRefreshToken
from app.schemas.auth import LoginRequest, LoginResponse, PrincipalResponse, TokenResponse
from app.services.auth_service import Principal, TokenPair

router = APIRouter(prefix="/auth", tags=["auth"])

REFRESH_COOKIE_NAME = "rozgar_refresh"
#: Scoped to the refresh and logout paths so the token is not attached to every
#: request — it should only ever be sent where it is actually needed.
REFRESH_COOKIE_PATH = "/api/v1/auth"


def _set_refresh_cookie(response: Response, pair: TokenPair) -> None:
    response.set_cookie(
        key=REFRESH_COOKIE_NAME,
        value=pair.refresh_token,
        max_age=settings.refresh_token_ttl_seconds,
        path=REFRESH_COOKIE_PATH,
        httponly=True,  # unreadable from JavaScript
        secure=settings.is_production,  # plain HTTP is fine locally, never in production
        samesite="strict",  # a cross-site POST cannot use it
    )


def _clear_refresh_cookie(response: Response) -> None:
    response.delete_cookie(
        key=REFRESH_COOKIE_NAME,
        path=REFRESH_COOKIE_PATH,
        httponly=True,
        secure=settings.is_production,
        samesite="strict",
    )


def _principal_payload(principal: Principal) -> PrincipalResponse:
    return PrincipalResponse(
        id=principal.admin_id,
        email=principal.email,
        full_name=principal.full_name,
        role=principal.role_key,
        permissions=sorted(principal.permissions),
    )


@router.post(
    "/login",
    response_model=LoginResponse,
    status_code=status.HTTP_200_OK,
    summary="Exchange credentials for an access token",
    responses={
        401: {"description": "Email or password is incorrect"},
        423: {"description": "Account temporarily locked after repeated failures"},
    },
)
async def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    auth: AuthServiceDep,
) -> LoginResponse:
    try:
        admin, pair = await auth.authenticate(
            payload.email,
            payload.password,
            user_agent=request.headers.get("user-agent"),
            ip=client_ip(request),
        )
    except Exception:
        # A failed attempt increments the lockout counter. That write has to be
        # committed even though the request fails, or brute-force protection
        # would be rolled back with the rest of the transaction.
        await auth.session.commit()
        raise

    await auth.session.commit()

    _set_refresh_cookie(response, pair)

    permissions = await auth.permissions.resolve(admin.role_id)
    return LoginResponse(
        access_token=pair.access_token,
        expires_in=settings.access_token_ttl_seconds,
        expires_at=pair.access_expires_at,
        admin=PrincipalResponse(
            id=admin.id,
            email=admin.email,
            full_name=admin.full_name,
            role=admin.role.key,
            permissions=sorted(permissions),
        ),
    )


@router.post(
    "/refresh",
    response_model=TokenResponse,
    status_code=status.HTTP_200_OK,
    summary="Rotate the refresh token and mint a new access token",
    responses={
        401: {
            "description": (
                "Missing, expired or already-used token. A reused token also "
                "revokes every session in its family."
            )
        }
    },
)
async def refresh(
    request: Request,
    response: Response,
    auth: AuthServiceDep,
    rozgar_refresh: Annotated[str | None, Cookie()] = None,
) -> TokenResponse:
    """Takes no request body on purpose.

    The cookie is `SameSite=Strict` and nothing else is required, so a
    cross-site form post cannot drive this endpoint.
    """
    if not rozgar_refresh:
        raise InvalidRefreshToken("No refresh token was supplied.")

    try:
        _, pair = await auth.refresh(
            rozgar_refresh,
            user_agent=request.headers.get("user-agent"),
            ip=client_ip(request),
        )
    except Exception:
        # Reuse detection revokes a whole family; that revocation has to
        # survive even though the request fails.
        await auth.session.commit()
        _clear_refresh_cookie(response)
        raise

    await auth.session.commit()
    _set_refresh_cookie(response, pair)

    return TokenResponse(
        access_token=pair.access_token,
        expires_in=settings.access_token_ttl_seconds,
        expires_at=pair.access_expires_at,
    )


@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Revoke the current session",
)
async def logout(
    response: Response,
    auth: AuthServiceDep,
    rozgar_refresh: Annotated[str | None, Cookie()] = None,
) -> Response:
    """Idempotent — logging out twice, or with no cookie, is still a 204.

    Requires no access token: a user whose access token has expired must still
    be able to end their session.
    """
    await auth.logout(rozgar_refresh)
    await auth.session.commit()
    _clear_refresh_cookie(response)
    response.status_code = status.HTTP_204_NO_CONTENT
    return response


@router.get(
    "/me",
    response_model=PrincipalResponse,
    summary="The authenticated admin and their resolved permissions",
)
async def me(principal: CurrentPrincipal) -> PrincipalResponse:
    return _principal_payload(principal)
