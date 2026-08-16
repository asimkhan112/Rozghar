"""AI drafting endpoints.

Both return a draft and persist nothing. The admin reviews it against what they
had and decides — which is a product requirement and also the only defensible
design: a model that can occasionally soften a requirement or invent a benefit
must not be able to publish that unreviewed.

Rate limited per admin rather than per IP: these calls cost money, and an
office behind one NAT should not share a budget.
"""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, Request

from app.api.v1.deps import DbSession, get_redis, require
from app.core.exceptions import RateLimited
from app.core.permissions import Permission
from app.core.rate_limit import AI_DRAFT, RateLimiter
from app.schemas.ai import AIDraft, GenerateRequest, RewriteRequest
from app.services.ai_service import AIService, JobFacts
from app.services.auth_service import Principal

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/ai", tags=["admin:ai"])


def ai_service() -> AIService:
    return AIService()


ServiceDep = Annotated[AIService, Depends(ai_service)]
#: Drafting a listing body is part of writing one. An editor who may create a
#: job may draft its text; nothing here can publish.
DrafterDep = Annotated[Principal, Depends(require(Permission.JOB_CREATE))]


async def _check_quota(request: Request, principal: Principal) -> None:
    """Per-admin hourly budget.

    Fails open when Redis is down, like every other limiter here — a cache
    outage should not take away a tool, and the spend ceiling is bounded by the
    API key's own limits regardless.
    """
    limiter = RateLimiter(await get_redis(request))
    decision = await limiter.check(AI_DRAFT, str(principal.admin_id))
    if not decision.allowed:
        raise RateLimited(
            decision.retry_after,
            "You have reached the hourly limit for AI drafting. "
            "Try again later, or write this one by hand.",
        )


@router.post(
    "/rewrite",
    response_model=AIDraft,
    summary="Rewrite a description, preserving its meaning",
    responses={
        422: {"description": "Too little text to work with, or the assistant declined"},
        429: {"description": "Hourly drafting limit reached"},
        502: {"description": "The AI service failed"},
        503: {"description": "AI assistance is not configured on this server"},
    },
)
async def rewrite(
    payload: RewriteRequest,
    request: Request,
    service: ServiceDep,
    principal: DrafterDep,
    _session: DbSession,
) -> AIDraft:
    """Improves grammar, readability and duplication without changing meaning.

    Skills, salary figures, requirements and conditions are preserved — the
    instruction is explicit about it, and the response is reviewed before it
    replaces anything.
    """
    await _check_quota(request, principal)
    draft = await service.rewrite(payload.description)
    return AIDraft.model_validate(draft.model_dump())


@router.post(
    "/generate",
    response_model=AIDraft,
    summary="Draft a description from the structured job details",
    responses={
        422: {"description": "The assistant declined this request"},
        429: {"description": "Hourly drafting limit reached"},
        502: {"description": "The AI service failed"},
        503: {"description": "AI assistance is not configured on this server"},
    },
)
async def generate(
    payload: GenerateRequest,
    request: Request,
    service: ServiceDep,
    principal: DrafterDep,
    _session: DbSession,
) -> AIDraft:
    """Writes a listing body from the fields the editor has already entered.

    Grounded in those fields only. A listing with no salary produces no salary
    sentence, and a listing with no benefits produces an empty benefits list —
    inventing either is the failure mode this feature has to avoid.
    """
    await _check_quota(request, principal)
    draft = await service.generate(
        JobFacts(
            title=payload.title,
            company=payload.company,
            location=payload.location,
            employment_type=payload.employment_type,
            experience_level=payload.experience_level,
            salary=payload.salary,
            skills=tuple(payload.skills),
        )
    )
    return AIDraft.model_validate(draft.model_dump())
