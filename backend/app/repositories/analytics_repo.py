"""Analytics persistence: event ingest, rollup rebuild, dashboard queries.

Three distinct workloads share this file because they share one data model.

*Ingest* is a bulk INSERT with no reads on the hot path. *Rollup* is one
`INSERT … SELECT … ON CONFLICT DO UPDATE` per day. *Reporting* reads the rollup
table almost exclusively — the raw events are scanned only by the rollup task
itself, which is the whole point of having a rollup table.

Raw SQL appears more here than anywhere else in the codebase, for reasons that
are specific rather than habitual: `analytics_events` is partitioned and has no
usable ORM identity to hydrate, the rollup is an upsert over an aggregate, and
the partition helpers are SQL functions by design.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import EventType

#: Event types that belong to a job and therefore roll up. `search` and
#: `filter_used` are site-wide; they stay in the raw table and are reported
#: from `search_logs`, which knows things the event row does not.
ROLLUP_COLUMNS: dict[str, EventType] = {
    "views": EventType.JOB_VIEW,
    "apply_clicks": EventType.APPLY_CLICK,
    "shares": EventType.SHARE,
    "source_clicks": EventType.SOURCE_CLICK,
    "saves": EventType.JOB_SAVED,
    "reports": EventType.REPORT_CREATED,
}


@dataclass(frozen=True)
class JobAttribution:
    source_id: UUID | None
    category_id: UUID | None
    location_id: UUID | None


class AnalyticsRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # --- ingest -----------------------------------------------------------

    async def attribution_for(self, job_ids: list[UUID]) -> dict[UUID, JobAttribution]:
        """Server-side attribution for a batch, in one query.

        Never taken from the client. A forged `source_id` would corrupt exactly
        the report that decides where acquisition spend goes, and the endpoint
        is unauthenticated.
        """
        if not job_ids:
            return {}
        rows = await self.session.execute(
            text(
                """
                SELECT id, source_id, category_id, location_id
                  FROM jobs
                 WHERE id = ANY(CAST(:ids AS uuid[]))
                """
            ),
            {"ids": [str(i) for i in job_ids]},
        )
        return {
            r[0]: JobAttribution(source_id=r[1], category_id=r[2], location_id=r[3])
            for r in rows.all()
        }

    async def record_events(self, rows: list[dict[str, Any]]) -> int:
        """Append a batch.

        One statement for the whole batch. `executemany` over fifty single-row
        inserts is fifty round trips to save nothing, and this runs while a
        reader is waiting for a page.
        """
        if not rows:
            return 0
        await self.session.execute(
            text(
                """
                INSERT INTO analytics_events (
                    occurred_at, event_type, session_id, job_id,
                    source_id, category_id, location_id,
                    filters, referrer_host, device_type, country
                ) VALUES (
                    :occurred_at, CAST(:event_type AS event_type), :session_id, :job_id,
                    :source_id, :category_id, :location_id,
                    CAST(:filters AS jsonb), :referrer_host,
                    CAST(:device_type AS device_type), :country
                )
                """
            ),
            rows,
        )
        return len(rows)

    # --- rollups ----------------------------------------------------------

    async def rebuild_day(self, day: date) -> int:
        """Recompute one day from the raw events.

        `ON CONFLICT DO UPDATE` **replaces** the counters rather than adding to
        them. That is what makes the task safe to re-run: a retry, an overlap
        with the hourly pass, and a manual backfill all converge on the same
        numbers. An incrementing upsert would double-count on every retry, and
        the failure would be silent — the dashboard would simply be wrong.
        """
        counters = ",\n".join(
            f"    count(*) FILTER (WHERE e.event_type = '{event.value}') AS {column}"
            for column, event in ROLLUP_COLUMNS.items()
        )
        updates = ",\n".join(f"    {column} = EXCLUDED.{column}" for column in ROLLUP_COLUMNS)
        result = await self.session.execute(
            text(
                f"""
                INSERT INTO analytics_daily_rollups AS r (
                    day, job_id, source_id, category_id, location_id,
                    {", ".join(ROLLUP_COLUMNS)}, unique_sessions, computed_at
                )
                SELECT
                    CAST(:day AS date),
                    e.job_id,
                    -- Attribution as most events saw it that day. Events are
                    -- stamped at write time, so a mid-day re-categorisation
                    -- leaves both values present; the majority is the honest
                    -- summary and `mode()` is cheaper than a weighted pick.
                    mode() WITHIN GROUP (ORDER BY e.source_id),
                    mode() WITHIN GROUP (ORDER BY e.category_id),
                    mode() WITHIN GROUP (ORDER BY e.location_id),
                {counters},
                    count(DISTINCT e.session_id) AS unique_sessions,
                    now()
                  FROM analytics_events e
                 WHERE e.job_id IS NOT NULL
                   AND e.occurred_at >= CAST(:day AS date)
                   AND e.occurred_at <  (CAST(:day AS date) + interval '1 day')
                 GROUP BY e.job_id
                ON CONFLICT (day, job_id) DO UPDATE SET
                    source_id = EXCLUDED.source_id,
                    category_id = EXCLUDED.category_id,
                    location_id = EXCLUDED.location_id,
                {updates},
                    unique_sessions = EXCLUDED.unique_sessions,
                    computed_at = EXCLUDED.computed_at
                """
            ),
            {"day": day},
        )
        return result.rowcount or 0

    async def delete_rollups_before(self, cutoff: date) -> int:
        result = await self.session.execute(
            text("DELETE FROM analytics_daily_rollups WHERE day < :cutoff"),
            {"cutoff": cutoff},
        )
        return result.rowcount or 0

    async def last_rollup_day(self) -> date | None:
        return (
            await self.session.execute(text("SELECT max(day) FROM analytics_daily_rollups"))
        ).scalar_one_or_none()

    # --- partition maintenance -------------------------------------------

    async def ensure_month_partition(self, parent: str, month: date) -> str:
        """Idempotent — creating a partition that exists returns its name."""
        return (
            await self.session.execute(
                text("SELECT ensure_month_partition(:parent, :month)"),
                {"parent": parent, "month": month},
            )
        ).scalar_one()

    async def drop_partitions_before(self, parent: str, cutoff: date) -> list[str]:
        rows = await self.session.execute(
            text("SELECT drop_partitions_before(:parent, :cutoff)"),
            {"parent": parent, "cutoff": cutoff},
        )
        return [r[0] for r in rows.all() if r[0]]

    async def partition_months(self, parent: str) -> list[str]:
        rows = await self.session.execute(
            text(
                """
                SELECT c.relname
                  FROM pg_inherits i
                  JOIN pg_class c ON c.oid = i.inhrelid
                  JOIN pg_class p ON p.oid = i.inhparent
                 WHERE p.relname = :parent
                 ORDER BY c.relname
                """
            ),
            {"parent": parent},
        )
        return [r[0] for r in rows.all()]

    # --- dashboard reads --------------------------------------------------

    async def totals(self, *, since: date, until: date) -> dict[str, int]:
        row = (
            await self.session.execute(
                text(
                    f"""
                    SELECT {", ".join(f"coalesce(sum({c}), 0)" for c in ROLLUP_COLUMNS)}
                      FROM analytics_daily_rollups
                     WHERE day BETWEEN :since AND :until
                    """
                ),
                {"since": since, "until": until},
            )
        ).one()
        return dict(zip(ROLLUP_COLUMNS, (int(v) for v in row), strict=True))

    async def series(self, *, since: date, until: date) -> list[tuple[date, int, int]]:
        """Daily views and apply clicks, with empty days filled in.

        `generate_series` rather than returning only days that had traffic: a
        chart with missing days draws a straight line across an outage, which
        is the opposite of what the reader needs to see.
        """
        rows = await self.session.execute(
            text(
                """
                SELECT CAST(d AS date),
                       coalesce(sum(r.views), 0),
                       coalesce(sum(r.apply_clicks), 0)
                  FROM generate_series(
                           CAST(:since AS date), CAST(:until AS date), interval '1 day'
                       ) AS d
                  LEFT JOIN analytics_daily_rollups r ON r.day = CAST(d AS date)
                 GROUP BY d
                 ORDER BY d
                """
            ),
            {"since": since, "until": until},
        )
        return [(r[0], int(r[1]), int(r[2])) for r in rows.all()]

    async def top_jobs(self, *, since: date, until: date, limit: int = 10) -> list[dict[str, Any]]:
        rows = await self.session.execute(
            text(
                """
                SELECT r.job_id, j.slug, j.title, j.company_name,
                       sum(r.views) AS views,
                       sum(r.apply_clicks) AS apply_clicks
                  FROM analytics_daily_rollups r
                  JOIN jobs j ON j.id = r.job_id
                 WHERE r.day BETWEEN :since AND :until
                 GROUP BY r.job_id, j.slug, j.title, j.company_name
                 -- Ordered by apply clicks, not views: an apply is the event
                 -- the business cares about, and ordering by views promotes
                 -- whatever happens to be linked from the homepage.
                 ORDER BY apply_clicks DESC, views DESC
                 LIMIT :limit
                """
            ),
            {"since": since, "until": until, "limit": limit},
        )
        return [
            {
                "job_id": r[0],
                "slug": r[1],
                "title": r[2],
                "company_name": r[3],
                "views": int(r[4]),
                "apply_clicks": int(r[5]),
            }
            for r in rows.all()
        ]

    async def source_performance(self, *, since: date, until: date) -> list[dict[str, Any]]:
        """Per-source funnel.

        `jobs` is joined for the listing count so a source that published a
        hundred listings and earned two clicks is visible as such, rather than
        being absent from the report because nothing it published was viewed.
        """
        rows = await self.session.execute(
            text(
                """
                WITH activity AS (
                    SELECT source_id,
                           sum(views) AS views,
                           sum(apply_clicks) AS apply_clicks,
                           sum(source_clicks) AS source_clicks,
                           sum(reports) AS reports
                      FROM analytics_daily_rollups
                     WHERE day BETWEEN :since AND :until
                     GROUP BY source_id
                ),
                published AS (
                    SELECT source_id, count(*) AS jobs
                      FROM jobs
                     WHERE deleted_at IS NULL
                     GROUP BY source_id
                )
                SELECT s.id, s.name, s.slug,
                       coalesce(p.jobs, 0),
                       coalesce(a.views, 0),
                       coalesce(a.apply_clicks, 0),
                       coalesce(a.source_clicks, 0),
                       coalesce(a.reports, 0)
                  FROM sources s
                  LEFT JOIN activity  a ON a.source_id = s.id
                  LEFT JOIN published p ON p.source_id = s.id
                 ORDER BY coalesce(a.apply_clicks, 0) DESC, s.name
                """
            ),
            {"since": since, "until": until},
        )
        return [
            {
                "source_id": r[0],
                "name": r[1],
                "slug": r[2],
                "jobs": int(r[3]),
                "views": int(r[4]),
                "apply_clicks": int(r[5]),
                "source_clicks": int(r[6]),
                "reports": int(r[7]),
            }
            for r in rows.all()
        ]

    async def event_count_since(self, since: datetime) -> int:
        """Raw event volume — used by the health check and by tests, not by
        the dashboard, which reads rollups."""
        return (
            await self.session.execute(
                text("SELECT count(*) FROM analytics_events WHERE occurred_at >= :since"),
                {"since": since},
            )
        ).scalar_one()


__all__ = ["AnalyticsRepository", "JobAttribution", "ROLLUP_COLUMNS"]
