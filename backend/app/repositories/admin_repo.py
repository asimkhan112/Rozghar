"""Admin account persistence."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.orm import selectinload

from app.models.admin import Admin
from app.models.rbac import Role
from app.repositories.base import BaseRepository


class AdminRepository(BaseRepository[Admin]):
    model = Admin

    async def get_with_role(self, admin_id: UUID) -> Admin | None:
        """Load the admin together with its role and that role's permissions.

        Eager-loaded in one round trip: the permission set is needed on every
        authenticated request, so a lazy load here would be an N+1 on the
        hottest path in the API.
        """
        stmt = (
            select(Admin)
            .where(Admin.id == admin_id)
            .options(selectinload(Admin.role).selectinload(Role.permissions))
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def get_by_email(self, email: str) -> Admin | None:
        """Case-insensitive by virtue of the CITEXT column."""
        stmt = (
            select(Admin)
            .where(Admin.email == email)
            .options(selectinload(Admin.role).selectinload(Role.permissions))
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def record_login(self, admin: Admin, *, when: datetime | None = None) -> None:
        """Stamp a successful login and clear the failure counter."""
        admin.last_login_at = when or datetime.now(UTC)
        admin.failed_attempts = 0
        admin.locked_until = None
        await self.session.flush()

    async def register_failed_attempt(
        self, admin: Admin, *, threshold: int, lock_for: timedelta
    ) -> bool:
        """Increment the failure counter and lock the account at the threshold.

        Uses an atomic UPDATE rather than read-modify-write: concurrent login
        attempts against one account would otherwise lose increments, which is
        exactly the situation a brute-force attack produces.

        Returns True when this attempt caused a lock.
        """
        stmt = (
            update(Admin)
            .where(Admin.id == admin.id)
            .values(failed_attempts=Admin.failed_attempts + 1)
            .returning(Admin.failed_attempts)
        )
        attempts = (await self.session.execute(stmt)).scalar_one()

        locked = attempts >= threshold
        if locked:
            await self.session.execute(
                update(Admin)
                .where(Admin.id == admin.id)
                .values(locked_until=datetime.now(UTC) + lock_for, failed_attempts=0)
            )
        await self.session.flush()
        return locked

    async def set_password_hash(self, admin: Admin, password_hash: str) -> None:
        """Change the password and stamp the moment.

        `password_changed_at` moving forward is what invalidates every access
        token issued before the change.
        """
        admin.password_hash = password_hash
        admin.password_changed_at = datetime.now(UTC)
        await self.session.flush()

    async def count_active_with_role(self, role_key: str) -> int:
        """Used to enforce "at least one active super admin must exist"."""
        stmt = (
            select(Admin)
            .join(Role, Admin.role_id == Role.id)
            .where(Role.key == role_key, Admin.is_active.is_(True))
        )
        return len((await self.session.execute(stmt)).scalars().all())
