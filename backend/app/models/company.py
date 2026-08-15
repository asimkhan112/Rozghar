"""Employer records.

Deliberately introduced in Milestone 1 with a *nullable* link from jobs. V1
keeps `company_name` denormalised on the job and may leave `company_id` null;
V2 backfills it with trigram matching once scrapers start producing "Systems
Ltd", "Systems Limited" and "SystemsLtd" for one employer. Creating the table
now means that is a data job rather than a schema migration under load.
"""

from __future__ import annotations

from sqlalchemy import Boolean, CheckConstraint, Index, Integer, SmallInteger, String, text
from sqlalchemy.dialects.postgresql import CITEXT
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPkMixin


class Company(UUIDPkMixin, TimestampMixin, Base):
    __tablename__ = "companies"

    name: Mapped[str] = mapped_column(String(160), nullable=False)
    slug: Mapped[str] = mapped_column(CITEXT(), nullable=False, unique=True)

    logo_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    #: Two-letter fallback rendered when there is no logo image.
    monogram: Mapped[str | None] = mapped_column(String(2), nullable=True)
    #: Index into the frontend logo palette. Stored rather than derived from an
    #: identifier so re-keying a row can never reshuffle card colours.
    palette_index: Mapped[int] = mapped_column(
        SmallInteger(), nullable=False, default=0, server_default=text("0")
    )

    website: Mapped[str | None] = mapped_column(String(500), nullable=True)
    verified: Mapped[bool] = mapped_column(
        Boolean(), nullable=False, default=False, server_default=text("false")
    )
    job_count: Mapped[int] = mapped_column(
        Integer(), nullable=False, default=0, server_default=text("0")
    )

    __table_args__ = (
        CheckConstraint("palette_index BETWEEN 0 AND 5", name="palette_index_in_range"),
        CheckConstraint("job_count >= 0", name="job_count_non_negative"),
        # Trigram index for the V2 dedupe pass. Created here because adding a
        # GIN index to a populated table later means a long lock.
        Index(
            "ix_companies_name_trgm",
            "name",
            postgresql_using="gin",
            postgresql_ops={"name": "gin_trgm_ops"},
        ),
    )


__all__ = ["Company"]
