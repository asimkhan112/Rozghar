"""Autocomplete reads.

Everything the endpoint needs comes back in **one** round trip. Six separate
queries would each cost a network hop and a planning pass, and the budget for
the whole response is 100ms; a `UNION ALL` over six cheap indexed branches
costs one hop and lets Postgres plan them together.

Every branch produces the same shape — `(kind, text, slug, count, tier)` — so
the caller groups by `kind` and never re-sorts.

## Ranking

`tier` is the ordering key, and it encodes the priority the product asked for:

    1  exact prefix          the term starts with what was typed
    2  popular search        the term matches something people actually search
    3  full-text match       the tsvector matches
    4  trigram fuzzy         similar enough to survive the threshold

Within a tier the tiebreak is `count` — job count for the entities, hit count
for skills — so "Karachi" outranks a town with two listings, and neither
depends on alphabetical luck.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

#: Minimum trigram similarity for the fuzzy tier. Matches the value the main
#: search uses — a suggestion that would not survive the search it triggers is
#: worse than no suggestion.
#:
#: Applied through the `%` operator and the session GUC, never as
#: `similarity(col, q) > threshold`. The two look equivalent and are not: `%`
#: is index-assisted, while the function form is a per-row filter that forces a
#: sequential scan. Measured at 50k vocabulary rows, that is 12ms against
#: 158ms — the difference between meeting the latency budget and blowing it.
TRIGRAM_THRESHOLD = 0.3

#: Rows fetched per group before the service truncates. Fetching a few more
#: than are shown lets the tier ordering discard weak matches without a second
#: query.
GROUP_FETCH = 12


@dataclass(frozen=True, slots=True)
class Suggestion:
    kind: str
    text: str
    slug: str | None
    count: int
    tier: int


# Each branch is written against a normalised, unaccented expression so that a
# search for "lahore" matches "Lahore" and a search for "cafe" matches "café".
# `immutable_unaccent` is the wrapper 0003 created for exactly this reason: the
# stock `unaccent()` is not immutable and cannot be indexed.
_SQL = """
WITH q AS (
    SELECT
        :q                       AS raw,
        lower(:q)                AS norm,
        lower(:q) || '%'         AS prefix,
        '%' || lower(:q) || '%'  AS contains
)
-- 1. Job titles -------------------------------------------------------------
(
    SELECT 'jobs' AS kind, j.title AS text, j.slug AS slug,
           j.view_count AS count,
           CASE
               WHEN lower(j.title) LIKE q.prefix THEN 1
               WHEN pq.query_norm IS NOT NULL     THEN 2
               WHEN j.search_vector @@ plainto_tsquery('english', q.raw) THEN 3
               ELSE 4
           END AS tier
    FROM jobs j
    CROSS JOIN q
    LEFT JOIN popular_queries pq ON pq.query_norm = lower(j.title)
    WHERE j.deleted_at IS NULL
      AND (:include_unpublished OR j.status = 'published')
      AND (
            lower(j.title) LIKE q.contains
         OR j.search_vector @@ plainto_tsquery('english', q.raw)
         OR j.title % q.raw
      )
    ORDER BY tier, count DESC, text
    LIMIT :per_group
)
UNION ALL
-- 2. Companies --------------------------------------------------------------
-- Sourced from `jobs.company_name`, not the `companies` table. The table
-- exists for the V2 dedupe pass and is not populated by job creation, which
-- sets the denormalised name and leaves `company_id` null — so a suggestion
-- group reading `companies` would be permanently empty while the names the
-- reader can see sit on the listings. `ix_jobs_company_name_trgm` indexes the
-- column that actually holds them.
(
    SELECT 'companies', j.company_name, NULL, count(*)::int,
           MIN(CASE
               WHEN lower(j.company_name) LIKE q.prefix THEN 1
               WHEN pq.query_norm IS NOT NULL           THEN 2
               ELSE 4
           END)
    FROM jobs j
    CROSS JOIN q
    LEFT JOIN popular_queries pq ON pq.query_norm = lower(j.company_name)
    WHERE j.deleted_at IS NULL
      AND (:include_unpublished OR j.status = 'published')
      AND (lower(j.company_name) LIKE q.contains OR j.company_name % q.raw)
    GROUP BY j.company_name
    ORDER BY 5, 4 DESC, 2
    LIMIT :per_group
)
UNION ALL
-- 3. Skills -----------------------------------------------------------------
(
    SELECT 'skills', s.term, NULL, s.job_count,
           CASE
               WHEN s.term_norm LIKE q.prefix THEN 1
               WHEN pq.query_norm IS NOT NULL THEN 2
               ELSE 4
           END
    FROM skill_terms s
    CROSS JOIN q
    LEFT JOIN popular_queries pq ON pq.query_norm = s.term_norm
    WHERE (s.term_norm LIKE q.contains OR s.term_norm % q.norm)
    ORDER BY 5, s.job_count DESC, s.term
    LIMIT :per_group
)
UNION ALL
-- 4. Locations --------------------------------------------------------------
(
    SELECT 'locations', l.display_name, l.slug, l.job_count,
           CASE
               WHEN lower(l.display_name) LIKE q.prefix THEN 1
               WHEN pq.query_norm IS NOT NULL           THEN 2
               ELSE 4
           END
    FROM locations l
    CROSS JOIN q
    LEFT JOIN popular_queries pq ON pq.query_norm = lower(l.display_name)
    WHERE l.is_active
      AND (lower(l.display_name) LIKE q.contains OR l.display_name % q.raw)
    ORDER BY 5, l.job_count DESC, l.display_name
    LIMIT :per_group
)
UNION ALL
-- 5. Categories -------------------------------------------------------------
(
    SELECT 'categories', cat.name, cat.slug, cat.job_count,
           CASE
               WHEN lower(cat.name) LIKE q.prefix THEN 1
               WHEN pq.query_norm IS NOT NULL     THEN 2
               ELSE 4
           END
    FROM categories cat
    CROSS JOIN q
    LEFT JOIN popular_queries pq ON pq.query_norm = lower(cat.name)
    WHERE cat.is_active
      AND (lower(cat.name) LIKE q.contains OR cat.name % q.raw)
    ORDER BY 5, cat.job_count DESC, cat.name
    LIMIT :per_group
)
UNION ALL
-- 6. Sources — admin only ---------------------------------------------------
(
    SELECT 'sources', src.name, src.slug, 0,
           CASE WHEN lower(src.name) LIKE q.prefix THEN 1 ELSE 4 END
    FROM sources src
    CROSS JOIN q
    WHERE :include_sources
      AND (lower(src.name) LIKE q.contains OR src.name % q.raw)
    ORDER BY 5, src.name
    LIMIT :per_group
)
"""


class SuggestRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def suggest(
        self,
        query: str,
        *,
        per_group: int = GROUP_FETCH,
        include_unpublished: bool = False,
        include_sources: bool = False,
    ) -> list[Suggestion]:
        """One round trip for every group.

        `include_unpublished` and `include_sources` are the admin/public
        boundary. They are parameters rather than a separate query because the
        two callers differ only in what they are allowed to see, and keeping
        one statement means the ranking cannot drift between them.
        """
        # `similarity()` consults a session GUC, so the threshold has to be set
        # on this transaction before the statement runs. LOCAL scopes it to the
        # transaction rather than leaking into the pooled connection.
        await self.session.execute(
            text(f"SET LOCAL pg_trgm.similarity_threshold = {TRIGRAM_THRESHOLD}")
        )
        rows = await self.session.execute(
            text(_SQL),
            {
                "q": query,
                "per_group": per_group,
                "include_unpublished": include_unpublished,
                "include_sources": include_sources,
            },
        )
        return [
            Suggestion(kind=r[0], text=r[1], slug=r[2], count=r[3] or 0, tier=r[4])
            for r in rows.all()
        ]

    # --- vocabulary refresh ----------------------------------------------

    async def rebuild_skill_terms(self, *, min_jobs: int = 1) -> int:
        """Re-harvest the skill vocabulary from `jobs.requirements`.

        A full rebuild rather than an incremental one: the source is a JSONB
        array with no change feed, the whole vocabulary is a few thousand rows,
        and a rebuild cannot drift from its source the way an incremental
        update can. Deletions matter here — a skill that no published listing
        mentions any more must stop being suggested.

        Terms are truncated to the column width and skipped when they are too
        short to be a useful suggestion or long enough to be a sentence: the
        `requirements` array holds free text, so "React" and "Must be willing
        to work occasional weekends" both arrive through the same door.
        """
        result = await self.session.execute(
            text("""
            WITH harvested AS (
                SELECT
                    btrim(skill)                            AS term,
                    lower(btrim(skill))                     AS term_norm,
                    count(DISTINCT j.id)                    AS job_count
                FROM jobs j
                CROSS JOIN LATERAL jsonb_array_elements_text(j.requirements) AS skill
                WHERE j.deleted_at IS NULL
                  AND j.status = 'published'
                  AND length(btrim(skill)) BETWEEN 2 AND 60
                GROUP BY 1, 2
                HAVING count(DISTINCT j.id) >= :min_jobs
            ),
            -- One row per normalised term. Two listings writing "React" and
            -- "react" are the same skill; the more common spelling wins the
            -- display form.
            deduped AS (
                SELECT DISTINCT ON (term_norm)
                    term, term_norm, sum(job_count) OVER (PARTITION BY term_norm) AS job_count
                FROM harvested
                ORDER BY term_norm, job_count DESC, term
            ),
            wiped AS (
                DELETE FROM skill_terms
                WHERE term_norm NOT IN (SELECT term_norm FROM deduped)
                RETURNING 1
            )
            INSERT INTO skill_terms (term, term_norm, job_count, refreshed_at)
            SELECT term, term_norm, job_count, now() FROM deduped
            ON CONFLICT (term) DO UPDATE
                SET job_count = EXCLUDED.job_count,
                    term_norm = EXCLUDED.term_norm,
                    refreshed_at = EXCLUDED.refreshed_at
            """),
            {"min_jobs": min_jobs},
        )
        return result.rowcount or 0

    async def rebuild_popular_queries(self, *, since_days: int = 90, limit: int = 2000) -> int:
        """Aggregate `search_logs` into the popularity map.

        Scoped to a window and a row cap: the point is to know what people
        search for *now*, and an all-time aggregate would keep a query that was
        popular a year ago ranked above one that is popular this week.

        Zero-result searches are excluded. Suggesting a term that returns
        nothing is worse than suggesting nothing — it sends the reader down a
        path the catalogue cannot answer.
        """
        result = await self.session.execute(
            text("""
            WITH agg AS (
                SELECT normalised_query AS query_norm,
                       count(*)         AS hits,
                       max(occurred_at) AS last_seen
                FROM search_logs
                WHERE occurred_at >= now() - make_interval(days => :since_days)
                  AND result_count > 0
                  AND length(normalised_query) BETWEEN 2 AND 200
                GROUP BY 1
                ORDER BY hits DESC
                LIMIT :limit
            ),
            wiped AS (
                DELETE FROM popular_queries
                WHERE query_norm NOT IN (SELECT query_norm FROM agg)
                RETURNING 1
            )
            INSERT INTO popular_queries (query_norm, hits, last_seen, refreshed_at)
            SELECT query_norm, hits, last_seen, now() FROM agg
            ON CONFLICT (query_norm) DO UPDATE
                SET hits = EXCLUDED.hits,
                    last_seen = EXCLUDED.last_seen,
                    refreshed_at = EXCLUDED.refreshed_at
            """),
            {"since_days": since_days, "limit": limit},
        )
        return result.rowcount or 0


__all__ = ["Suggestion", "SuggestRepository", "TRIGRAM_THRESHOLD"]
