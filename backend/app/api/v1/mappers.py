"""ORM → schema projection.

Kept out of the routers so the same job renders identically wherever it
appears, and out of the schemas so Pydantic models stay free of domain logic.
`badge` is computed here because it is derived from three columns, not stored.
"""

from __future__ import annotations

from app.models.job import Job
from app.models.report import Report
from app.schemas.common import Paginated
from app.schemas.job import JobAdmin, JobDetail, JobSummary
from app.schemas.report import ReportJobRef, ReportRead
from app.schemas.taxonomy import CategoryRead, LocationRead, SourceRead
from app.services.job_service import JobPage, compute_badge
from app.services.report_service import ReportPage


def job_summary(job: Job) -> JobSummary:
    return JobSummary(
        id=job.id,
        slug=job.slug,
        title=job.title,
        company_name=job.company_name,
        company_logo=job.company_logo,
        logo_palette=job.logo_palette,
        category=CategoryRead.model_validate(job.category),
        location=LocationRead.model_validate(job.location),
        work_type=job.work_type,
        employment_type=job.employment_type,
        experience_level=job.experience_level,
        experience_min_years=job.experience_min_years,
        experience_max_years=job.experience_max_years,
        badge=compute_badge(job),
        featured=job.featured,
        verified=job.verified,
        published_at=job.published_at,
        expiry_date=job.expiry_date,
    )


def job_detail(job: Job, related: list[Job] | None = None) -> JobDetail:
    return JobDetail(
        **job_summary(job).model_dump(),
        description=job.description,
        requirements=list(job.requirements or []),
        responsibilities=list(job.responsibilities or []),
        benefits=list(job.benefits or []),
        apply_url=job.apply_url,
        source=SourceRead.model_validate(job.source),
        related=[job_summary(j) for j in (related or [])],
    )


def job_admin(job: Job) -> JobAdmin:
    """Adds editorial state that must never appear on a public response."""
    return JobAdmin(
        **job_detail(job).model_dump(),
        status=job.status,
        featured_until=job.featured_until,
        verified_at=job.verified_at,
        verified_by=job.verified_by,
        view_count=job.view_count,
        apply_click_count=job.apply_click_count,
        save_count=job.save_count,
        created_by=job.created_by,
        updated_by=job.updated_by,
        version=job.version,
        created_at=job.created_at,
        updated_at=job.updated_at,
        deleted_at=job.deleted_at,
    )


def paginate_jobs(page: JobPage, *, admin: bool = False) -> Paginated:
    projector = job_admin if admin else job_summary
    return Paginated(
        items=[projector(j) for j in page.items],
        page=page.page,
        per_page=page.per_page,
        total=page.total,
        total_pages=page.total_pages,
        has_more=page.has_more,
    )


def report_read(report: Report) -> ReportRead:
    """Moderation row.

    `reporter_ip_hash` and `session_id` are on the model and never appear here.
    Both are abuse-control identifiers, not case detail, and a moderator has no
    reason to see either — which is the whole argument for building the
    response explicitly rather than validating the ORM object wholesale.
    """
    return ReportRead(
        id=report.id,
        reason=report.reason,
        comment=report.comment,
        status=report.status,
        resolution_note=report.resolution_note,
        resolved_by=report.resolved_by,
        resolved_at=report.resolved_at,
        created_at=report.created_at,
        job=ReportJobRef.model_validate(report.job),
    )


def paginate_reports(page: ReportPage) -> Paginated[ReportRead]:
    return Paginated[ReportRead](
        items=[report_read(r) for r in page.items],
        page=page.page,
        per_page=page.per_page,
        total=page.total,
        total_pages=page.total_pages,
        has_more=page.has_more,
    )
