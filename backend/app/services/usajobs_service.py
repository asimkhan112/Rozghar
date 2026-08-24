"""One import run.

Fetch a page of announcements, map each one, and create the ones that are new
as drafts. Nothing here publishes: an imported listing is a proposal, reviewed
in the admin queue exactly like a job an editor half-finished.

Idempotent by `(source_id, source_ref)`. Running it twice in a row creates
nothing the second time, which is what makes a button safe to press twice.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import JobStatus
from app.core.exceptions import DomainError
from app.core.slug import slugify
from app.models.job import Job
from app.models.taxonomy import Location
from app.repositories.taxonomy_repo import CategoryRepository, LocationRepository, SourceRepository
from app.services.auth_service import Principal
from app.services.job_service import JobService
from app.services.usajobs_client import USAJobsClient
from app.services.usajobs_mapper import DEFAULT_CATEGORY, MappedJob, map_announcement

logger = logging.getLogger(__name__)

SOURCE_SLUG = "usajobs"


class ImportMisconfigured(DomainError):
    status = 503
    code = "import_misconfigured"
    title = "The importer is not set up on this server"


@dataclass
class ImportResult:
    """What the admin sees after pressing the button.

    `skipped` is the number already imported — a large one is the expected
    outcome of a second run, not a fault, so it is reported plainly rather
    than folded into `failed`.
    """

    fetched: int = 0
    created: int = 0
    skipped: int = 0
    failed: int = 0
    errors: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, object]:
        return {
            "fetched": self.fetched,
            "created": self.created,
            "skipped": self.skipped,
            "failed": self.failed,
            "errors": self.errors[:5],
        }


class USAJobsImportService:
    def __init__(self, session: AsyncSession, jobs: JobService) -> None:
        self.session = session
        self.jobs = jobs
        self.sources = SourceRepository(session)
        self.categories = CategoryRepository(session)
        self.locations = LocationRepository(session)
        self.client = USAJobsClient()

    async def run(self, *, principal: Principal, ip_hash: str | None = None) -> ImportResult:
        source = await self.sources.get_by_slug(SOURCE_SLUG)
        if source is None:
            raise ImportMisconfigured(
                "The USAJOBS source row is missing. Run `alembic upgrade head`."
            )

        from app.core.config import settings

        descriptors = await self.client.search(
            series=settings.usajobs_series,
            days_posted=settings.usajobs_days_posted,
            page_size=settings.usajobs_page_size,
        )
        result = ImportResult(fetched=len(descriptors))

        # One query for every reference already held, rather than one per
        # announcement: a 250-row page would otherwise be 250 round trips
        # before a single job is created.
        known = await self._known_refs(source.id)

        for descriptor in descriptors:
            mapped = map_announcement(descriptor)
            if mapped is None:
                result.failed += 1
                continue
            if mapped.source_ref in known:
                result.skipped += 1
                continue
            try:
                await self._create(
                    mapped, source_id=source.id, principal=principal, ip_hash=ip_hash
                )
            except Exception as exc:  # noqa: BLE001 - one bad row must not end the run
                result.failed += 1
                result.errors.append(f"{mapped.data['title'][:60]}: {exc}")
                logger.warning(
                    "usajobs import row failed",
                    extra={"event": "usajobs.row_failed", "ref": mapped.source_ref},
                )
                await self.session.rollback()
                continue
            known.add(mapped.source_ref)
            result.created += 1

        source.last_run_at = datetime.now(UTC)
        if result.created or not result.failed:
            source.last_success_at = datetime.now(UTC)
        await self.session.commit()

        logger.info("usajobs import finished", extra={"event": "usajobs.done", **result.as_dict()})
        return result

    async def _known_refs(self, source_id: UUID) -> set[str]:
        rows = await self.session.execute(
            select(Job.source_ref).where(
                Job.source_id == source_id,
                Job.source_ref.is_not(None),
                Job.deleted_at.is_(None),
            )
        )
        return {row[0] for row in rows if row[0]}

    async def _create(
        self,
        mapped: MappedJob,
        *,
        source_id: UUID,
        principal: Principal,
        ip_hash: str | None,
    ) -> None:
        category = await self.categories.get_by_slug(mapped.category_slug)
        if category is None:
            category = await self.categories.get_by_slug(DEFAULT_CATEGORY)
        if category is None:
            raise ImportMisconfigured(
                "No category to file imported listings under. Run the taxonomy seed."
            )

        location = await self._ensure_location(mapped)
        data = {
            **mapped.data,
            "category_id": category.id,
            "location_id": location.id,
            "source_id": source_id,
            "source_ref": mapped.source_ref,
            # Explicit, though it is also the default: an imported listing must
            # never reach the public site without a person deciding it should.
            "status": JobStatus.DRAFT,
        }
        await self.jobs.create(data, principal=principal, ip_hash=ip_hash)
        await self.session.commit()

    async def _ensure_location(self, mapped: MappedJob) -> Location:
        """Finds or creates the US location a listing points at.

        Created on demand rather than seeded: the set of federal duty stations
        is thousands of towns long, and seeding all of them to use forty would
        fill the location filter with dead entries.
        """
        slug = slugify(mapped.display_name)
        existing = await self.locations.get_by_slug(slug)
        if existing is not None:
            return existing
        return await self.locations.create(
            Location(
                city=mapped.city[:80],
                region=(mapped.region or None) and mapped.region[:80],
                country=mapped.country,
                slug=slug,
                display_name=mapped.display_name[:160],
                is_remote=False,
            )
        )


__all__ = ["ImportMisconfigured", "ImportResult", "USAJobsImportService"]
