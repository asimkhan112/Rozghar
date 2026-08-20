"""Milestone 6 behavioural tests.

The ingest tests are mostly about what the endpoint *refuses* and what it
*derives*, because it is unauthenticated and its output drives spend decisions.
The reporting tests pin the two properties that make the rollup trustworthy:
it is idempotent, and it agrees with the raw events it came from.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, date, datetime, time, timedelta
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select, text

from app.core.permissions import SystemRole
from app.core.security import hash_password
from app.db.database import SessionFactory
from app.main import app
from app.models.admin import Admin, AdminSession
from app.models.analytics import AnalyticsDailyRollup
from app.models.audit import AuditLog
from app.models.job import Job
from app.models.rbac import Role
from app.models.taxonomy import Category, Location, Source
from app.services.analytics_service import AnalyticsService, resolve_window

ADMIN_EMAIL = "m6-admin@plenilo.com"
EDITOR_EMAIL = "m6-editor@plenilo.com"
PASSWORD = "milestone-six-pass"
LOGIN = "/api/v1/auth/login"
EVENTS = "/api/v1/analytics/events"
DASH = "/api/v1/admin/analytics"


async def _seed() -> dict:
    async with SessionFactory() as s:
        await s.execute(text("DELETE FROM analytics_events"))
        await s.execute(delete(AnalyticsDailyRollup))
        for email in (ADMIN_EMAIL, EDITOR_EMAIL):
            existing = (
                await s.execute(select(Admin).where(Admin.email == email))
            ).scalar_one_or_none()
            if existing:
                await s.execute(delete(AdminSession).where(AdminSession.admin_id == existing.id))
                await s.execute(delete(AuditLog).where(AuditLog.admin_id == existing.id))
                await s.execute(delete(Job).where(Job.created_by == existing.id))
                await s.delete(existing)
        await s.commit()

        roles = {r.key: r for r in (await s.execute(select(Role))).scalars().all()}
        admin = Admin(
            email=ADMIN_EMAIL,
            full_name="M6 Admin",
            password_hash=hash_password(PASSWORD),
            role_id=roles[SystemRole.ADMIN.value].id,
            is_active=True,
        )
        # Editor holds no ANALYTICS_VIEW — the negative case for the dashboards.
        editor = Admin(
            email=EDITOR_EMAIL,
            full_name="M6 Editor",
            password_hash=hash_password(PASSWORD),
            role_id=roles[SystemRole.EDITOR.value].id,
            is_active=True,
        )
        s.add_all([admin, editor])

        category = (
            await s.execute(select(Category).where(Category.slug == "m6-tech"))
        ).scalar_one_or_none() or Category(name="M6 Tech", slug="m6-tech", job_count=0)
        location = (
            await s.execute(select(Location).where(Location.slug == "m6-lahore"))
        ).scalar_one_or_none() or Location(
            city="Lahore", country="PK", slug="m6-lahore", display_name="Lahore, PK", job_count=0
        )
        s.add_all([category, location])
        source = (await s.execute(select(Source).where(Source.slug == "manual"))).scalar_one()
        await s.flush()

        def job(slug: str, title: str, **extra) -> Job:
            return Job(
                slug=slug,
                title=title,
                company_name="Metrics Co",
                category_id=category.id,
                location_id=location.id,
                source_id=source.id,
                work_type="remote",
                employment_type="full_time",
                experience_level="mid",
                description=(
                    "A listing used by the Milestone 6 analytics tests. It needs at "
                    "least fifty characters to satisfy the description constraint."
                ),
                apply_url="https://example.com/apply",
                status="published",
                published_at=datetime.now(UTC),
                created_by=admin.id,
                **extra,
            )

        popular = job("m6-popular", "Popular Role")
        quiet = job("m6-quiet", "Quiet Role")
        draft = job("m6-draft", "Draft Role")
        draft.status = "draft"
        draft.published_at = None
        s.add_all([popular, quiet, draft])
        await s.commit()

        return {
            "popular": str(popular.id),
            "quiet": str(quiet.id),
            "draft": str(draft.id),
            "source_id": str(source.id),
        }


@pytest.fixture
def world():
    return asyncio.run(_seed())


@pytest.fixture
def client(world):
    with TestClient(app) as c:
        yield c


def token_for(client: TestClient, email: str) -> str:
    r = client.post(LOGIN, json={"email": email, "password": PASSWORD})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


def auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def send(client: TestClient, events: list[dict], **headers) -> dict:
    r = client.post(
        EVENTS, json={"session_id": str(uuid4()), "events": events}, headers=headers or None
    )
    assert r.status_code == 202, r.text
    return r.json()


def rollup() -> None:
    async def run() -> None:
        async with SessionFactory() as s:
            await AnalyticsService(s).rebuild_rollups(days=1)
            await s.commit()

    asyncio.run(run())


# --- ingest ---------------------------------------------------------------


def test_ingest_is_anonymous_and_batched(client, world):
    body = send(
        client,
        [
            {"type": "job_view", "job_id": world["popular"]},
            {"type": "apply_click", "job_id": world["popular"]},
            {"type": "share", "job_id": world["popular"]},
            {"type": "source_click", "job_id": world["popular"]},
        ],
    )
    assert body == {"accepted": 4, "rejected": 0}


def test_bad_rows_do_not_reject_the_whole_batch(client, world):
    """One stale client build must not be able to zero a day of data."""
    body = send(
        client,
        [
            {"type": "job_view", "job_id": world["popular"]},
            {"type": "job_view", "job_id": str(uuid4())},  # unknown job
            {
                "type": "job_view",
                "job_id": world["popular"],
                "occurred_at": "2019-01-01T00:00:00Z",  # older than the backdate window
            },
        ],
    )
    assert body == {"accepted": 1, "rejected": 2}


def test_future_timestamps_are_rejected(client, world):
    ahead = (datetime.now(UTC) + timedelta(days=1)).isoformat()
    body = send(client, [{"type": "job_view", "job_id": world["popular"], "occurred_at": ahead}])
    assert body["rejected"] == 1


def test_attribution_is_derived_server_side(client, world):
    """The client says what happened; the server decides what it is attributed
    to. This endpoint needs no credentials, and attribution drives spend."""
    send(client, [{"type": "job_view", "job_id": world["popular"]}])

    async def read():
        async with SessionFactory() as s:
            return (
                await s.execute(
                    text(
                        "SELECT source_id, category_id, location_id, device_type, referrer_host "
                        "FROM analytics_events LIMIT 1"
                    )
                )
            ).one()

    source_id, category_id, location_id, *_ = asyncio.run(read())
    assert source_id is not None
    assert category_id is not None
    assert location_id is not None


def test_device_and_referrer_are_derived_from_headers(client, world):
    send(
        client,
        [{"type": "job_view", "job_id": world["popular"]}],
        **{
            "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0)",
            "Referer": "https://www.google.com/search?q=secret+search+terms",
        },
    )

    async def read():
        async with SessionFactory() as s:
            return (
                await s.execute(
                    text("SELECT device_type, referrer_host FROM analytics_events LIMIT 1")
                )
            ).one()

    device, host = asyncio.run(read())
    assert device == "mobile"
    # Host only — the full referrer carries query strings, which carry search
    # terms and sometimes session tokens.
    assert host == "www.google.com"
    assert "secret" not in (host or "")


def test_ingest_moves_the_denormalised_job_counters(client, world):
    send(
        client,
        [
            {"type": "job_view", "job_id": world["popular"]},
            {"type": "job_view", "job_id": world["popular"]},
            {"type": "apply_click", "job_id": world["popular"]},
        ],
    )

    async def read():
        async with SessionFactory() as s:
            return (
                await s.execute(
                    text("SELECT view_count, apply_click_count FROM jobs WHERE id = :i"),
                    {"i": world["popular"]},
                )
            ).one()

    views, applies = asyncio.run(read())
    assert (views, applies) == (2, 1)


def test_oversized_batch_is_rejected(client, world):
    r = client.post(
        EVENTS,
        json={
            "session_id": str(uuid4()),
            "events": [{"type": "job_view", "job_id": world["popular"]}] * 51,
        },
    )
    assert r.status_code == 422


def test_renamed_event_types_are_the_ones_exposed(client):
    schema = client.get("/openapi.json").json()
    assert set(schema["components"]["schemas"]["EventType"]["enum"]) == {
        "job_view",
        "apply_click",
        "search",
        "share",
        "report_created",
        "source_click",
        "job_saved",
        "filter_used",
    }


# --- rollups --------------------------------------------------------------


def test_rollup_matches_the_raw_events(client, world):
    send(
        client,
        [
            {"type": "job_view", "job_id": world["popular"]},
            {"type": "job_view", "job_id": world["popular"]},
            {"type": "apply_click", "job_id": world["popular"]},
            {"type": "share", "job_id": world["popular"]},
            {"type": "job_view", "job_id": world["quiet"]},
        ],
    )
    rollup()

    async def read():
        async with SessionFactory() as s:
            rows = (
                (
                    await s.execute(
                        select(AnalyticsDailyRollup).order_by(AnalyticsDailyRollup.views.desc())
                    )
                )
                .scalars()
                .all()
            )
            return [(str(r.job_id), r.views, r.apply_clicks, r.shares) for r in rows]

    rows = asyncio.run(read())
    assert (world["popular"], 2, 1, 1) in rows
    assert (world["quiet"], 1, 0, 0) in rows


def test_rollup_is_idempotent(client, world):
    """Replacing rather than incrementing is what makes a retry safe. An
    incrementing upsert would double-count silently — the dashboard would just
    be wrong, with nothing in the logs to say so."""
    send(client, [{"type": "job_view", "job_id": world["popular"]}] * 3)
    rollup()
    rollup()
    rollup()

    async def read():
        async with SessionFactory() as s:
            return (
                await s.execute(
                    select(AnalyticsDailyRollup.views).where(
                        AnalyticsDailyRollup.job_id == world["popular"]
                    )
                )
            ).scalar_one()

    assert asyncio.run(read()) == 3


def test_unique_sessions_counts_sessions_not_events(client, world):
    for _ in range(3):
        send(client, [{"type": "job_view", "job_id": world["popular"]}] * 2)
    rollup()

    async def read():
        async with SessionFactory() as s:
            return (
                await s.execute(
                    select(AnalyticsDailyRollup.views, AnalyticsDailyRollup.unique_sessions).where(
                        AnalyticsDailyRollup.job_id == world["popular"]
                    )
                )
            ).one()

    views, sessions = asyncio.run(read())
    assert (views, sessions) == (6, 3)


# --- dashboards -----------------------------------------------------------


def test_overview_reports_totals_and_computed_rates(client, world):
    send(
        client,
        [
            {"type": "job_view", "job_id": world["popular"]},
            {"type": "job_view", "job_id": world["popular"]},
            {"type": "job_view", "job_id": world["popular"]},
            {"type": "job_view", "job_id": world["popular"]},
            {"type": "apply_click", "job_id": world["popular"]},
        ],
    )
    rollup()
    t = token_for(client, ADMIN_EMAIL)
    body = client.get(f"{DASH}/overview", headers=auth(t)).json()

    assert body["totals"]["job_views"] == 4
    assert body["totals"]["apply_clicks"] == 1
    # Rates are computed, never stored — a stored rate eventually disagrees
    # with the numbers it was derived from.
    assert body["rates"]["view_to_apply"] == 0.25
    assert body["top_jobs"][0]["slug"] == "m6-popular"
    assert body["top_jobs"][0]["ctr"] == 0.25


def test_series_fills_days_with_no_traffic(client, world):
    send(client, [{"type": "job_view", "job_id": world["popular"]}])
    rollup()
    t = token_for(client, ADMIN_EMAIL)

    # The window is relative to today, not a fixed pair of dates. Hardcoding
    # them made this pass only on the day it was written: the event is stamped
    # `now`, so a window ending yesterday contains nothing.
    today = date.today()
    since = today - timedelta(days=14)
    body = client.get(
        f"{DASH}/overview?from={since.isoformat()}&to={today.isoformat()}", headers=auth(t)
    ).json()

    # A chart missing its empty days draws a straight line across an outage.
    assert len(body["series"]) == 15
    assert sum(p["job_views"] for p in body["series"]) == 1
    assert body["series"][-1]["date"] == today.isoformat()


def test_sources_include_those_with_no_activity(client, world):
    t = token_for(client, ADMIN_EMAIL)
    rows = client.get(f"{DASH}/sources", headers=auth(t)).json()
    assert rows, "a source with no events must still appear"
    manual = next(r for r in rows if r["slug"] == "manual")
    assert manual["jobs"] >= 2
    assert "apply_rate_per_job" in manual


def test_search_dashboard_reads_search_logs(client, world):
    client.get("/api/v1/jobs?q=analytics-probe-query")
    t = token_for(client, ADMIN_EMAIL)
    body = client.get(f"{DASH}/search", headers=auth(t)).json()

    assert "latency_p95_ms" in body
    assert "zero_result_queries" in body
    queries = [q["query"] for q in body["top_queries"]]
    assert "analytics-probe-query" in queries


def test_window_is_clamped(client, world):
    """An unbounded range is not a feature — it is a table scan a client can
    trigger by omitting a parameter."""
    window = resolve_window(datetime(2000, 1, 1).date(), None)
    assert window.days <= 365


# --- traffic --------------------------------------------------------------


def traffic(client: TestClient) -> dict:
    r = client.get(f"{DASH}/traffic", headers=auth(token_for(client, ADMIN_EMAIL)))
    assert r.status_code == 200, r.text
    return r.json()


def test_traffic_is_grained_by_session_not_by_event(client, world):
    """The tiles count visits and page views, which are different numbers.

    `send` opens a new session per call, so this is one visitor who read two
    listings and applied, and one who opened a single listing and left.
    """
    send(
        client,
        [
            {"type": "job_view", "job_id": world["popular"]},
            {"type": "job_view", "job_id": world["quiet"]},
            {"type": "apply_click", "job_id": world["popular"]},
        ],
    )
    send(client, [{"type": "job_view", "job_id": world["popular"]}])

    body = traffic(client)
    # Three views out of four events: the apply click is not a page view.
    assert body["page_views"] == 3
    assert body["unique_sessions"] == 2
    assert body["views_per_session"] == 1.5


def test_bounce_is_a_session_with_one_event(client, world):
    send(client, [{"type": "job_view", "job_id": world["popular"]}])
    send(
        client,
        [
            {"type": "job_view", "job_id": world["popular"]},
            {"type": "apply_click", "job_id": world["popular"]},
        ],
    )
    assert traffic(client)["bounce_rate"] == 0.5


def test_avg_session_duration_spans_first_event_to_last(client, world):
    """Last event minus first, not a guess at dwell time on the final page."""
    now = datetime.now(UTC)
    r = client.post(
        EVENTS,
        json={
            "session_id": str(uuid4()),
            "events": [
                {
                    "type": "job_view",
                    "job_id": world["popular"],
                    "occurred_at": (now - timedelta(minutes=6)).isoformat(),
                },
                {
                    "type": "job_view",
                    "job_id": world["quiet"],
                    "occurred_at": (now - timedelta(minutes=2)).isoformat(),
                },
            ],
        },
    )
    assert r.status_code == 202, r.text
    assert traffic(client)["avg_session_seconds"] == 240


def test_traffic_is_zero_safe_before_any_traffic(client, world):
    """Every one of these is a division by the session count. A dashboard that
    500s on a quiet day is worse than one that reads zero."""
    body = traffic(client)
    assert body["page_views"] == 0
    assert body["unique_sessions"] == 0
    assert body["avg_session_seconds"] == 0
    assert body["bounce_rate"] == 0.0
    assert body["views_per_session"] == 0.0
    assert body["top_locations"] == []


def test_top_locations_come_from_traffic_not_from_the_catalogue(client, world):
    """Both listings sit in one location, so the panel reports the views they
    earned rather than the number of listings published there."""
    send(client, [{"type": "job_view", "job_id": world["popular"]}])
    send(client, [{"type": "job_view", "job_id": world["quiet"]}])
    rollup()

    locations = traffic(client)["top_locations"]
    assert [loc["name"] for loc in locations] == ["Lahore"]
    assert locations[0]["views"] == 2
    # One location holds all the located traffic in the window.
    assert locations[0]["share"] == 1.0


# --- visitors -------------------------------------------------------------


def visitors(client: TestClient) -> dict:
    r = client.get(f"{DASH}/visitors", headers=auth(token_for(client, ADMIN_EMAIL)))
    assert r.status_code == 200, r.text
    return r.json()


def utc_midnight() -> datetime:
    """Today's boundary, which is the one the endpoint counts against."""
    return datetime.combine(datetime.now(UTC).date(), time.min, tzinfo=UTC)


def write_views(rows: list[tuple[datetime, str, str]]) -> None:
    """Write view events straight to the table, past the ingest endpoint.

    Ingest refuses anything backdated more than two days, deliberately — so it
    is not a route to a populated thirty day window. These tests are about the
    reporting arithmetic, and the ingest path has its own tests above.
    """

    async def run() -> None:
        async with SessionFactory() as s:
            for occurred_at, session_id, job_id in rows:
                await s.execute(
                    text("SELECT ensure_month_partition('analytics_events', :month)"),
                    {"month": occurred_at.date()},
                )
                await s.execute(
                    text(
                        """
                        INSERT INTO analytics_events
                            (occurred_at, event_type, session_id, job_id)
                        VALUES
                            (:at, CAST('job_view' AS event_type), :sid, :jid)
                        """
                    ),
                    {"at": occurred_at, "sid": session_id, "jid": job_id},
                )
            await s.commit()

    asyncio.run(run())


def test_a_week_is_not_the_sum_of_its_days(client, world):
    """The property the whole panel rests on.

    Visitors are distinct sessions, and a distinct count is not additive. One
    reader who came back yesterday and today is two daily visitors and one
    weekly visitor — never three.
    """
    midnight = utc_midnight()
    job = world["popular"]
    returning, today_only, this_week, this_month = (str(uuid4()) for _ in range(4))
    write_views(
        [
            (midnight, returning, job),
            (midnight - timedelta(hours=1), returning, job),  # yesterday, same reader
            (midnight, today_only, job),
            (midnight, today_only, job),  # a second page, same visit
            (midnight - timedelta(days=5), this_week, job),
            (midnight - timedelta(days=20), this_month, job),
        ]
    )

    body = visitors(client)
    assert body["daily"]["visitors"] == 2
    assert body["daily"]["previous_visitors"] == 1
    # Three page views across two visits today.
    assert body["daily"]["views_per_session"] == 1.5
    # Not 3: yesterday's visitor is the same person as one of today's.
    assert body["weekly"]["visitors"] == 3
    assert body["monthly"]["visitors"] == 4


def test_change_is_undefined_rather_than_infinite(client, world):
    """Growth from nothing is not a percentage, and must not be printed as one."""
    write_views([(utc_midnight(), str(uuid4()), world["popular"])])

    body = visitors(client)
    assert body["daily"]["visitors"] == 1
    for period in ("daily", "weekly", "monthly"):
        assert body[period]["change"] is None, period


def test_change_compares_against_the_period_before(client, world):
    midnight = utc_midnight()
    job = world["popular"]
    write_views(
        [(midnight, str(uuid4()), job) for _ in range(3)]
        + [(midnight - timedelta(hours=2), str(uuid4()), job) for _ in range(2)]
    )

    daily = visitors(client)["daily"]
    assert (daily["visitors"], daily["previous_visitors"]) == (3, 2)
    assert daily["change"] == 0.5


def test_visitors_are_zero_safe_before_any_traffic(client, world):
    """Every rate here divides by a visitor count. A dashboard that 500s on a
    quiet day is worse than one that reads zero."""
    body = visitors(client)
    for period in ("daily", "weekly", "monthly"):
        assert body[period]["visitors"] == 0
        assert body[period]["page_views"] == 0
        assert body[period]["views_per_session"] == 0.0
        assert body[period]["change"] is None, period


def test_dashboards_require_analytics_view(client, world):
    t = token_for(client, EDITOR_EMAIL)
    for path in ("overview", "jobs", "sources", "search", "traffic", "visitors"):
        r = client.get(f"{DASH}/{path}", headers=auth(t))
        assert r.status_code == 403, path
    assert client.get(f"{DASH}/overview").status_code == 401
