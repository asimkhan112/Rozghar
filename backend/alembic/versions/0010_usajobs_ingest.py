"""External listing references, and the USAJOBS source row.

`source_ref` is the identity an import run recognises a listing by. Without it
the second run cannot tell a job it already created from a new one, and the
only alternatives are re-creating everything or matching on the slug — which
changes the moment a title is edited.

Nullable, and unique only *with* a source: a hand-entered job has no external
reference, and NULLs do not collide in a Postgres unique index, so the
constraint never stands between an editor and the create form.

Revision ID: 0010_usajobs_ingest
Revises: 0009_company_website
Created: 2026-08-24
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0010_usajobs_ingest"
down_revision: str | None = "0009_company_website"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("jobs", sa.Column("source_ref", sa.String(length=64), nullable=True))
    op.create_index(
        "uq_jobs_source_ref",
        "jobs",
        ["source_id", "source_ref"],
        unique=True,
        postgresql_where=sa.text("source_ref IS NOT NULL AND deleted_at IS NULL"),
    )

    # Seeded here rather than by the importer: the source is configuration, and
    # a fetch endpoint that creates its own source row on first call makes the
    # first call different from every later one.
    op.execute(
        """
        INSERT INTO sources (id, name, slug, type, base_url, is_active, config,
                             created_at, updated_at)
        VALUES (gen_random_uuid(), 'USAJOBS', 'usajobs', 'partner',
                'https://data.usajobs.gov', true, '{}'::jsonb, now(), now())
        ON CONFLICT (slug) DO NOTHING
        """
    )


def downgrade() -> None:
    op.execute("DELETE FROM sources WHERE slug = 'usajobs'")
    op.drop_index("uq_jobs_source_ref", table_name="jobs")
    op.drop_column("jobs", "source_ref")
