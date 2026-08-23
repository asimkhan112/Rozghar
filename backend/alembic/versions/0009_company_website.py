"""The employer's own site, recorded on the listing.

Denormalised onto `jobs` beside `company_name` rather than read through
`companies.website`, for the reason stated in `models/company.py`: V1 leaves
`company_id` null and treats the employer as text on the listing. An editor
entering a job knows the company's URL; making them create a company row first
would be ceremony in service of a join that does not exist yet. When V2
backfills `company_id`, this column becomes the seed for `companies.website`
rather than something to unpick.

Nullable with no default: most listings will carry one, but a job found on an
aggregator often has no employer site to point at, and inventing one is worse
than omitting the link.

Revision ID: 0009_company_website
Revises: 0008_suggest
Created: 2026-08-23
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0009_company_website"
down_revision: str | None = "0008_suggest"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "jobs",
        sa.Column("company_website", sa.String(length=500), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("jobs", "company_website")
