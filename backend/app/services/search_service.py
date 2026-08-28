"""Search orchestration: normalisation, the degradation ladder, and logging.

This is the seam that keeps the query engine replaceable. Everything above it
asks for "jobs matching a query"; everything below is PostgreSQL specific. The
day Elasticsearch genuinely earns its place, it replaces this file's internals
and nothing else.

Every search is logged with its result count, which makes zero-result rate a
first-class product metric from launch rather than a later instrumentation
project.
"""

from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass, field
from enum import StrEnum
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.job import Job
from app.repositories.job_repo import JobFilters
from app.repositories.search_log_repo import SearchLogRepository
from app.repositories.search_repo import SearchRepository
from app.services.cache_service import TTL_SEARCH, CacheService

logger = logging.getLogger(__name__)

MAX_QUERY_LENGTH = 120
_WHITESPACE = re.compile(r"\s+")
#: Control characters and the tsquery operators users do not mean literally.
_STRIP = re.compile(r"[\x00-\x1f\x7f&|!<>():*]")


class SearchStrategy(StrEnum):
    """Which tier produced the results. Returned to the client so the UI can
    say "no exact matches — showing similar roles" instead of pretending."""

    EXACT = "exact"
    BROADENED = "broadened"
    FUZZY = "fuzzy"
    RELATED = "related"
    NONE = "none"


#: Market vocabulary the English dictionary cannot know about. Applied before
#: the query reaches PostgreSQL.
SYNONYMS: dict[str, str] = {
    "fresher": "fresh graduate entry",
    "freshers": "fresh graduate entry",
    "swe": "software engineer",
    "sde": "software engineer",
    "se": "software engineer",
    "dev": "developer",
    "devs": "developer",
    "frontend": "frontend front-end",
    "backend": "backend back-end",
    "fullstack": "fullstack full-stack",
    "wfh": "remote work from home",
    "lhr": "lahore",
    "khi": "karachi",
    "isb": "islamabad",
    "pindi": "rawalpindi",
    "hr": "human resources",
    "ba": "business analyst",
    "qa": "quality assurance testing",
}


@dataclass
class SearchOutcome:
    items: list[Job]
    scores: list[float]
    total: int
    strategy: SearchStrategy
    degraded: bool
    response_ms: int
    normalised_query: str
    expanded_terms: list[str] = field(default_factory=list)


def normalise(raw: str) -> str:
    """Trim, collapse whitespace, strip operators, cap length.

    Capping matters: a megabyte query would otherwise reach the tsquery parser
    and cost real CPU for a request that can never be useful.
    """
    cleaned = _STRIP.sub(" ", raw or "")
    cleaned = _WHITESPACE.sub(" ", cleaned).strip()
    return cleaned[:MAX_QUERY_LENGTH]


def expand_synonyms(query: str) -> tuple[str, list[str]]:
    """Return the expanded query and its individual terms."""
    terms: list[str] = []
    for token in query.lower().split():
        expansion = SYNONYMS.get(token)
        terms.extend(expansion.split() if expansion else [token])
    # Preserve order while removing duplicates.
    seen: set[str] = set()
    unique = [t for t in terms if not (t in seen or seen.add(t))]
    return " ".join(unique), unique


class SearchService:
    def __init__(self, session: AsyncSession, cache: CacheService | None = None) -> None:
        self.session = session
        self.repo = SearchRepository(session)
        self.logs = SearchLogRepository(session)
        self.cache = cache

    async def search(
        self,
        raw_query: str,
        filters: JobFilters,
        *,
        page: int = 1,
        per_page: int = 20,
        session_id: UUID | None = None,
        log: bool = True,
    ) -> SearchOutcome:
        started = time.perf_counter()
        query = normalise(raw_query)
        offset = (page - 1) * per_page

        if not query:
            outcome = SearchOutcome(
                items=[],
                scores=[],
                total=0,
                strategy=SearchStrategy.NONE,
                degraded=False,
                response_ms=0,
                normalised_query="",
            )
            return outcome

        _, terms = expand_synonyms(query)

        # A cache hit skips the ranking scan — the part that costs 145ms at
        # 100k listings because `ts_rank_cd` is not index-assisted — but it
        # deliberately does *not* skip the search log below. Caching the
        # measurement along with the result would make popular queries
        # invisible in the telemetry, which is exactly backwards.
        cache_key = _cache_key(query, filters, page, per_page)
        cached = await self.cache.get("search", cache_key) if self.cache else None
        if cached is not None:
            outcome = await self._from_cache(cached, query, terms, started)
            await self._log(outcome, raw_query, filters, session_id, log)
            return outcome

        # --- tier 1: exactly what the user typed --------------------------
        # Deliberately *not* synonym-expanded. Expansion adds terms, and with
        # AND semantics every added term is another requirement — "frontend"
        # expanding to include "front-end" made an exact title match fail.
        results, total = await self.repo.search_exact(query, filters, limit=per_page, offset=offset)
        strategy = SearchStrategy.EXACT

        # --- tier 2: any term, synonyms included --------------------------
        # OR semantics is where expansion belongs: synonyms become
        # alternatives rather than extra requirements.
        if not results:
            results, total = await self.repo.search_broadened(
                terms, filters, limit=per_page, offset=offset
            )
            strategy = SearchStrategy.BROADENED

        # --- tier 3: typo tolerance ---------------------------------------
        if not results:
            results, total = await self.repo.search_fuzzy(
                query, filters, limit=per_page, offset=offset
            )
            strategy = SearchStrategy.FUZZY

        # --- tier 4: something rather than nothing ------------------------
        if not results:
            related = await self.repo.recent_fallback(filters, limit=per_page)
            results, total = related, len(related)
            strategy = SearchStrategy.RELATED if related else SearchStrategy.NONE

        response_ms = int((time.perf_counter() - started) * 1000)
        degraded = strategy not in (SearchStrategy.EXACT, SearchStrategy.NONE)

        outcome = SearchOutcome(
            items=[r.job for r in results],
            scores=[r.score for r in results],
            total=total,
            strategy=strategy,
            degraded=degraded,
            response_ms=response_ms,
            normalised_query=query.lower(),
            expanded_terms=terms,
        )

        # Only exact results are cached. A degraded result set is a symptom of
        # a gap in the catalogue, and freezing it for two minutes would keep
        # serving the fallback after the listing that fixes it was published.
        if self.cache is not None and strategy is SearchStrategy.EXACT and results:
            await self.cache.set(
                "search",
                {
                    "job_ids": [str(r.job.id) for r in results],
                    "scores": [r.score for r in results],
                    "total": total,
                },
                cache_key,
                ttl=TTL_SEARCH,
            )

        await self._log(outcome, raw_query, filters, session_id, log)

        if strategy is SearchStrategy.NONE:
            logger.info(
                "zero-result search",
                extra={"event": "search.zero_results", "query": outcome.normalised_query},
            )

        return outcome

    async def _from_cache(
        self, payload: dict, query: str, terms: list[str], started: float
    ) -> SearchOutcome:
        """Rehydrate jobs by id, preserving the cached ranking order.

        Only the ids and scores are cached, never the rows: a listing cached
        whole would keep being served after it was expired or edited, and this
        endpoint is the one a reader sees first.
        """
        jobs = await self.repo.jobs_by_ids([UUID(i) for i in payload["job_ids"]])
        return SearchOutcome(
            items=jobs,
            scores=payload.get("scores", []),
            total=payload["total"],
            strategy=SearchStrategy.EXACT,
            degraded=False,
            response_ms=int((time.perf_counter() - started) * 1000),
            normalised_query=query.lower(),
            expanded_terms=terms,
        )

    async def _log(
        self,
        outcome: SearchOutcome,
        raw_query: str,
        filters: JobFilters,
        session_id: UUID | None,
        enabled: bool,
    ) -> None:
        """Never let telemetry break a search."""
        if not enabled:
            return
        try:
            await self.logs.record(
                session_id=session_id,
                raw_query=raw_query[:200],
                normalised_query=outcome.normalised_query[:200],
                filters=_filters_to_dict(filters),
                result_count=outcome.total,
                was_degraded=outcome.degraded,
                response_ms=outcome.response_ms,
            )
        except Exception:  # noqa: BLE001
            logger.warning("failed to record search log", exc_info=True)

    async def suggest(self, prefix: str, *, limit: int = 8) -> list[str]:
        cleaned = normalise(prefix)
        if len(cleaned) < 2:
            return []
        return await self.repo.suggest_titles(cleaned, limit=limit)


def _cache_key(query: str, filters: JobFilters, page: int, per_page: int) -> str:
    """Filters are part of the key. "react" with a Karachi filter and "react"
    without are different result sets, and sharing a key between them would
    serve one to the other."""
    parts = [query.lower(), str(page), str(per_page)]
    parts.extend(f"{k}={v}" for k, v in sorted(_filters_to_dict(filters).items()))
    return "|".join(parts)


def _filters_to_dict(filters: JobFilters) -> dict:
    """Only the filters that were actually set.

    Recording the full struct with a dozen nulls makes the "which filters do
    people use?" report unreadable.
    """
    payload = {
        "category": filters.category_slug,
        "location": filters.location_slug,
        # Must stay listed: this dict is the cache key, so a filter missing
        # from it is a filter two different result sets can collide on —
        # "engineer" in Pakistan would be served the cached "engineer" in the
        # United States.
        "country": filters.country,
        "work_type": filters.work_type,
        "employment_type": filters.employment_type,
        "experience": filters.experience_level,
        "featured": filters.featured,
        "verified": filters.verified,
        "salary_min": str(filters.salary_min) if filters.salary_min is not None else None,
        "posted_within_days": filters.posted_within_days,
    }
    return {k: str(v) for k, v in payload.items() if v is not None}
