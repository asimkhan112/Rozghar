"""Domain errors and their single mapping to HTTP.

Services raise these; they know nothing about FastAPI. One handler in `main.py`
turns them into RFC 7807 problem responses, so status codes and error bodies
are decided in one place rather than scattered across routers.
"""

from __future__ import annotations

from typing import Any


class DomainError(Exception):
    """Base for every error the application raises deliberately."""

    status: int = 400
    code: str = "domain_error"
    title: str = "Request could not be completed"

    def __init__(
        self,
        detail: str | None = None,
        *,
        errors: dict[str, list[str]] | None = None,
        headers: dict[str, str] | None = None,
        meta: dict[str, Any] | None = None,
    ) -> None:
        self.detail = detail or self.title
        self.errors = errors
        self.headers = headers or {}
        self.meta = meta or {}
        super().__init__(self.detail)


# --- authentication -------------------------------------------------------


class AuthenticationError(DomainError):
    status = 401
    code = "invalid_credentials"
    title = "Authentication failed"


class InvalidCredentials(AuthenticationError):
    """Wrong email or password.

    The message is deliberately identical for an unknown email and a wrong
    password — anything else lets an attacker enumerate accounts.
    """

    detail_message = "Email or password is incorrect."

    def __init__(self) -> None:
        super().__init__(self.detail_message)


class AccountInactive(AuthenticationError):
    code = "account_inactive"
    title = "Account is not active"


class AccountLocked(AuthenticationError):
    status = 423
    code = "account_locked"
    title = "Account temporarily locked"


class InvalidToken(AuthenticationError):
    code = "invalid_token"
    title = "Access token is missing or invalid"


class TokenExpired(AuthenticationError):
    code = "token_expired"
    title = "Access token has expired"


class InvalidRefreshToken(AuthenticationError):
    code = "invalid_refresh_token"
    title = "Refresh token is missing, expired or already used"


class RefreshTokenReused(AuthenticationError):
    """A token that had already been rotated was presented again.

    Treated as theft: the entire family is revoked, so both the attacker and
    the legitimate holder are forced to authenticate again.
    """

    code = "refresh_token_reused"
    title = "Refresh token reuse detected — all sessions revoked"


class RefreshRace(AuthenticationError):
    """Two concurrent refreshes; this one lost.

    Not a breach. The winner already rotated the cookie, so the client simply
    retries and picks up the newer token.
    """

    code = "refresh_race"
    title = "Refresh already in progress — retry with the current token"


# --- authorisation --------------------------------------------------------


class PermissionDenied(DomainError):
    status = 403
    code = "permission_denied"
    title = "Insufficient permissions"

    def __init__(self, required: str | None = None) -> None:
        detail = (
            f"This action requires the {required} permission."
            if required
            else "You do not have permission to perform this action."
        )
        super().__init__(detail, meta={"required_permission": required} if required else None)


# --- generic --------------------------------------------------------------


class NotFound(DomainError):
    status = 404
    code = "not_found"
    title = "Resource not found"


class Conflict(DomainError):
    status = 409
    code = "conflict"
    title = "Conflicting state"


class RateLimited(DomainError):
    status = 429
    code = "rate_limited"
    title = "Too many requests"

    def __init__(self, retry_after: int, detail: str | None = None) -> None:
        super().__init__(
            detail or f"Too many requests. Try again in {retry_after} seconds.",
            headers={"Retry-After": str(retry_after)},
            meta={"retry_after": retry_after},
        )
