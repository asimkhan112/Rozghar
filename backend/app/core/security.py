"""Password hashing, access tokens and refresh-token primitives.

Two token types with deliberately different designs:

* **Access** — a short-lived signed JWT. Stateless, so verifying it costs no
  database round trip beyond loading the principal.
* **Refresh** — a long-lived opaque random string. Only its SHA-256 hash is
  stored, and the row can be revoked. A stateless refresh JWT cannot be
  invalidated, which makes session revocation impossible; that is the whole
  reason for the asymmetry.
"""

from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

from app.core.config import settings
from app.core.ids import uuid7

# --- password hashing -----------------------------------------------------

#: Argon2id with OWASP-recommended parameters. Memory-hard, so a leaked hash
#: cannot be attacked cheaply on GPUs the way a fast hash can.
_hasher = PasswordHasher(
    time_cost=2,
    memory_cost=64 * 1024,  # 64 MiB
    parallelism=2,
    hash_len=32,
    salt_len=16,
)

#: A real Argon2 hash of a random value. Verified against when the email is
#: unknown, so a login attempt costs the same time whether or not the account
#: exists — otherwise response timing enumerates accounts.
_DUMMY_HASH = _hasher.hash(secrets.token_urlsafe(32))


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str | None) -> bool:
    """Constant-work verification.

    Passing `None` (no such account) still performs a full Argon2 verification
    against a dummy hash before returning False.
    """
    target = password_hash or _DUMMY_HASH
    try:
        _hasher.verify(target, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False
    return password_hash is not None


def needs_rehash(password_hash: str) -> bool:
    """True when the hash was produced with weaker parameters than current."""
    try:
        return _hasher.check_needs_rehash(password_hash)
    except InvalidHashError:
        return True


# --- access tokens --------------------------------------------------------

ALGORITHM = "HS256"
ACCESS_TOKEN_TYPE = "access"


@dataclass(frozen=True)
class AccessTokenClaims:
    admin_id: UUID
    role: str
    jti: UUID
    issued_at: datetime
    expires_at: datetime
    #: `password_changed_at` at issue time. Compared against the current value
    #: so changing a password invalidates tokens minted before the change.
    password_changed_at: datetime


def create_access_token(
    *,
    admin_id: UUID,
    role: str,
    password_changed_at: datetime,
    now: datetime | None = None,
) -> tuple[str, datetime]:
    """Return the encoded token and its expiry."""
    issued = now or datetime.now(UTC)
    expires = issued + timedelta(seconds=settings.access_token_ttl_seconds)
    payload: dict[str, Any] = {
        "sub": str(admin_id),
        "role": role,
        "jti": str(uuid7()),
        "iat": int(issued.timestamp()),
        "exp": int(expires.timestamp()),
        "pwd_at": int(password_changed_at.timestamp()),
        "typ": ACCESS_TOKEN_TYPE,
    }
    return jwt.encode(payload, settings.secret_key, algorithm=ALGORITHM), expires


def decode_access_token(token: str) -> AccessTokenClaims:
    """Verify signature, expiry and token type.

    Raises `TokenExpired` or `InvalidToken`. Whether the principal still exists
    and is active is a separate question, answered by the dependency.
    """
    from app.core.exceptions import InvalidToken, TokenExpired

    try:
        payload = jwt.decode(
            token,
            settings.secret_key,
            algorithms=[ALGORITHM],
            options={"require": ["exp", "iat", "sub", "jti"]},
        )
    except jwt.ExpiredSignatureError as exc:
        raise TokenExpired() from exc
    except jwt.InvalidTokenError as exc:
        raise InvalidToken() from exc

    # A refresh or any other token type must never authenticate a request.
    if payload.get("typ") != ACCESS_TOKEN_TYPE:
        raise InvalidToken("Token is not an access token.")

    try:
        return AccessTokenClaims(
            admin_id=UUID(payload["sub"]),
            role=payload.get("role", ""),
            jti=UUID(payload["jti"]),
            issued_at=datetime.fromtimestamp(payload["iat"], tz=UTC),
            expires_at=datetime.fromtimestamp(payload["exp"], tz=UTC),
            password_changed_at=datetime.fromtimestamp(payload.get("pwd_at", 0), tz=UTC),
        )
    except (KeyError, ValueError, TypeError) as exc:
        raise InvalidToken("Token claims are malformed.") from exc


# --- refresh tokens -------------------------------------------------------

#: 32 bytes of entropy, URL-safe. Opaque: it carries no claims and means
#: nothing without the matching database row.
REFRESH_TOKEN_BYTES = 32


def generate_refresh_token() -> tuple[str, str]:
    """Return `(raw_token, token_hash)`.

    Only the hash is ever persisted, so a database leak yields no usable
    sessions.
    """
    raw = secrets.token_urlsafe(REFRESH_TOKEN_BYTES)
    return raw, hash_refresh_token(raw)


def hash_refresh_token(raw: str) -> str:
    """SHA-256, not Argon2.

    The input is 256 bits of server-generated entropy, so there is nothing to
    brute-force and a slow hash would only add latency to every refresh.
    """
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def refresh_token_expiry(now: datetime | None = None) -> datetime:
    return (now or datetime.now(UTC)) + timedelta(seconds=settings.refresh_token_ttl_seconds)


# --- misc -----------------------------------------------------------------


def hash_ip(ip: str | None) -> str | None:
    """Hash a client address for abuse control.

    Keyed with the application secret so the digest cannot be reversed with a
    rainbow table of the IPv4 space, which is small enough to enumerate.
    """
    if not ip:
        return None
    return hashlib.sha256(f"{settings.secret_key}:{ip}".encode()).hexdigest()
