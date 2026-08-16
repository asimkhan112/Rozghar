"""Autocomplete endpoints.

Two of them, and the split is a security boundary rather than a convenience.
The public endpoint may only ever see published listings; the admin one sees
drafts and expired rows and adds sources. Collapsing them into one route with a
flag would put "does this caller get to see unpublished job titles?" inside a
query parameter.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.api.v1.deps import CacheDep, DbSession, require
from app.core.permissions import Permission
from app.schemas.suggest import AdminSuggestResponse, SuggestResponse
from app.services.auth_service import Principal
from app.services.suggest_service import MIN_QUERY_LENGTH, SuggestService

router = APIRouter(tags=["search"])


def suggest_service(session: DbSession, cache: CacheDep) -> SuggestService:
    return SuggestService(session, cache)


SuggestServiceDep = Annotated[SuggestService, Depends(suggest_service)]

_Q = Annotated[
    str,
    Query(
        min_length=MIN_QUERY_LENGTH,
        max_length=120,
        description="What has been typed so far. Shorter than two characters is rejected.",
    ),
]


@router.get(
    "/search/suggest",
    response_model=SuggestResponse,
    summary="Grouped autocomplete suggestions",
)
async def suggest(service: SuggestServiceDep, q: _Q) -> SuggestResponse:
    """Suggestions across titles, companies, skills, locations and categories.

    Groups are always present, empty when nothing matched, so the client can
    render a stable layout without probing for keys.
    """
    return await service.suggest_public(q)


@router.get(
    "/admin/search/suggest",
    response_model=AdminSuggestResponse,
    summary="Grouped autocomplete across everything an editor can reach",
)
async def admin_suggest(
    service: SuggestServiceDep,
    q: _Q,
    _: Annotated[Principal, Depends(require(Permission.JOB_VIEW_ALL))],
) -> AdminSuggestResponse:
    """Adds sources, and includes drafts and expired listings in the job group."""
    return await service.suggest_admin(q)
