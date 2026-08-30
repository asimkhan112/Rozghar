"""Job business rules.

Owns the status machine, slug generation and freezing, counter maintenance, and
the audit trail. Repositories flush; this layer decides *whether* something may
happen and owns the transaction boundary.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import JobStatus
from app.core.exceptions import Conflict, DomainError, NotFound, PermissionDenied
from app.core.permissions import Permission
from app.core.slug import job_slug, with_discriminator
from app.models.job import Job
from app.repositories.job_repo import AdminJobFilters, JobFilters, JobRepository
from app.repositories.taxonomy_repo import (
    CategoryRepository,
    CompanyRepository,
    LocationRepository,
    SourceRepository,
)
from app.services.audit_service import AuditService, diff
from app.services.auth_service import Principal

logger = logging.getLogger(__name__)

#: A listing inside this many days of expiry is badged "expiring".
EXPIRING_SOON_DAYS = 7

#: Slug collision retries before giving up. Three duplicates of one title at
#: one company is already implausible; more suggests a bug worth surfacing.
MAX_SLUG_ATTEMPTS = 25

#: Which status transitions are legal. Anything absent is rejected, so a
#: malformed request cannot walk a listing into a nonsensical state.
ALLOWED_TRANSITIONS: dict[JobStatus, frozenset[JobStatus]] = {
    JobStatus.DRAFT: frozenset({JobStatus.PUBLISHED, JobStatus.SCHEDULED, JobStatus.ARCHIVED}),
    JobStatus.SCHEDULED: frozenset({JobStatus.PUBLISHED, JobStatus.DRAFT, JobStatus.ARCHIVED}),
    JobStatus.PUBLISHED: frozenset({JobStatus.EXPIRED, JobStatus.ARCHIVED, JobStatus.DRAFT}),
    JobStatus.EXPIRED: frozenset({JobStatus.PUBLISHED, JobStatus.ARCHIVED}),
    JobStatus.ARCHIVED: frozenset({JobStatus.DRAFT}),
}


#: How many listings one bulk call may touch.
#:
#: A ceiling on the transaction, not on the operation: the endpoints report what
#: is left so the admin can run again.
#:
#: It was 500, chosen against the number of rows. That was the wrong quantity to
#: measure — the cost was never the rows, it was the round trips, and the
#: original loop spent four or five per row. Six hundred drafts meant well over
#: two thousand sequential hops to a hosted database, which ran past the
#: client's timeout in production while finishing instantly against a local
#: container.
#:
#: Both operations are now a fixed handful of statements regardless of size, so
#: the cap exists only to bound how much one transaction locks at once. Raised
#: so a realistic backlog clears in a single press rather than a dozen.
MAX_BULK = 5000


class InvalidTransition(DomainError):
    status = 422
    code = "invalid_transition"
    title = "Status transition is not allowed"


class UnknownReference(DomainError):
    status = 422
    code = "unknown_reference"
    title = "Referenced record does not exist"


class VersionConflict(Conflict):
    code = "version_conflict"
    title = "The record changed since it was read"


@dataclass(frozen=True)
class JobPage:
    items: list[Job]
    total: int
    page: int
    per_page: int

    @property
    def total_pages(self) -> int:
        return (self.total + self.per_page - 1) // self.per_page if self.per_page else 0

    @property
    def has_more(self) -> bool:
        return self.page * self.per_page < self.total


def compute_badge(job: Job, *, today: date | None = None) -> str:
    """Display badge, derived rather than stored.

    Priority order matters: a featured listing that is also about to expire
    shows as featured, because that is what the placement was paid for.
    """
    if job.featured:
        return "featured"
    reference = today or datetime.now(UTC).date()
    if job.expiry_date is not None and job.expiry_date - reference <= timedelta(
        days=EXPIRING_SOON_DAYS
    ):
        return "expiring"
    if job.verified:
        return "verified"
    return "fresh"


def _snapshot(job: Job) -> dict[str, Any]:
    """Auditable fields only — counters and search denormalisations are noise."""
    return {
        c.name: getattr(job, c.name)
        for c in job.__table__.columns
        if c.name
        not in {
            "view_count",
            "apply_click_count",
            "save_count",
            "location_text",
            "skills_text",
            "updated_at",
            "version",
        }
    }


class JobService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.jobs = JobRepository(session)
        self.categories = CategoryRepository(session)
        self.locations = LocationRepository(session)
        self.sources = SourceRepository(session)
        self.companies = CompanyRepository(session)
        self.audit = AuditService(session)

    # --- public reads -----------------------------------------------------

    async def list_public(
        self, filters: JobFilters, *, sort: str, page: int, per_page: int
    ) -> JobPage:
        offset = (page - 1) * per_page
        total = await self.jobs.count_public(filters)
        items = (
            await self.jobs.list_public(filters, sort=sort, limit=per_page, offset=offset)
            if total
            else []
        )
        return JobPage(items=items, total=total, page=page, per_page=per_page)

    async def get_public(self, slug: str) -> tuple[Job, list[Job]]:
        job = await self.jobs.get_by_slug(slug)
        if job is None:
            # Distinguish "never existed" from "no longer available": a crawler
            # should drop a 410 permanently but retry a 404.
            any_state = await self.jobs.get_any_by_slug(slug)
            if any_state is not None and any_state.status in {
                JobStatus.EXPIRED,
                JobStatus.ARCHIVED,
            }:
                raise _Gone("This listing is no longer available.")
            raise NotFound("No job exists at this address.")
        related = await self.jobs.list_related(job)
        return job, related

    # --- admin reads ------------------------------------------------------

    async def list_admin(self, filters: AdminJobFilters, *, page: int, per_page: int) -> JobPage:
        offset = (page - 1) * per_page
        total = await self.jobs.count_admin(filters)
        items = await self.jobs.list_admin(filters, limit=per_page, offset=offset) if total else []
        return JobPage(items=items, total=total, page=page, per_page=per_page)

    async def get_admin(self, job_id: UUID) -> Job:
        job = await self.jobs.get_by_id(job_id)
        if job is None:
            raise NotFound("No job exists with that identifier.")
        return job

    # --- create -----------------------------------------------------------

    async def create(
        self, data: dict[str, Any], *, principal: Principal, ip_hash: str | None = None
    ) -> Job:
        requested_status = data.pop("status", JobStatus.DRAFT)
        if requested_status == JobStatus.PUBLISHED and not principal.has(
            Permission.JOB_PUBLISH.value
        ):
            raise PermissionDenied(Permission.JOB_PUBLISH.value)

        await self._validate_references(data)
        source_id = data.get("source_id") or await self._default_source_id()

        job = Job(
            **{k: v for k, v in data.items() if k != "source_id"},
            source_id=source_id,
            slug="",  # replaced below, once uniqueness is settled
            created_by=principal.admin_id,
            status=JobStatus.DRAFT,
        )
        job.slug = await self._unique_slug(job.title, job.company_name)
        job.location_text, job.skills_text = await self._denormalise(job)

        await self.jobs.create(job)

        if requested_status == JobStatus.PUBLISHED:
            await self._transition(job, JobStatus.PUBLISHED)

        await self.audit.record(
            admin_id=principal.admin_id,
            action="job.create",
            entity_type="job",
            entity_id=job.id,
            after={"slug": job.slug, "title": job.title, "status": job.status},
            ip_hash=ip_hash,
        )
        return job

    # --- update -----------------------------------------------------------

    async def update(
        self,
        job_id: UUID,
        changes: dict[str, Any],
        *,
        principal: Principal,
        expected_version: int | None = None,
        ip_hash: str | None = None,
    ) -> Job:
        job = await self.get_admin(job_id)
        self._assert_may_edit(job, principal)

        if expected_version is not None and job.version != expected_version:
            raise VersionConflict(
                f"This job is at version {job.version}; the request was based on "
                f"version {expected_version}. Re-read it and re-apply the change."
            )

        await self._validate_references(changes)
        before = _snapshot(job)

        for field, value in changes.items():
            setattr(job, field, value)

        # The slug follows the title only while the listing is still private.
        # Once published it is frozen — it is the URL people have already shared.
        if ("title" in changes or "company_name" in changes) and job.status == JobStatus.DRAFT:
            job.slug = await self._unique_slug(job.title, job.company_name, exclude_id=job.id)

        job.location_text, job.skills_text = await self._denormalise(job)

        # Decide whether anything actually moved *before* stamping provenance.
        # Setting `updated_by` first would make every request look like a change
        # and fill the audit log with entries that record nothing.
        after = _snapshot(job)
        _, changed = diff(before, after)
        if not changed:
            return job

        job.updated_by = principal.admin_id
        await self.jobs.bump_version(job)

        await self.audit.record(
            admin_id=principal.admin_id,
            action="job.update",
            entity_type="job",
            entity_id=job.id,
            before={k: before.get(k) for k in changed},
            after=changed,
            ip_hash=ip_hash,
        )
        return job

    # --- lifecycle actions ------------------------------------------------

    async def publish(
        self, job_id: UUID, *, principal: Principal, ip_hash: str | None = None
    ) -> Job:
        job = await self.get_admin(job_id)
        await self._transition(job, JobStatus.PUBLISHED)
        job.updated_by = principal.admin_id
        await self.audit.record(
            admin_id=principal.admin_id,
            action="job.publish",
            entity_type="job",
            entity_id=job.id,
            after={"status": job.status, "published_at": job.published_at},
            ip_hash=ip_hash,
        )
        return job

    async def expire(
        self,
        job_id: UUID,
        *,
        principal: Principal,
        reason: str | None = None,
        ip_hash: str | None = None,
    ) -> Job:
        job = await self.get_admin(job_id)
        self._assert_may_edit(job, principal)
        await self._transition(job, JobStatus.EXPIRED)
        job.updated_by = principal.admin_id
        await self.audit.record(
            admin_id=principal.admin_id,
            action="job.expire",
            entity_type="job",
            entity_id=job.id,
            after={"status": job.status, "reason": reason},
            ip_hash=ip_hash,
        )
        return job

    async def set_verified(
        self, job_id: UUID, verified: bool, *, principal: Principal, ip_hash: str | None = None
    ) -> Job:
        job = await self.get_admin(job_id)
        before = {"verified": job.verified}

        job.verified = verified
        # The database CHECK requires a verifier whenever `verified` is true,
        # so the attribution is set and cleared alongside the flag.
        job.verified_at = datetime.now(UTC) if verified else None
        job.verified_by = principal.admin_id if verified else None
        job.updated_by = principal.admin_id
        await self.jobs.bump_version(job)

        await self.audit.record(
            admin_id=principal.admin_id,
            action="job.verify" if verified else "job.unverify",
            entity_type="job",
            entity_id=job.id,
            before=before,
            after={"verified": verified},
            ip_hash=ip_hash,
        )
        return job

    async def set_featured(
        self,
        job_id: UUID,
        featured: bool,
        *,
        principal: Principal,
        until: datetime | None = None,
        ip_hash: str | None = None,
    ) -> Job:
        job = await self.get_admin(job_id)

        # Mirrors the database CHECK, so the caller gets a clear 422 instead of
        # a constraint violation surfacing as a 500.
        if featured and job.status != JobStatus.PUBLISHED:
            raise InvalidTransition("Only a published job can be featured.")

        before = {"featured": job.featured, "featured_until": job.featured_until}
        job.featured = featured
        job.featured_until = until if featured else None
        job.updated_by = principal.admin_id
        await self.jobs.bump_version(job)

        await self.audit.record(
            admin_id=principal.admin_id,
            action="job.feature" if featured else "job.unfeature",
            entity_type="job",
            entity_id=job.id,
            before=before,
            after={"featured": featured, "featured_until": until},
            ip_hash=ip_hash,
        )
        return job

    async def delete(
        self, job_id: UUID, *, principal: Principal, ip_hash: str | None = None
    ) -> None:
        job = await self.get_admin(job_id)

        # Counters track live listings only.
        if job.status == JobStatus.PUBLISHED:
            await self._adjust_counters(job, -1)

        await self.jobs.soft_delete(job)
        await self.audit.record(
            admin_id=principal.admin_id,
            action="job.delete",
            entity_type="job",
            entity_id=job.id,
            before={"slug": job.slug, "status": job.status},
            ip_hash=ip_hash,
        )

    # --- bulk operations --------------------------------------------------

    async def purge_expired(
        self, *, principal: Principal, ip_hash: str | None = None, limit: int = MAX_BULK
    ) -> dict[str, Any]:
        """Permanently delete every expired listing.

        A hard delete, unlike `delete` above, which only sets `deleted_at`. The
        rows stop existing and the reports, share cards and per-job analytics
        rollups that hang off them go too — see `purge_by_status` for the exact
        cascade. There is no undo, which is why the route asks for confirmation
        and why the audit entries below are written before the statement runs.

        No counter adjustment. `_adjust_counters` runs on the transitions into
        and out of `PUBLISHED`, and `ALLOWED_TRANSITIONS` only reaches `EXPIRED`
        from `PUBLISHED` — so every row this touches was already decremented on
        its way out of the public site. Decrementing again here would drive the
        category and location counts negative.

        Capped, and the caller is told what is left. An unbounded delete over a
        catalogue of any size is one long transaction holding row locks on
        `reports` and `analytics_daily_rollups` as it cascades.
        """
        doomed = await self.jobs.purge_by_status(JobStatus.EXPIRED, limit=limit)

        # One row per listing, written as one statement. After the delete these
        # entries are the only remaining record that the listing ever existed —
        # `audit_logs.entity_id` carries no foreign key precisely so it can
        # outlive what it points at — so the batch keeps its per-listing detail
        # rather than collapsing into a single summary entry.
        await self.audit.record_many(
            admin_id=principal.admin_id,
            action="job.purge",
            entity_type="job",
            entries=[
                (job_id, {"slug": slug, "status": JobStatus.EXPIRED.value}, None)
                for job_id, slug in doomed
            ],
            ip_hash=ip_hash,
        )

        # The counters are rebuilt from the jobs table rather than nudged by a
        # delta. Nothing this statement removed was still counted as live — see
        # above — so this is not correcting for the purge. It is the moment to
        # repair the drift that `expire_jobs` accumulated while it bypassed the
        # state machine, and a cleanup action is exactly where an admin expects
        # the numbers to come out right afterwards.
        await self.jobs.recount_live_jobs()

        remaining = await self.jobs.count_by_status(JobStatus.EXPIRED)
        return {
            "deleted": len(doomed),
            "remaining": remaining,
            "slugs": [slug for _, slug in doomed[:20]],
        }

    async def publish_drafts(
        self, *, principal: Principal, ip_hash: str | None = None, limit: int = MAX_BULK
    ) -> dict[str, Any]:
        """Publish every draft listing.

        Drafts only. `ALLOWED_TRANSITIONS` also permits `EXPIRED -> PUBLISHED`,
        but reviving an expired listing here would be undone the same night:
        `expire_due` re-expires anything published whose `expiry_date` has
        passed, which is exactly the set that expired in the first place.
        Extending those dates is an editorial decision about whether a role is
        still open, and not something a bulk button should make on its own.

        Three statements, not three per listing. This began as a loop calling
        `_transition` per row so it would share a code path with the
        single-listing publish button, which was the right instinct and the
        wrong shape: that path flushes four to five times per listing, and
        against a hosted database the request ran past two minutes on six
        hundred drafts and was cut off, while completing instantly against a
        local container. `publish_drafts` in the repository preserves the same
        transition rules in one `UPDATE`, and documents each of them.

        Still all-or-nothing: one transaction, so a failure rolls the whole
        batch back. A bulk action that half-applied would leave the admin unable
        to tell which half without reading every row.
        """
        published = await self.jobs.publish_drafts(
            updated_by=principal.admin_id, limit=limit
        )

        await self.audit.record_many(
            admin_id=principal.admin_id,
            action="job.publish",
            entity_type="job",
            entries=[
                (
                    job_id,
                    {"status": JobStatus.DRAFT.value},
                    {"status": JobStatus.PUBLISHED.value, "slug": slug},
                )
                for job_id, slug in published
            ],
            ip_hash=ip_hash,
        )

        # Rebuilt from the jobs table rather than incremented per listing. Three
        # statements instead of three per row, and derived counts cannot drift.
        await self.jobs.recount_live_jobs()

        remaining = await self.jobs.count_by_status(JobStatus.DRAFT)
        return {
            "published": len(published),
            "remaining": remaining,
            "slugs": [slug for _, slug in published[:20]],
        }

    # --- internals --------------------------------------------------------

    def _assert_may_edit(self, job: Job, principal: Principal) -> None:
        """Editors may only touch what they created.

        Enforced here rather than in a route decorator because it needs the
        entity. Anyone holding JOB_PUBLISH is a full editor and is unrestricted.
        """
        if principal.has(Permission.JOB_PUBLISH.value):
            return
        if job.created_by != principal.admin_id:
            raise PermissionDenied(Permission.JOB_PUBLISH.value)

    async def _transition(self, job: Job, target: JobStatus) -> None:
        current = JobStatus(job.status)
        if current == target:
            return
        if target not in ALLOWED_TRANSITIONS.get(current, frozenset()):
            raise InvalidTransition(f"A job cannot move from {current.value} to {target.value}.")

        was_live = current == JobStatus.PUBLISHED
        now_live = target == JobStatus.PUBLISHED

        # Every field that the CHECK constraints relate must be set before the
        # first flush. `ck_jobs_featured_requires_published` fires the moment a
        # status change reaches the database while `featured` is still true, so
        # the flag is cleared here rather than after the counter update — which
        # flushes.
        job.status = target
        if now_live and job.published_at is None:
            # Stamped exactly once. Re-publishing must not reset a listing's
            # age and let it jump the recency ordering.
            job.published_at = datetime.now(UTC)
        if was_live and not now_live:
            # A listing that has left the public site cannot stay featured.
            job.featured = False
            job.featured_until = None

        job.version = (job.version or 0) + 1
        await self.session.flush()

        if now_live and not was_live:
            await self._adjust_counters(job, +1)
        elif was_live and not now_live:
            await self._adjust_counters(job, -1)

    async def _adjust_counters(self, job: Job, delta: int) -> None:
        await self.categories.adjust_job_count(job.category_id, delta)
        await self.locations.adjust_job_count(job.location_id, delta)
        if job.company_id is not None:
            await self.companies.adjust_job_count(job.company_id, delta)

    async def _validate_references(self, data: dict[str, Any]) -> None:
        """Check foreign keys before insert.

        The database would reject a bad reference anyway, but as an opaque
        integrity error. Checking here produces a 422 that names the field.
        """
        errors: dict[str, list[str]] = {}

        category_id = data.get("category_id")
        if category_id is not None:
            if not await self.categories.exists(category_id):
                errors["category_id"] = ["No category exists with this id."]
            elif not await self.categories.is_active(category_id):
                errors["category_id"] = ["This category is not active."]

        location_id = data.get("location_id")
        if location_id is not None and not await self.locations.exists(location_id):
            errors["location_id"] = ["No location exists with this id."]

        source_id = data.get("source_id")
        if source_id is not None and not await self.sources.exists(source_id):
            errors["source_id"] = ["No source exists with this id."]

        company_id = data.get("company_id")
        if company_id is not None and not await self.companies.exists(company_id):
            errors["company_id"] = ["No company exists with this id."]

        if errors:
            raise UnknownReference("One or more referenced records do not exist.", errors=errors)

    async def _default_source_id(self) -> UUID:
        manual = await self.sources.get_manual()
        if manual is None:
            raise UnknownReference(
                "No source was supplied and the 'manual' source is missing. "
                "Run the RBAC seed migration."
            )
        return manual.id

    async def _unique_slug(
        self, title: str, company: str, *, exclude_id: UUID | None = None
    ) -> str:
        base = job_slug(title, company)
        candidate = base
        for attempt in range(2, MAX_SLUG_ATTEMPTS + 2):
            existing = await self.jobs.get_any_by_slug(candidate)
            if existing is None or existing.id == exclude_id:
                return candidate
            candidate = with_discriminator(base, attempt)
        raise Conflict("Could not derive a unique slug for this listing.")

    async def _denormalise(self, job: Job) -> tuple[str, str]:
        """Mirror the text the Milestone 5 search vector will consume.

        A generated column cannot read another table, so the location's display
        name and the flattened requirements live on the job row. Maintained
        here now; a trigger takes over when the vector is added.
        """
        location = await self.locations.get(job.location_id)
        location_text = location.display_name if location else ""
        skills = job.requirements or []
        skills_text = " ".join(str(s) for s in skills)
        return location_text, skills_text[:4000]


class _Gone(DomainError):
    """410 — the listing existed and is permanently unavailable."""

    status = 410
    code = "job_gone"
    title = "Listing is no longer available"


async def handle_integrity_error(exc: IntegrityError) -> None:
    """Translate the slug race into a 409.

    The uniqueness pre-check narrows the window but cannot close it; two
    simultaneous creates can still collide at the index.
    """
    message = str(exc.orig) if exc.orig else str(exc)
    if "uq_jobs_slug_active" in message:
        raise Conflict("A job with this slug already exists.") from exc
    raise
