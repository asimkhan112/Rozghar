"""Admin account lifecycle: creation, role changes, deactivation, sessions.

This is the most dangerous service in the application. Everything it does is
either granting access or taking it away, so three invariants are enforced here
rather than trusted to the caller:

**Nobody can lock everyone out.** Deactivating or demoting the last active
account that holds `ADMIN_MANAGE` leaves a system with no administrator and no
way back except direct database access. Checked before the write, not after.

**Nobody can escalate themselves.** An admin cannot change their own role or
deactivate their own account. Both are refused even for a super admin — the
second person exists precisely so the first cannot act unilaterally.

**Access changes take effect now.** A role change rewrites what someone may do,
so it revokes their sessions and bumps the RBAC cache version. Waiting for a
fifteen-minute token expiry is not "eventually consistent", it is a window.
"""

from __future__ import annotations

import logging
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import SessionRevokeReason
from app.core.exceptions import Conflict, DomainError, NotFound, PermissionDenied
from app.core.permissions import Permission
from app.core.security import hash_password, hash_refresh_token, verify_password
from app.models.admin import Admin, AdminSession
from app.repositories.admin_management_repo import AdminFilters, AdminManagementRepository
from app.repositories.rbac_repo import RoleRepository
from app.repositories.session_repo import SessionRepository
from app.services.audit_service import AuditService
from app.services.auth_service import Principal
from app.services.permission_service import PermissionService

logger = logging.getLogger(__name__)

#: How long an issued reset token stays usable. Short, because the token is
#: delivered out-of-band by a human and a link that works for a week is a
#: credential sitting in someone's chat history.
RESET_TTL = timedelta(hours=2)

#: Fields worth auditing on an admin record. `password_hash` is excluded here
#: *and* redacted in `AuditService`, because one layer of defence around a
#: credential is not enough.
_AUDITED_FIELDS = ("email", "full_name", "is_active", "role_id")


class LastAdministrator(DomainError):
    status = 409
    code = "last_administrator"
    title = "This would leave the platform without an administrator"


class SelfModification(DomainError):
    status = 403
    code = "self_modification"
    title = "You cannot perform this action on your own account"


class EmailTaken(Conflict):
    code = "email_taken"
    title = "An account with that email already exists"


class InvalidResetToken(DomainError):
    status = 400
    code = "invalid_reset_token"
    title = "This reset link is invalid, expired, or already used"


@dataclass(frozen=True)
class AdminPage:
    items: list[Admin]
    total: int
    page: int
    per_page: int

    @property
    def total_pages(self) -> int:
        return (self.total + self.per_page - 1) // self.per_page if self.per_page else 0

    @property
    def has_more(self) -> bool:
        return self.page * self.per_page < self.total


@dataclass(frozen=True)
class IssuedReset:
    """The raw token exists only in this object and the response that carries
    it. Nothing persists it, and it is never logged."""

    token: str
    expires_at: datetime


def _snapshot(admin: Admin) -> dict[str, Any]:
    return {field: getattr(admin, field) for field in _AUDITED_FIELDS}


class AdminManagementService:
    def __init__(
        self,
        session: AsyncSession,
        *,
        permissions: PermissionService | None = None,
    ) -> None:
        self.session = session
        self.admins = AdminManagementRepository(session)
        self.roles = RoleRepository(session)
        self.sessions = SessionRepository(session)
        self.audit = AuditService(session)
        self.permissions = permissions

    # --- reads ------------------------------------------------------------

    async def list(self, filters: AdminFilters, *, page: int, per_page: int) -> AdminPage:
        total = await self.admins.count(filters)
        items = await self.admins.list(filters, limit=per_page, offset=(page - 1) * per_page)
        return AdminPage(items=items, total=total, page=page, per_page=per_page)

    async def get(self, admin_id: UUID) -> Admin:
        admin = await self.admins.get_detail(admin_id)
        if admin is None:
            raise NotFound("Admin account not found.")
        return admin

    async def list_sessions(
        self, *, admin_id: UUID | None = None, active_only: bool = True
    ) -> list[tuple[AdminSession, str, str]]:
        return await self.admins.list_sessions(admin_id=admin_id, active_only=active_only)

    # --- writes -----------------------------------------------------------

    async def create(
        self, data: dict[str, Any], *, principal: Principal, ip_hash: str | None = None
    ) -> Admin:
        role = await self.roles.get_with_permissions(data["role_id"])
        if role is None:
            raise NotFound("That role does not exist.")

        if await self.admins.email_exists(data["email"]):
            raise EmailTaken("An account with that email already exists.")

        admin = Admin(
            email=data["email"],
            full_name=data["full_name"],
            password_hash=hash_password(data["password"]),
            role_id=role.id,
            is_active=True,
            created_by=principal.admin_id,
        )
        self.admins.add(admin)
        try:
            await self.session.flush()
        except IntegrityError as exc:
            await self.session.rollback()
            # The uniqueness check above loses a race; the constraint does not.
            if "admins_email" in str(exc.orig):
                raise EmailTaken("An account with that email already exists.") from exc
            raise

        await self.audit.record(
            admin_id=principal.admin_id,
            action="admin.create",
            entity_type="admin",
            entity_id=admin.id,
            after={"email": admin.email, "full_name": admin.full_name, "role": role.key},
            ip_hash=ip_hash,
        )
        return await self.get(admin.id)

    async def update(
        self,
        admin_id: UUID,
        changes: dict[str, Any],
        *,
        principal: Principal,
        ip_hash: str | None = None,
    ) -> Admin:
        """Update name, activation state, or role.

        Locked for the duration. Two operators demoting the same account
        concurrently would otherwise both read "two administrators remain" and
        both proceed, leaving zero — the check and the write have to be in one
        serialised unit.
        """
        admin = await self.admins.get_for_update(admin_id)
        if admin is None:
            raise NotFound("Admin account not found.")

        before = _snapshot(admin)
        is_self = admin.id == principal.admin_id
        role_changed = "role_id" in changes and changes["role_id"] != admin.role_id
        deactivating = changes.get("is_active") is False and admin.is_active

        if is_self and (role_changed or deactivating):
            raise SelfModification(
                "You cannot change your own role or deactivate your own account. "
                "Ask another administrator."
            )

        if role_changed:
            new_role = await self.roles.get_with_permissions(changes["role_id"])
            if new_role is None:
                raise NotFound("That role does not exist.")

        if deactivating or role_changed:
            await self._assert_not_last_administrator(admin, changes)

        if "full_name" in changes and changes["full_name"] is not None:
            admin.full_name = changes["full_name"]
        if "is_active" in changes and changes["is_active"] is not None:
            admin.is_active = changes["is_active"]
        if role_changed:
            admin.role_id = changes["role_id"]

        after = _snapshot(admin)
        if before == after:
            return await self.get(admin_id)

        action = (
            "admin.role_change"
            if role_changed
            else ("admin.deactivate" if deactivating else "admin.update")
        )
        if changes.get("is_active") is True and not before["is_active"]:
            action = "admin.activate"

        await self.audit.record_change(
            admin_id=principal.admin_id,
            action=action,
            entity_type="admin",
            entity_id=admin.id,
            before=before,
            after=after,
            ip_hash=ip_hash,
        )

        # Access changed, so live credentials must stop working now rather
        # than at the next token expiry.
        if role_changed or deactivating:
            revoked = await self.sessions.revoke_all_for_admin(
                admin.id, SessionRevokeReason.ADMIN_ACTION
            )
            logger.info(
                "revoked sessions after an access change",
                extra={
                    "event": "admin.sessions_revoked",
                    "target_admin": str(admin.id),
                    "count": revoked,
                },
            )
        if role_changed:
            await self._invalidate_permission_cache()

        await self.session.flush()
        return await self.get(admin_id)

    async def deactivate(
        self, admin_id: UUID, *, principal: Principal, ip_hash: str | None = None
    ) -> None:
        """DELETE means deactivate.

        Accounts are never row-deleted: `audit_logs.admin_id` and
        `jobs.created_by` reference them, the latter with RESTRICT, so the
        database would refuse anyway. Deactivation is the honest operation and
        it preserves the trail.
        """
        await self.update(admin_id, {"is_active": False}, principal=principal, ip_hash=ip_hash)

    async def _assert_not_last_administrator(self, admin: Admin, changes: dict[str, Any]) -> None:
        """Refuse a change that would leave nobody able to manage admins."""
        role = await self.roles.get_with_permissions(admin.role_id)
        manage = Permission.ADMIN_MANAGE.value
        if role is None or manage not in role.permission_keys:
            return  # this account was never an administrator

        if "role_id" in changes and changes["role_id"] != admin.role_id:
            new_role = await self.roles.get_with_permissions(changes["role_id"])
            if new_role is not None and manage in new_role.permission_keys:
                return  # still an administrator afterwards

        remaining = await self.admins.count_active_holders_of(manage)
        if remaining <= 1:
            raise LastAdministrator(
                "This is the last active account that can manage administrators. "
                "Grant another account that permission first."
            )

    # --- sessions ---------------------------------------------------------

    async def revoke_session(
        self, session_id: UUID, *, principal: Principal, ip_hash: str | None = None
    ) -> bool:
        """Revoke one session. Idempotent — revoking twice is not an error."""
        row = await self.admins.get_session(session_id)
        if row is None:
            raise NotFound("Session not found.")
        if row.revoked_at is not None:
            return False

        await self.sessions.revoke(row, SessionRevokeReason.ADMIN_ACTION)
        await self.audit.record(
            admin_id=principal.admin_id,
            action="admin.session_revoke",
            entity_type="admin_session",
            entity_id=row.id,
            after={"admin_id": str(row.admin_id), "reason": SessionRevokeReason.ADMIN_ACTION.value},
            ip_hash=ip_hash,
        )
        return True

    async def logout_everyone(self, *, principal: Principal, ip_hash: str | None = None) -> int:
        """Sign every admin out, including the caller.

        The break-glass response to a suspected credential compromise. It
        deliberately includes the caller: an operator who has to stay signed in
        while everyone else is ejected is describing a different, narrower
        action, and pretending otherwise would leave the one session an
        attacker might be holding.
        """
        sessions = await self.admins.list_sessions(active_only=True, limit=10_000)
        count = 0
        for row, _, _ in sessions:
            await self.sessions.revoke(row, SessionRevokeReason.ADMIN_ACTION)
            count += 1

        await self.audit.record(
            admin_id=principal.admin_id,
            action="admin.logout_all",
            entity_type="admin_session",
            after={"revoked": count},
            ip_hash=ip_hash,
        )
        logger.warning(
            "all admin sessions revoked",
            extra={
                "event": "admin.logout_all",
                "by": str(principal.admin_id),
                "count": count,
            },
        )
        return count

    # --- passwords --------------------------------------------------------

    async def issue_password_reset(
        self, admin_id: UUID, *, principal: Principal, ip_hash: str | None = None
    ) -> IssuedReset:
        """Mint a single-use reset token, returned once.

        Only the hash is stored. Any outstanding reset for the account is
        discarded first — two live reset links for one account is one more than
        can ever be legitimate.
        """
        admin = await self.admins.get_for_update(admin_id)
        if admin is None:
            raise NotFound("Admin account not found.")

        await self.admins.invalidate_resets_for(admin.id)

        raw = secrets.token_urlsafe(32)
        expires_at = datetime.now(UTC) + RESET_TTL
        await self.admins.create_reset(
            admin_id=admin.id,
            token_hash=hash_refresh_token(raw),
            issued_by=principal.admin_id,
            expires_at=expires_at,
        )
        await self.audit.record(
            admin_id=principal.admin_id,
            action="admin.password_reset_issued",
            entity_type="admin",
            entity_id=admin.id,
            after={"expires_at": expires_at.isoformat()},
            ip_hash=ip_hash,
        )
        return IssuedReset(token=raw, expires_at=expires_at)

    async def consume_password_reset(self, token: str, new_password: str) -> Admin:
        """Redeem a reset token and set the new password.

        Unauthenticated by necessity — the whole point is that the holder
        cannot sign in. The token is the credential, so it is single-use, short
        lived, and consuming it revokes every session the account had.
        """
        reset = await self.admins.get_reset_by_hash(hash_refresh_token(token))
        now = datetime.now(UTC)
        if reset is None or not reset.is_usable(now):
            # One message for unknown, expired and already-used. Distinguishing
            # them tells an attacker which of their guesses was once real.
            raise InvalidResetToken("This reset link is invalid, expired, or already used.")

        admin = await self.admins.get_for_update(reset.admin_id)
        if admin is None or not admin.is_active:
            raise InvalidResetToken("This reset link is invalid, expired, or already used.")

        admin.password_hash = hash_password(new_password)
        admin.password_changed_at = now
        admin.failed_attempts = 0
        admin.locked_until = None
        reset.used_at = now

        await self.sessions.revoke_all_for_admin(admin.id, SessionRevokeReason.PASSWORD_CHANGE)
        await self.audit.record(
            admin_id=admin.id,
            action="admin.password_reset_used",
            entity_type="admin",
            entity_id=admin.id,
            after={"password_changed_at": now.isoformat()},
        )
        await self.session.flush()
        return admin

    async def change_own_password(
        self, *, principal: Principal, current_password: str, new_password: str
    ) -> None:
        """Self-service change. Requires the current password.

        Every other session is revoked; the caller's own is not. Signing
        someone out of the tab they just used to change their password is a
        way of teaching people not to change their passwords.
        """
        admin = await self.admins.get_for_update(principal.admin_id)
        if admin is None:
            raise NotFound("Admin account not found.")
        if not verify_password(current_password, admin.password_hash):
            raise PermissionDenied("The current password is incorrect.")

        now = datetime.now(UTC)
        admin.password_hash = hash_password(new_password)
        admin.password_changed_at = now
        await self.admins.invalidate_resets_for(admin.id)
        await self.sessions.revoke_all_for_admin(admin.id, SessionRevokeReason.PASSWORD_CHANGE)
        await self.audit.record(
            admin_id=admin.id,
            action="admin.password_change",
            entity_type="admin",
            entity_id=admin.id,
            after={"password_changed_at": now.isoformat()},
        )
        await self.session.flush()

    # --- cache ------------------------------------------------------------

    async def _invalidate_permission_cache(self) -> None:
        """Bump the RBAC cache version after a grant change.

        One INCR makes every cached role set for every role unreachable at
        once. Deleting keys individually can leave a straggler, and a straggler
        here means somebody keeps a permission that was revoked.
        """
        if self.permissions is not None:
            await self.permissions.invalidate()


__all__ = [
    "AdminManagementService",
    "AdminPage",
    "EmailTaken",
    "InvalidResetToken",
    "IssuedReset",
    "LastAdministrator",
    "SelfModification",
]
