"""Analytics ingest and reporting.

Two rules shape everything here.

**Ingest must never fail a page view.** The endpoint returns 202 and swallows
persistence errors, because a dropped analytics row costs a decimal place in a
report while a 500 costs a reader. Measurement is subordinate to the thing
being measured.

**Attribution is server-side.** The client says *what happened*; the server
decides *which job, source, category and location that belongs to*. The ingest
endpoint is unauthenticated, so a client-supplied `source_id` would let anyone
rewrite the report that decides where acquisition budget goes.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import DeviceType, EventType
from app.repositories.analytics_repo import AnalyticsRepository
from app.repositories.job_repo import JobRepository
from app.repositories.search_log_repo import SearchLogRepository

logger = logging.getLogger(__name__)

#: Events that also move a denormalised counter on the job row. Those counters
#: are what the public listing renders; the event stream is what the dashboard
#: reports. Keeping both is deliberate — the counter must survive analytics
#: retention dropping the partition the event lived in.
COUNTER_FOR_EVENT: dict[EventType, str] = {
    EventType.JOB_VIEW: "view_count",
    EventType.APPLY_CLICK: "apply_click_count",
    EventType.JOB_SAVED: "save_count",
}

#: How far back a client may backdate an event. Generous enough for a batch
#: that was queued while the browser was offline, tight enough that nobody can
#: write into a partition that retention already dropped.
MAX_BACKDATE = timedelta(days=2)

#: And how far forward — clock skew only, never the future.
MAX_FUTURE_SKEW = timedelta(minutes=5)

DEFAULT_WINDOW_DAYS = 30
MAX_WINDOW_DAYS = 365


@dataclass(frozen=True)
class IngestResult:
    accepted: int
    rejected: int


@dataclass(frozen=True)
class DateWindow:
    since: date
    until: date

    @property
    def days(self) -> int:
        return (self.until - self.since).days + 1


def resolve_window(since: date | None, until: date | None) -> DateWindow:
    """Clamp a requested range to something the indexes can serve.

    An unbounded range is not a feature — it is a table scan a client can
    trigger by omitting a parameter.
    """
    today = datetime.now(UTC).date()
    end = min(until or today, today)
    start = since or (end - timedelta(days=DEFAULT_WINDOW_DAYS - 1))
    if start > end:
        start = end
    if (end - start).days + 1 > MAX_WINDOW_DAYS:
        start = end - timedelta(days=MAX_WINDOW_DAYS - 1)
    return DateWindow(since=start, until=end)


def _change(current: int, previous: int) -> float | None:
    """Period-over-period movement, or `None` when there is nothing to compare.

    Growth from zero is not a large percentage, it is an undefined one. Every
    analytics dashboard that returns a number here ends up printing something
    like "+∞%" or a meaningless "+100%" on its first quiet week, and somebody
    eventually reports it as a bug.
    """
    if not previous:
        return None
    return round((current - previous) / previous, 4)


def _rate(numerator: int, denominator: int) -> float:
    """Ratios are computed, never stored. Rounded to four places so a rate
    reads as a rate rather than as floating-point noise."""
    if not denominator:
        return 0.0
    return round(numerator / denominator, 4)


def _device_from_user_agent(user_agent: str | None) -> DeviceType | None:
    """Coarse bucketing, deliberately.

    Real device detection needs a maintained database and answers a question
    nobody here is asking. Three buckets is enough to know whether the mobile
    experience is the one that matters, which for this market it is.
    """
    if not user_agent:
        return None
    ua = user_agent.lower()
    if "ipad" in ua or "tablet" in ua:
        return DeviceType.TABLET
    if "mobi" in ua or "android" in ua or "iphone" in ua:
        return DeviceType.MOBILE
    return DeviceType.DESKTOP


class AnalyticsService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = AnalyticsRepository(session)
        self.jobs = JobRepository(session)
        self.searches = SearchLogRepository(session)

    # --- ingest -----------------------------------------------------------

    async def ingest(
        self,
        *,
        session_id: UUID,
        events: list[Any],
        user_agent: str | None = None,
        referrer: str | None = None,
        country: str | None = None,
    ) -> IngestResult:
        """Persist a batch of client events.

        Returns counts rather than raising: a batch with one bad row still
        writes the other forty-nine. Rejecting the whole batch would mean one
        stale client version silently zeroing a day of data.
        """
        now = datetime.now(UTC)
        job_ids = [e.job_id for e in events if e.job_id is not None]
        attribution = await self.repo.attribution_for(list(set(job_ids)))

        device = _device_from_user_agent(user_agent)
        host = _referrer_host(referrer)

        rows: list[dict[str, Any]] = []
        rejected = 0
        counter_deltas: dict[UUID, dict[str, int]] = {}

        for event in events:
            occurred_at = _clamp_time(event.occurred_at, now)
            if occurred_at is None:
                rejected += 1
                continue

            # An event naming a job that does not exist is either a stale
            # client or someone probing. Either way it must not create a row
            # with unresolvable attribution.
            attributes = attribution.get(event.job_id) if event.job_id else None
            if event.job_id is not None and attributes is None:
                rejected += 1
                continue

            rows.append(
                {
                    "occurred_at": occurred_at,
                    "event_type": event.type.value,
                    "session_id": str(session_id),
                    "job_id": str(event.job_id) if event.job_id else None,
                    "source_id": str(attributes.source_id)
                    if attributes and attributes.source_id
                    else None,
                    "category_id": str(attributes.category_id)
                    if attributes and attributes.category_id
                    else None,
                    "location_id": str(attributes.location_id)
                    if attributes and attributes.location_id
                    else None,
                    "filters": json.dumps(event.filters or {}),
                    "referrer_host": host,
                    "device_type": device.value if device else None,
                    "country": (country or "")[:2].upper() or None,
                }
            )

            counter = COUNTER_FOR_EVENT.get(event.type)
            if counter and event.job_id:
                counter_deltas.setdefault(event.job_id, {}).setdefault(counter, 0)
                counter_deltas[event.job_id][counter] += 1

        accepted = await self.repo.record_events(rows)

        for job_id, deltas in counter_deltas.items():
            await self.jobs.adjust_counters(job_id, **deltas)

        return IngestResult(accepted=accepted, rejected=rejected)

    # --- reporting --------------------------------------------------------

    async def overview(self, window: DateWindow) -> dict[str, Any]:
        """The dashboard's headline numbers.

        Reads rollups for behaviour and `search_logs` for search. Those are two
        tables on purpose: search rows carry result counts, degradation flags
        and latency that no event row has, and duplicating them into the rollup
        would create a second source of truth for one number.
        """
        totals = await self.repo.totals(since=window.since, until=window.until)
        series = await self.repo.series(since=window.since, until=window.until)
        top_jobs = await self.repo.top_jobs(since=window.since, until=window.until, limit=10)
        top_queries = await self.searches.top_queries(since=window.since, limit=10)
        zero_result = await self.searches.zero_result_queries(since=window.since, limit=10)

        searches = sum(count for _, count, _ in top_queries)
        zero_searches = sum(count for _, count in zero_result)

        return {
            "range": {"from": window.since, "to": window.until},
            "totals": {
                "job_views": totals["views"],
                "apply_clicks": totals["apply_clicks"],
                "shares": totals["shares"],
                "source_clicks": totals["source_clicks"],
                "saves": totals["saves"],
                "reports": totals["reports"],
                "searches": searches,
                "zero_result_searches": zero_searches,
            },
            "rates": {
                "view_to_apply": _rate(totals["apply_clicks"], totals["views"]),
                "save_rate": _rate(totals["saves"], totals["views"]),
                "zero_result_rate": _rate(zero_searches, searches),
            },
            "series": [
                {"date": day, "job_views": views, "apply_clicks": clicks}
                for day, views, clicks in series
            ],
            "top_jobs": [_with_ctr(job) for job in top_jobs],
            "top_queries": [
                {"query": q, "count": n, "zero_result_count": z} for q, n, z in top_queries
            ],
        }

    async def traffic(self, window: DateWindow, *, locations: int = 5) -> dict[str, Any]:
        """Audience shape: how many visits, how long, how many left at once.

        Deliberately not folded into `overview`. That method reports on
        *listings* and reads the rollups; this one reports on *sessions* and
        has to read the raw events, because a session is not something a
        per-job daily counter can describe. Two questions, two grains, two
        methods — merging them would hide a much more expensive query behind a
        name that promises a cheap one.

        The location breakdown rides along because it answers the same
        editorial question the tiles do — where the audience is — and the panel
        that renders it sits on the same screen. Its source is stated in
        `AnalyticsRepository.top_locations`: the rollups, not the events.

        `bounce_rate` is computed here rather than in SQL for the reason every
        other rate in this file is: a stored or hand-rolled ratio eventually
        disagrees with the two numbers it came from, and both of those numbers
        are already in the response for the reader to check.
        """
        summary = await self.repo.traffic(since=window.since, until=window.until)
        top = await self.repo.top_locations(since=window.since, until=window.until, limit=locations)
        sessions = summary["unique_sessions"]
        return {
            "range": {"from": window.since, "to": window.until},
            "page_views": summary["page_views"],
            "unique_sessions": sessions,
            # Rounded to whole seconds. Sub-second precision on an average
            # built from browser-reported activity is false confidence.
            "avg_session_seconds": round(summary["avg_session_seconds"]),
            "bounce_rate": _rate(summary["bounced_sessions"], sessions),
            "views_per_session": _rate(summary["page_views"], sessions),
            "top_locations": [
                {
                    "location_id": row["location_id"],
                    "name": row["name"],
                    "slug": row["slug"],
                    "views": row["views"],
                    "apply_clicks": row["apply_clicks"],
                    "share": _rate(row["views"], row["total_views"]),
                }
                for row in top
            ],
        }

    async def visitor_trends(self) -> dict[str, Any]:
        """Today, the last seven days, the last thirty — each against the
        period before it.

        Anchored to today rather than to a caller-supplied window, which is why
        this is not part of `traffic`: "last week" is only meaningful relative
        to now, and a `from`/`to` pair would make the comparison arbitrary.

        Each period is counted independently. See `VISITOR_PERIODS` for why a
        week is not the sum of its days.
        """
        today = datetime.now(UTC).date()
        counts = await self.repo.visitor_trends(today=today)

        def period(name: str) -> dict[str, Any]:
            visitors = counts[f"{name}_visitors"]
            previous = counts[f"{name}_prev_visitors"]
            return {
                "visitors": visitors,
                "page_views": counts[f"{name}_views"],
                "views_per_session": _rate(counts[f"{name}_views"], visitors),
                "previous_visitors": previous,
                "change": _change(visitors, previous),
            }

        return {
            "as_of": today,
            "daily": period("daily"),
            "weekly": period("weekly"),
            "monthly": period("monthly"),
        }

    async def job_performance(self, window: DateWindow, *, limit: int = 50) -> list[dict[str, Any]]:
        jobs = await self.repo.top_jobs(since=window.since, until=window.until, limit=limit)
        return [_with_ctr(job) for job in jobs]

    async def source_performance(self, window: DateWindow) -> list[dict[str, Any]]:
        rows = await self.repo.source_performance(since=window.since, until=window.until)
        return [
            {
                **row,
                # Apply rate per source — the number that says whether a feed
                # is worth the integration effort.
                "ctr": _rate(row["apply_clicks"], row["views"]),
                "apply_rate_per_job": _rate(row["apply_clicks"], row["jobs"]),
                "report_rate": _rate(row["reports"], row["jobs"]),
            }
            for row in rows
        ]

    async def search_analytics(self, window: DateWindow) -> dict[str, Any]:
        """Search health, straight from `search_logs`."""
        top = await self.searches.top_queries(since=window.since, limit=25)
        zero = await self.searches.zero_result_queries(since=window.since, limit=25)
        since_dt = datetime.combine(window.since, datetime.min.time(), tzinfo=UTC)
        p50 = await self.searches.latency_percentile(since=since_dt, percentile=0.50)
        p95 = await self.searches.latency_percentile(since=since_dt, percentile=0.95)

        searches = sum(count for _, count, _ in top)
        zero_total = sum(count for _, count in zero)

        return {
            "range": {"from": window.since, "to": window.until},
            "total_searches": searches,
            "zero_result_searches": zero_total,
            "zero_result_rate": _rate(zero_total, searches),
            "latency_p50_ms": p50,
            "latency_p95_ms": p95,
            "top_queries": [{"query": q, "count": n, "zero_result_count": z} for q, n, z in top],
            # The most actionable list on the dashboard: demand the catalogue
            # cannot meet, ranked by how many people wanted it.
            "zero_result_queries": [{"query": q, "count": n} for q, n in zero],
        }

    # --- maintenance (called by the scheduler) ---------------------------

    async def rebuild_rollups(self, *, days: int = 2) -> dict[str, int]:
        """Recompute the last `days` days, today included.

        Today is always incomplete, so it is rebuilt every run rather than
        finalised once. Replacing instead of incrementing is what makes that
        safe — see `AnalyticsRepository.rebuild_day`.
        """
        today = datetime.now(UTC).date()
        written: dict[str, int] = {}
        for offset in range(days):
            day = today - timedelta(days=offset)
            written[day.isoformat()] = await self.repo.rebuild_day(day)
        return written

    async def backfill_rollups(self, *, since: date, until: date) -> int:
        total = 0
        day = since
        while day <= until:
            total += await self.repo.rebuild_day(day)
            day += timedelta(days=1)
        return total


def _with_ctr(job: dict[str, Any]) -> dict[str, Any]:
    return {**job, "ctr": _rate(job["apply_clicks"], job["views"])}


def _clamp_time(supplied: datetime | None, now: datetime) -> datetime | None:
    """Validate a client-supplied timestamp, or reject it.

    A client clock is not trustworthy, and an event dated 2019 would be routed
    to a partition that no longer exists — an insert failure rather than a bad
    number. Rejecting here keeps the batch insert unconditional.
    """
    if supplied is None:
        return now
    stamped = supplied if supplied.tzinfo else supplied.replace(tzinfo=UTC)
    if stamped > now + MAX_FUTURE_SKEW:
        return None
    if stamped < now - MAX_BACKDATE:
        return None
    return stamped


def _referrer_host(referrer: str | None) -> str | None:
    """Host only. The full referrer carries query strings, which carry
    everything from search terms to session tokens."""
    if not referrer:
        return None
    from urllib.parse import urlparse

    try:
        host = urlparse(referrer).hostname
    except ValueError:
        return None
    return host[:255] if host else None


__all__ = ["AnalyticsService", "DateWindow", "IngestResult", "resolve_window"]
