"""Permission catalogue — the single source of truth.

The `permissions` table exists so the admin UI can render a role editor, but
this enum is the authority. A migration seeds the table from here, and
`app.db.validate` asserts on startup that the two still agree. If the database
is allowed to be the authority, a permission string can silently drift from
what the code actually checks and nothing catches it.
"""

from enum import StrEnum


class PermissionGroup(StrEnum):
    JOBS = "jobs"
    TAXONOMY = "taxonomy"
    REPORTS = "reports"
    ANALYTICS = "analytics"
    ADMIN = "admin"


class Permission(StrEnum):
    # --- jobs ------------------------------------------------------------
    JOB_VIEW = "JOB_VIEW"
    JOB_VIEW_ALL = "JOB_VIEW_ALL"
    JOB_CREATE = "JOB_CREATE"
    JOB_EDIT = "JOB_EDIT"
    JOB_PUBLISH = "JOB_PUBLISH"
    JOB_VERIFY = "JOB_VERIFY"
    JOB_FEATURE = "JOB_FEATURE"
    JOB_EXPIRE = "JOB_EXPIRE"
    JOB_DELETE = "JOB_DELETE"
    JOB_BULK = "JOB_BULK"

    # --- taxonomy --------------------------------------------------------
    TAXONOMY_MANAGE = "TAXONOMY_MANAGE"
    SOURCE_MANAGE = "SOURCE_MANAGE"

    # --- reports ---------------------------------------------------------
    REPORT_VIEW = "REPORT_VIEW"
    REPORT_RESOLVE = "REPORT_RESOLVE"

    # --- analytics -------------------------------------------------------
    ANALYTICS_VIEW = "ANALYTICS_VIEW"
    ANALYTICS_EXPORT = "ANALYTICS_EXPORT"

    # --- administration --------------------------------------------------
    ADMIN_MANAGE = "ADMIN_MANAGE"
    ADMIN_ROLE_ASSIGN = "ADMIN_ROLE_ASSIGN"
    AUDIT_VIEW = "AUDIT_VIEW"
    SETTINGS_MANAGE = "SETTINGS_MANAGE"


#: Group and human description for every permission. Rendered by the role
#: editor, and seeded verbatim into the `permissions` table.
PERMISSION_METADATA: dict[Permission, tuple[PermissionGroup, str]] = {
    Permission.JOB_VIEW: (PermissionGroup.JOBS, "View published job listings"),
    Permission.JOB_VIEW_ALL: (PermissionGroup.JOBS, "View drafts and archived listings"),
    Permission.JOB_CREATE: (PermissionGroup.JOBS, "Create a job listing"),
    Permission.JOB_EDIT: (PermissionGroup.JOBS, "Edit a job listing"),
    Permission.JOB_PUBLISH: (PermissionGroup.JOBS, "Publish or unpublish a listing"),
    Permission.JOB_VERIFY: (PermissionGroup.JOBS, "Mark a listing as verified"),
    Permission.JOB_FEATURE: (PermissionGroup.JOBS, "Feature a listing on the homepage"),
    Permission.JOB_EXPIRE: (PermissionGroup.JOBS, "Expire a listing"),
    Permission.JOB_DELETE: (PermissionGroup.JOBS, "Delete a listing"),
    Permission.JOB_BULK: (PermissionGroup.JOBS, "Run bulk operations on listings"),
    Permission.TAXONOMY_MANAGE: (PermissionGroup.TAXONOMY, "Manage categories and locations"),
    Permission.SOURCE_MANAGE: (PermissionGroup.TAXONOMY, "Manage job sources"),
    Permission.REPORT_VIEW: (PermissionGroup.REPORTS, "View reported listings"),
    Permission.REPORT_RESOLVE: (PermissionGroup.REPORTS, "Resolve or dismiss reports"),
    Permission.ANALYTICS_VIEW: (PermissionGroup.ANALYTICS, "View analytics dashboards"),
    Permission.ANALYTICS_EXPORT: (PermissionGroup.ANALYTICS, "Export analytics data"),
    Permission.ADMIN_MANAGE: (PermissionGroup.ADMIN, "Create and manage admin accounts"),
    Permission.ADMIN_ROLE_ASSIGN: (PermissionGroup.ADMIN, "Assign roles to admins"),
    Permission.AUDIT_VIEW: (PermissionGroup.ADMIN, "View the audit log"),
    Permission.SETTINGS_MANAGE: (PermissionGroup.ADMIN, "Manage platform settings"),
}


class SystemRole(StrEnum):
    """Roles seeded by migration. Custom roles may be added at runtime."""

    SUPER_ADMIN = "super_admin"
    ADMIN = "admin"
    EDITOR = "editor"
    ANALYST = "analyst"


SYSTEM_ROLE_LABELS: dict[SystemRole, tuple[str, str]] = {
    SystemRole.SUPER_ADMIN: ("Super Admin", "Full control, including team management"),
    SystemRole.ADMIN: ("Admin", "Runs the product day to day"),
    SystemRole.EDITOR: ("Editor", "Drafts and revises listings; cannot publish"),
    SystemRole.ANALYST: ("Analyst", "Read-only access to reporting and analytics"),
}


#: Role → permission mapping. Mirrors the approved permissions matrix.
#: `JOB_EDIT` and `JOB_EXPIRE` are ownership-scoped for editors — the grant is
#: here, the "own rows only" narrowing is enforced in the service layer because
#: it needs the entity.
ROLE_PERMISSIONS: dict[SystemRole, frozenset[Permission]] = {
    SystemRole.SUPER_ADMIN: frozenset(Permission),
    SystemRole.ADMIN: frozenset(
        {
            Permission.JOB_VIEW,
            Permission.JOB_VIEW_ALL,
            Permission.JOB_CREATE,
            Permission.JOB_EDIT,
            Permission.JOB_PUBLISH,
            Permission.JOB_VERIFY,
            Permission.JOB_FEATURE,
            Permission.JOB_EXPIRE,
            Permission.JOB_DELETE,
            Permission.JOB_BULK,
            Permission.TAXONOMY_MANAGE,
            Permission.SOURCE_MANAGE,
            Permission.REPORT_VIEW,
            Permission.REPORT_RESOLVE,
            Permission.ANALYTICS_VIEW,
            Permission.ANALYTICS_EXPORT,
            Permission.AUDIT_VIEW,
        }
    ),
    SystemRole.EDITOR: frozenset(
        {
            Permission.JOB_VIEW,
            Permission.JOB_VIEW_ALL,
            Permission.JOB_CREATE,
            Permission.JOB_EDIT,
            Permission.JOB_EXPIRE,
            Permission.REPORT_VIEW,
            Permission.REPORT_RESOLVE,
        }
    ),
    SystemRole.ANALYST: frozenset(
        {
            Permission.JOB_VIEW,
            Permission.REPORT_VIEW,
            Permission.ANALYTICS_VIEW,
            Permission.ANALYTICS_EXPORT,
        }
    ),
}
