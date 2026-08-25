"""Bullets that the update schema would refuse, moved into the description.

The USAJOBS importer wrote through `JobService` rather than the request schema,
so nothing enforced `ShortText`'s 300-character limit on a bullet — and JSONB
has no opinion about the length of what it holds. The result was listings that
imported cleanly and then failed with a 422 the moment an editor pressed
publish, because the PATCH that publishes them validates what the import never
did.

The over-long items are moved rather than truncated: a duty cut off mid-sentence
is worse than one read as a paragraph, and the listing page renders the
description's text with the same structure either way.

Revision ID: 0011_trim_imported_bullets
Revises: 0010_usajobs_ingest
Created: 2026-08-25
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0011_trim_imported_bullets"
down_revision: str | None = "0010_usajobs_ingest"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: Mirrors `ShortText` and `BulletList` in `app/schemas/`.
MAX_CHARS = 300
MAX_ITEMS = 30

COLUMNS = ("responsibilities", "requirements", "benefits")


def upgrade() -> None:
    for column in COLUMNS:
        # Long items first: appended to the description, then dropped from the
        # list. One statement, so a row is never left with the item removed and
        # the text not yet added.
        op.execute(
            f"""
            UPDATE jobs SET
              description = left(
                description || E'\\n\\n' || (
                  SELECT string_agg(item, E'\\n\\n')
                  FROM jsonb_array_elements_text({column}) AS item
                  WHERE length(item) > {MAX_CHARS}
                ),
                20000
              ),
              {column} = COALESCE(
                (
                  SELECT jsonb_agg(item)
                  FROM jsonb_array_elements_text({column}) AS item
                  WHERE length(item) <= {MAX_CHARS}
                ),
                '[]'::jsonb
              )
            WHERE source_ref IS NOT NULL
              AND EXISTS (
                SELECT 1 FROM jsonb_array_elements_text({column}) AS item
                WHERE length(item) > {MAX_CHARS}
              )
            """
        )

        # A list longer than the schema allows is refused whole, so the tail is
        # dropped. No import has produced one yet; this exists so a future
        # agency that writes forty duties cannot reintroduce the same 422.
        op.execute(
            f"""
            UPDATE jobs
            SET {column} = (
              SELECT jsonb_agg(item)
              FROM (
                SELECT item FROM jsonb_array_elements({column}) AS item LIMIT {MAX_ITEMS}
              ) AS kept
            )
            WHERE source_ref IS NOT NULL
              AND jsonb_array_length({column}) > {MAX_ITEMS}
            """
        )


def downgrade() -> None:
    """Irreversible.

    The bullets are now sentences inside a paragraph, with no marker saying
    where each one began. Rebuilding the arrays would mean guessing at
    boundaries the data no longer records — and re-running the import against a
    cleared `source_ref` is the honest way back.
    """
