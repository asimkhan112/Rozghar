"""Seed the RBAC model and the manual source.

Rows are generated from `app.core.permissions` rather than written out as
literals. Hardcoding them here would create a second source of truth and
guarantee eventual drift — which is exactly what the startup validator exists
to catch. Importing the enum means this migration cannot disagree with the code
it was written against.

The migration is idempotent per key: re-running it after adding a permission to
the enum inserts only the new rows and re-syncs the grants.

Revision ID: 0002_seed_rbac
Revises: 0001_initial_schema
Created: 2026-08-14
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op
from app.core.permissions import (
    PERMISSION_METADATA,
    ROLE_PERMISSIONS,
    SYSTEM_ROLE_LABELS,
    Permission,
    SystemRole,
)

revision: str = "0002_seed_rbac"
down_revision: str | None = "0001_initial_schema"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()

    # --- permissions ------------------------------------------------------
    for permission in Permission:
        group, description = PERMISSION_METADATA[permission]
        bind.execute(
            sa.text(
                """
                INSERT INTO permissions (key, group_name, description)
                VALUES (:key, :group_name, :description)
                ON CONFLICT (key) DO UPDATE
                    SET group_name = EXCLUDED.group_name,
                        description = EXCLUDED.description
                """
            ),
            {"key": permission.value, "group_name": group.value, "description": description},
        )

    # --- system roles -----------------------------------------------------
    for role in SystemRole:
        name, description = SYSTEM_ROLE_LABELS[role]
        bind.execute(
            sa.text(
                """
                INSERT INTO roles (key, name, description, is_system)
                VALUES (:key, :name, :description, true)
                ON CONFLICT (key) DO UPDATE
                    SET name = EXCLUDED.name,
                        description = EXCLUDED.description,
                        is_system = true,
                        updated_at = now()
                """
            ),
            {"key": role.value, "name": name, "description": description},
        )

    # --- grants -----------------------------------------------------------
    # Replace rather than merge: the code map is authoritative, so a permission
    # removed from a role in code must disappear from the database too.
    for role, permissions in ROLE_PERMISSIONS.items():
        bind.execute(
            sa.text(
                """
                DELETE FROM role_permissions
                WHERE role_id = (SELECT id FROM roles WHERE key = :role_key)
                """
            ),
            {"role_key": role.value},
        )
        for permission in sorted(permissions, key=lambda p: p.value):
            bind.execute(
                sa.text(
                    """
                    INSERT INTO role_permissions (role_id, permission_id)
                    SELECT r.id, p.id
                      FROM roles r, permissions p
                     WHERE r.key = :role_key AND p.key = :permission_key
                    ON CONFLICT DO NOTHING
                    """
                ),
                {"role_key": role.value, "permission_key": permission.value},
            )

    # --- the manual source ------------------------------------------------
    # Every job carries a source. V1 is manual entry, but the column is NOT
    # NULL from the start so per-source reporting is possible the day scraper
    # ingestion lands, rather than needing a backfill.
    bind.execute(
        sa.text(
            """
            INSERT INTO sources (name, slug, type, is_active)
            VALUES ('Manual Entry', 'manual', 'manual', true)
            ON CONFLICT (slug) DO NOTHING
            """
        )
    )

    # --- assert the seed actually took ------------------------------------
    # A silently partial seed would surface much later as a confusing 403.
    seeded_permissions = bind.execute(sa.text("SELECT count(*) FROM permissions")).scalar_one()
    if seeded_permissions != len(Permission):
        raise RuntimeError(
            f"permission seed incomplete: {seeded_permissions} rows for {len(Permission)} enum members"
        )

    seeded_roles = bind.execute(sa.text("SELECT count(*) FROM roles WHERE is_system")).scalar_one()
    if seeded_roles != len(SystemRole):
        raise RuntimeError(
            f"role seed incomplete: {seeded_roles} rows for {len(SystemRole)} system roles"
        )


def downgrade() -> None:
    bind = op.get_bind()
    bind.execute(sa.text("DELETE FROM sources WHERE slug = 'manual'"))
    # role_permissions rows disappear via ON DELETE CASCADE.
    bind.execute(sa.text("DELETE FROM roles WHERE is_system"))
    bind.execute(
        sa.text("DELETE FROM permissions WHERE key = ANY(:keys)"),
        {"keys": [p.value for p in Permission]},
    )
