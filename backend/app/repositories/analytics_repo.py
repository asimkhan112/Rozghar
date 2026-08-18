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
from datetime import UTC, date, datetime, time, timedelta
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


#: The three visitor cards, each as (current, previous) day offsets from today.
#: A range is `[today + start, today + end)` in whole days, so the current day
#: runs `(0, 1)` and the seven-day window ends today rather than yesterday.
#:
#: Every period is counted separately and none is derived from another. Visitor
#: counts are distinct-session counts, and a distinct count is not additive: a
#: reader who came back on Tuesday and Thursday is one weekly visitor and two
#: daily ones. Summing days into a week would report them twice.
VISITOR_PERIODS: dict[str, tuple[tuple[int, int], tuple[int, int]]] = {
    "daily": ((0, 1), (-1, 0)),
    "weekly": ((-6, 1), (-13, -6)),
    "monthly": ((-29, 1), (-59, -29)),
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

    async def traffic(self, *, since: date, until: date) -> dict[str, Any]:
        """Session-shaped traffic metrics.

        Read from `analytics_events` rather than the rollups, and not by
        oversight: every one of these numbers is grained by *session*, and the
        rollup is grained by `(day, job_id)`. Its `unique_sessions` column
        carries the warning in its own docstring — summing it across days
        counts a returning visitor once per day. A distinct count over the raw
        events is the only way to get the real figure, and a duration or a
        bounce cannot be derived from a per-job counter at all.

        One pass, one grouping. The window is a date range on a partitioned
        table, so the planner prunes to the months involved rather than
        touching the whole history.

        Two definitions worth stating, because dashboards that leave them
        implicit get misread:

        *Duration* is last event minus first event within the window. The dwell
        time on the final page of a visit is unobservable — nothing is emitted
        when a reader simply stops reading — so a session with one event
        measures zero. Those sessions are kept in the average rather than
        filtered out; excluding them would report the average length of
        *engaged* visits under a label that says "per visit".

        *A bounce* is a session that produced exactly one event. A visitor who
        opened one listing and left is the thing the number is for.

        Sessions straddling the window edge are counted only for the part
        inside it, which is the same convention every other metric here uses.
        """
        row = (
            await self.session.execute(
                text(
                    """
                    WITH visit AS (
                        SELECT session_id,
                               count(*) AS events,
                               count(*) FILTER (WHERE event_type = 'job_view') AS views,
                               extract(
                                   epoch FROM max(occurred_at) - min(occurred_at)
                               ) AS seconds
                          FROM analytics_events
                         WHERE occurred_at >= CAST(:since AS date)
                           AND occurred_at <  CAST(:until AS date) + interval '1 day'
                         GROUP BY session_id
                    )
                    SELECT coalesce(sum(views), 0),
                           count(*),
                           coalesce(avg(seconds), 0),
                           count(*) FILTER (WHERE events = 1)
                      FROM visit
                    """
                ),
                {"since": since, "until": until},
            )
        ).one()
        return {
            "page_views": int(row[0]),
            "unique_sessions": int(row[1]),
            "avg_session_seconds": float(row[2]),
            "bounced_sessions": int(row[3]),
        }

    async def top_locations(
        self, *, since: date, until: date, limit: int = 5
    ) -> list[dict[str, Any]]:
        """Where the demand is, by views on listings in each location.

        From the rollups, which already carry `location_id` copied down from
        the events — so a listing re-homed next month does not rewrite last
        month's geography.

        Locations with no traffic are excluded rather than listed at zero. The
        panel ranks demand; a tail of zeroes is noise, and the catalogue view
        of the same question is already answered by `locations.job_count`.

        `total_views` is a window function over the full grouped set rather
        than a sum of the rows returned, so the shares stay honest after the
        LIMIT: five locations out of forty should add up to well under 100%,
        not to exactly it.
        """
        rows = await self.session.execute(
            text(
                """
                WITH by_location AS (
                    SELECT l.id, l.display_name, l.city, l.slug,
                           sum(r.views) AS views,
                           sum(r.apply_clicks) AS apply_clicks
                      FROM analytics_daily_rollups r
                      JOIN locations l ON l.id = r.location_id
                     WHERE r.day BETWEEN :since AND :until
                     GROUP BY l.id, l.display_name, l.city, l.slug
                    HAVING sum(r.views) > 0
                )
                SELECT id, display_name, city, slug, views, apply_clicks,
                       sum(views) OVER () AS total_views
                  FROM by_location
                 ORDER BY views DESC, display_name
                 LIMIT :limit
                """
            ),
            {"since": since, "until": until, "limit": limit},
        )
        return [
            {
                "location_id": r[0],
                # `city` is what a chart row has space for; `display_name` is
                # the fallback for a location that has none, such as "Remote".
                "name": r[2] or r[1],
                "slug": r[3],
                "views": int(r[4]),
                "apply_clicks": int(r[5]),
                "total_views": int(r[6]),
            }
            for r in rows.all()
        ]

    async def visitor_trends(self, *, today: date) -> dict[str, int]:
        """Distinct visitors for each card, and for the period before it.

        Six distinct-session counts and six view counts in one pass. The
        alternative is twelve queries over overlapping ranges of the same
        partitions, which is twelve scans to answer one panel.

        Boundaries are computed here as explicit UTC instants rather than left
        to Postgres to derive from a bare `date`, which it resolves against
        whatever the server's `TimeZone` happens to be. A dashboard whose "day"
        silently moves with a database setting is not one anybody can reconcile
        against another number later.

        That does mean the day boundary is midnight UTC — five hours before
        midnight in Karachi. It matches the rest of the analytics, which is the
        property worth having: one convention the whole dashboard shares beats
        a per-panel one that is locally nicer and globally inconsistent.
        """
        midnight = datetime.combine(today, time.min, tzinfo=UTC)
        params: dict[str, Any] = {}
        selects: list[str] = []

        for name, ranges in VISITOR_PERIODS.items():
            for suffix, (start, end) in zip(("", "_prev"), ranges, strict=True):
                key = f"{name}{suffix}"
                params[f"{key}_from"] = midnight + timedelta(days=start)
                params[f"{key}_to"] = midnight + timedelta(days=end)
                window = f"occurred_at >= :{key}_from AND occurred_at < :{key}_to"
                selects.append(
                    f"count(DISTINCT session_id) FILTER (WHERE {window}) AS {key}_visitors"
                )
                selects.append(
                    f"count(*) FILTER (WHERE {window} AND event_type = 'job_view') AS {key}_views"
                )

        # The scan covers every window at once, so the planner prunes to the
        # partitions those two months live in and reads them once.
        params["scan_from"] = min(v for k, v in params.items() if k.endswith("_from"))
        params["scan_to"] = max(v for k, v in params.items() if k.endswith("_to"))

        row = (
            (
                await self.session.execute(
                    text(
                        f"""
                    SELECT {", ".join(selects)}
                      FROM analytics_events
                     WHERE occurred_at >= :scan_from AND occurred_at < :scan_to
                    """
                    ),
                    params,
                )
            )
            .mappings()
            .one()
        )
        return {key: int(value) for key, value in row.items()}

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
