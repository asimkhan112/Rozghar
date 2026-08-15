"""Editorial taxonomy: categories, locations and sources.

These are tables rather than enums because operators add rows at runtime. The
value sets that belong to the domain rather than to editorial content
(work type, employment type, job status) are PostgreSQL enums instead.

`job_count` on each is a denormalised counter. The homepage renders category
counts on every visit, and a COUNT(*) per category per request is the kind of
query that looks fine at twelve jobs and is a problem at a hundred thousand.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Index,
    Integer,
    SmallInteger,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import CITEXT, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.enums import SourceType, pg_enum
from app.db.base import Base, TimestampMixin, UUIDPkMixin


class Category(UUIDPkMixin, TimestampMixin, Base):
    __tablename__ = "categories"

    name: Mapped[str] = mapped_column(String(80), nullable=False)
    slug: Mapped[str] = mapped_column(CITEXT(), nullable=False, unique=True)
    icon: Mapped[str | None] = mapped_column(String(16), nullable=True)
    description: Mapped[str | None] = mapped_column(Text(), nullable=True)

    #: Deactivated rather than deleted — jobs reference this with RESTRICT.
    is_active: Mapped[bool] = mapped_column(
        Boolean(), nullable=False, default=True, server_default=text("true")
    )
    sort_order: Mapped[int] = mapped_column(
        SmallInteger(), nullable=False, default=0, server_default=text("0")
    )
    job_count: Mapped[int] = mapped_column(
        Integer(), nullable=False, default=0, server_default=text("0")
    )

    __table_args__ = (
        CheckConstraint("job_count >= 0", name="job_count_non_negative"),
        Index("ix_categories_is_active_sort_order", "is_active", "sort_order"),
    )


class Location(UUIDPkMixin, TimestampMixin, Base):
    __tablename__ = "locations"

    city: Mapped[str | None] = mapped_column(String(80), nullable=True)
    region: Mapped[str | None] = mapped_column(String(80), nullable=True)
    #: ISO 3166-1 alpha-2.
    country: Mapped[str] = mapped_column(String(2), nullable=False, server_default=text("'PK'"))
    slug: Mapped[str] = mapped_column(CITEXT(), nullable=False, unique=True)
    #: Pre-composed for display: "Lahore, Pakistan", "Remote – Worldwide".
    display_name: Mapped[str] = mapped_column(String(160), nullable=False)

    is_remote: Mapped[bool] = mapped_column(
        Boolean(), nullable=False, default=False, server_default=text("false")
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean(), nullable=False, default=True, server_default=text("true")
    )
    job_count: Mapped[int] = mapped_column(
        Integer(), nullable=False, default=0, server_default=text("0")
    )

    __table_args__ = (
        # A physical location must name its city; a remote one need not.
        CheckConstraint("is_remote OR city IS NOT NULL", name="city_required_unless_remote"),
        CheckConstraint("job_count >= 0", name="job_count_non_negative"),
        Index("ix_locations_country_city", "country", "city"),
        Index("ix_locations_is_remote", "is_remote", postgresql_where=text("is_remote")),
    )


class Source(UUIDPkMixin, TimestampMixin, Base):
    """Where a listing came from.

    Present in V1 even though every job is entered by hand: per-source
    click-through rate is impossible to compute unless every job carries its
    origin, and seeding a `manual` source now means V2 ingestion adds rows
    rather than requiring a migration.
    """

    __tablename__ = "sources"

    name: Mapped[str] = mapped_column(String(120), nullable=False)
    slug: Mapped[str] = mapped_column(CITEXT(), nullable=False, unique=True)
    type: Mapped[SourceType] = mapped_column(pg_enum(SourceType, "source_type"), nullable=False)
    base_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    is_active: Mapped[bool] = mapped_column(
        Boolean(), nullable=False, default=True, server_default=text("true")
    )

    #: Milestone-2+ scraper configuration: selectors, cadence, credentials ref.
    config: Mapped[dict] = mapped_column(
        JSONB(), nullable=False, server_default=text("'{}'::jsonb")
    )

    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (Index("ix_sources_is_active_type", "is_active", "type"),)


__all__ = ["Category", "Location", "Source"]
