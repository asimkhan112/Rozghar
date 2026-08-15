"""Full-text and fuzzy search queries.

Three query shapes, one per tier of the degradation ladder. Filtering is always
SQL predicates applied alongside the text match, never folded into the tsquery,
so facet counts stay exact rather than approximate.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import Select, case, func, literal, or_, select, text
from sqlalchemy.orm import selectinload

from app.core.enums import JobStatus
from app.models.job import Job
from app.repositories.job_repo import JobFilters, JobRepository

#: Configuration used to parse the query. English stemming makes "engineers"
#: match "engineer"; location lexemes are indexed with `simple` and still match
#: because city names survive stemming unchanged.
TS_CONFIG = "english"

# --- ranking weights ------------------------------------------------------
# Bounded and multiplicative, so no single signal can dominate relevance:
# a boost moves a result up, it cannot manufacture a match that is not there.
RECENCY_HALF_LIFE_DAYS = 30.0
RECENCY_FLOOR = 0.3
FEATURED_BOOST = 0.25
VERIFIED_BOOST = 0.10
SALARY_DISCLOSED_BOOST = 0.15

#: ts_rank_cd normalisation: 32 divides by (rank + 1), producing a 0..1 value
#: that multiplies cleanly with the boosts below.
RANK_NORMALISATION = 32

#: Minimum trigram similarity for the fuzzy tier.
#:
#: This is not just a filter — it is what makes the GIN trigram index
#: *selective*. The `%` operator consults `pg_trgm.similarity_threshold`, and
#: at the 0.3 default the index returned 5,426 candidate rows for a query that
#: matched one, every other row being discarded by a heap recheck. Raising it
#: to 0.45 cut that query from 70ms to 4ms and still matches a real typo
#: comfortably ("techation" scores 0.615 against "TechNation").
TRIGRAM_THRESHOLD = 0.45

#: Upper bound on the rows that get scored.
#:
#: `ts_rank_cd` is not index-assisted: PostgreSQL has to fetch every matching
#: row from the heap and compute a score before it can sort. On a large
#: catalogue a common term matches tens of thousands of rows, and ranking all
#: of them costs seconds — the GIN scan itself is milliseconds.
#:
#: So the candidate pool is bounded first, newest-first, and only that pool is
#: scored. For a broad query relevance is therefore approximate beyond the
#: pool, which is an easy trade: nobody paginates to result 500, and recency is
#: the right bias for a job board anyway.
#:
#: Measured at 100k rows on a term matching 6% of the catalogue: ordering the
#: pool costs ~76ms regardless of its size, while scoring is linear in it.
#: 500 is where the scoring cost stops dominating.
MAX_RANK_CANDIDATES = 500

#: Counting every match is its own scan. Past this the total is reported as a
#: floor rather than an exact figure.
MAX_EXACT_COUNT = 1000


@dataclass(frozen=True)
class ScoredJob:
    job: Job
    score: float


class SearchRepository:
    """Text search over published listings."""

    def __init__(self, session) -> None:  # noqa: ANN001 - AsyncSession
        self.session = session
        self.jobs = JobRepository(session)

    # --- shared pieces ----------------------------------------------------

    def _base(self, filters: JobFilters) -> Select:
        stmt = select(Job).where(Job.deleted_at.is_(None), Job.status == JobStatus.PUBLISHED)
        return self.jobs._apply_public_filters(stmt, filters)

    def _recency_factor(self):
        """`exp(-age_days / 30)`, floored so an old but perfect match is
        demoted rather than buried.

        Recency is a multiplier, not a tiebreaker: job search is a freshness
        domain, and a strong title match on a 90-day-old listing should lose to
        a good match posted yesterday.
        """
        age_days = func.extract("epoch", func.now() - Job.published_at) / 86400.0
        return func.greatest(
            literal(RECENCY_FLOOR),
            func.exp(-func.coalesce(age_days, 0.0) / RECENCY_HALF_LIFE_DAYS),
        )

    @staticmethod
    def _boost(column, amount: float):
        """`1 + amount` when the flag is set, otherwise 1.

        A CASE rather than a cast: PostgreSQL refuses to coerce boolean to
        double precision directly.
        """
        return literal(1.0) + case((column.is_(True), literal(amount)), else_=literal(0.0))

    def _score(self, tsquery):
        relevance = func.ts_rank_cd(Job.search_vector, tsquery, RANK_NORMALISATION)
        return (
            relevance
            * self._recency_factor()
            * self._boost(Job.featured, FEATURED_BOOST)
            * self._boost(Job.verified, VERIFIED_BOOST)
            * self._boost(Job.salary_is_disclosed, SALARY_DISCLOSED_BOOST)
        ).label("score")

    async def _run(self, stmt: Select) -> list[ScoredJob]:
        rows = (await self.session.execute(stmt)).unique().all()
        return [ScoredJob(job=row[0], score=float(row[1] or 0.0)) for row in rows]

    # --- tier 1: exact ----------------------------------------------------

    async def search_exact(
        self, query: str, filters: JobFilters, *, limit: int, offset: int
    ) -> tuple[list[ScoredJob], int]:
        """All terms must match. `websearch_to_tsquery` gives users quoted
        phrases and `-exclusions` for free, and never raises on malformed
        input the way `to_tsquery` does."""
        tsquery = func.websearch_to_tsquery(TS_CONFIG, query)
        return await self._ranked(tsquery, filters, limit=limit, offset=offset)

    # --- tier 2: broadened ------------------------------------------------

    async def search_broadened(
        self, terms: list[str], filters: JobFilters, *, limit: int, offset: int
    ) -> tuple[list[ScoredJob], int]:
        """Any term may match.

        Fixes multi-word queries where one term is simply absent from the
        catalogue — "remote python architect" should not return nothing just
        because nobody used the word "architect".
        """
        joined = " or ".join(terms)
        tsquery = func.websearch_to_tsquery(TS_CONFIG, joined)
        return await self._ranked(tsquery, filters, limit=limit, offset=offset)

    async def _ranked(
        self, tsquery, filters: JobFilters, *, limit: int, offset: int
    ) -> tuple[list[ScoredJob], int]:
        match = Job.search_vector.op("@@")(tsquery)

        # --- how many matched, bounded ------------------------------------
        # Counting is capped for the same reason ranking is: an exact count of
        # a 50,000-row match set is a scan nobody reads the answer to.
        counted = select(Job.id).where(
            Job.deleted_at.is_(None), Job.status == JobStatus.PUBLISHED, match
        )
        counted = self.jobs._apply_public_filters(counted, filters).limit(MAX_EXACT_COUNT)
        total = (
            await self.session.execute(select(func.count()).select_from(counted.subquery()))
        ).scalar_one()
        if not total:
            return [], 0

        # --- bound the pool, then score it --------------------------------
        candidates = select(Job.id).where(
            Job.deleted_at.is_(None), Job.status == JobStatus.PUBLISHED, match
        )
        candidates = (
            self.jobs._apply_public_filters(candidates, filters)
            .order_by(Job.published_at.desc().nullslast(), Job.id.desc())
            .limit(MAX_RANK_CANDIDATES)
            .subquery()
        )

        score = self._score(tsquery)
        stmt = (
            select(Job)
            .join(candidates, Job.id == candidates.c.id)
            .add_columns(score)
            # `Job.id` breaks ties so a row cannot appear on two pages.
            .order_by(score.desc(), Job.id.desc())
            .limit(limit)
            .offset(offset)
            .options(
                selectinload(Job.category),
                selectinload(Job.location),
                selectinload(Job.source),
                selectinload(Job.company),
            )
        )
        return await self._run(stmt), total

    # --- tier 3: trigram --------------------------------------------------

    async def search_fuzzy(
        self, query: str, filters: JobFilters, *, limit: int, offset: int
    ) -> tuple[list[ScoredJob], int]:
        """Typo tolerance.

        Trigram similarity on title and company, which is what "software
        enginer" needs — the tsquery for a misspelling matches nothing at all,
        because stemming cannot recover a word that was never spelled right.
        """
        similarity = func.greatest(
            func.similarity(Job.title, query),
            func.similarity(Job.company_name, query),
        )
        match = or_(
            Job.title.op("%")(query),
            Job.company_name.op("%")(query),
        )

        # The threshold governs index selectivity, not just the final filter,
        # so it has to be set on the connection before the query runs. SET
        # LOCAL scopes it to this transaction.
        await self.session.execute(
            text(f"SET LOCAL pg_trgm.similarity_threshold = {TRIGRAM_THRESHOLD}")
        )

        # Bounded for the same reason the ranked tiers are: `similarity()` is
        # computed per row, so a permissive trigram match over a large
        # catalogue is an expensive scan. The `%` operator is index-assisted;
        # the similarity score behind it is not.
        counted = select(Job.id).where(
            Job.deleted_at.is_(None), Job.status == JobStatus.PUBLISHED, match
        )
        counted = self.jobs._apply_public_filters(counted, filters).limit(MAX_EXACT_COUNT)
        total = (
            await self.session.execute(select(func.count()).select_from(counted.subquery()))
        ).scalar_one()
        if not total:
            return [], 0

        candidates = select(Job.id).where(
            Job.deleted_at.is_(None), Job.status == JobStatus.PUBLISHED, match
        )
        candidates = (
            self.jobs._apply_public_filters(candidates, filters)
            .limit(MAX_RANK_CANDIDATES)
            .subquery()
        )

        score = (similarity * self._recency_factor()).label("score")
        stmt = (
            select(Job)
            .join(candidates, Job.id == candidates.c.id)
            .add_columns(score)
            .order_by(score.desc(), Job.id.desc())
            .limit(limit)
            .offset(offset)
            .options(
                selectinload(Job.category),
                selectinload(Job.location),
                selectinload(Job.source),
                selectinload(Job.company),
            )
        )
        return await self._run(stmt), total

    # --- tier 4: related --------------------------------------------------

    async def recent_fallback(self, filters: JobFilters, *, limit: int) -> list[ScoredJob]:
        """Last resort: recent listings honouring whatever filters remain.

        An empty page is a dead end. Showing something relevant, clearly
        labelled as not-an-exact-match, keeps the session alive.
        """
        stmt = (
            self._base(filters)
            .add_columns(literal(0.0).label("score"))
            .order_by(Job.published_at.desc().nullslast(), Job.id.desc())
            .limit(limit)
            .options(
                selectinload(Job.category),
                selectinload(Job.location),
                selectinload(Job.source),
                selectinload(Job.company),
            )
        )
        return await self._run(stmt)

    # --- suggestions ------------------------------------------------------

    async def suggest_titles(self, prefix: str, *, limit: int = 8) -> list[str]:
        stmt = (
            select(Job.title)
            .where(
                Job.deleted_at.is_(None),
                Job.status == JobStatus.PUBLISHED,
                Job.title.ilike(f"%{prefix}%"),
            )
            .distinct()
            .order_by(Job.title)
            .limit(limit)
        )
        return list((await self.session.execute(stmt)).scalars().all())

    async def jobs_by_ids(self, job_ids: list[UUID]) -> list[Job]:
        """Load jobs by id, preserving the order given.

        Postgres returns no order without an ORDER BY, so the ranking a cache
        hit is meant to reproduce would be lost. Re-sorting in Python keeps the
        query a simple indexed lookup rather than an array_position join.
        """
        if not job_ids:
            return []
        stmt = (
            select(Job)
            .where(Job.id.in_(job_ids), Job.deleted_at.is_(None))
            .where(Job.status == JobStatus.PUBLISHED)
            .options(
                selectinload(Job.category),
                selectinload(Job.location),
                selectinload(Job.source),
                selectinload(Job.company),
            )
        )
        found = {j.id: j for j in (await self.session.execute(stmt)).scalars().unique().all()}
        # Missing ids are listings deleted or expired since the entry was
        # cached; dropping them is correct and self-healing.
        return [found[i] for i in job_ids if i in found]
