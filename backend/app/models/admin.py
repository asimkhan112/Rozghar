"""Admin accounts and their refresh-token sessions."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    SmallInteger,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import CITEXT
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.enums import SessionRevokeReason, pg_enum
from app.db.base import Base, TimestampMixin, UUIDPkMixin

if TYPE_CHECKING:
    from app.models.rbac import Role


class Admin(UUIDPkMixin, TimestampMixin, Base):
    """A staff account. There is no public registration path.

    Accounts are deactivated, never deleted — audit rows and `jobs.created_by`
    reference them with RESTRICT, which enforces that at the database level.
    """

    __tablename__ = "admins"

    #: CITEXT so casing can never produce two accounts for one person.
    email: Mapped[str] = mapped_column(CITEXT(), nullable=False, unique=True)
    #: Argon2id. Never a reversible format, never logged.
    password_hash: Mapped[str] = mapped_column(Text(), nullable=False)
    full_name: Mapped[str] = mapped_column(String(120), nullable=False)

    role_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("roles.id", ondelete="RESTRICT"),
        nullable=False,
    )

    is_active: Mapped[bool] = mapped_column(
        Boolean(), nullable=False, default=True, server_default=text("true")
    )
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    #: Access tokens issued before this instant are rejected, so a password
    #: change invalidates live sessions without waiting for token expiry.
    password_changed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    failed_attempts: Mapped[int] = mapped_column(
        SmallInteger(), nullable=False, default=0, server_default=text("0")
    )
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    #: Self-referential: who created this account. SET NULL so removing an
    #: account never cascades into the accounts it created.
    created_by: Mapped[UUID | None] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("admins.id", ondelete="SET NULL"),
        nullable=True,
    )

    role: Mapped[Role] = relationship(back_populates="admins", lazy="selectin")
    sessions: Mapped[list[AdminSession]] = relationship(
        back_populates="admin",
        cascade="all, delete-orphan",
        lazy="noload",
    )

    __table_args__ = (
        CheckConstraint("failed_attempts >= 0", name="failed_attempts_non_negative"),
        Index("ix_admins_role_id", "role_id"),
        # Partial index: lookups are almost always scoped to active accounts.
        Index("ix_admins_is_active", "is_active", postgresql_where=text("is_active")),
    )


class AdminSession(UUIDPkMixin, Base):
    """One opaque refresh token.

    The token itself is never stored — only its SHA-256 hash, so a database
    leak does not hand over live sessions. `family_id` ties a rotation lineage
    together: presenting a token that has already been rotated means it was
    captured, and the whole family is revoked.
    """

    __tablename__ = "admin_sessions"

    admin_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("admins.id", ondelete="CASCADE"),
        nullable=False,
    )
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    family_id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), nullable=False)

    replaced_by: Mapped[UUID | None] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("admin_sessions.id", ondelete="SET NULL"),
        nullable=True,
    )

    issued_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_reason: Mapped[SessionRevokeReason | None] = mapped_column(
        pg_enum(SessionRevokeReason, "session_revoke_reason"),
        nullable=True,
    )

    #: Shown in a "your sessions" list so an admin can spot an unknown device.
    user_agent: Mapped[str | None] = mapped_column(String(400), nullable=True)
    #: Hashed, never raw — abuse investigation without storing an identifier.
    ip_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)

    admin: Mapped[Admin] = relationship(back_populates="sessions", lazy="noload")

    __table_args__ = (
        CheckConstraint("expires_at > issued_at", name="expiry_after_issue"),
        Index("ix_admin_sessions_admin_id_revoked_at", "admin_id", "revoked_at"),
        Index("ix_admin_sessions_family_id", "family_id"),
        Index("ix_admin_sessions_expires_at", "expires_at"),
    )

    @property
    def is_active(self) -> bool:
        return self.revoked_at is None


__all__ = ["Admin", "AdminSession"]
