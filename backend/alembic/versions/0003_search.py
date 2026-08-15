"""Full-text search: vector, indexes and the triggers that feed them.

Two things here are easy to get wrong and expensive to discover late.

**Immutability.** `unaccent(text)` is STABLE, not IMMUTABLE, because its result
depends on a dictionary that could be changed. PostgreSQL therefore refuses it
inside a generated column or an index expression. The two-argument form with an
explicit dictionary is safe to wrap as IMMUTABLE, which is what
`immutable_unaccent` does. The same applies to `to_tsvector`: the one-argument
form is STABLE (it reads `default_text_search_config`), so every call here names
its configuration.

**Denormalisation.** A generated column cannot join. The location's display name
and the flattened requirements therefore live on the job row, maintained by
trigger — including a trigger on `locations`, so renaming a city refreshes every
listing that references it. Without that second trigger the search text silently
rots.

Revision ID: 0003_search
Revises: 0002_seed_rbac
Created: 2026-08-15
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0003_search"
down_revision: str | None = "0002_seed_rbac"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # --- immutable unaccent ----------------------------------------------
    op.execute(
        """
        CREATE OR REPLACE FUNCTION immutable_unaccent(text)
        RETURNS text
        LANGUAGE sql
        IMMUTABLE PARALLEL SAFE STRICT
        AS $$ SELECT public.unaccent('public.unaccent'::regdictionary, $1) $$
        """
    )

    # --- keep the denormalised search text current ------------------------
    op.execute(
        """
        CREATE OR REPLACE FUNCTION jobs_sync_search_text()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            SELECT coalesce(l.display_name, '')
              INTO NEW.location_text
              FROM locations l
             WHERE l.id = NEW.location_id;

            NEW.location_text := coalesce(NEW.location_text, '');

            -- requirements is a JSONB array of strings; flatten to plain text
            -- so the generated column has something tokenisable.
            NEW.skills_text := coalesce(
                (
                    SELECT string_agg(elem #>> '{}', ' ')
                      FROM jsonb_array_elements(
                            CASE
                                WHEN jsonb_typeof(NEW.requirements) = 'array'
                                THEN NEW.requirements
                                ELSE '[]'::jsonb
                            END
                           ) AS elem
                ),
                ''
            );
            RETURN NEW;
        END
        $$
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_jobs_sync_search_text
        BEFORE INSERT OR UPDATE OF location_id, requirements ON jobs
        FOR EACH ROW EXECUTE FUNCTION jobs_sync_search_text()
        """
    )

    op.execute(
        """
        CREATE OR REPLACE FUNCTION locations_refresh_job_text()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            IF NEW.display_name IS DISTINCT FROM OLD.display_name THEN
                UPDATE jobs
                   SET location_text = NEW.display_name
                 WHERE location_id = NEW.id;
            END IF;
            RETURN NEW;
        END
        $$
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_locations_refresh_job_text
        AFTER UPDATE OF display_name ON locations
        FOR EACH ROW EXECUTE FUNCTION locations_refresh_job_text()
        """
    )

    # --- backfill before the generated column is added --------------------
    # Any row written before this migration has empty denormalised text.
    op.execute(
        """
        UPDATE jobs j
           SET location_text = coalesce(l.display_name, ''),
               skills_text = coalesce(
                   (
                       SELECT string_agg(elem #>> '{}', ' ')
                         FROM jsonb_array_elements(
                               CASE WHEN jsonb_typeof(j.requirements) = 'array'
                                    THEN j.requirements ELSE '[]'::jsonb END
                              ) AS elem
                   ),
                   ''
               )
          FROM locations l
         WHERE l.id = j.location_id
        """
    )

    # --- the search vector ------------------------------------------------
    # Weights follow the approved design: title A, company and location B,
    # skills C, description D. `simple` for location so city names are not
    # stemmed as if they were English words.
    op.execute(
        """
        ALTER TABLE jobs
        ADD COLUMN search_vector tsvector
        GENERATED ALWAYS AS (
            setweight(to_tsvector('english', immutable_unaccent(coalesce(title, ''))), 'A')
         || setweight(to_tsvector('english', immutable_unaccent(coalesce(company_name, ''))), 'B')
         || setweight(to_tsvector('english', immutable_unaccent(coalesce(location_text, ''))), 'B')
         || setweight(to_tsvector('simple',  immutable_unaccent(coalesce(location_text, ''))), 'B')
         || setweight(to_tsvector('english', immutable_unaccent(coalesce(skills_text, ''))), 'C')
         || setweight(to_tsvector('english', immutable_unaccent(coalesce(description, ''))), 'D')
        ) STORED
        """
    )

    op.execute("CREATE INDEX ix_jobs_search_vector ON jobs USING gin (search_vector)")
    # Trigram on company as well as title (title's index came with 0001), so a
    # misspelled employer name still resolves through the fuzzy tier.
    op.execute(
        "CREATE INDEX ix_jobs_company_name_trgm ON jobs USING gin (company_name gin_trgm_ops)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_jobs_company_name_trgm")
    op.execute("DROP INDEX IF EXISTS ix_jobs_search_vector")
    op.execute("ALTER TABLE jobs DROP COLUMN IF EXISTS search_vector")
    op.execute("DROP TRIGGER IF EXISTS trg_locations_refresh_job_text ON locations")
    op.execute("DROP FUNCTION IF EXISTS locations_refresh_job_text()")
    op.execute("DROP TRIGGER IF EXISTS trg_jobs_sync_search_text ON jobs")
    op.execute("DROP FUNCTION IF EXISTS jobs_sync_search_text()")
    op.execute("DROP FUNCTION IF EXISTS immutable_unaccent(text)")
