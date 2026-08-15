"""Declarative base and shared column mixins.

Mixins are composed rather than inherited from a single fat base, so a table
carries only the columns it genuinely has. Append-only tables
(`analytics_events`, `search_logs`, `audit_logs`) deliberately take no
`updated_at` — a column that is never written is a lie about the data.
"""

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import DateTime, MetaData, func, text
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.core.ids import uuid7

#: Explicit naming convention so Alembic emits stable, predictable constraint
#: names. Without it, autogenerate produces unnamed constraints that cannot be
#: dropped in a downgrade.
NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        pk = getattr(self, "id", None)
        return f"<{type(self).__name__} id={pk}>"


class UUIDPkMixin:
    """Time-ordered UUID primary key.

    Generated in Python rather than by the database so the identifier is known
    before flush — needed when building related rows in one unit of work.
    `gen_random_uuid()` remains as a server default for any row inserted
    outside the application (migrations, manual fixes).
    """

    id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        primary_key=True,
        default=uuid7,
        server_default=text("gen_random_uuid()"),
    )


class TimestampMixin:
    """`created_at` / `updated_at`, maintained by the database.

    Both defaults are server-side so rows written by a migration or by psql
    carry correct timestamps. `onupdate` covers ORM writes; a trigger would be
    needed to cover raw SQL updates, which Milestone 3 adds alongside the first
    mutations that need it.
    """

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class CreatedAtMixin:
    """`created_at` only — for append-only tables that are never updated."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class SoftDeleteMixin:
    """Soft deletion.

    Applied only where history must outlive the row. A deleted job still has to
    resolve for its reports and for historic analytics, so the row stays and
    `deleted_at` is set. Everything else in this schema deactivates instead
    (`is_active`), which is a different concept and deliberately not conflated.
    """

    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        default=None,
    )

    @property
    def is_deleted(self) -> bool:
        return self.deleted_at is not None


def as_dict(instance: Any) -> dict[str, Any]:
    """Column values as a plain dict. Used by audit diffing in Milestone 3."""
    return {c.name: getattr(instance, c.name) for c in instance.__table__.columns}
