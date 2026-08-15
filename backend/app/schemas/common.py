"""Shared schema primitives.

Read models are separated from write models throughout. A single model reused
for both directions is how internal columns (`deleted_at`, `created_by`,
`ip_hash`) end up on public responses.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ORMModel(BaseModel):
    """Base for responses built from ORM instances."""

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class StrictModel(BaseModel):
    """Base for request bodies.

    `extra="forbid"` makes a typo in a client payload a 422 rather than a
    silently ignored field — which is how "why didn't my update apply?" bugs
    happen.
    """

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class TimestampedRead(ORMModel):
    id: UUID
    created_at: datetime
    updated_at: datetime


class SearchMeta(BaseModel):
    """How the result set was produced.

    Returned so the interface can be honest — "no exact matches, showing
    similar roles" rather than silently presenting fuzzy results as if they
    were what the user asked for.
    """

    query: str
    strategy: str
    degraded: bool
    response_ms: int


class Paginated[T](BaseModel):
    """The one list envelope used by every collection endpoint."""

    items: list[T]
    page: int = Field(ge=1)
    per_page: int = Field(ge=1, le=100)
    total: int = Field(ge=0)
    total_pages: int = Field(ge=0)
    has_more: bool
    #: Present only on responses that ran a text search.
    search: SearchMeta | None = None


class Problem(BaseModel):
    """RFC 7807 error body."""

    type: str = "about:blank"
    title: str
    status: int
    detail: str | None = None
    instance: str | None = None
    errors: dict[str, list[str]] | None = None


class PageParams(BaseModel):
    page: Annotated[int, Field(ge=1)] = 1
    per_page: Annotated[int, Field(ge=1, le=50)] = 20

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.per_page


#: Reusable constrained aliases.
Slug = Annotated[str, Field(min_length=1, max_length=160, pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")]
ShortText = Annotated[str, Field(min_length=1, max_length=300)]
