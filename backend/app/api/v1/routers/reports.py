"""Public report submission.

The only unauthenticated write in the API, and therefore the only endpoint an
adversary can reach without credentials. Every control that keeps it honest —
address hashing, per-session dedupe, the sliding window — lives behind it in
the service, so this file stays a thin translation of HTTP into a domain call.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request, status

from app.api.v1.deps import DbSession, client_ip
from app.core.security import hash_ip
from app.schemas.report import ReportCreate, ReportCreated
from app.services.report_service import ReportService

router = APIRouter(tags=["reports"])


def report_service(session: DbSession) -> ReportService:
    return ReportService(session)


ServiceDep = Annotated[ReportService, Depends(report_service)]


@router.post(
    "/reports",
    response_model=ReportCreated,
    status_code=status.HTTP_201_CREATED,
    summary="Report a problem with a listing",
    responses={
        404: {"description": "No such listing, or it was never published"},
        409: {"description": "You already have an open report on this listing"},
        422: {"description": "Validation failed"},
        429: {"description": "Too many reports from this connection"},
    },
)
async def create_report(
    payload: ReportCreate,
    request: Request,
    service: ServiceDep,
) -> ReportCreated:
    """Anonymous. `session_id` is optional but worth sending: with it a
    duplicate is caught precisely, by a unique index. Without it the fallback
    matches on the hashed address, which everyone behind one office NAT
    shares — still the right call, since the listing already has an open
    report either way, but less exact."""
    report = await service.submit(
        payload.model_dump(),
        ip_hash=hash_ip(client_ip(request)),
    )
    await service.session.commit()
    return ReportCreated(id=report.id, status=report.status)
