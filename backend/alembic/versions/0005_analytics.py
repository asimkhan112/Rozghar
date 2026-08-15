"""Analytics: event vocabulary, daily rollups, and partition maintenance.

Three things land together because they are one feature.

**Vocabulary.** Four event labels were named in the past tense from the
schema's point of view; the product names the action. `RENAME VALUE` rewrites
the catalogue label without touching a row, since an enum column stores an
ordinal. Two genuinely new labels are appended — PostgreSQL 16 permits
`ADD VALUE` inside a transaction as long as the new label is not *used* in the
same transaction, and nothing here uses them.

**Rollups.** `analytics_daily_rollups` is the ninety-day dashboard scan, done
once by a scheduled task instead of on every page load.

**Partition maintenance.** `ensure_month_partition` and `drop_partitions_before`
live in SQL rather than Python because they are also the operator's tools: when
ingest starts rejecting inserts at 3am, `SELECT ensure_month_partition(...)` is
a shorter path back to service than deploying a fix. This is not optional
housekeeping — the initial migration created partitions through 2026-11-01, and
a partitioned table with no matching partition rejects the insert outright.

Revision ID: 0005_analytics
Revises: 0004_report_vocabulary
Created: 2026-08-15
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0005_analytics"
down_revision: str | None = "0004_report_vocabulary"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: (old label, new label)
EVENT_RENAMES: tuple[tuple[str, str], ...] = (
    ("job_viewed", "job_view"),
    ("apply_clicked", "apply_click"),
    ("search_submitted", "search"),
    ("job_reported", "report_created"),
)

NEW_EVENTS: tuple[str, ...] = ("share", "source_click")

#: Tables that carry a monthly partition window.
PARTITIONED = ("analytics_events", "search_logs")


def upgrade() -> None:
    # --- event vocabulary -------------------------------------------------
    for old, new in EVENT_RENAMES:
        op.execute(f"ALTER TYPE event_type RENAME VALUE '{old}' TO '{new}'")
    for label in NEW_EVENTS:
        op.execute(f"ALTER TYPE event_type ADD VALUE IF NOT EXISTS '{label}'")

    # --- attribution parity on the raw events -----------------------------
    # The rollup carries location; without it here the rollup could not be
    # rebuilt from the events, which is the property that makes the rollup
    # disposable rather than a second primary record.
    op.execute("ALTER TABLE analytics_events ADD COLUMN location_id uuid")

    # --- daily rollups ----------------------------------------------------
    op.create_table(
        "analytics_daily_rollups",
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("job_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("category_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("location_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("views", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("apply_clicks", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("shares", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("source_clicks", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("saves", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("reports", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("unique_sessions", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column(
            "computed_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint(
            "views >= 0 AND apply_clicks >= 0 AND shares >= 0 AND source_clicks >= 0 "
            "AND saves >= 0 AND reports >= 0 AND unique_sessions >= 0",
            name="counts_non_negative",
        ),
        sa.ForeignKeyConstraint(
            ["job_id"],
            ["jobs.id"],
            name="fk_analytics_daily_rollups_job_id_jobs",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("day", "job_id", name="pk_analytics_daily_rollups"),
    )
    op.execute("CREATE INDEX ix_analytics_daily_rollups_day ON analytics_daily_rollups (day DESC)")
    op.execute(
        "CREATE INDEX ix_analytics_daily_rollups_source_day "
        "ON analytics_daily_rollups (source_id, day DESC)"
    )
    op.execute(
        "CREATE INDEX ix_analytics_daily_rollups_category_day "
        "ON analytics_daily_rollups (category_id, day DESC)"
    )

    # --- partition maintenance -------------------------------------------
    # Idempotent by construction: creating a partition that exists is a no-op,
    # so the scheduled task can run every hour and the operator can run it by
    # hand at the same moment without either failing.
    op.execute(
        """
        CREATE OR REPLACE FUNCTION ensure_month_partition(parent text, month date)
        RETURNS text
        LANGUAGE plpgsql
        AS $$
        DECLARE
            start_at date := date_trunc('month', month)::date;
            end_at   date := (date_trunc('month', month) + interval '1 month')::date;
            child    text := parent || '_' || to_char(start_at, 'YYYY_MM');
        BEGIN
            IF to_regclass(child) IS NOT NULL THEN
                RETURN child;
            END IF;
            EXECUTE format(
                'CREATE TABLE %I PARTITION OF %I FOR VALUES FROM (%L) TO (%L)',
                child, parent, start_at, end_at
            );
            RETURN child;
        END
        $$
        """
    )

    # Retention. DETACH then DROP rather than a bare DROP: detaching takes a
    # brief lock and releases it, so a long DROP of a large partition cannot
    # block writers to the live one.
    op.execute(
        """
        CREATE OR REPLACE FUNCTION drop_partitions_before(parent text, cutoff date)
        RETURNS SETOF text
        LANGUAGE plpgsql
        AS $$
        DECLARE
            child      record;
            bound_text text;
            lower_at   date;
        BEGIN
            FOR child IN
                SELECT c.relname
                  FROM pg_inherits i
                  JOIN pg_class c      ON c.oid = i.inhrelid
                  JOIN pg_class parent_c ON parent_c.oid = i.inhparent
                 WHERE parent_c.relname = parent
            LOOP
                bound_text := pg_get_expr(
                    (SELECT relpartbound FROM pg_class WHERE relname = child.relname),
                    (SELECT oid FROM pg_class WHERE relname = child.relname)
                );
                -- FOR VALUES FROM ('2026-07-01') TO ('2026-08-01')
                lower_at := substring(bound_text from 'FROM \\(''([0-9-]+)')::date;
                IF lower_at IS NOT NULL AND lower_at < date_trunc('month', cutoff)::date THEN
                    EXECUTE format('ALTER TABLE %I DETACH PARTITION %I', parent, child.relname);
                    EXECUTE format('DROP TABLE %I', child.relname);
                    RETURN NEXT child.relname;
                END IF;
            END LOOP;
        END
        $$
        """
    )

    # Extend the window immediately. The initial migration stops at 2026-11-01
    # and the scheduler only runs once the application is deployed; a database
    # migrated but not yet serving must not be one insert away from failing.
    op.execute(
        f"""
        DO $$
        DECLARE
            m date;
            t text;
        BEGIN
            FOREACH t IN ARRAY ARRAY{list(PARTITIONED)}::text[] LOOP
                FOR m IN
                    SELECT generate_series(
                        date_trunc('month', current_date),
                        date_trunc('month', current_date) + interval '6 months',
                        interval '1 month'
                    )::date
                LOOP
                    PERFORM ensure_month_partition(t, m);
                END LOOP;
            END LOOP;
        END
        $$
        """
    )


def downgrade() -> None:
    op.execute("DROP FUNCTION IF EXISTS drop_partitions_before(text, date)")
    op.execute("DROP FUNCTION IF EXISTS ensure_month_partition(text, date)")
    op.drop_table("analytics_daily_rollups")
    op.execute("ALTER TABLE analytics_events DROP COLUMN IF EXISTS location_id")
    # Enum labels cannot be removed without rewriting the type; renaming the
    # four back is the honest reverse. `share` and `source_click` remain,
    # harmlessly, because dropping a label would require recreating every
    # column that uses the type.
    for old, new in EVENT_RENAMES:
        op.execute(f"ALTER TYPE event_type RENAME VALUE '{new}' TO '{old}'")
