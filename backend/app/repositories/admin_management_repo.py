"""Admin account, session and reset-token persistence for the management API.

Separate from `AdminRepository`, which serves the authentication path and is
tuned for it — one admin, by id or email, with role and permissions eagerly
loaded. This one serves a list screen: many admins, filtered and paginated,
where eager-loading every role's permission set would be a wasted join on every
row.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import Select, delete, func, select
from sqlalchemy.orm import selectinload

from app.models.admin import Admin, AdminPasswordReset, AdminSession
from app.models.rbac import Permission, Role, role_permissions
from app.repositories.base import BaseRepository


@dataclass(frozen=True)
class AdminFilters:
    is_active: bool | None = None
    role_id: UUID | None = None
    #: Substring match on name or email, for the list screen's search box.
    search: str | None = None


class AdminManagementRepository(BaseRepository[Admin]):
    model = Admin

    # --- accounts ---------------------------------------------------------

    def _apply(self, stmt: Select, filters: AdminFilters) -> Select:
        if filters.is_active is not None:
            stmt = stmt.where(Admin.is_active.is_(filters.is_active))
        if filters.role_id is not None:
            stmt = stmt.where(Admin.role_id == filters.role_id)
        if filters.search:
            pattern = f"%{filters.search.strip()}%"
            # `email` is CITEXT so LIKE is already case-insensitive there;
            # `full_name` is not, hence the explicit ilike.
            stmt = stmt.where(Admin.full_name.ilike(pattern) | Admin.email.like(pattern))
        return stmt

    async def count(self, filters: AdminFilters) -> int:
        return (
            await self.session.execute(
                self._apply(select(func.count()).select_from(Admin), filters)
            )
        ).scalar_one()

    async def list(self, filters: AdminFilters, *, limit: int, offset: int) -> list[Admin]:
        """Role only, not its permissions.

        The list screen renders a role name. Loading each role's permission set
        to display it would be a second query returning hundreds of rows that
        nothing reads.
        """
        stmt = (
            self._apply(select(Admin), filters)
            .options(selectinload(Admin.role))
            .order_by(Admin.created_at.desc(), Admin.id.desc())
            .limit(limit)
            .offset(offset)
        )
        return list((await self.session.execute(stmt)).scalars().unique().all())

    async def get_detail(self, admin_id: UUID) -> Admin | None:
        """One admin with the full permission set — the detail screen."""
        stmt = (
            select(Admin)
            .where(Admin.id == admin_id)
            .options(selectinload(Admin.role).selectinload(Role.permissions))
        )
        return (await self.session.execute(stmt)).scalars().unique().one_or_none()

    async def get_for_update(self, admin_id: UUID) -> Admin | None:
        stmt = select(Admin).where(Admin.id == admin_id).with_for_update()
        return (await self.session.execute(stmt)).scalars().one_or_none()

    async def email_exists(self, email: str) -> bool:
        stmt = select(Admin.id).where(Admin.email == email).limit(1)
        return (await self.session.execute(stmt)).first() is not None

    async def count_active_holders_of(self, permission_key: str) -> int:
        """How many *active* accounts still hold a given permission.

        The guard behind "you cannot lock everyone out": deactivating the last
        account that can manage admins leaves a system nobody can administer,
        and the only fix is direct database access.
        """
        stmt = (
            select(func.count())
            .select_from(Admin)
            .join(Role, Role.id == Admin.role_id)
            .join(role_permissions, role_permissions.c.role_id == Role.id)
            .join(Permission, Permission.id == role_permissions.c.permission_id)
            .where(Admin.is_active.is_(True), Permission.key == permission_key)
        )
        return (await self.session.execute(stmt)).scalar_one()

    # --- sessions ---------------------------------------------------------

    async def list_sessions(
        self, *, admin_id: UUID | None = None, active_only: bool = True, limit: int = 100
    ) -> list[tuple[AdminSession, str, str]]:
        """Sessions with the owning account's identity attached.

        Joined rather than lazy-loaded: the platform-wide session list is the
        screen where an operator spots an unfamiliar device, and it is useless
        without knowing whose device it is.
        """
        stmt = (
            select(AdminSession, Admin.email, Admin.full_name)
            .join(Admin, Admin.id == AdminSession.admin_id)
            .order_by(AdminSession.issued_at.desc())
            .limit(limit)
        )
        if admin_id is not None:
            stmt = stmt.where(AdminSession.admin_id == admin_id)
        if active_only:
            stmt = stmt.where(
                AdminSession.revoked_at.is_(None),
                AdminSession.expires_at > datetime.now(UTC),
            )
        return [(row[0], row[1], row[2]) for row in (await self.session.execute(stmt)).all()]

    async def get_session(self, session_id: UUID) -> AdminSession | None:
        return await self.session.get(AdminSession, session_id)

    # --- password resets --------------------------------------------------

    async def create_reset(
        self, *, admin_id: UUID, token_hash: str, issued_by: UUID | None, expires_at: datetime
    ) -> AdminPasswordReset:
        reset = AdminPasswordReset(
            admin_id=admin_id,
            token_hash=token_hash,
            issued_by=issued_by,
            expires_at=expires_at,
        )
        self.session.add(reset)
        await self.session.flush()
        return reset

    async def get_reset_by_hash(self, token_hash: str) -> AdminPasswordReset | None:
        stmt = (
            select(AdminPasswordReset)
            .where(AdminPasswordReset.token_hash == token_hash)
            .with_for_update()
        )
        return (await self.session.execute(stmt)).scalars().one_or_none()

    async def invalidate_resets_for(self, admin_id: UUID) -> int:
        """Outstanding resets die when a new one is issued or the password
        changes. Two live reset links for one account is one more than can ever
        be legitimate."""
        now = datetime.now(UTC)
        stmt = (
            delete(AdminPasswordReset)
            .where(
                AdminPasswordReset.admin_id == admin_id,
                AdminPasswordReset.used_at.is_(None),
                AdminPasswordReset.expires_at > now,
            )
            .returning(AdminPasswordReset.id)
        )
        removed = (await self.session.execute(stmt)).scalars().all()
        await self.session.flush()
        return len(removed)


__all__ = ["AdminFilters", "AdminManagementRepository"]
