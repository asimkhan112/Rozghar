"""Autocomplete contracts."""

from __future__ import annotations

from pydantic import BaseModel, Field


class SuggestionItem(BaseModel):
    """One row in a suggestion group.

    `text` is returned unhighlighted. Marking the matched span server-side
    would mean emitting HTML and trusting the client to render it as HTML,
    which is an injection surface for a payload that changes on every
    keystroke. The client already knows what was typed and highlights locally.
    """

    text: str
    #: Where selecting it navigates. Null for skills, which are a free-text
    #: query rather than a page.
    slug: str | None = None
    #: Listings behind the suggestion — the number shown beside it.
    count: int = 0


class SuggestResponse(BaseModel):
    """Grouped suggestions. Empty groups are returned rather than omitted, so
    the client renders a stable set of sections and never has to guess whether
    a missing key means "none" or "not supported by this endpoint"."""

    jobs: list[SuggestionItem] = Field(default_factory=list)
    companies: list[SuggestionItem] = Field(default_factory=list)
    skills: list[SuggestionItem] = Field(default_factory=list)
    locations: list[SuggestionItem] = Field(default_factory=list)
    categories: list[SuggestionItem] = Field(default_factory=list)


class AdminSuggestResponse(SuggestResponse):
    """Admin autocomplete. Adds sources, and its job group includes drafts and
    expired listings — which is exactly why it is a separate, authorised
    endpoint rather than a flag on the public one."""

    sources: list[SuggestionItem] = Field(default_factory=list)


__all__ = ["AdminSuggestResponse", "SuggestionItem", "SuggestResponse"]
