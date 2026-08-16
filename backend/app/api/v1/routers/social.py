"""Share assets: the admin payload and the public image.

Two audiences, deliberately split. The payload is editorial — captions, intent
URLs, the things a person acts on — and is gated on being able to see the
listing. The image is public and unauthenticated, because a social crawler
fetching `og:image` has no credentials and never will.
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Path, Response

from app.api.v1.deps import DbSession, require
from app.core.enums import SocialVariant
from app.core.exceptions import NotFound
from app.core.permissions import Permission
from app.repositories.job_repo import JobRepository
from app.schemas.social import ShareAssets
from app.services.auth_service import Principal
from app.services.share_service import ShareService

router = APIRouter(tags=["social"])


def share_service(session: DbSession) -> ShareService:
    return ShareService(session)


ServiceDep = Annotated[ShareService, Depends(share_service)]


@router.get(
    "/admin/jobs/{job_id}/share-assets",
    response_model=ShareAssets,
    tags=["admin:jobs"],
    summary="Captions, image URLs and share links for a listing",
)
async def share_assets(
    job_id: UUID,
    service: ServiceDep,
    _: Annotated[Principal, Depends(require(Permission.JOB_VIEW_ALL))],
) -> ShareAssets:
    """Returns immediately. The image URL points at an endpoint that renders on
    first request, so opening the share modal never waits on Pillow."""
    return ShareAssets.model_validate(await service.share_payload(job_id))


@router.get(
    "/jobs/{slug}/social/{variant}.png",
    summary="Generated share card",
    responses={404: {"description": "No published listing at this address"}},
)
async def social_card(
    session: DbSession,
    service: ServiceDep,
    slug: Annotated[str, Path(max_length=160)],
    variant: SocialVariant = SocialVariant.SQUARE,
) -> Response:
    """Public and cacheable.

    Addressed by slug rather than id because this URL ends up in an `og:image`
    tag beside the canonical job URL, and two different identifiers for one
    listing in adjacent meta tags is a needless inconsistency.

    Only published listings render. A draft's card would otherwise be a
    readable preview of unreleased editorial work, retrievable by anyone who
    guesses the slug.
    """
    job = await JobRepository(session).get_by_slug(slug, published_only=True)
    if job is None:
        raise NotFound("No listing at this address.")

    png, regenerated = await service.ensure_asset(job.id, variant)
    # The service writes an asset row; without a commit the next request
    # re-renders an image that is already on disk.
    if regenerated:
        await session.commit()

    return Response(
        content=png,
        media_type="image/png",
        headers={
            # Crawlers refetch often. A day of caching with a week of
            # stale-while-revalidate keeps them off the renderer without making
            # an edited card take a week to propagate.
            "Cache-Control": "public, max-age=86400, stale-while-revalidate=604800",
            "Content-Disposition": f'inline; filename="{slug}-{variant.value}.png"',
        },
    )
