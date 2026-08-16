"""Generated social share assets.

The table records where a card lives and what it was rendered from. The
`content_hash` is the whole point: it is a digest of exactly the job fields the
image displays, so regeneration is decided by comparison rather than by a
timestamp. A view counter moving does not invalidate an image that would come
out byte-identical.

Revision ID: 0007_social_assets
Revises: 0006_password_reset
Created: 2026-08-16
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0007_social_assets"
down_revision: str | None = "0006_password_reset"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

VARIANTS = ("square", "landscape")


def upgrade() -> None:
    labels = ", ".join(f"'{v}'" for v in VARIANTS)
    op.execute(f"CREATE TYPE social_variant AS ENUM ({labels})")

    op.create_table(
        "job_social_assets",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("job_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "variant",
            postgresql.ENUM(*VARIANTS, name="social_variant", create_type=False),
            nullable=False,
        ),
        sa.Column("path", sa.String(300), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("width", sa.Integer(), nullable=False),
        sa.Column("height", sa.Integer(), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "generated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint("width > 0 AND height > 0", name="dimensions_positive"),
        sa.ForeignKeyConstraint(
            ["job_id"], ["jobs.id"], name="fk_job_social_assets_job_id_jobs", ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_job_social_assets"),
        sa.UniqueConstraint("job_id", "variant", name="uq_job_social_assets_job_id_variant"),
    )
    op.create_index("ix_job_social_assets_job_id", "job_social_assets", ["job_id"])


def downgrade() -> None:
    op.drop_table("job_social_assets")
    op.execute("DROP TYPE IF EXISTS social_variant")
