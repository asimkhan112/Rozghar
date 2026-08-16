"""Share assets for a listing: captions, images, and the URLs to post them to.

Composes the renderer, the caption writer and storage into the one thing the
admin UI asks for. This is also where the regeneration decision lives — the
only place that compares a stored `content_hash` against the job as it is now.

**Images are produced lazily.** Nothing renders inside `POST /admin/jobs`.
Publishing must not get slower for an image that may never be looked at, and a
font problem or a full disk must never be able to fail a publish. The first
request for a card renders it; every later one reads the stored file.
"""

from __future__ import annotations

import asyncio
import logging
from decimal import Decimal
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.enums import SocialVariant
from app.core.exceptions import NotFound
from app.models.job import Job
from app.repositories.job_repo import JobRepository
from app.repositories.social_asset_repo import SocialAssetRepository
from app.services.caption_service import CaptionInput, Captions, build_captions, share_urls
from app.services.social_card_service import (
    SPECS,
    JobCardData,
    render_card,
    storage_key,
)
from app.storage import Storage, get_storage

logger = logging.getLogger(__name__)

#: Rendering is CPU-bound and blocks the event loop for a couple of hundred
#: milliseconds. One at a time, off the loop: a burst of requests should queue
#: rather than starve every other request on the worker.
_render_lock = asyncio.Semaphore(2)


def _format_salary(job: Job) -> str | None:
    """The salary as it appears on the card, or nothing.

    Mirrors the public API's rule: an undisclosed figure is withheld rather
    than rendered as a zero, and a card with no salary line is better than one
    advertising `PKR 0`.
    """
    if not job.salary_is_disclosed:
        return None
    low: Decimal | None = job.salary_min
    high: Decimal | None = job.salary_max
    if low is None and high is None:
        return None

    period = {"hour": "/hr", "month": "/mo", "year": "/yr"}.get(job.salary_period.value, "")
    currency = job.salary_currency

    def money(value: Decimal) -> str:
        return f"{int(value):,}"

    if low is not None and high is not None and low != high:
        return f"{currency} {money(low)} – {money(high)}{period}"
    return f"{currency} {money(low if low is not None else high)}{period}"  # type: ignore[arg-type]


def _format_experience(job: Job) -> str | None:
    low, high = job.experience_min_years, job.experience_max_years
    if low is not None and high is not None:
        return f"{low}–{high} years" if low != high else f"{low} years"
    if low is not None:
        return f"{low}+ years"
    return None


_EMPLOYMENT_LABEL = {
    "full_time": "Full Time",
    "part_time": "Part Time",
    "contract": "Contract",
    "internship": "Internship",
}


def card_data_for(job: Job) -> JobCardData:
    """Project a listing into exactly what the card and captions render.

    Requirements double as the skill chips: they are the short, scannable
    fragments an editor already enters one per line.
    """
    skills = [str(item).strip() for item in (job.requirements or []) if str(item).strip()]
    return JobCardData(
        title=job.title,
        company=job.company_name,
        location=job.location.display_name if job.location else "",
        employment_type=_EMPLOYMENT_LABEL.get(job.employment_type.value, job.employment_type.value),
        slug=job.slug,
        salary=_format_salary(job),
        experience=_format_experience(job),
        skills=skills,
    )


class ShareService:
    def __init__(self, session: AsyncSession, storage: Storage | None = None) -> None:
        self.session = session
        self.jobs = JobRepository(session)
        self.assets = SocialAssetRepository(session)
        self.storage = storage or get_storage()

    async def _job(self, job_id: UUID) -> Job:
        job = await self.jobs.get_by_id(job_id)
        if job is None:
            raise NotFound("Listing not found.")
        return job

    async def ensure_asset(
        self, job_id: UUID, variant: SocialVariant = SocialVariant.SQUARE
    ) -> tuple[bytes, bool]:
        """Return the card's bytes, rendering it first if it is missing or stale.

        Returns `(png, regenerated)`. Three conditions force a re-render: no
        record, a `content_hash` that no longer matches the job, or a record
        whose file has gone — which happens whenever storage is a container
        filesystem that was replaced.
        """
        job = await self._job(job_id)
        data = card_data_for(job)
        digest = data.content_hash()
        key = storage_key(str(job_id), variant)

        record = await self.assets.get(job_id, variant)
        if record is not None and record.content_hash == digest:
            existing = await self.storage.read(record.path)
            if existing is not None:
                return existing, False
            logger.info(
                "social asset record without a file; re-rendering",
                extra={"event": "social.asset_missing", "job_id": str(job_id), "path": record.path},
            )

        async with _render_lock:
            png = await asyncio.to_thread(render_card, data, variant)

        stored = await self.storage.write(key, png, content_type="image/png")
        spec = SPECS[variant]
        await self.assets.upsert(
            job_id=job_id,
            variant=variant,
            path=stored.key,
            content_hash=digest,
            width=spec.width,
            height=spec.height,
            size_bytes=stored.size_bytes,
        )
        logger.info(
            "social asset generated",
            extra={
                "event": "social.generated",
                "job_id": str(job_id),
                "variant": variant.value,
                "bytes": stored.size_bytes,
            },
        )
        return png, True

    async def captions_for(self, job: Job) -> Captions:
        data = card_data_for(job)
        return build_captions(
            CaptionInput(
                title=data.title,
                company=data.company,
                location=data.location,
                employment_type=data.employment_type,
                slug=data.slug,
                salary=data.salary,
                experience=data.experience,
                skills=tuple(data.skills),
            )
        )

    async def share_payload(self, job_id: UUID) -> dict:
        """Everything the share modal needs, in one request.

        Deliberately does *not* render the image — it returns the URL that will.
        The modal opens the instant a job is published, and blocking that on a
        200ms render would be paying for an asset the admin may never scroll to.
        """
        job = await self._job(job_id)
        data = card_data_for(job)
        captions = await self.captions_for(job)

        base = settings.site_url.rstrip("/")
        image_url = f"{base}{settings.api_v1_prefix}/jobs/{job.slug}/social/square.png"

        return {
            "job_id": job.id,
            "job_url": data.job_url,
            "job_title": job.title,
            "image_url": image_url,
            "image_urls": {
                variant.value: (
                    f"{base}{settings.api_v1_prefix}/jobs/{job.slug}/social/{variant.value}.png"
                )
                for variant in SocialVariant
            },
            "linkedin_caption": captions.linkedin,
            "whatsapp_message": captions.whatsapp,
            "facebook_caption": captions.facebook,
            "twitter_caption": captions.twitter,
            "hashtags": list(captions.hashtags),
            "share_urls": share_urls(data.job_url, captions),
        }

    async def invalidate(self, job_id: UUID) -> int:
        """Drop a listing's assets, files included.

        Not normally needed — a changed `content_hash` already forces a
        re-render — but a template change invalidates nothing by itself, so this
        is the hook a redesign uses.
        """
        paths = await self.assets.delete_for_job(job_id)
        for path in paths:
            await self.storage.delete(path)
        return len(paths)


__all__ = ["ShareService", "card_data_for"]
