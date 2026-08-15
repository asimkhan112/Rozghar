"""Role and permission lookups."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.models.rbac import Permission, Role
from app.repositories.base import BaseRepository


class RoleRepository(BaseRepository[Role]):
    model = Role

    async def get_by_key(self, key: str) -> Role | None:
        stmt = select(Role).where(Role.key == key).options(selectinload(Role.permissions))
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def get_with_permissions(self, role_id: UUID) -> Role | None:
        stmt = select(Role).where(Role.id == role_id).options(selectinload(Role.permissions))
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def list_with_permissions(self) -> list[Role]:
        stmt = select(Role).options(selectinload(Role.permissions)).order_by(Role.key)
        return list((await self.session.execute(stmt)).scalars().all())

    async def permission_keys_for(self, role_id: UUID) -> frozenset[str]:
        """Just the keys — avoids hydrating Permission objects that the
        authorisation check never inspects beyond their name."""
        stmt = select(Permission.key).join(Role.permissions).where(Role.id == role_id)
        return frozenset((await self.session.execute(stmt)).scalars().all())


class PermissionRepository(BaseRepository[Permission]):
    model = Permission

    async def get_by_key(self, key: str) -> Permission | None:
        stmt = select(Permission).where(Permission.key == key)
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def list_ordered(self) -> list[Permission]:
        stmt = select(Permission).order_by(Permission.group_name, Permission.key)
        return list((await self.session.execute(stmt)).scalars().all())
