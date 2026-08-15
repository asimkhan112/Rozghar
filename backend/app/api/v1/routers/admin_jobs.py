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
    for url_field in ("apply_url", "company_logo"):
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
    responses={409: {"description": "If-Match version mismatch"}},
)
async def update_job(
    job_id: UUID,
    payload: JobUpdate,
    request: Request,
    service: ServiceDep,
    principal: Annotated[Principal, Depends(require(Permission.JOB_EDIT))],
    if_match: Annotated[int | None, Header(alias="If-Match")] = None,
) -> JobAdmin:
    """`If-Match` carries the version last read. When supplied, a concurrent
    edit is rejected rather than silently overwritten."""
    changes = payload.model_dump(exclude_unset=True)
    for url_field in ("apply_url", "company_logo"):
        if changes.get(url_field) is not None:
            changes[url_field] = str(changes[url_field])

    await service.update(
        job_id,
        changes,
        principal=principal,
        expected_version=if_match,
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
