"""Admin job management.

Each lifecycle action is its own endpoint rather than a flag on PATCH: they
carry distinct permissions, write distinct audit entries, and are separately
rate-limitable. They are actions, not field edits.
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, Request, Response, status
from sqlalchemy.exc import IntegrityError

from app.api.v1.deps import DbSession, client_ip, require
from app.api.v1.mappers import job_admin, paginate_jobs
from app.core.enums import JobStatus
from app.core.permissions import Permission
from app.core.security import hash_ip
from app.repositories.job_repo import AdminJobFilters
from app.schemas.common import Paginated
from app.schemas.job import (
    BulkPublishResult,
    BulkPurgeResult,
    JobAdmin,
    JobCreate,
    JobExpireRequest,
    JobFeatureRequest,
    JobUpdate,
    JobVerifyRequest,
)
from app.services.auth_service import Principal
from app.services.job_service import JobService, handle_integrity_error

router = APIRouter(prefix="/admin/jobs", tags=["admin:jobs"])


def job_service(session: DbSession) -> JobService:
    return JobService(session)


ServiceDep = Annotated[JobService, Depends(job_service)]


def _ip(request: Request) -> str | None:
    return hash_ip(client_ip(request))


@router.get("", response_model=Paginated[JobAdmin], summary="List every listing, any state")
async def list_jobs(
    service: ServiceDep,
    _: Annotated[Principal, Depends(require(Permission.JOB_VIEW_ALL))],
    job_status: Annotated[JobStatus | None, Query(alias="status")] = None,
    category_id: UUID | None = None,
    created_by: UUID | None = None,
    include_deleted: bool = False,
    page: Annotated[int, Query(ge=1)] = 1,
    per_page: Annotated[int, Query(ge=1, le=100)] = 20,
) -> Paginated[JobAdmin]:
    result = await service.list_admin(
        AdminJobFilters(
            status=job_status,
            category_id=category_id,
            created_by=created_by,
            include_deleted=include_deleted,
        ),
        page=page,
        per_page=per_page,
    )
    return paginate_jobs(result, admin=True)


# --- bulk operations ------------------------------------------------------
#
# Registered above the `/{job_id}` routes. FastAPI matches in declaration order,
# and while `job_id` is typed as a UUID — so `/bulk/...` would fail validation
# rather than being mistaken for a listing — relying on a 422 to disambiguate a
# route is a subtlety that outlives whoever knew about it. Ordering makes it
# unambiguous.
#
# Both carry JOB_BULK *in addition to* the permission for the single-listing
# equivalent. Holding JOB_DELETE means an admin may remove a listing they are
# looking at; it does not by itself mean they may remove seven hundred they are
# not. JOB_BULK is held by super admins and admins, and not by editors.


@router.post(
    "/bulk/purge-expired",
    response_model=BulkPurgeResult,
    summary="Permanently delete every expired listing",
)
async def purge_expired_jobs(
    request: Request,
    service: ServiceDep,
    principal: Annotated[
        Principal, Depends(require(Permission.JOB_DELETE, Permission.JOB_BULK))
    ],
) -> BulkPurgeResult:
    """Hard delete, and there is no undo.

    Unlike `DELETE /{job_id}`, which sets `deleted_at` and leaves the row for
    reports and analytics to reference, this removes the rows outright. Reports
    filed against them, their generated share cards and their per-job analytics
    rollups cascade away with them; raw analytics events survive with their
    `job_id` nulled, so totals stay intact and per-listing attribution does not.
    """
    result = await service.purge_expired(principal=principal, ip_hash=_ip(request))
    await service.session.commit()
    return BulkPurgeResult(**result)


@router.post(
    "/bulk/publish-drafts",
    response_model=BulkPublishResult,
    summary="Publish every draft listing",
)
async def publish_draft_jobs(
    request: Request,
    service: ServiceDep,
    principal: Annotated[
        Principal, Depends(require(Permission.JOB_PUBLISH, Permission.JOB_BULK))
    ],
) -> BulkPublishResult:
    """Drafts only — expired listings are left alone.

    Publishing an expired listing would be reversed the same night by the
    scheduled `expire_due` task, which re-expires anything live whose
    `expiry_date` has passed.
    """
    result = await service.publish_drafts(principal=principal, ip_hash=_ip(request))
    await service.session.commit()
    return BulkPublishResult(**result)


@router.get("/{job_id}", response_model=JobAdmin, summary="One listing, editorial view")
async def get_job(
    job_id: UUID,
    service: ServiceDep,
    _: Annotated[Principal, Depends(require(Permission.JOB_VIEW_ALL))],
) -> JobAdmin:
    return job_admin(await service.get_admin(job_id))


@router.post(
    "",
    response_model=JobAdmin,
    status_code=status.HTTP_201_CREATED,
    summary="Create a listing",
    responses={
        403: {"description": "Publishing on create requires JOB_PUBLISH"},
        409: {"description": "Slug conflict"},
        422: {"description": "Unknown category, location, source or company"},
    },
)
async def create_job(
    payload: JobCreate,
    request: Request,
    response: Response,
    service: ServiceDep,
    principal: Annotated[Principal, Depends(require(Permission.JOB_CREATE))],
) -> JobAdmin:
    data = payload.model_dump(exclude_unset=False)
    # Pydantic URL types are not what SQLAlchemy wants to persist.
    for url_field in ("apply_url", "company_logo", "company_website"):
        if data.get(url_field) is not None:
            data[url_field] = str(data[url_field])

    try:
        created = await service.create(data, principal=principal, ip_hash=_ip(request))
        await service.session.commit()
    except IntegrityError as exc:
        await service.session.rollback()
        await handle_integrity_error(exc)
        raise

    # Re-read so the response carries the eager-loaded relations.
    job = await service.get_admin(created.id)
    response.headers["Location"] = f"/api/v1/admin/jobs/{job.id}"
    return job_admin(job)


@router.patch(
    "/{job_id}",
    response_model=JobAdmin,
    summary="Partially update a listing",
    responses={409: {"description": "X-Expected-Version mismatch"}},
)
async def update_job(
    job_id: UUID,
    payload: JobUpdate,
    request: Request,
    service: ServiceDep,
    principal: Annotated[Principal, Depends(require(Permission.JOB_EDIT))],
    expected_version: Annotated[int | None, Header(alias="X-Expected-Version")] = None,
    if_match: Annotated[int | None, Header(alias="If-Match")] = None,
) -> JobAdmin:
    """The version last read, so a concurrent edit is rejected rather than
    silently overwritten.

    Carried in `X-Expected-Version` rather than `If-Match`. `If-Match` is a
    standard conditional header, which means any cache between the browser and
    this process is entitled to evaluate it against an entity-tag of its own and
    answer `412 Precondition Failed` without forwarding the request — which is
    what Vercel's edge did to every update from the deployed admin, while
    localhost worked because nothing sat in between. A bare version number is
    not a valid entity-tag either.

    `If-Match` is still read, so an existing API client does not break."""
    changes = payload.model_dump(exclude_unset=True)
    for url_field in ("apply_url", "company_logo", "company_website"):
        if changes.get(url_field) is not None:
            changes[url_field] = str(changes[url_field])

    await service.update(
        job_id,
        changes,
        principal=principal,
        expected_version=expected_version if expected_version is not None else if_match,
        ip_hash=_ip(request),
    )
    await service.session.commit()
    # Re-read so the response reflects committed state with relations loaded.
    return job_admin(await service.get_admin(job_id))


@router.delete(
    "/{job_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Soft-delete a listing",
)
async def delete_job(
    job_id: UUID,
    request: Request,
    service: ServiceDep,
    principal: Annotated[Principal, Depends(require(Permission.JOB_DELETE))],
) -> Response:
    """Soft delete. Reports and historic analytics still reference this row,
    and the slug is released for reuse."""
    await service.delete(job_id, principal=principal, ip_hash=_ip(request))
    await service.session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{job_id}/publish", response_model=JobAdmin, summary="Publish a listing")
async def publish_job(
    job_id: UUID,
    request: Request,
    service: ServiceDep,
    principal: Annotated[Principal, Depends(require(Permission.JOB_PUBLISH))],
) -> JobAdmin:
    await service.publish(job_id, principal=principal, ip_hash=_ip(request))
    await service.session.commit()
    return job_admin(await service.get_admin(job_id))


@router.post("/{job_id}/expire", response_model=JobAdmin, summary="Expire a listing")
async def expire_job(
    job_id: UUID,
    payload: JobExpireRequest,
    request: Request,
    service: ServiceDep,
    principal: Annotated[Principal, Depends(require(Permission.JOB_EXPIRE))],
) -> JobAdmin:
    await service.expire(job_id, principal=principal, reason=payload.reason, ip_hash=_ip(request))
    await service.session.commit()
    return job_admin(await service.get_admin(job_id))


@router.post("/{job_id}/verify", response_model=JobAdmin, summary="Verify or unverify")
async def verify_job(
    job_id: UUID,
    payload: JobVerifyRequest,
    request: Request,
    service: ServiceDep,
    principal: Annotated[Principal, Depends(require(Permission.JOB_VERIFY))],
) -> JobAdmin:
    await service.set_verified(job_id, payload.verified, principal=principal, ip_hash=_ip(request))
    await service.session.commit()
    return job_admin(await service.get_admin(job_id))


@router.post("/{job_id}/feature", response_model=JobAdmin, summary="Feature or unfeature")
async def feature_job(
    job_id: UUID,
    payload: JobFeatureRequest,
    request: Request,
    service: ServiceDep,
    principal: Annotated[Principal, Depends(require(Permission.JOB_FEATURE))],
) -> JobAdmin:
    await service.set_featured(
        job_id,
        payload.featured,
        principal=principal,
        until=payload.until,
        ip_hash=_ip(request),
    )
    await service.session.commit()
    return job_admin(await service.get_admin(job_id))
