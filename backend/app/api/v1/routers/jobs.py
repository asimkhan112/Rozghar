"""Public job listings.

Anonymous, cacheable, and restricted to published listings. Search is
deliberately absent — filters only until Milestone 5 adds the tsvector.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Path, Query

from app.api.v1.deps import DbSession
from app.api.v1.mappers import job_detail, job_summary, paginate_jobs
from app.core.enums import EmploymentType, ExperienceLevel, WorkType
from app.repositories.job_repo import PUBLIC_SORTS, JobFilters
from app.schemas.common import Paginated, SearchMeta
from app.schemas.job import JobDetail, JobSummary
from app.services.job_service import JobService
from app.services.search_service import SearchService

router = APIRouter(tags=["jobs"])

SortOption = Literal["recent", "salary_desc", "salary_asc", "title"]


def job_service(session: DbSession) -> JobService:
    return JobService(session)


JobServiceDep = Annotated[JobService, Depends(job_service)]


def search_service(session: DbSession) -> SearchService:
    return SearchService(session)


SearchServiceDep = Annotated[SearchService, Depends(search_service)]


@router.get(
    "/jobs",
    response_model=Paginated[JobSummary],
    summary="Browse published listings",
)
async def list_jobs(
    service: JobServiceDep,
    search: SearchServiceDep,
    q: Annotated[str | None, Query(max_length=120, description="Full-text query")] = None,
    session_id: Annotated[UUID | None, Query(description="Anonymous session, for search telemetry")] = None,
    category: Annotated[str | None, Query(max_length=160)] = None,
    location: Annotated[str | None, Query(max_length=160)] = None,
    work_type: WorkType | None = None,
    employment_type: EmploymentType | None = None,
    experience: ExperienceLevel | None = None,
    featured: bool | None = None,
    verified: bool | None = None,
    salary_min: Annotated[Decimal | None, Query(ge=0)] = None,
    posted_within_days: Annotated[int | None, Query(ge=1, le=365)] = None,
    sort: SortOption = "recent",
    page: Annotated[int, Query(ge=1)] = 1,
    per_page: Annotated[int, Query(ge=1, le=50)] = 20,
) -> Paginated[JobSummary]:
    """Filters combine with AND. Unknown category or location slugs simply
    return no results rather than erroring — a stale bookmark should show an
    empty list, not a failure."""
    filters = JobFilters(
        category_slug=category,
        location_slug=location,
        work_type=work_type,
        employment_type=employment_type,
        experience_level=experience,
        featured=featured,
        verified=verified,
        salary_min=salary_min,
        posted_within_days=posted_within_days,
    )

    if q and q.strip():
        # Relevance ordering is only meaningful with a query; sort is ignored.
        outcome = await search.search(
            q, filters, page=page, per_page=per_page, session_id=session_id
        )
        await search.session.commit()  # persist the search log
        total_pages = (outcome.total + per_page - 1) // per_page if per_page else 0
        return Paginated[JobSummary](
            items=[job_summary(j) for j in outcome.items],
            page=page,
            per_page=per_page,
            total=outcome.total,
            total_pages=total_pages,
            has_more=page * per_page < outcome.total,
            search=SearchMeta(
                query=outcome.normalised_query,
                strategy=outcome.strategy.value,
                degraded=outcome.degraded,
                response_ms=outcome.response_ms,
            ),
        )

    result = await service.list_public(
        filters,
        sort=sort if sort in PUBLIC_SORTS else "recent",
        page=page,
        per_page=per_page,
    )
    return paginate_jobs(result)


@router.get(
    "/jobs/{slug}",
    response_model=JobDetail,
    summary="One listing, with related roles",
    responses={
        404: {"description": "No listing has ever existed at this address"},
        410: {"description": "The listing existed and is no longer available"},
    },
)
async def get_job(
    service: JobServiceDep,
    slug: Annotated[str, Path(max_length=160)],
) -> JobDetail:
    job, related = await service.get_public(slug)
    return job_detail(job, related)
