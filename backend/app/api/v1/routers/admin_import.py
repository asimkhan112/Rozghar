"""Importing listings from USAJOBS.

One endpoint, pressed by a person. There is no scheduler behind it on purpose:
every imported listing needs a human to publish it anyway, so a nightly job
would only ever be filling a queue nobody asked for that morning.

Requires JOB_CREATE — importing is creating listings, and nothing here can
publish one.
"""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, Request

from app.api.v1.deps import DbSession, client_ip, get_redis, require
from app.core.exceptions import RateLimited
from app.core.permissions import Permission
from app.core.rate_limit import AI_DRAFT, RateLimiter
from app.core.security import hash_ip
from app.schemas.ingest import ImportRun
from app.services.auth_service import Principal
from app.services.job_service import JobService
from app.services.usajobs_service import USAJobsImportService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/import", tags=["admin:import"])


def import_service(session: DbSession) -> USAJobsImportService:
    return USAJobsImportService(session, JobService(session))


ServiceDep = Annotated[USAJobsImportService, Depends(import_service)]
ImporterDep = Annotated[Principal, Depends(require(Permission.JOB_CREATE))]


@router.post(
    "/usajobs",
    response_model=ImportRun,
    summary="Fetch open federal listings and file them as drafts",
    responses={
        429: {"description": "Too many import runs this hour"},
        502: {"description": "The USAJOBS API could not be reached"},
        503: {"description": "Importing is not configured on this server"},
    },
)
async def import_usajobs(
    request: Request,
    service: ServiceDep,
    principal: ImporterDep,
) -> ImportRun:
    """Runs synchronously and returns a summary of what happened.

    Slow — a page of 250 announcements is 250 inserts — but honest: the admin
    who pressed the button sees the count it produced rather than a "started"
    message and a queue they have to go and check.

    Safe to press twice. Listings already imported are recognised by their
    USAJOBS id and skipped, so a second run creates nothing.
    """
    # Shares the AI drafting budget: both are per-admin ceilings on an action
    # that reaches out to a third party, and neither needs its own dial.
    limiter = RateLimiter(await get_redis(request))
    decision = await limiter.check(AI_DRAFT, f"import:{principal.admin_id}")
    if not decision.allowed:
        raise RateLimited(
            decision.retry_after,
            "You have reached the hourly limit for imports. Try again later.",
        )

    result = await service.run(principal=principal, ip_hash=hash_ip(client_ip(request)))
    return ImportRun.model_validate(result.as_dict())
