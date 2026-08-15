"""Job schemas.

Four read models, not one:

    JobSummary  list rows — no description, no apply_url
    JobDetail   public detail page
    JobAdmin    adds editorial fields (status, counters, provenance)

`slug` never appears on a write model: it is derived server-side from title and
company, and frozen once published so shared links cannot break.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID

from pydantic import Field, HttpUrl, field_validator, model_validator

from app.core.enums import (
    EmploymentType,
    ExperienceLevel,
    JobStatus,
    SalaryPeriod,
    WorkType,
)
from app.schemas.common import ORMModel, ShortText, StrictModel
from app.schemas.taxonomy import CategoryRead, LocationRead, SourceRead

#: Display badge, computed from `featured` / `verified` / `expiry_date` rather
#: than stored. One stored enum could not express a listing that is both
#: verified and featured.
JobBadge = Literal["featured", "expiring", "verified", "fresh"]

BulletList = Annotated[list[ShortText], Field(default_factory=list, max_length=30)]

#: Link shorteners hide the real destination, which defeats apply-URL review.
BLOCKED_URL_HOSTS = frozenset(
    {"bit.ly", "tinyurl.com", "t.co", "goo.gl", "ow.ly", "is.gd", "buff.ly", "cutt.ly"}
)


class _JobWriteBase(StrictModel):
    title: str = Field(min_length=3, max_length=200)
    company_name: str = Field(min_length=2, max_length=160)
    company_id: UUID | None = None
    company_logo: HttpUrl | None = None
    logo_palette: int = Field(default=0, ge=0, le=5)

    category_id: UUID
    location_id: UUID
    source_id: UUID | None = None  # defaults to the seeded 'manual' source

    work_type: WorkType
    employment_type: EmploymentType
    experience_level: ExperienceLevel
    experience_min_years: int | None = Field(default=None, ge=0, le=50)
    experience_max_years: int | None = Field(default=None, ge=0, le=50)

    salary_min: Decimal | None = Field(default=None, ge=0, max_digits=12, decimal_places=2)
    salary_max: Decimal | None = Field(default=None, ge=0, max_digits=12, decimal_places=2)
    salary_currency: str = Field(default="PKR", min_length=3, max_length=3)
    salary_period: SalaryPeriod = SalaryPeriod.MONTH
    salary_is_disclosed: bool = True

    description: str = Field(min_length=50, max_length=20_000)
    requirements: BulletList
    responsibilities: BulletList
    benefits: BulletList
    apply_url: HttpUrl

    expiry_date: date | None = None

    @field_validator("salary_currency")
    @classmethod
    def currency_uppercase(cls, value: str) -> str:
        return value.upper()

    @field_validator("apply_url")
    @classmethod
    def reject_shorteners(cls, value: HttpUrl) -> HttpUrl:
        if value.scheme not in {"http", "https"}:
            raise ValueError("apply_url must be http or https")
        host = (value.host or "").lower().removeprefix("www.")
        if host in BLOCKED_URL_HOSTS:
            raise ValueError("link shorteners are not accepted — use the direct employer URL")
        return value

    @model_validator(mode="after")
    def check_ranges(self) -> _JobWriteBase:
        if (
            self.salary_min is not None
            and self.salary_max is not None
            and self.salary_max < self.salary_min
        ):
            raise ValueError("salary_max must be greater than or equal to salary_min")
        if (
            self.experience_min_years is not None
            and self.experience_max_years is not None
            and self.experience_max_years < self.experience_min_years
        ):
            raise ValueError("experience_max_years must be >= experience_min_years")
        return self

    @field_validator("expiry_date")
    @classmethod
    def expiry_in_future(cls, value: date | None) -> date | None:
        from datetime import UTC
        from datetime import datetime as _dt

        if value is not None and value <= _dt.now(UTC).date():
            raise ValueError("expiry_date must be in the future")
        return value


class JobCreate(_JobWriteBase):
    #: Publishing on create requires JOB_PUBLISH; the router enforces that.
    status: Literal[JobStatus.DRAFT, JobStatus.PUBLISHED] = JobStatus.DRAFT


class JobUpdate(StrictModel):
    """Partial update. Every field optional; immutable fields are simply
    absent, so sending one is a 422 rather than a silent no-op."""

    title: str | None = Field(default=None, min_length=3, max_length=200)
    company_name: str | None = Field(default=None, min_length=2, max_length=160)
    company_id: UUID | None = None
    company_logo: HttpUrl | None = None
    logo_palette: int | None = Field(default=None, ge=0, le=5)
    category_id: UUID | None = None
    location_id: UUID | None = None
    source_id: UUID | None = None
    work_type: WorkType | None = None
    employment_type: EmploymentType | None = None
    experience_level: ExperienceLevel | None = None
    experience_min_years: int | None = Field(default=None, ge=0, le=50)
    experience_max_years: int | None = Field(default=None, ge=0, le=50)
    salary_min: Decimal | None = Field(default=None, ge=0, max_digits=12, decimal_places=2)
    salary_max: Decimal | None = Field(default=None, ge=0, max_digits=12, decimal_places=2)
    salary_currency: str | None = Field(default=None, min_length=3, max_length=3)
    salary_period: SalaryPeriod | None = None
    salary_is_disclosed: bool | None = None
    description: str | None = Field(default=None, min_length=50, max_length=20_000)
    requirements: list[ShortText] | None = Field(default=None, max_length=30)
    responsibilities: list[ShortText] | None = Field(default=None, max_length=30)
    benefits: list[ShortText] | None = Field(default=None, max_length=30)
    apply_url: HttpUrl | None = None
    expiry_date: date | None = None


# --- action payloads -----------------------------------------------------


class JobVerifyRequest(StrictModel):
    verified: bool


class JobFeatureRequest(StrictModel):
    featured: bool
    until: datetime | None = None


class JobExpireRequest(StrictModel):
    reason: str | None = Field(default=None, max_length=300)


class JobPublishRequest(StrictModel):
    scheduled_at: datetime | None = None


# --- read models ---------------------------------------------------------


class SalaryRead(ORMModel):
    min: Decimal | None = None
    max: Decimal | None = None
    currency: str
    period: SalaryPeriod
    disclosed: bool


class JobSummary(ORMModel):
    """List row. Carries no description and no apply_url — a list of 20 should
    not ship 20 job descriptions."""

    id: UUID
    slug: str
    title: str
    company_name: str
    company_logo: str | None
    logo_palette: int
    category: CategoryRead
    location: LocationRead
    work_type: WorkType
    employment_type: EmploymentType
    experience_level: ExperienceLevel
    experience_min_years: int | None
    experience_max_years: int | None
    badge: JobBadge
    featured: bool
    verified: bool
    published_at: datetime | None
    expiry_date: date | None


class JobDetail(JobSummary):
    description: str
    requirements: list[str]
    responsibilities: list[str]
    benefits: list[str]
    apply_url: str
    source: SourceRead
    related: list[JobSummary] = Field(default_factory=list)


class JobAdmin(JobDetail):
    """Editorial view. Adds state, counters and provenance that must never
    appear on a public response."""

    status: JobStatus
    featured_until: datetime | None
    verified_at: datetime | None
    verified_by: UUID | None
    view_count: int
    apply_click_count: int
    save_count: int
    created_by: UUID
    updated_by: UUID | None
    version: int
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None
