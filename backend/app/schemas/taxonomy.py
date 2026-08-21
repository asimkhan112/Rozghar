"""Category, location and source schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated
from uuid import UUID

from pydantic import AfterValidator, Field, HttpUrl, StringConstraints, model_validator

from app.core.countries import COUNTRY_CODES
from app.core.enums import SourceType
from app.schemas.common import ORMModel, Slug, StrictModel


def _known_country(code: str) -> str:
    """Reject codes that are not ISO 3166-1 alpha-2.

    Without this any two characters are storable, and the damage surfaces far
    from the typo: the label, the sitemap and every share card for that market
    render "Berlin, DA" until somebody notices.
    """
    if code not in COUNTRY_CODES:
        raise ValueError(f"{code} is not an ISO 3166-1 alpha-2 country code")
    return code


#: Upper-cased before validation, so a caller sending "de" is corrected rather
#: than rejected — the case is a formatting detail, not a mistake.
CountryCode = Annotated[
    str,
    StringConstraints(strip_whitespace=True, to_upper=True, min_length=2, max_length=2),
    AfterValidator(_known_country),
]

# --- categories ----------------------------------------------------------


class CategoryCreate(StrictModel):
    name: str = Field(min_length=2, max_length=80)
    slug: Slug | None = None  # derived from name when omitted
    icon: str | None = Field(default=None, max_length=16)
    description: str | None = Field(default=None, max_length=500)
    sort_order: int = Field(default=0, ge=0, le=999)


class CategoryUpdate(StrictModel):
    name: str | None = Field(default=None, min_length=2, max_length=80)
    icon: str | None = Field(default=None, max_length=16)
    description: str | None = Field(default=None, max_length=500)
    sort_order: int | None = Field(default=None, ge=0, le=999)
    is_active: bool | None = None


class CategoryRead(ORMModel):
    id: UUID
    name: str
    slug: str
    icon: str | None
    job_count: int


class CategoryDetail(CategoryRead):
    description: str | None
    is_active: bool
    sort_order: int
    created_at: datetime
    updated_at: datetime


# --- locations -----------------------------------------------------------


class LocationCreate(StrictModel):
    city: str | None = Field(default=None, min_length=2, max_length=80)
    region: str | None = Field(default=None, max_length=80)
    #: Required, with no default. A default meant every location created
    #: through the console silently became Pakistani, which is precisely the
    #: bug this field exists to prevent.
    country: CountryCode
    is_remote: bool = False
    slug: Slug | None = None
    display_name: str | None = Field(default=None, max_length=160)

    @model_validator(mode="after")
    def city_required_unless_remote(self) -> LocationCreate:
        """Mirrors the database CHECK, so the caller gets a 422 with a field
        error rather than a 500 from a constraint violation."""
        if not self.is_remote and not self.city:
            raise ValueError("city is required for a non-remote location")
        return self


class LocationUpdate(StrictModel):
    city: str | None = Field(default=None, min_length=2, max_length=80)
    region: str | None = Field(default=None, max_length=80)
    #: Editable, so a location filed under the wrong country can be corrected
    #: rather than archived and recreated.
    country: CountryCode | None = None
    display_name: str | None = Field(default=None, max_length=160)
    is_active: bool | None = None


class LocationRead(ORMModel):
    id: UUID
    slug: str
    display_name: str
    city: str | None
    region: str | None
    country: str
    is_remote: bool
    job_count: int


class LocationDetail(LocationRead):
    is_active: bool
    created_at: datetime
    updated_at: datetime


class CountryRead(ORMModel):
    """One ISO 3166-1 alpha-2 country, for the location picker."""

    code: str
    name: str


# --- sources -------------------------------------------------------------


class SourceCreate(StrictModel):
    name: str = Field(min_length=2, max_length=120)
    slug: Slug | None = None
    type: SourceType = SourceType.MANUAL
    base_url: HttpUrl | None = None
    config: dict = Field(default_factory=dict)


class SourceUpdate(StrictModel):
    name: str | None = Field(default=None, min_length=2, max_length=120)
    base_url: HttpUrl | None = None
    is_active: bool | None = None
    config: dict | None = None


class SourceRead(ORMModel):
    """Public projection — deliberately omits `config`, which may hold
    credentials once scraper ingestion exists."""

    id: UUID
    name: str
    slug: str
    type: SourceType


class SourceDetail(SourceRead):
    base_url: str | None
    is_active: bool
    config: dict
    last_run_at: datetime | None
    last_success_at: datetime | None
    created_at: datetime
    updated_at: datetime
