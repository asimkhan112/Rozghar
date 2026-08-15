"""Reference data: public reads and admin management.

Both live in one module because they are the same four small resources seen
from two angles. The public projections deliberately omit `config` on sources,
which will hold scraper credentials once ingestion exists.
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, status

from app.api.v1.deps import DbSession, client_ip, require
from app.core.permissions import Permission
from app.core.security import hash_ip
from app.schemas.common import Paginated
from app.schemas.company import CompanyCreate, CompanyDetail, CompanyRead, CompanyUpdate
from app.schemas.taxonomy import (
    CategoryCreate,
    CategoryDetail,
    CategoryRead,
    CategoryUpdate,
    LocationCreate,
    LocationDetail,
    LocationRead,
    LocationUpdate,
    SourceCreate,
    SourceDetail,
    SourceRead,
    SourceUpdate,
)
from app.services.auth_service import Principal
from app.services.taxonomy_service import (
    CategoryService,
    CompanyService,
    LocationService,
    SourceService,
)

public = APIRouter(tags=["reference"])
admin = APIRouter(prefix="/admin", tags=["admin:reference"])


def _ip(request: Request) -> str | None:
    return hash_ip(client_ip(request))


def categories(session: DbSession) -> CategoryService:
    return CategoryService(session)


def locations(session: DbSession) -> LocationService:
    return LocationService(session)


def sources(session: DbSession) -> SourceService:
    return SourceService(session)


def companies(session: DbSession) -> CompanyService:
    return CompanyService(session)


CategoryDep = Annotated[CategoryService, Depends(categories)]
LocationDep = Annotated[LocationService, Depends(locations)]
SourceDep = Annotated[SourceService, Depends(sources)]
CompanyDep = Annotated[CompanyService, Depends(companies)]

Taxonomy = Annotated[Principal, Depends(require(Permission.TAXONOMY_MANAGE))]
SourceAdmin = Annotated[Principal, Depends(require(Permission.SOURCE_MANAGE))]


# --- public ---------------------------------------------------------------


@public.get("/categories", response_model=list[CategoryRead], summary="Active categories")
async def list_categories(service: CategoryDep) -> list[CategoryRead]:
    """Unpaginated — the set is bounded and rendered whole by the homepage."""
    return [CategoryRead.model_validate(c) for c in await service.list_public()]


@public.get("/locations", response_model=list[LocationRead], summary="Active locations")
async def list_locations(
    service: LocationDep,
    country: Annotated[str | None, Query(min_length=2, max_length=2)] = None,
) -> list[LocationRead]:
    return [LocationRead.model_validate(loc) for loc in await service.list_public(country=country)]


@public.get("/sources", response_model=list[SourceRead], summary="Active sources")
async def list_sources(service: SourceDep) -> list[SourceRead]:
    return [SourceRead.model_validate(s) for s in await service.list_public()]


# --- admin: categories ----------------------------------------------------


@admin.get("/categories", response_model=list[CategoryDetail], summary="All categories")
async def admin_list_categories(service: CategoryDep, _: Taxonomy) -> list[CategoryDetail]:
    return [CategoryDetail.model_validate(c) for c in await service.list_all()]


@admin.post(
    "/categories",
    response_model=CategoryDetail,
    status_code=status.HTTP_201_CREATED,
    responses={409: {"description": "Slug already in use"}},
)
async def create_category(
    payload: CategoryCreate, request: Request, service: CategoryDep, principal: Taxonomy
) -> CategoryDetail:
    entity = await service.create(
        payload.model_dump(exclude_unset=True), principal=principal, ip_hash=_ip(request)
    )
    await service.session.commit()
    return CategoryDetail.model_validate(entity)


@admin.patch(
    "/categories/{category_id}",
    response_model=CategoryDetail,
    responses={409: {"description": "Deactivating a category that still has listings"}},
)
async def update_category(
    category_id: UUID,
    payload: CategoryUpdate,
    request: Request,
    service: CategoryDep,
    principal: Taxonomy,
) -> CategoryDetail:
    entity = await service.update(
        category_id,
        payload.model_dump(exclude_unset=True),
        principal=principal,
        ip_hash=_ip(request),
    )
    await service.session.commit()
    return CategoryDetail.model_validate(entity)


# --- admin: locations -----------------------------------------------------


@admin.post(
    "/locations",
    response_model=LocationDetail,
    status_code=status.HTTP_201_CREATED,
    responses={422: {"description": "A non-remote location must name a city"}},
)
async def create_location(
    payload: LocationCreate, request: Request, service: LocationDep, principal: Taxonomy
) -> LocationDetail:
    entity = await service.create(
        payload.model_dump(exclude_unset=True), principal=principal, ip_hash=_ip(request)
    )
    await service.session.commit()
    return LocationDetail.model_validate(entity)


@admin.patch("/locations/{location_id}", response_model=LocationDetail)
async def update_location(
    location_id: UUID,
    payload: LocationUpdate,
    request: Request,
    service: LocationDep,
    principal: Taxonomy,
) -> LocationDetail:
    entity = await service.update(
        location_id,
        payload.model_dump(exclude_unset=True),
        principal=principal,
        ip_hash=_ip(request),
    )
    await service.session.commit()
    return LocationDetail.model_validate(entity)


# --- admin: sources -------------------------------------------------------


@admin.post("/sources", response_model=SourceDetail, status_code=status.HTTP_201_CREATED)
async def create_source(
    payload: SourceCreate, request: Request, service: SourceDep, principal: SourceAdmin
) -> SourceDetail:
    entity = await service.create(
        payload.model_dump(exclude_unset=True), principal=principal, ip_hash=_ip(request)
    )
    await service.session.commit()
    return SourceDetail.model_validate(entity)


@admin.patch(
    "/sources/{source_id}",
    response_model=SourceDetail,
    responses={409: {"description": "The manual source cannot be deactivated"}},
)
async def update_source(
    source_id: UUID,
    payload: SourceUpdate,
    request: Request,
    service: SourceDep,
    principal: SourceAdmin,
) -> SourceDetail:
    entity = await service.update(
        source_id,
        payload.model_dump(exclude_unset=True),
        principal=principal,
        ip_hash=_ip(request),
    )
    await service.session.commit()
    return SourceDetail.model_validate(entity)


# --- admin: companies -----------------------------------------------------


@admin.get("/companies", response_model=Paginated[CompanyRead], summary="Employers")
async def admin_list_companies(
    service: CompanyDep,
    _: Taxonomy,
    page: Annotated[int, Query(ge=1)] = 1,
    per_page: Annotated[int, Query(ge=1, le=100)] = 20,
) -> Paginated[CompanyRead]:
    items, total = await service.list_paginated(page=page, per_page=per_page)
    total_pages = (total + per_page - 1) // per_page if per_page else 0
    return Paginated[CompanyRead](
        items=[CompanyRead.model_validate(c) for c in items],
        page=page,
        per_page=per_page,
        total=total,
        total_pages=total_pages,
        has_more=page * per_page < total,
    )


@admin.post("/companies", response_model=CompanyDetail, status_code=status.HTTP_201_CREATED)
async def create_company(
    payload: CompanyCreate, request: Request, service: CompanyDep, principal: Taxonomy
) -> CompanyDetail:
    entity = await service.create(
        payload.model_dump(exclude_unset=True), principal=principal, ip_hash=_ip(request)
    )
    await service.session.commit()
    return CompanyDetail.model_validate(entity)


@admin.patch("/companies/{company_id}", response_model=CompanyDetail)
async def update_company(
    company_id: UUID,
    payload: CompanyUpdate,
    request: Request,
    service: CompanyDep,
    principal: Taxonomy,
) -> CompanyDetail:
    entity = await service.update(
        company_id,
        payload.model_dump(exclude_unset=True),
        principal=principal,
        ip_hash=_ip(request),
    )
    await service.session.commit()
    return CompanyDetail.model_validate(entity)
