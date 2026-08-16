"""Autocomplete: skill vocabulary, query popularity, and the trigram indexes
the grouped suggest endpoint needs.

Three things are missing before a typeahead can answer in under 100ms:

1. **Skills have no table.** They live in `jobs.requirements`, a JSONB array
   denormalised into `jobs.skills_text` for the tsvector. Unnesting that array
   on every keystroke cannot use an index — it is a sequential scan over every
   published listing — so the vocabulary is materialised here and refreshed by
   a scheduled task.

2. **Query popularity is spread across a partitioned table.** `search_logs` is
   range-partitioned by month; aggregating it per keystroke would touch every
   partition. The aggregate is small, changes slowly, and is materialised for
   the same reason.

3. **Locations, categories and sources have no trigram index.** Jobs and
   companies already got theirs in 0001; the other three were never searched
   directly.

Revision ID: 0008_suggest
Revises: 0007_social_assets
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0008_suggest"
down_revision = "0007_social_assets"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # --- skill vocabulary -------------------------------------------------
    op.create_table(
        "skill_terms",
        sa.Column("term", sa.String(120), primary_key=True),
        # Unaccented and lowercased at write time. Matching against a
        # normalised column means the query side needs no function call, so
        # the trigram index is usable.
        sa.Column("term_norm", sa.String(120), nullable=False),
        sa.Column("job_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column(
            "refreshed_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.execute(
        "CREATE INDEX ix_skill_terms_norm_trgm ON skill_terms USING gin (term_norm gin_trgm_ops)"
    )
    # Prefix matches are the top ranking tier and deserve their own index:
    # `text_pattern_ops` is what makes `LIKE 'react%'` indexable regardless of
    # the database collation.
    op.execute(
        "CREATE INDEX ix_skill_terms_norm_prefix "
        "ON skill_terms (term_norm text_pattern_ops)"
    )

    # --- query popularity -------------------------------------------------
    op.create_table(
        "popular_queries",
        sa.Column("query_norm", sa.String(200), primary_key=True),
        sa.Column("hits", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("last_seen", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "refreshed_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.execute(
        "CREATE INDEX ix_popular_queries_prefix "
        "ON popular_queries (query_norm text_pattern_ops)"
    )

    # --- trigram indexes for the remaining suggestion sources -------------
    op.execute(
        "CREATE INDEX ix_locations_display_name_trgm "
        "ON locations USING gin (display_name gin_trgm_ops)"
    )
    op.execute(
        "CREATE INDEX ix_categories_name_trgm ON categories USING gin (name gin_trgm_ops)"
    )
    op.execute("CREATE INDEX ix_sources_name_trgm ON sources USING gin (name gin_trgm_ops)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_sources_name_trgm")
    op.execute("DROP INDEX IF EXISTS ix_categories_name_trgm")
    op.execute("DROP INDEX IF EXISTS ix_locations_display_name_trgm")
    op.drop_table("popular_queries")
    op.drop_table("skill_terms")
