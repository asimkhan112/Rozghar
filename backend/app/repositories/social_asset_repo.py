"""Generated share-asset records."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert

from app.core.enums import SocialVariant
from app.models.social import JobSocialAsset
from app.repositories.base import BaseRepository


class SocialAssetRepository(BaseRepository[JobSocialAsset]):
    model = JobSocialAsset

    async def get(self, job_id: UUID, variant: SocialVariant) -> JobSocialAsset | None:
        stmt = select(JobSocialAsset).where(
            JobSocialAsset.job_id == job_id, JobSocialAsset.variant == variant
        )
        return (await self.session.execute(stmt)).scalars().one_or_none()

    async def list_for_job(self, job_id: UUID) -> list[JobSocialAsset]:
        stmt = select(JobSocialAsset).where(JobSocialAsset.job_id == job_id)
        return list((await self.session.execute(stmt)).scalars().all())

    async def upsert(
        self,
        *,
        job_id: UUID,
        variant: SocialVariant,
        path: str,
        content_hash: str,
        width: int,
        height: int,
        size_bytes: int,
    ) -> JobSocialAsset:
        """Insert or replace the record for this job and variant.

        `ON CONFLICT` rather than select-then-branch: two requests for a card
        that does not exist yet will both render and both try to record the
        result, and the loser of that race should update the row rather than
        raise a unique-violation the caller has to interpret.
        """
        stmt = (
            insert(JobSocialAsset)
            .values(
                job_id=job_id,
                variant=variant,
                path=path,
                content_hash=content_hash,
                width=width,
                height=height,
                size_bytes=size_bytes,
            )
            .on_conflict_do_update(
                constraint="uq_job_social_assets_job_id_variant",
                set_={
                    "path": path,
                    "content_hash": content_hash,
                    "width": width,
                    "height": height,
                    "size_bytes": size_bytes,
                    "generated_at": __import__("sqlalchemy").func.now(),
                },
            )
            .returning(JobSocialAsset)
        )
        row = (await self.session.execute(stmt)).scalars().one()
        await self.session.flush()
        return row

    async def delete_for_job(self, job_id: UUID) -> list[str]:
        """Drop the records and return the storage keys, so the caller can
        remove the files the database no longer points at."""
        stmt = (
            delete(JobSocialAsset)
            .where(JobSocialAsset.job_id == job_id)
            .returning(JobSocialAsset.path)
        )
        paths = list((await self.session.execute(stmt)).scalars().all())
        await self.session.flush()
        return paths


__all__ = ["SocialAssetRepository"]
