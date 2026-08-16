"""AI drafting request and response schemas.

The response is a *draft*. Nothing here is persisted — the admin reviews it
side by side with what they had and decides whether to apply it.
"""

from __future__ import annotations

from pydantic import Field

from app.schemas.common import ORMModel, StrictModel


class RewriteRequest(StrictModel):
    description: str = Field(min_length=40, max_length=20_000)


class GenerateRequest(StrictModel):
    """The structured fields the editor has already filled in.

    Title and company are required because a description generated without them
    is generic filler. Everything else is optional and simply constrains the
    output further when present.
    """

    title: str = Field(min_length=3, max_length=200)
    company: str = Field(min_length=2, max_length=160)
    location: str = Field(default="", max_length=160)
    employment_type: str = Field(default="Full Time", max_length=40)
    experience_level: str = Field(default="Mid level", max_length=40)
    salary: str | None = Field(default=None, max_length=120)
    skills: list[str] = Field(default_factory=list, max_length=20)


class AIDraft(ORMModel):
    """A proposed listing body, for review.

    Mirrors the job form's own fields so the review UI can diff old against new
    field by field, and applying it is a straight assignment.
    """

    description: str
    responsibilities: list[str]
    requirements: list[str]
    benefits: list[str]
    apply_note: str
