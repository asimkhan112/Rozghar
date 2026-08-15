"""Append-only record of every privileged mutation.

Required the moment a second person has admin access. Written inside the same
transaction as the change it describes, so a committed change always has a
committed audit row.

No update or delete path exists at any layer — the API is read-only and
retention is enforced by a maintenance task, not by the application.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import (
    BigInteger,
    ForeignKey,
    Identity,
    Index,
    String,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, CreatedAtMixin


class AuditLog(CreatedAtMixin, Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(BigInteger(), Identity(), primary_key=True)

    #: SET NULL rather than CASCADE — the trail has to outlive the account.
    admin_id: Mapped[UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("admins.id", ondelete="SET NULL"), nullable=True
    )

    #: Dotted verb: 'job.publish', 'admin.role_change', 'report.resolve'.
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(32), nullable=False)
    entity_id: Mapped[UUID | None] = mapped_column(PgUUID(as_uuid=True), nullable=True)

    #: Changed fields only, never the whole row. A full-row snapshot on every
    #: edit turns this table into a second copy of the database.
    before: Mapped[dict | None] = mapped_column(JSONB(), nullable=True)
    after: Mapped[dict | None] = mapped_column(JSONB(), nullable=True)

    ip_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)

    __table_args__ = (
        # "What happened to this job?" — the most common audit question.
        Index(
            "ix_audit_logs_entity_created_at",
            "entity_type",
            "entity_id",
            text("created_at DESC"),
        ),
        # "What did this admin do?"
        Index("ix_audit_logs_admin_id_created_at", "admin_id", text("created_at DESC")),
        Index("ix_audit_logs_action_created_at", "action", text("created_at DESC")),
    )


__all__ = ["AuditLog"]
