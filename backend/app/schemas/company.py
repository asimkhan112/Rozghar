"""Company schemas."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import Field, HttpUrl

from app.schemas.common import ORMModel, Slug, StrictModel


class CompanyCreate(StrictModel):
    name: str = Field(min_length=2, max_length=160)
    slug: Slug | None = None  # derived from name when omitted
    logo_url: HttpUrl | None = None
    monogram: str | None = Field(default=None, min_length=1, max_length=2)
    palette_index: int = Field(default=0, ge=0, le=5)
    website: HttpUrl | None = None


class CompanyUpdate(StrictModel):
    """`verified` is absent — it is a moderation action with its own
    permission, not a field anyone may set on a general edit."""

    name: str | None = Field(default=None, min_length=2, max_length=160)
    logo_url: HttpUrl | None = None
    monogram: str | None = Field(default=None, min_length=1, max_length=2)
    palette_index: int | None = Field(default=None, ge=0, le=5)
    website: HttpUrl | None = None


class CompanyRead(ORMModel):
    id: UUID
    name: str
    slug: str
    logo_url: str | None
    monogram: str | None
    palette_index: int
    verified: bool
    job_count: int


class CompanyDetail(CompanyRead):
    website: str | None
    created_at: datetime
    updated_at: datetime
