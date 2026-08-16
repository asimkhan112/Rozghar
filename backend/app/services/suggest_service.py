"""Autocomplete orchestration.

Thin by design: the ranking lives in SQL because it has to be applied before
the `LIMIT`, and re-sorting in Python would only be able to reorder rows the
database had already discarded.
"""

from __future__ import annotations

import logging

from app.repositories.suggest_repo import Suggestion, SuggestRepository
from app.schemas.suggest import AdminSuggestResponse, SuggestionItem, SuggestResponse
from app.services.cache_service import CacheService
from app.services.search_service import normalise

logger = logging.getLogger("rozgar.suggest")

#: Below this, every listing matches and the dropdown is noise.
MIN_QUERY_LENGTH = 2

#: Rows shown per group. Five keeps the whole dropdown inside a phone screen
#: without scrolling, which is the constraint that matters on mobile.
PER_GROUP = 5

#: Suggestions are cached briefly. The vocabulary changes when a listing is
#: published, not between two keystrokes, and a short TTL turns the common case
#: — several people typing the same popular prefix — into one database round
#: trip. Kept short so a newly published listing appears in seconds.
CACHE_TTL_SECONDS = 60


class SuggestService:
    def __init__(self, session, cache: CacheService | None = None) -> None:  # noqa: ANN001
        self.repo = SuggestRepository(session)
        self.cache = cache

    async def suggest_public(self, raw: str) -> SuggestResponse:
        grouped = await self._grouped(raw, include_unpublished=False, include_sources=False)
        return SuggestResponse(**{k: v for k, v in grouped.items() if k != "sources"})

    async def suggest_admin(self, raw: str) -> AdminSuggestResponse:
        grouped = await self._grouped(raw, include_unpublished=True, include_sources=True)
        return AdminSuggestResponse(**grouped)

    async def _grouped(
        self, raw: str, *, include_unpublished: bool, include_sources: bool
    ) -> dict[str, list[SuggestionItem]]:
        empty: dict[str, list[SuggestionItem]] = {
            "jobs": [], "companies": [], "skills": [],
            "locations": [], "categories": [], "sources": [],
        }
        query = normalise(raw)
        if len(query) < MIN_QUERY_LENGTH:
            return empty

        scope = "admin" if include_unpublished else "public"
        if self.cache:
            cached = await self.cache.get("suggest", scope, query.lower())
            if cached is not None:
                return {k: [SuggestionItem(**i) for i in v] for k, v in cached.items()}

        rows = await self.repo.suggest(
            query,
            include_unpublished=include_unpublished,
            include_sources=include_sources,
        )
        grouped = dict(empty)
        for row in rows:
            bucket = grouped[row.kind]
            if len(bucket) >= PER_GROUP:
                continue
            if any(existing.text.lower() == row.text.lower() for existing in bucket):
                # Two listings with the same title are one suggestion. The
                # first wins because the SQL already ordered by tier.
                continue
            bucket.append(_to_item(row))

        if self.cache:
            await self.cache.set(
                "suggest",
                {k: [i.model_dump() for i in v] for k, v in grouped.items()},
                scope,
                query.lower(),
                ttl=CACHE_TTL_SECONDS,
            )
        return grouped


def _to_item(row: Suggestion) -> SuggestionItem:
    return SuggestionItem(text=row.text, slug=row.slug, count=row.count)


__all__ = ["MIN_QUERY_LENGTH", "PER_GROUP", "SuggestService"]
