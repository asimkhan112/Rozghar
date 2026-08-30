"""Job persistence and querying.

Every read that returns jobs eager-loads the four relations the response
renders. A 20-item page costs five queries — one for the page, four for the
relations — regardless of page size. Lazy loading here would be 81.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import Select, delete, false, func, select, update
from sqlalchemy.orm import selectinload

from app.core.enums import EmploymentType, ExperienceLevel, JobStatus, WorkType
from app.models.job import Job
from app.models.company import Company
from app.models.taxonomy import Category, Location
from app.repositories.base import BaseRepository

#: The relations every job response renders. Loaded together, always.
_EAGER = (
    selectinload(Job.category),
    selectinload(Job.location),
    selectinload(Job.source),
    selectinload(Job.company),
)


@dataclass(frozen=True)
class JobFilters:
    """Public list filters. All optional; absent means "no constraint"."""

    category_slug: str | None = None
    location_slug: str | None = None
    #: ISO 3166-1 alpha-2, matched against the listing's location. Broader than
    #: `location_slug`, which names one city: this is what answers "jobs in
    #: Pakistan" without enumerating every Pakistani city in the taxonomy, and
    #: it is the filter the country landing pages are built on.
    country: str | None = None
    work_type: WorkType | None = None
    employment_type: EmploymentType | None = None
    experience_level: ExperienceLevel | None = None
    featured: bool | None = None
    verified: bool | None = None
    salary_min: Decimal | None = None
    posted_within_days: int | None = None
    #: Explicit id set, for rendering a client-held collection — the saved-jobs
    #: page keeps ids in local storage and needs them resolved in one request
    #: rather than one request per saved listing.
    ids: tuple[UUID, ...] | None = None


@dataclass(frozen=True)
class FacetCounts:
    """Live listing counts per landing-page facet, keyed by slug or country code."""

    categories: dict[str, int]
    locations: dict[str, int]
    countries: dict[str, int]


@dataclass(frozen=True)
class AdminJobFilters:
    """Editorial filters. Adds the states the public never sees."""

    status: JobStatus | None = None
    created_by: UUID | None = None
    category_id: UUID | None = None
    include_deleted: bool = False


SORT_RECENT = "recent"
SORT_SALARY_DESC = "salary_desc"
SORT_SALARY_ASC = "salary_asc"
SORT_TITLE = "title"
PUBLIC_SORTS = (SORT_RECENT, SORT_SALARY_DESC, SORT_SALARY_ASC, SORT_TITLE)

#: Rough conversion so mixed-currency listings sort against each other. A real
#: rates table is a later concern; a constant is honest about being an estimate.
USD_TO_PKR = 280

#: Which column on `jobs` each counter counts through. Used by
#: `recount_live_jobs` so the three repairs are one loop rather than three
#: near-identical statements that can be corrected one at a time.
_COUNTED_BY = {
    Category: Job.category_id,
    Location: Job.location_id,
    Company: Job.company_id,
}


class JobRepository(BaseRepository[Job]):
    model = Job

    # --- reads ------------------------------------------------------------

    def _live(self) -> Select:
        """Base query for anything the public may see."""
        return select(Job).where(
            Job.deleted_at.is_(None),
            Job.status == JobStatus.PUBLISHED,
        )

    def _apply_public_filters(self, stmt: Select, filters: JobFilters) -> Select:
        if filters.category_slug:
            stmt = stmt.join(Category, Job.category_id == Category.id).where(
                Category.slug == filters.category_slug
            )
        # One join for both location filters. Joining per-filter would emit
        # `Location` twice when a country and a city are combined, which
        # SQLAlchemy renders as an ambiguous self-cross-product rather than the
        # conjunction that was meant.
        if filters.location_slug or filters.country:
            stmt = stmt.join(Location, Job.location_id == Location.id)
            if filters.location_slug:
                stmt = stmt.where(Location.slug == filters.location_slug)
            if filters.country:
                stmt = stmt.where(Location.country == filters.country.upper())
        if filters.work_type is not None:
            stmt = stmt.where(Job.work_type == filters.work_type)
        if filters.employment_type is not None:
            stmt = stmt.where(Job.employment_type == filters.employment_type)
        if filters.experience_level is not None:
            stmt = stmt.where(Job.experience_level == filters.experience_level)
        if filters.featured is not None:
            stmt = stmt.where(Job.featured.is_(filters.featured))
        if filters.verified is not None:
            stmt = stmt.where(Job.verified.is_(filters.verified))
        if filters.salary_min is not None:
            # Compare against the floor of the range, normalised to PKR.
            normalised = func.coalesce(Job.salary_min, 0) * func.case(
                (Job.salary_currency == "USD", USD_TO_PKR), else_=1
            )
            stmt = stmt.where(normalised >= filters.salary_min)
        if filters.ids is not None:
            # An empty set means "nothing was asked for", not "no constraint" —
            # without this an empty saved list would return the whole catalogue.
            stmt = stmt.where(Job.id.in_(filters.ids) if filters.ids else false())
        if filters.posted_within_days is not None:
            cutoff = datetime.now(UTC) - __import__("datetime").timedelta(
                days=filters.posted_within_days
            )
            stmt = stmt.where(Job.published_at >= cutoff)
        return stmt

    def _apply_sort(self, stmt: Select, sort: str) -> Select:
        """Every ordering ends with a unique tiebreaker.

        Without one, two rows with equal sort keys can appear on two different
        pages, or on neither — the classic duplicate-row pagination bug.
        """
        if sort == SORT_SALARY_DESC:
            return stmt.order_by(Job.salary_min.desc().nullslast(), Job.id.desc())
        if sort == SORT_SALARY_ASC:
            return stmt.order_by(Job.salary_min.asc().nullslast(), Job.id.desc())
        if sort == SORT_TITLE:
            return stmt.order_by(Job.title.asc(), Job.id.desc())
        return stmt.order_by(Job.published_at.desc().nullslast(), Job.id.desc())

    async def list_public(
        self, filters: JobFilters, *, sort: str = SORT_RECENT, limit: int, offset: int
    ) -> list[Job]:
        stmt = self._apply_public_filters(self._live(), filters)
        stmt = self._apply_sort(stmt, sort).limit(limit).offset(offset).options(*_EAGER)
        return list((await self.session.execute(stmt)).scalars().unique().all())

    async def count_public(self, filters: JobFilters) -> int:
        """Counting does not need the relations, so it does not load them."""
        stmt = self._apply_public_filters(
            select(func.count())
            .select_from(Job)
            .where(Job.deleted_at.is_(None), Job.status == JobStatus.PUBLISHED),
            filters,
        )
        return (await self.session.execute(stmt)).scalar_one()

    async def get_by_slug(self, slug: str, *, published_only: bool = True) -> Job | None:
        stmt = select(Job).where(Job.slug == slug, Job.deleted_at.is_(None)).options(*_EAGER)
        if published_only:
            stmt = stmt.where(Job.status == JobStatus.PUBLISHED)
        return (await self.session.execute(stmt)).scalars().unique().one_or_none()

    async def get_any_by_slug(self, slug: str) -> Job | None:
        """Includes drafts and archived — used to distinguish 404 from 410."""
        stmt = select(Job).where(Job.slug == slug, Job.deleted_at.is_(None)).options(*_EAGER)
        return (await self.session.execute(stmt)).scalars().unique().one_or_none()

    async def get_by_id(self, job_id: UUID, *, include_deleted: bool = False) -> Job | None:
        stmt = select(Job).where(Job.id == job_id).options(*_EAGER)
        if not include_deleted:
            stmt = stmt.where(Job.deleted_at.is_(None))
        return (await self.session.execute(stmt)).scalars().unique().one_or_none()

    async def slug_exists(self, slug: str) -> bool:
        stmt = (
            select(func.count()).select_from(Job).where(Job.slug == slug, Job.deleted_at.is_(None))
        )
        return (await self.session.execute(stmt)).scalar_one() > 0

    async def published_slugs(self, *, limit: int) -> list[tuple[str, datetime]]:
        """Slugs and their last change, for the sitemap.

        Two columns, no relations, no ORM entities — a sitemap of fifty
        thousand listings must not hydrate fifty thousand `Job` objects with
        four eager-loaded relations each. Newest first so that if the cap is
        ever hit, the listings that are dropped are the stalest.
        """
        stmt = (
            select(Job.slug, Job.updated_at)
            .where(Job.status == JobStatus.PUBLISHED, Job.deleted_at.is_(None))
            .order_by(Job.published_at.desc().nullslast(), Job.id.desc())
            .limit(limit)
        )
        return [(row[0], row[1]) for row in (await self.session.execute(stmt)).all()]

    async def count_by_status(self, status: JobStatus) -> int:
        """How many listings sit in one lifecycle state, deleted ones excluded.

        Used to tell an admin what a bulk action is about to touch *before*
        they confirm it, and to report what a capped run left behind.
        """
        stmt = (
            select(func.count(Job.id))
            .where(Job.status == status, Job.deleted_at.is_(None))
        )
        return int((await self.session.execute(stmt)).scalar_one())

    async def list_by_status(self, status: JobStatus, *, limit: int) -> list[Job]:
        """Listings in one state, oldest first, for a bulk operation to walk.

        Oldest first so a capped run drains the backlog from the end that has
        been waiting longest, and so two consecutive runs cannot revisit the
        same rows.
        """
        stmt = (
            select(Job)
            .where(Job.status == status, Job.deleted_at.is_(None))
            .order_by(Job.created_at, Job.id)
            .limit(limit)
        )
        return list((await self.session.execute(stmt)).scalars().all())

    async def purge_by_status(
        self, status: JobStatus, *, limit: int
    ) -> list[tuple[UUID, str]]:
        """Permanently remove listings in one state. Returns what went.

        A real `DELETE`, not the `soft_delete` above — the row stops existing.
        The database is what makes this safe to do in one statement: every
        foreign key pointing at `jobs` declares its own behaviour, so the
        cascade is the schema's decision rather than this function's.

            reports                    ON DELETE CASCADE   (go with the listing)
            job_social_assets          ON DELETE CASCADE   (generated, rebuildable)
            analytics_daily_rollups    ON DELETE CASCADE
            analytics_events.job_id    ON DELETE SET NULL  (totals survive,
                                                            attribution does not)

        `synchronize_session=False` because nothing in this session is expected
        to hold these rows afterwards — the caller reads them back from the
        `RETURNING` clause, which is also the only record of what was removed
        once the statement has run.

        Soft-deleted rows in this state are included deliberately: a listing
        that is both expired and already hidden is exactly the kind this is
        meant to clear out for good.
        """
        doomed = select(Job.id).where(Job.status == status).limit(limit).scalar_subquery()
        stmt = (
            delete(Job)
            .where(Job.id.in_(doomed))
            .returning(Job.id, Job.slug)
            .execution_options(synchronize_session=False)
        )
        return [(row[0], row[1]) for row in (await self.session.execute(stmt)).all()]

    async def recount_live_jobs(self) -> None:
        """Reset every `job_count` to what the jobs table actually says.

        The counters are a denormalised cache, and a cache that only ever moves
        by deltas drifts the moment one delta is missed. One was: `expire_jobs`
        used to set `status` directly instead of going through the state
        machine, so every listing the nightly task expired stayed counted as
        live. That is fixed at the source, but the accumulated drift is still
        sitting in these columns, and no delta will ever remove it.

        A correlated subquery rather than a `GROUP BY` join, because the rows
        that need it most are the ones with no live listings at all — those do
        not appear in a grouped result, so a join-based repair would leave
        exactly the wrong counters untouched.

        Companies are included and sources are not: `SourceRepository` has no
        counter, by design.
        """
        for model in (Category, Location, Company):
            live = (
                select(func.count(Job.id))
                .where(
                    Job.status == JobStatus.PUBLISHED,
                    Job.deleted_at.is_(None),
                    _COUNTED_BY[model] == model.id,
                )
                .scalar_subquery()
            )
            await self.session.execute(update(model).values(job_count=live))
        await self.session.flush()

    async def published_facet_counts(self) -> "FacetCounts":
        """How many live listings sit behind each landing page.

        The sitemap uses this to decide which landing pages are worth
        submitting. It counts rather than reading `Category.job_count` and
        `Location.job_count` deliberately: those are denormalised counters
        maintained by `adjust_job_count`, and a counter that has drifted — by a
        failed decrement, a restored listing, a direct edit — would put an
        empty page into the sitemap or keep a full one out. A sitemap is read
        by search engines as an assertion about what is worth crawling, so it
        is worth three aggregate queries to make the assertion true.

        Counted over published, undeleted listings only, which is exactly the
        set the landing page itself will show.
        """
        live = (Job.status == JobStatus.PUBLISHED, Job.deleted_at.is_(None))

        by_category = (
            select(Category.slug, func.count(Job.id))
            .join(Job, Job.category_id == Category.id)
            .where(*live)
            .group_by(Category.slug)
        )
        by_location = (
            select(Location.slug, func.count(Job.id))
            .join(Job, Job.location_id == Location.id)
            .where(*live)
            .group_by(Location.slug)
        )
        by_country = (
            select(Location.country, func.count(Job.id))
            .join(Job, Job.location_id == Location.id)
            .where(*live, Location.country.is_not(None))
            .group_by(Location.country)
        )

        return FacetCounts(
            categories={row[0]: row[1] for row in (await self.session.execute(by_category)).all()},
            locations={row[0]: row[1] for row in (await self.session.execute(by_location)).all()},
            countries={row[0]: row[1] for row in (await self.session.execute(by_country)).all()},
        )

    async def list_related(self, job: Job, *, limit: int = 3) -> list[Job]:
        """Same category or same work type, newest first."""
        stmt = (
            self._live()
            .where(
                Job.id != job.id,
                (Job.category_id == job.category_id) | (Job.work_type == job.work_type),
            )
            .order_by(Job.published_at.desc().nullslast(), Job.id.desc())
            .limit(limit)
            .options(*_EAGER)
        )
        return list((await self.session.execute(stmt)).scalars().unique().all())

    # --- admin reads ------------------------------------------------------

    def _admin_base(self, filters: AdminJobFilters) -> Select:
        stmt = select(Job)
        if not filters.include_deleted:
            stmt = stmt.where(Job.deleted_at.is_(None))
        if filters.status is not None:
            stmt = stmt.where(Job.status == filters.status)
        if filters.created_by is not None:
            stmt = stmt.where(Job.created_by == filters.created_by)
        if filters.category_id is not None:
            stmt = stmt.where(Job.category_id == filters.category_id)
        return stmt

    async def list_admin(self, filters: AdminJobFilters, *, limit: int, offset: int) -> list[Job]:
        stmt = (
            self._admin_base(filters)
            .order_by(Job.created_at.desc(), Job.id.desc())
            .limit(limit)
            .offset(offset)
            .options(*_EAGER)
        )
        return list((await self.session.execute(stmt)).scalars().unique().all())

    async def count_admin(self, filters: AdminJobFilters) -> int:
        base = self._admin_base(filters).subquery()
        return (await self.session.execute(select(func.count()).select_from(base))).scalar_one()

    # --- writes -----------------------------------------------------------

    async def create(self, job: Job) -> Job:
        self.session.add(job)
        await self.session.flush()
        return job

    async def soft_delete(self, job: Job) -> None:
        """Sets `deleted_at`, which also frees the slug for reuse — the unique
        index is partial on `deleted_at IS NULL`."""
        job.deleted_at = datetime.now(UTC)
        await self.session.flush()

    async def restore(self, job: Job) -> None:
        job.deleted_at = None
        await self.session.flush()

    async def bump_version(self, job: Job) -> None:
        job.version = (job.version or 0) + 1
        await self.session.flush()

    async def list_expiring(self, *, on_or_before: date) -> list[Job]:
        """Feeds the nightly expiry sweep. Hits the partial index on
        `expiry_date WHERE status = 'published'`."""
        stmt = select(Job).where(
            Job.status == JobStatus.PUBLISHED,
            Job.deleted_at.is_(None),
            Job.expiry_date.is_not(None),
            Job.expiry_date <= on_or_before,
        )
        return list((await self.session.execute(stmt)).scalars().all())

    async def adjust_counters(self, job_id: UUID, **deltas: int) -> None:
        """Atomic counter arithmetic.

        `UPDATE … SET x = x + :n` rather than load-add-save: concurrent updates
        would otherwise lose increments, which is precisely what happens on a
        popular listing.
        """
        if not deltas:
            return
        values = {name: getattr(Job, name) + delta for name, delta in deltas.items()}
        await self.session.execute(update(Job).where(Job.id == job_id).values(**values))
        await self.session.flush()
