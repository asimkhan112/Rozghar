"""Role, Permission and their association.

The rows here mirror `app.core.permissions`. They exist so the admin UI can
render a role editor and so custom roles become possible later — not so the
database can decide what the code enforces.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Index,
    String,
    Table,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import CITEXT
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, CreatedAtMixin, UUIDPkMixin

if TYPE_CHECKING:
    from app.models.admin import Admin


#: Association table. A plain Table rather than a model — it carries no
#: behaviour and is never queried on its own.
role_permissions = Table(
    "role_permissions",
    Base.metadata,
    Column(
        "role_id",
        PgUUID(as_uuid=True),
        ForeignKey("roles.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column(
        "permission_id",
        PgUUID(as_uuid=True),
        ForeignKey("permissions.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column("granted_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    # Reverse lookup: "which roles can publish?" — needed by the role editor.
    Index("ix_role_permissions_permission_id", "permission_id"),
)


class Permission(UUIDPkMixin, Base):
    """One capability the API can gate on.

    Seeded from `app.core.permissions.Permission`; never edited at runtime.
    """

    __tablename__ = "permissions"

    key: Mapped[str] = mapped_column(CITEXT(), nullable=False, unique=True)
    group_name: Mapped[str] = mapped_column(String(32), nullable=False)
    description: Mapped[str] = mapped_column(Text(), nullable=False)

    roles: Mapped[list[Role]] = relationship(
        secondary=role_permissions,
        back_populates="permissions",
        lazy="selectin",
    )

    __table_args__ = (Index("ix_permissions_group_name", "group_name"),)


class Role(UUIDPkMixin, CreatedAtMixin, Base):
    """A named bundle of permissions."""

    __tablename__ = "roles"

    key: Mapped[str] = mapped_column(CITEXT(), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    description: Mapped[str | None] = mapped_column(Text(), nullable=True)
    #: System roles are seeded and protected — they cannot be renamed or
    #: deleted, because the code and the seed migration both depend on them.
    is_system: Mapped[bool] = mapped_column(
        Boolean(), nullable=False, default=False, server_default=text("false")
    )
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    permissions: Mapped[list[Permission]] = relationship(
        secondary=role_permissions,
        back_populates="roles",
        lazy="selectin",
    )
    admins: Mapped[list[Admin]] = relationship(back_populates="role", lazy="noload")

    @property
    def permission_keys(self) -> frozenset[str]:
        return frozenset(p.key for p in self.permissions)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Role {self.key}>"


__all__ = ["Permission", "Role", "role_permissions", "UUID"]
