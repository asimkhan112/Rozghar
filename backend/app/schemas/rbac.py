"""Role and permission schemas.

Permissions have no create or update schema by design: they are seeded from
`app.core.permissions.Permission` and are reference data, not editable content.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import Field

from app.schemas.common import ORMModel, StrictModel


class PermissionRead(ORMModel):
    id: UUID
    key: str
    group_name: str
    description: str


class RoleCreate(StrictModel):
    key: str = Field(min_length=2, max_length=64, pattern=r"^[a-z][a-z0-9_]*$")
    name: str = Field(min_length=2, max_length=64)
    description: str | None = Field(default=None, max_length=500)
    permission_keys: list[str] = Field(default_factory=list)


class RoleUpdate(StrictModel):
    """`key` and `is_system` are absent on purpose — neither may change."""

    name: str | None = Field(default=None, min_length=2, max_length=64)
    description: str | None = Field(default=None, max_length=500)
    permission_keys: list[str] | None = None


class RoleRead(ORMModel):
    id: UUID
    key: str
    name: str
    description: str | None
    is_system: bool
    created_at: datetime


class RoleDetail(RoleRead):
    permissions: list[PermissionRead] = Field(default_factory=list)
