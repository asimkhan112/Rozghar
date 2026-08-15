"""The job listing — the central entity of the product."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Computed,
    Numeric,
    SmallInteger,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import CITEXT, JSONB, TSVECTOR
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.enums import (
    EmploymentType,
    ExperienceLevel,
    JobStatus,
    SalaryPeriod,
    WorkType,
    pg_enum,
)
from app.db.base import Base, SoftDeleteMixin, TimestampMixin, UUIDPkMixin

if TYPE_CHECKING:
    from app.models.company import Company
    from app.models.report import Report
    from app.models.taxonomy import Category, Location, Source


class Job(UUIDPkMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "jobs"

    # --- identity --------------------------------------------------------
    #: Derived server-side from title + company, and frozen once published —
    #: changing it would break every link already shared.
    slug: Mapped[str] = mapped_column(CITEXT(), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)

    # --- employer --------------------------------------------------------
    #: Denormalised so the list query renders without joining companies.
    company_name: Mapped[str] = mapped_column(String(160), nullable=False)
    company_id: Mapped[UUID | None] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="SET NULL"),
        nullable=True,
    )
    company_logo: Mapped[str | None] = mapped_column(String(500), nullable=True)
    logo_palette: Mapped[int] = mapped_column(
        SmallInteger(), nullable=False, default=0, server_default=text("0")
    )

    # --- taxonomy --------------------------------------------------------
    # RESTRICT throughout: deleting a taxonomy row that live listings depend on
    # must fail loudly rather than orphan or cascade.
    category_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("categories.id", ondelete="RESTRICT"), nullable=False
    )
    location_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("locations.id", ondelete="RESTRICT"), nullable=False
    )
    source_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("sources.id", ondelete="RESTRICT"), nullable=False
    )

    # --- classification --------------------------------------------------
    work_type: Mapped[WorkType] = mapped_column(pg_enum(WorkType, "work_type"), nullable=False)
    employment_type: Mapped[EmploymentType] = mapped_column(
        pg_enum(EmploymentType, "employment_type"), nullable=False
    )
    experience_level: Mapped[ExperienceLevel] = mapped_column(
        pg_enum(ExperienceLevel, "experience_level"), nullable=False
    )
    #: Numeric range alongside the coarse enum: the enum drives the facet, the
    #: range drives "3-5 years" style filtering.
    experience_min_years: Mapped[int | None] = mapped_column(SmallInteger(), nullable=True)
    experience_max_years: Mapped[int | None] = mapped_column(SmallInteger(), nullable=True)

    # --- compensation ----------------------------------------------------
    # Numeric, not a display string: a formatted salary cannot be sorted or
    # range-filtered, which the product already offers as a control.
    salary_min: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    salary_max: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    salary_currency: Mapped[str] = mapped_column(
        String(3), nullable=False, server_default=text("'PKR'")
    )
    salary_period: Mapped[SalaryPeriod] = mapped_column(
        pg_enum(SalaryPeriod, "salary_period"),
        nullable=False,
        server_default=text("'month'"),
    )
    #: Distinguishes "salary not stated" from a genuine zero.
    salary_is_disclosed: Mapped[bool] = mapped_column(
        Boolean(), nullable=False, default=True, server_default=text("true")
    )

    # --- content ---------------------------------------------------------
    description: Mapped[str] = mapped_column(Text(), nullable=False)
    requirements: Mapped[list] = mapped_column(
        JSONB(), nullable=False, server_default=text("'[]'::jsonb")
    )
    responsibilities: Mapped[list] = mapped_column(
        JSONB(), nullable=False, server_default=text("'[]'::jsonb")
    )
    benefits: Mapped[list] = mapped_column(
        JSONB(), nullable=False, server_default=text("'[]'::jsonb")
    )
    apply_url: Mapped[str] = mapped_column(String(1000), nullable=False)

    # --- editorial state -------------------------------------------------
    status: Mapped[JobStatus] = mapped_column(
        pg_enum(JobStatus, "job_status"),
        nullable=False,
        server_default=text("'draft'"),
    )
    #: Independent booleans, not one badge enum — a listing can be verified and
    #: featured at the same time. The display badge is computed from these.
    featured: Mapped[bool] = mapped_column(
        Boolean(), nullable=False, default=False, server_default=text("false")
    )
    featured_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    verified: Mapped[bool] = mapped_column(
        Boolean(), nullable=False, default=False, server_default=text("false")
    )
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    verified_by: Mapped[UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("admins.id", ondelete="SET NULL"), nullable=True
    )

    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expiry_date: Mapped[date | None] = mapped_column(Date(), nullable=True)

    # --- counters --------------------------------------------------------
    # Caches refreshed from the analytics rollups, never the source of truth.
    # Incremented with atomic SQL, never read-modify-write.
    view_count: Mapped[int] = mapped_column(
        Integer(), nullable=False, default=0, server_default=text("0")
    )
    apply_click_count: Mapped[int] = mapped_column(
        Integer(), nullable=False, default=0, server_default=text("0")
    )
    save_count: Mapped[int] = mapped_column(
        Integer(), nullable=False, default=0, server_default=text("0")
    )

    # --- search denormalisation -----------------------------------------
    # A generated column cannot join or read another row, so the text that
    # feeds the search vector is mirrored here. Milestone 5 adds the triggers
    # that maintain these and the tsvector column that consumes them.
    location_text: Mapped[str] = mapped_column(Text(), nullable=False, server_default=text("''"))
    skills_text: Mapped[str] = mapped_column(Text(), nullable=False, server_default=text("''"))

    #: Weighted full-text vector, maintained by PostgreSQL.
    #:
    #: A: title · B: company and location · C: skills · D: description.
    #: `immutable_unaccent` exists because plain `unaccent()` is STABLE and a
    #: generated column requires IMMUTABLE. Every `to_tsvector` names its
    #: configuration for the same reason.
    search_vector: Mapped[str | None] = mapped_column(
        TSVECTOR(),
        Computed(
            "setweight(to_tsvector('english', immutable_unaccent(coalesce(title, ''))), 'A') "
            "|| setweight(to_tsvector('english', immutable_unaccent(coalesce(company_name, ''))), 'B') "
            "|| setweight(to_tsvector('english', immutable_unaccent(coalesce(location_text, ''))), 'B') "
            "|| setweight(to_tsvector('simple', immutable_unaccent(coalesce(location_text, ''))), 'B') "
            "|| setweight(to_tsvector('english', immutable_unaccent(coalesce(skills_text, ''))), 'C') "
            "|| setweight(to_tsvector('english', immutable_unaccent(coalesce(description, ''))), 'D')",
            persisted=True,
        ),
        nullable=True,
    )

    # --- provenance ------------------------------------------------------
    created_by: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("admins.id", ondelete="RESTRICT"), nullable=False
    )
    updated_by: Mapped[UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("admins.id", ondelete="SET NULL"), nullable=True
    )
    #: Optimistic concurrency. Two editors cannot silently overwrite each other.
    version: Mapped[int] = mapped_column(
        Integer(), nullable=False, default=1, server_default=text("1")
    )

    # --- relationships ---------------------------------------------------
    category: Mapped[Category] = relationship(lazy="selectin")
    location: Mapped[Location] = relationship(lazy="selectin")
    source: Mapped[Source] = relationship(lazy="selectin")
    company: Mapped[Company | None] = relationship(lazy="selectin")
    reports: Mapped[list[Report]] = relationship(
        back_populates="job", cascade="all, delete-orphan", lazy="noload"
    )

    __table_args__ = (
        # --- business invariants, enforced by the database ----------------
        CheckConstraint(
            "status <> 'published' OR published_at IS NOT NULL",
            name="published_requires_timestamp",
        ),
        CheckConstraint(
            "NOT featured OR status = 'published'",
            name="featured_requires_published",
        ),
        CheckConstraint(
            "NOT verified OR verified_by IS NOT NULL",
            name="verified_requires_verifier",
        ),
        CheckConstraint(
            "salary_max IS NULL OR salary_min IS NULL OR salary_max >= salary_min",
            name="salary_range_ordered",
        ),
        CheckConstraint(
            "experience_max_years IS NULL OR experience_min_years IS NULL "
            "OR experience_max_years >= experience_min_years",
            name="experience_range_ordered",
        ),
        CheckConstraint(
            "experience_min_years IS NULL OR experience_min_years BETWEEN 0 AND 50",
            name="experience_min_in_range",
        ),
        CheckConstraint("length(title) BETWEEN 3 AND 200", name="title_length"),
        CheckConstraint("length(description) >= 50", name="description_min_length"),
        CheckConstraint("apply_url ~ '^https?://'", name="apply_url_is_http"),
        CheckConstraint("logo_palette BETWEEN 0 AND 5", name="logo_palette_in_range"),
        CheckConstraint(
            "view_count >= 0 AND apply_click_count >= 0 AND save_count >= 0",
            name="counters_non_negative",
        ),
        # --- indexes ------------------------------------------------------
        # A soft-deleted job releases its slug for reuse.
        Index(
            "uq_jobs_slug_active", "slug", unique=True, postgresql_where=text("deleted_at IS NULL")
        ),
        # The default public list — the hottest query in the system.
        Index(
            "ix_jobs_status_published_at",
            "status",
            text("published_at DESC"),
            postgresql_where=text("deleted_at IS NULL"),
        ),
        Index("ix_jobs_category_id_status", "category_id", "status", text("published_at DESC")),
        Index("ix_jobs_location_id_status", "location_id", "status", text("published_at DESC")),
        Index("ix_jobs_work_type_status", "work_type", "status"),
        Index("ix_jobs_employment_type_status", "employment_type", "status"),
        Index("ix_jobs_experience_level_status", "experience_level", "status"),
        # Partial: the homepage rail reads a handful of rows out of many.
        Index(
            "ix_jobs_featured_published_at",
            "featured",
            text("published_at DESC"),
            postgresql_where=text("featured"),
        ),
        # The nightly expiry sweep touches only live rows.
        Index(
            "ix_jobs_expiry_date",
            "expiry_date",
            postgresql_where=text("status = 'published'"),
        ),
        Index("ix_jobs_source_id_published_at", "source_id", text("published_at DESC")),
        Index(
            "ix_jobs_company_id",
            "company_id",
            postgresql_where=text("company_id IS NOT NULL"),
        ),
        # Editor ownership checks scope by creator.
        Index("ix_jobs_created_by_created_at", "created_by", text("created_at DESC")),
        # Typo tolerance and prefix suggestions.
        Index(
            "ix_jobs_title_trgm",
            "title",
            postgresql_using="gin",
            postgresql_ops={"title": "gin_trgm_ops"},
        ),
        Index(
            "ix_jobs_company_name_trgm",
            "company_name",
            postgresql_using="gin",
            postgresql_ops={"company_name": "gin_trgm_ops"},
        ),
        # The full-text index — the dominant read path once search is live.
        Index("ix_jobs_search_vector", "search_vector", postgresql_using="gin"),
    )


__all__ = ["Job"]
