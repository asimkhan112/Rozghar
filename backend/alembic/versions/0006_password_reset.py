"""Single-use admin password reset tokens.

Only the hash is stored, matching how refresh tokens are handled: a database
leak must not become the ability to take over every account. `used_at` rather
than deleting the row, so a replayed token is distinguishable from an unknown
one — "this link was already used" and "someone is guessing tokens" are
different events and only one of them is worth waking someone up for.

Revision ID: 0006_password_reset
Revises: 0005_analytics
Created: 2026-08-15
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0006_password_reset"
down_revision: str | None = "0005_analytics"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "admin_password_resets",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("admin_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("issued_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "issued_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("expires_at > issued_at", name="expiry_after_issue"),
        sa.ForeignKeyConstraint(
            ["admin_id"],
            ["admins.id"],
            name="fk_admin_password_resets_admin_id_admins",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["issued_by"],
            ["admins.id"],
            name="fk_admin_password_resets_issued_by_admins",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_admin_password_resets"),
        sa.UniqueConstraint("token_hash", name="uq_admin_password_resets_token_hash"),
    )
    op.create_index("ix_admin_password_resets_admin_id", "admin_password_resets", ["admin_id"])
    op.create_index("ix_admin_password_resets_expires_at", "admin_password_resets", ["expires_at"])


def downgrade() -> None:
    op.drop_table("admin_password_resets")
