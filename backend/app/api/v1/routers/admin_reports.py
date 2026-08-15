"""Report moderation.

One PATCH rather than an endpoint per verb, unlike admin jobs. The difference
is real: a job's lifecycle actions carry distinct permissions and distinct
side effects, whereas every report decision is the same permission acting on
the same two columns. Splitting them would be ceremony. The audit trail still
records a distinct verb per destination state.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request

from app.api.v1.deps import DbSession, client_ip, require
from app.api.v1.mappers import paginate_reports, report_read
from app.core.enums import ReportReason, ReportStatus
from app.core.permissions import Permission
from app.core.security import hash_ip
from app.repositories.report_repo import ReportFilters
from app.schemas.common import Paginated
from app.schemas.report import ReportRead, ReportUpdate
from app.services.auth_service import Principal
from app.services.report_service import ReportService

router = APIRouter(prefix="/admin/reports", tags=["admin:reports"])


def report_service(session: DbSession) -> ReportService:
    return ReportService(session)


ServiceDep = Annotated[ReportService, Depends(report_service)]


@router.get("", response_model=Paginated[ReportRead], summary="The moderation queue")
async def list_reports(
    service: ServiceDep,
    _: Annotated[Principal, Depends(require(Permission.REPORT_VIEW))],
    report_status: Annotated[ReportStatus | None, Query(alias="status")] = None,
    reason: ReportReason | None = None,
    job_id: UUID | None = None,
    created_from: datetime | None = None,
    created_to: datetime | None = None,
    page: Annotated[int, Query(ge=1)] = 1,
    per_page: Annotated[int, Query(ge=1, le=100)] = 20,
) -> Paginated[ReportRead]:
    """Newest first. Filtering by `status=open` is the working view and is
    served directly by `ix_reports_status_created_at`."""
    result = await service.list_queue(
        ReportFilters(
            status=report_status,
            reason=reason,
            job_id=job_id,
            created_from=created_from,
            created_to=created_to,
        ),
        page=page,
        per_page=per_page,
    )
    return paginate_reports(result)


@router.get("/{report_id}", response_model=ReportRead, summary="One report")
async def get_report(
    report_id: UUID,
    service: ServiceDep,
    _: Annotated[Principal, Depends(require(Permission.REPORT_VIEW))],
) -> ReportRead:
    return report_read(await service.get(report_id))


@router.patch(
    "/{report_id}",
    response_model=ReportRead,
    summary="Move a report through the workflow",
    responses={
        403: {"description": "Moderating requires REPORT_RESOLVE"},
        404: {"description": "No such report"},
        422: {"description": "Transition not allowed from the current state"},
    },
)
async def update_report(
    report_id: UUID,
    payload: ReportUpdate,
    request: Request,
    service: ServiceDep,
    principal: Annotated[Principal, Depends(require(Permission.REPORT_RESOLVE))],
) -> ReportRead:
    """Resolving or dismissing requires a note, enforced by the schema, the
    service and a database CHECK. Three layers is not redundancy here — the
    note is the only record of *why* a listing was left alone, and a queue full
    of unexplained dismissals is indistinguishable from a queue nobody read."""
    report = await service.moderate(
        report_id,
        payload.model_dump(exclude_unset=True),
        principal=principal,
        ip_hash=hash_ip(client_ip(request)),
    )
    await service.session.commit()
    return report_read(report)
