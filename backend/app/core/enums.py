"""Domain enumerations.

Each of these is mirrored by a PostgreSQL enum type of the same name. Values
are snake_case because they travel over the wire; display labels belong to the
frontend design system, not to the database.

Lives in `core` rather than `models` so schemas can import it without reaching
into the persistence layer.
"""

from enum import StrEnum
from typing import Any

from sqlalchemy import Enum as SAEnum


class WorkType(StrEnum):
    REMOTE = "remote"
    ON_SITE = "on_site"
    HYBRID = "hybrid"


class EmploymentType(StrEnum):
    FULL_TIME = "full_time"
    PART_TIME = "part_time"
    CONTRACT = "contract"
    INTERNSHIP = "internship"


class ExperienceLevel(StrEnum):
    INTERN = "intern"
    ENTRY = "entry"
    MID = "mid"
    SENIOR = "senior"
    LEAD = "lead"
    EXECUTIVE = "executive"


class JobStatus(StrEnum):
    DRAFT = "draft"
    SCHEDULED = "scheduled"
    PUBLISHED = "published"
    EXPIRED = "expired"
    ARCHIVED = "archived"


class SalaryPeriod(StrEnum):
    HOUR = "hour"
    MONTH = "month"
    YEAR = "year"


class SourceType(StrEnum):
    MANUAL = "manual"
    SCRAPER = "scraper"
    PARTNER = "partner"
    COMMUNITY = "community"


class ReportReason(StrEnum):
    BROKEN_LINK = "broken_link"
    SUSPICIOUS = "suspicious"
    EXPIRED = "expired"
    INCORRECT_INFORMATION = "incorrect_information"
    DUPLICATE = "duplicate"
    OTHER = "other"


class ReportStatus(StrEnum):
    OPEN = "open"
    UNDER_REVIEW = "under_review"
    RESOLVED = "resolved"
    DISMISSED = "dismissed"


class EventType(StrEnum):
    """Behavioural events.

    `job_saved` and `filter_used` predate the rest and are kept: the first
    drives `jobs.save_count`, the second answers "which filters do people
    actually use", and both are already instrumented. Removing them to tidy the
    list would delete working measurement.
    """

    JOB_VIEW = "job_view"
    APPLY_CLICK = "apply_click"
    SEARCH = "search"
    SHARE = "share"
    REPORT_CREATED = "report_created"
    SOURCE_CLICK = "source_click"
    JOB_SAVED = "job_saved"
    FILTER_USED = "filter_used"


class DeviceType(StrEnum):
    MOBILE = "mobile"
    TABLET = "tablet"
    DESKTOP = "desktop"


class SessionRevokeReason(StrEnum):
    LOGOUT = "logout"
    ROTATED = "rotated"
    REUSE_DETECTED = "reuse_detected"
    PASSWORD_CHANGE = "password_change"
    ADMIN_ACTION = "admin_action"


#: Terminal report states — a resolution note and resolver are mandatory here.
TERMINAL_REPORT_STATUSES = frozenset({ReportStatus.RESOLVED, ReportStatus.DISMISSED})

#: Every PostgreSQL enum type this application owns, in creation order.
PG_ENUMS: dict[str, type[StrEnum]] = {
    "work_type": WorkType,
    "employment_type": EmploymentType,
    "experience_level": ExperienceLevel,
    "job_status": JobStatus,
    "salary_period": SalaryPeriod,
    "source_type": SourceType,
    "report_reason": ReportReason,
    "report_status": ReportStatus,
    "event_type": EventType,
    "device_type": DeviceType,
    "session_revoke_reason": SessionRevokeReason,
}


def pg_enum(enum_cls: type[StrEnum], name: str) -> Any:
    """Column type bound to an existing PostgreSQL enum.

    `values_callable` is not optional. SQLAlchemy persists the enum *member
    name* by default — `ROTATED` rather than `rotated` — which the database
    rejects because the type was created from the values. Every enum column
    must go through this helper.

    `create_type=False` because the types are created once by the initial
    migration, not implicitly per table.
    """
    return SAEnum(
        enum_cls,
        name=name,
        create_type=False,
        values_callable=lambda members: [m.value for m in members],
    )
