"""Authentication: login, refresh with rotation, logout, principal resolution.

The refresh design is the important part. Tokens rotate on every use and are
tracked as a *family* — one lineage per login. Presenting a token that has
already been rotated means it was captured, because the legitimate holder would
be using its replacement. The response is to revoke the whole family: both the
attacker and the real user are signed out, since there is no way to tell them
apart.

The one exception is a race. Two tabs refreshing at the same moment both send
the same valid token; the loser would otherwise look like an attacker. Within a
short window a rotated token is treated as a benign race instead — the winner
has already replaced the cookie, so the loser simply retries and picks it up.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.enums import SessionRevokeReason
from app.core.exceptions import (
    AccountInactive,
    AccountLocked,
    InvalidCredentials,
    InvalidRefreshToken,
    InvalidToken,
    RefreshRace,
    RefreshTokenReused,
)
from app.core.ids import uuid7
from app.core.security import (
    create_access_token,
    generate_refresh_token,
    hash_ip,
    hash_password,
    hash_refresh_token,
    needs_rehash,
    refresh_token_expiry,
    verify_password,
)
from app.models.admin import Admin
from app.repositories.admin_repo import AdminRepository
from app.repositories.session_repo import SessionRepository
from app.services.permission_service import PermissionService

logger = logging.getLogger(__name__)


def _max_failed_attempts() -> int:
    return settings.max_failed_login_attempts


def _lockout_duration() -> timedelta:
    return timedelta(minutes=settings.account_lockout_minutes)


def _race_window() -> timedelta:
    """Read at call time, not import time, so tests can vary it."""
    return timedelta(seconds=settings.refresh_race_window_seconds)


@dataclass(frozen=True)
class Principal:
    """The authenticated caller, as every downstream layer sees it.

    Carries resolved permissions rather than a role name, so authorisation is a
    set membership test and adding a role later changes no call site.
    """

    admin_id: UUID
    email: str
    full_name: str
    role_key: str
    permissions: frozenset[str]

    def has(self, permission: str) -> bool:
        return permission in self.permissions

    def has_any(self, *permissions: str) -> bool:
        return any(p in self.permissions for p in permissions)


@dataclass(frozen=True)
class TokenPair:
    access_token: str
    access_expires_at: datetime
    refresh_token: str
    refresh_expires_at: datetime


class AuthService:
    def __init__(
        self,
        session: AsyncSession,
        *,
        permissions: PermissionService | None = None,
    ) -> None:
        self.session = session
        self.admins = AdminRepository(session)
        self.sessions = SessionRepository(session)
        self.permissions = permissions or PermissionService(session)

    # --- login ------------------------------------------------------------

    async def authenticate(
        self,
        email: str,
        password: str,
        *,
        user_agent: str | None = None,
        ip: str | None = None,
    ) -> tuple[Admin, TokenPair]:
        admin = await self.admins.get_by_email(email)

        # Verification runs even when the account does not exist, against a
        # dummy hash, so response timing cannot be used to enumerate accounts.
        password_ok = verify_password(password, admin.password_hash if admin else None)

        if admin is None or not password_ok:
            if admin is not None:
                locked = await self.admins.register_failed_attempt(
                    admin, threshold=_max_failed_attempts(), lock_for=_lockout_duration()
                )
                if locked:
                    logger.warning("account locked after repeated failures: %s", admin.id)
            raise InvalidCredentials()

        # Checked *after* the password so a wrong password against a locked or
        # inactive account still reveals nothing about the account's state.
        if admin.locked_until and admin.locked_until > datetime.now(UTC):
            remaining = int((admin.locked_until - datetime.now(UTC)).total_seconds())
            raise AccountLocked(f"Account is locked. Try again in {remaining} seconds.")

        if not admin.is_active:
            raise AccountInactive("This account has been deactivated.")

        # Transparently upgrade a hash produced with older Argon2 parameters,
        # now that we hold the plaintext and know it is correct.
        if needs_rehash(admin.password_hash):
            admin.password_hash = hash_password(password)

        await self.admins.record_login(admin)

        pair = await self._issue_pair(
            admin,
            family_id=uuid7(),  # a new login starts a new lineage
            user_agent=user_agent,
            ip=ip,
        )
        return admin, pair

    # --- refresh ----------------------------------------------------------

    async def refresh(
        self,
        raw_token: str,
        *,
        user_agent: str | None = None,
        ip: str | None = None,
    ) -> tuple[Admin, TokenPair]:
        token_hash = hash_refresh_token(raw_token)

        # Row lock: two concurrent refreshes with the same token serialise here
        # rather than both reading an unrevoked row and both rotating.
        session_row = await self.sessions.get_by_hash(token_hash, for_update=True)
        if session_row is None:
            raise InvalidRefreshToken("Refresh token is not recognised.")

        now = datetime.now(UTC)

        if session_row.revoked_at is not None:
            rotated_recently = (
                session_row.revoked_reason == SessionRevokeReason.ROTATED
                and now - session_row.revoked_at <= _race_window()
            )
            if rotated_recently:
                # Benign: another tab won the race moments ago and has already
                # replaced the cookie. Do not punish the loser.
                logger.info("refresh race on family %s", session_row.family_id)
                raise RefreshRace()

            # Anything else replaying a revoked token is treated as theft.
            revoked = await self.sessions.revoke_family(
                session_row.family_id, SessionRevokeReason.REUSE_DETECTED
            )
            logger.warning(
                "refresh token reuse detected; revoked %d session(s) in family %s",
                revoked,
                session_row.family_id,
            )
            raise RefreshTokenReused()

        if session_row.expires_at <= now:
            await self.sessions.revoke(session_row, SessionRevokeReason.LOGOUT)
            raise InvalidRefreshToken("Refresh token has expired.")

        admin = await self.admins.get_with_role(session_row.admin_id)
        if admin is None or not admin.is_active:
            await self.sessions.revoke_family(
                session_row.family_id, SessionRevokeReason.ADMIN_ACTION
            )
            raise AccountInactive("This account is no longer active.")

        # Rotate: the presented token dies, a replacement joins the same family.
        pair = await self._issue_pair(
            admin,
            family_id=session_row.family_id,
            user_agent=user_agent,
            ip=ip,
        )
        new_row = await self.sessions.get_by_hash(hash_refresh_token(pair.refresh_token))
        await self.sessions.revoke(
            session_row,
            SessionRevokeReason.ROTATED,
            replaced_by=new_row.id if new_row else None,
        )
        return admin, pair

    # --- logout -----------------------------------------------------------

    async def logout(self, raw_token: str | None) -> None:
        """Revoke one session. Idempotent: logging out twice is not an error."""
        if not raw_token:
            return
        session_row = await self.sessions.get_by_hash(hash_refresh_token(raw_token))
        if session_row is None or session_row.revoked_at is not None:
            return
        await self.sessions.revoke(session_row, SessionRevokeReason.LOGOUT)

    async def logout_all(self, admin_id: UUID) -> int:
        return await self.sessions.revoke_all_for_admin(admin_id, SessionRevokeReason.LOGOUT)

    # --- principal resolution --------------------------------------------

    async def resolve_principal(self, admin_id: UUID, token_issued_at: datetime) -> Principal:
        """Turn a verified token into a Principal.

        The database is consulted on purpose. A signature check alone cannot
        tell whether the account was deactivated or its password changed since
        the token was minted, and for an admin API those must take effect
        immediately rather than after the token expires.
        """
        admin = await self.admins.get_with_role(admin_id)
        if admin is None:
            raise InvalidToken("Account no longer exists.")
        if not admin.is_active:
            raise AccountInactive("This account has been deactivated.")

        # Tokens minted before the current password are refused. One second of
        # tolerance absorbs timestamp truncation in the JWT `iat` claim.
        if token_issued_at < admin.password_changed_at - timedelta(seconds=1):
            raise InvalidToken("Credentials changed since this token was issued.")

        permissions = await self.permissions.resolve(admin.role_id)
        return Principal(
            admin_id=admin.id,
            email=admin.email,
            full_name=admin.full_name,
            role_key=admin.role.key,
            permissions=permissions,
        )

    # --- internals --------------------------------------------------------

    async def _issue_pair(
        self,
        admin: Admin,
        *,
        family_id: UUID,
        user_agent: str | None,
        ip: str | None,
    ) -> TokenPair:
        access_token, access_expires = create_access_token(
            admin_id=admin.id,
            role=admin.role.key,
            password_changed_at=admin.password_changed_at,
        )
        raw_refresh, refresh_hash = generate_refresh_token()
        expires_at = refresh_token_expiry()

        await self.sessions.create(
            admin_id=admin.id,
            token_hash=refresh_hash,
            family_id=family_id,
            expires_at=expires_at,
            user_agent=(user_agent or "")[:400] or None,
            ip_hash=hash_ip(ip),
        )

        return TokenPair(
            access_token=access_token,
            access_expires_at=access_expires,
            refresh_token=raw_refresh,
            refresh_expires_at=expires_at,
        )


def access_token_ttl() -> int:
    return settings.access_token_ttl_seconds
