"""Startup consistency checks.

The `permissions` table exists so the admin UI can render a role editor. The
`Permission` enum is what the API actually gates on. If those two are allowed
to drift, a permission can be granted in the database that no code path checks,
or checked in code but absent from every role — and neither failure is visible
at runtime.

These checks run once during application startup and abort the process on
mismatch. Failing to boot is a better outcome than serving requests with an
authorisation model nobody can reason about.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.permissions import (
    PERMISSION_METADATA,
    ROLE_PERMISSIONS,
    Permission,
    SystemRole,
)
from app.models.rbac import Permission as PermissionModel
from app.models.rbac import Role as RoleModel


class PermissionSyncError(RuntimeError):
    """Raised when the database and the Permission enum disagree."""


@dataclass
class SyncReport:
    missing_in_db: set[str] = field(default_factory=set)
    unknown_in_db: set[str] = field(default_factory=set)
    metadata_mismatch: set[str] = field(default_factory=set)
    missing_roles: set[str] = field(default_factory=set)
    role_grant_mismatch: dict[str, str] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return not (
            self.missing_in_db
            or self.unknown_in_db
            or self.metadata_mismatch
            or self.missing_roles
            or self.role_grant_mismatch
        )

    def describe(self) -> str:
        lines: list[str] = []
        if self.missing_in_db:
            lines.append(
                f"  permissions in the enum but not in the database: "
                f"{', '.join(sorted(self.missing_in_db))}"
            )
        if self.unknown_in_db:
            lines.append(
                f"  permissions in the database but not in the enum: "
                f"{', '.join(sorted(self.unknown_in_db))}"
            )
        if self.metadata_mismatch:
            lines.append(
                f"  permissions whose group or description drifted: "
                f"{', '.join(sorted(self.metadata_mismatch))}"
            )
        if self.missing_roles:
            lines.append(f"  system roles not seeded: {', '.join(sorted(self.missing_roles))}")
        for role, detail in sorted(self.role_grant_mismatch.items()):
            lines.append(f"  role '{role}' grants do not match the code: {detail}")
        return "\n".join(lines)


async def check_permission_sync(session: AsyncSession) -> SyncReport:
    """Compare the database against the enum. Pure — raises nothing."""
    report = SyncReport()

    rows = (await session.execute(select(PermissionModel))).scalars().all()
    db_permissions = {row.key: row for row in rows}
    enum_keys = {p.value for p in Permission}

    report.missing_in_db = enum_keys - set(db_permissions)
    report.unknown_in_db = set(db_permissions) - enum_keys

    for permission, (group, description) in PERMISSION_METADATA.items():
        row = db_permissions.get(permission.value)
        if row is None:
            continue
        if row.group_name != group.value or row.description != description:
            report.metadata_mismatch.add(permission.value)

    role_rows = (await session.execute(select(RoleModel))).scalars().all()
    db_roles = {row.key: row for row in role_rows}

    for system_role, expected in ROLE_PERMISSIONS.items():
        row = db_roles.get(system_role.value)
        if row is None:
            report.missing_roles.add(system_role.value)
            continue

        granted = {p.key for p in row.permissions}
        expected_keys = {p.value for p in expected}
        if granted != expected_keys:
            missing = expected_keys - granted
            extra = granted - expected_keys
            parts = []
            if missing:
                parts.append(f"missing {sorted(missing)}")
            if extra:
                parts.append(f"unexpected {sorted(extra)}")
            report.role_grant_mismatch[system_role.value] = "; ".join(parts)

    return report


async def assert_permissions_in_sync(session: AsyncSession) -> None:
    """Fail fast on drift.

    Called from the application lifespan. The message names every discrepancy
    so the fix is obvious without a debugging session.
    """
    report = await check_permission_sync(session)
    if report.ok:
        return

    raise PermissionSyncError(
        "The permissions table and the Permission enum are out of sync.\n"
        f"{report.describe()}\n"
        "Run the RBAC seed migration, or add a migration for the enum change."
    )


def expected_permission_count() -> int:
    """Convenience for tests and for the seed migration's own assertion."""
    return len(Permission)


def expected_role_count() -> int:
    return len(SystemRole)
