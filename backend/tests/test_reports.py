"""Milestone 5 behavioural tests.

Two surfaces with opposite threat models share one table, so the tests are
split the same way. The submission tests are mostly about what the endpoint
*refuses* — it is the only unauthenticated write in the API. The moderation
tests are about the workflow staying coherent and every decision being
attributable afterwards.
"""

from __future__ import annotations

import asyncio
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, func, select

from app.core.config import settings
from app.core.enums import JobStatus
from app.core.permissions import SystemRole
from app.core.security import hash_password
from app.db.database import SessionFactory
from app.main import app
from app.models.admin import Admin, AdminSession
from app.models.audit import AuditLog
from app.models.job import Job
from app.models.rbac import Role
from app.models.report import Report
from app.models.taxonomy import Category, Location, Source
from app.services.report_service import ReportService

ADMIN_EMAIL = "m5-admin@rozgar.pk"
ANALYST_EMAIL = "m5-analyst@rozgar.pk"
PASSWORD = "milestone-five-pass"
LOGIN = "/api/v1/auth/login"
REPORTS = "/api/v1/reports"
ADMIN_REPORTS = "/api/v1/admin/reports"


async def _seed() -> dict:
    """One admin, one analyst, and four listings in four states."""
    async with SessionFactory() as s:
        # Every report in the schema belongs to a job, and the rate limiter
        # counts by address hash across all of them — so a leftover row from an
        # earlier run is not inert, it eats this run's budget.
        await s.execute(delete(Report))
        for email in (ADMIN_EMAIL, ANALYST_EMAIL):
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
            full_name="M5 Admin",
            password_hash=hash_password(PASSWORD),
            role_id=roles[SystemRole.ADMIN.value].id,
            is_active=True,
        )
        analyst = Admin(
            email=ANALYST_EMAIL,
            full_name="M5 Analyst",
            password_hash=hash_password(PASSWORD),
            role_id=roles[SystemRole.ANALYST.value].id,
            is_active=True,
        )
        s.add_all([admin, analyst])

        category = (
            await s.execute(select(Category).where(Category.slug == "m5-tech"))
        ).scalar_one_or_none() or Category(name="M5 Tech", slug="m5-tech", job_count=0)
        location = (
            await s.execute(select(Location).where(Location.slug == "m5-karachi"))
        ).scalar_one_or_none() or Location(
            city="Karachi",
            country="PK",
            slug="m5-karachi",
            display_name="Karachi, Pakistan",
            job_count=0,
        )
        s.add_all([category, location])
        source = (await s.execute(select(Source).where(Source.slug == "manual"))).scalar_one()
        await s.flush()

        def job(slug: str, title: str, status: JobStatus, **extra) -> Job:
            return Job(
                slug=slug,
                title=title,
                company_name="Reportable Co",
                category_id=category.id,
                location_id=location.id,
                source_id=source.id,
                work_type="on_site",
                employment_type="full_time",
                experience_level="mid",
                description=(
                    "A listing used by the Milestone 5 report tests. It needs "
                    "at least fifty characters to satisfy the description "
                    "length constraint."
                ),
                apply_url="https://example.com/apply",
                status=status,
                created_by=admin.id,
                **extra,
            )

        now = func.now()
        published = job("m5-published", "Published Role", JobStatus.PUBLISHED, published_at=now)
        second = job("m5-second", "Second Role", JobStatus.PUBLISHED, published_at=now)
        expired = job("m5-expired", "Expired Role", JobStatus.EXPIRED, published_at=now)
        draft = job("m5-draft", "Draft Role", JobStatus.DRAFT)
        removed = job("m5-removed", "Removed Role", JobStatus.PUBLISHED, published_at=now)
        s.add_all([published, second, expired, draft, removed])
        await s.flush()
        removed.deleted_at = func.now()
        await s.commit()

        return {
            "published": str(published.id),
            "second": str(second.id),
            "expired": str(expired.id),
            "draft": str(draft.id),
            "removed": str(removed.id),
            "admin_id": str(admin.id),
        }


@pytest.fixture
def world():
    return asyncio.run(_seed())


@pytest.fixture
def client(world):
    with TestClient(app) as c:
        yield c


@pytest.fixture
def tight_rate_limit():
    """Two submissions per window, so the limiter is testable in three calls."""
    original = settings.report_rate_limit_per_window
    settings.report_rate_limit_per_window = 2
    yield
    settings.report_rate_limit_per_window = original


def token_for(client: TestClient, email: str) -> str:
    r = client.post(LOGIN, json={"email": email, "password": PASSWORD})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


def auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def submit(client: TestClient, job_id: str, **overrides):
    body = {"job_id": job_id, "reason": "broken_link", "session_id": str(uuid4())}
    body.update(overrides)
    return client.post(REPORTS, json=body)


def audit_rows(entity_id: str | None = None) -> list[AuditLog]:
    async def run() -> list[AuditLog]:
        async with SessionFactory() as s:
            stmt = select(AuditLog).where(AuditLog.entity_type == "report")
            if entity_id is not None:
                stmt = stmt.where(AuditLog.entity_id == entity_id)
            return list((await s.execute(stmt.order_by(AuditLog.id))).scalars().all())

    return asyncio.run(run())


# --- public submission ----------------------------------------------------


def test_submission_is_accepted_without_authentication(client, world):
    r = submit(client, world["published"], reason="expired")
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["status"] == "open"
    assert set(body) == {"id", "status"}, "the public response must stay an acknowledgement"


def test_expired_listing_is_reportable(client, world):
    """The single most common report is "this job has expired" — an endpoint
    that refuses expired listings refuses its own busiest case."""
    assert submit(client, world["expired"], reason="expired").status_code == 201


@pytest.mark.parametrize("target", ["draft", "removed"])
def test_unpublished_listings_are_indistinguishable_from_unknown(client, world, target):
    """A 422 saying "not published yet" would turn this endpoint into an
    oracle for the editorial pipeline."""
    assert submit(client, world[target]).status_code == 404


def test_unknown_listing_is_a_404(client):
    assert submit(client, str(uuid4())).status_code == 404


def test_same_session_cannot_report_one_listing_twice(client, world):
    session_id = str(uuid4())
    assert submit(client, world["published"], session_id=session_id).status_code == 201
    second = submit(client, world["published"], session_id=session_id, reason="duplicate")
    assert second.status_code == 409
    assert second.json()["type"].endswith("duplicate_report")


def test_duplicate_is_caught_without_a_session_id(client, world):
    """The unique index is partial — `WHERE session_id IS NOT NULL`. Without
    the service-side fallback a client that simply omits the field would be
    able to file the same report indefinitely."""
    body = {"job_id": world["published"], "reason": "broken_link"}
    assert client.post(REPORTS, json=body).status_code == 201
    assert client.post(REPORTS, json=body).status_code == 409


def test_duplicate_check_is_scoped_to_one_listing(client, world):
    session_id = str(uuid4())
    assert submit(client, world["published"], session_id=session_id).status_code == 201
    assert submit(client, world["second"], session_id=session_id).status_code == 201


def test_rate_limit_returns_429_with_retry_after(client, world, tight_rate_limit):
    for _ in range(settings.report_rate_limit_per_window):
        assert submit(client, world["published"]).status_code == 201

    blocked = submit(client, world["second"])
    assert blocked.status_code == 429
    assert blocked.headers["Retry-After"] == str(settings.report_rate_limit_window_minutes * 60)


def test_other_reason_requires_a_comment(client, world):
    r = submit(client, world["published"], reason="other", comment=None)
    assert r.status_code == 422
    assert "comment" in r.text


def test_renamed_reasons_are_accepted(client, world):
    for reason in ("suspicious", "incorrect_information"):
        r = submit(client, world["published"], reason=reason)
        assert r.status_code == 201, f"{reason}: {r.text}"


def test_public_submission_writes_no_audit_entry(client, world):
    before = len(audit_rows())
    assert submit(client, world["published"]).status_code == 201
    assert len(audit_rows()) == before, (
        "public submissions are their own record; mirroring them into the "
        "audit trail buries the moderator actions it exists for"
    )


def test_reporter_identifiers_are_never_returned(client, world):
    session_id = str(uuid4())
    submit(client, world["published"], session_id=session_id, reporter_email="a@example.com")
    t = token_for(client, ADMIN_EMAIL)
    queue = client.get(ADMIN_REPORTS, headers=auth(t)).text
    assert session_id not in queue
    for leaked in ("reporter_ip_hash", "session_id", "reporter_email"):
        assert leaked not in queue


# --- moderation queue -----------------------------------------------------


def test_queue_requires_report_view(client, world):
    submit(client, world["published"])
    assert client.get(ADMIN_REPORTS).status_code == 401


def test_queue_filters_and_orders_newest_first(client, world):
    submit(client, world["published"], reason="expired")
    submit(client, world["second"], reason="suspicious")
    t = token_for(client, ADMIN_EMAIL)

    everything = client.get(ADMIN_REPORTS, headers=auth(t)).json()
    assert everything["total"] == 2
    assert [i["reason"] for i in everything["items"]] == ["suspicious", "expired"]

    filtered = client.get(f"{ADMIN_REPORTS}?reason=expired", headers=auth(t)).json()
    assert filtered["total"] == 1
    assert filtered["items"][0]["job"]["slug"] == "m5-published"

    by_status = client.get(f"{ADMIN_REPORTS}?status=resolved", headers=auth(t)).json()
    assert by_status["total"] == 0


def test_queue_does_not_n_plus_one(client, world):
    """`Report.job` is `selectin`, and `Job` eager-loads four relations of its
    own. Left at the defaults a page of reports costs six queries to render a
    four-field job reference; the explicit join collapses it to two."""
    for _ in range(8):
        body = {"job_id": world["published"], "reason": "broken_link", "session_id": str(uuid4())}
        assert client.post(REPORTS, json=body).status_code == 201

    async def count_queries(per_page: int) -> int:
        from sqlalchemy import event

        from app.db.database import engine
        from app.repositories.report_repo import ReportFilters
        from app.services.report_service import ReportService

        counter = {"n": 0}

        def before(conn, cursor, statement, *args):
            if statement.lstrip().upper().startswith("SELECT"):
                counter["n"] += 1

        sync_engine = engine.sync_engine
        event.listen(sync_engine, "before_cursor_execute", before)
        try:
            async with SessionFactory() as s:
                await ReportService(s).list_queue(ReportFilters(), page=1, per_page=per_page)
        finally:
            event.remove(sync_engine, "before_cursor_execute", before)
        return counter["n"]

    small = asyncio.run(count_queries(2))
    large = asyncio.run(count_queries(8))
    assert small == large, (
        f"query count grew with page size ({small} -> {large}); the job "
        "reference is loading per row"
    )
    assert large == 2, f"expected one count and one page query, got {large}"


# --- moderation workflow --------------------------------------------------


def _open_report(client: TestClient, world: dict) -> str:
    r = submit(client, world["published"])
    assert r.status_code == 201, r.text
    return r.json()["id"]


def test_full_workflow_open_to_resolved(client, world):
    report_id = _open_report(client, world)
    t = token_for(client, ADMIN_EMAIL)

    review = client.patch(
        f"{ADMIN_REPORTS}/{report_id}", json={"status": "under_review"}, headers=auth(t)
    )
    assert review.status_code == 200, review.text
    assert review.json()["status"] == "under_review"
    assert review.json()["resolved_by"] is None

    resolved = client.patch(
        f"{ADMIN_REPORTS}/{report_id}",
        json={"status": "resolved", "resolution_note": "Apply link corrected."},
        headers=auth(t),
    )
    assert resolved.status_code == 200, resolved.text
    body = resolved.json()
    assert body["status"] == "resolved"
    assert body["resolution_note"] == "Apply link corrected."
    assert body["resolved_by"] == world["admin_id"]
    assert body["resolved_at"] is not None


def test_resolved_cannot_go_straight_back_to_open(client, world):
    report_id = _open_report(client, world)
    t = token_for(client, ADMIN_EMAIL)
    client.patch(
        f"{ADMIN_REPORTS}/{report_id}",
        json={"status": "dismissed", "resolution_note": "Listing is fine."},
        headers=auth(t),
    )
    rejected = client.patch(
        f"{ADMIN_REPORTS}/{report_id}", json={"status": "open"}, headers=auth(t)
    )
    assert rejected.status_code == 422
    assert rejected.json()["type"].endswith("invalid_report_transition")
    assert "under_review" in rejected.json()["detail"]


def test_reopening_clears_the_resolution(client, world):
    """A note left behind on a reopened report reads as current guidance, and
    the next moderator acts on it."""
    report_id = _open_report(client, world)
    t = token_for(client, ADMIN_EMAIL)
    client.patch(
        f"{ADMIN_REPORTS}/{report_id}",
        json={"status": "resolved", "resolution_note": "Employer fixed the link."},
        headers=auth(t),
    )
    reopened = client.patch(
        f"{ADMIN_REPORTS}/{report_id}", json={"status": "under_review"}, headers=auth(t)
    )
    assert reopened.status_code == 200, reopened.text
    body = reopened.json()
    assert body["resolution_note"] is None
    assert body["resolved_by"] is None
    assert body["resolved_at"] is None

    # Nothing is lost — the superseded values are in the audit trail.
    before_values = [row.before for row in audit_rows(report_id)]
    assert any(v and v.get("resolution_note") == "Employer fixed the link." for v in before_values)


def test_resolving_without_a_note_is_rejected(client, world):
    report_id = _open_report(client, world)
    t = token_for(client, ADMIN_EMAIL)
    r = client.patch(f"{ADMIN_REPORTS}/{report_id}", json={"status": "resolved"}, headers=auth(t))
    assert r.status_code == 422
    assert "resolution_note" in r.text


def test_note_on_a_non_terminal_transition_is_rejected(client, world):
    """Reopening clears the note, so accepting one here would write it and
    immediately discard it."""
    report_id = _open_report(client, world)
    t = token_for(client, ADMIN_EMAIL)
    r = client.patch(
        f"{ADMIN_REPORTS}/{report_id}",
        json={"status": "under_review", "resolution_note": "looking into it"},
        headers=auth(t),
    )
    assert r.status_code == 422


def test_empty_patch_is_rejected(client, world):
    report_id = _open_report(client, world)
    t = token_for(client, ADMIN_EMAIL)
    assert client.patch(f"{ADMIN_REPORTS}/{report_id}", json={}, headers=auth(t)).status_code == 422


# --- audit ----------------------------------------------------------------


def test_each_decision_records_its_own_verb(client, world):
    report_id = _open_report(client, world)
    t = token_for(client, ADMIN_EMAIL)
    client.patch(f"{ADMIN_REPORTS}/{report_id}", json={"status": "under_review"}, headers=auth(t))
    client.patch(
        f"{ADMIN_REPORTS}/{report_id}",
        json={"status": "dismissed", "resolution_note": "Duplicate of an earlier report."},
        headers=auth(t),
    )
    client.patch(f"{ADMIN_REPORTS}/{report_id}", json={"status": "under_review"}, headers=auth(t))

    rows = audit_rows(report_id)
    assert [r.action for r in rows] == [
        "report.review",
        "report.dismiss",
        # Not "review" again: arriving at under_review from a decided state
        # means the earlier decision was wrong, which is the event worth
        # being able to count.
        "report.reopen",
    ], "a single report.update verb would make 'how many did we dismiss?' a JSONB scan"
    assert all(r.admin_id is not None for r in rows)
    assert rows[1].before["status"] == "under_review"
    assert rows[1].after["status"] == "dismissed"


def test_audit_entries_never_carry_reporter_identifiers(client, world):
    report_id = _open_report(client, world)
    t = token_for(client, ADMIN_EMAIL)
    client.patch(f"{ADMIN_REPORTS}/{report_id}", json={"status": "under_review"}, headers=auth(t))
    for row in audit_rows(report_id):
        assert "reporter_ip_hash" not in (row.after or {})
        assert "session_id" not in (row.after or {})


def test_no_op_patch_writes_no_audit_entry(client, world):
    report_id = _open_report(client, world)
    t = token_for(client, ADMIN_EMAIL)
    client.patch(f"{ADMIN_REPORTS}/{report_id}", json={"status": "under_review"}, headers=auth(t))
    before = len(audit_rows(report_id))

    repeat = client.patch(
        f"{ADMIN_REPORTS}/{report_id}", json={"status": "under_review"}, headers=auth(t)
    )
    assert repeat.status_code == 200
    assert len(audit_rows(report_id)) == before, "a PATCH that changes nothing is not an event"


def test_note_edit_is_recorded_separately(client, world):
    report_id = _open_report(client, world)
    t = token_for(client, ADMIN_EMAIL)
    client.patch(
        f"{ADMIN_REPORTS}/{report_id}",
        json={"status": "resolved", "resolution_note": "Fixed."},
        headers=auth(t),
    )
    edited = client.patch(
        f"{ADMIN_REPORTS}/{report_id}",
        json={"resolution_note": "Fixed — employer confirmed by email."},
        headers=auth(t),
    )
    assert edited.status_code == 200, edited.text
    assert edited.json()["status"] == "resolved"
    assert audit_rows(report_id)[-1].action == "report.note_edit"


# --- authorisation --------------------------------------------------------


def test_report_view_alone_cannot_moderate(client, world):
    """The analyst role holds REPORT_VIEW and not REPORT_RESOLVE — read-only
    access to the queue is a real position, not a degenerate one."""
    report_id = _open_report(client, world)
    t = token_for(client, ANALYST_EMAIL)

    assert client.get(ADMIN_REPORTS, headers=auth(t)).status_code == 200
    assert client.get(f"{ADMIN_REPORTS}/{report_id}", headers=auth(t)).status_code == 200

    denied = client.patch(
        f"{ADMIN_REPORTS}/{report_id}", json={"status": "under_review"}, headers=auth(t)
    )
    assert denied.status_code == 403
    assert denied.json()["detail"].startswith("This action requires the REPORT_RESOLVE")


def test_unknown_report_is_a_404(client):
    with TestClient(app) as c:
        t = token_for(c, ADMIN_EMAIL)
        assert c.get(f"{ADMIN_REPORTS}/{uuid4()}", headers=auth(t)).status_code == 404
        r = c.patch(f"{ADMIN_REPORTS}/{uuid4()}", json={"status": "under_review"}, headers=auth(t))
        assert r.status_code == 404


def test_report_status_enum_is_exposed_with_the_product_wording(client, world):
    """The workflow states are `under_review`, not `in_review`."""
    schema = client.get("/openapi.json").json()
    assert set(schema["components"]["schemas"]["ReportStatus"]["enum"]) == {
        "open",
        "under_review",
        "resolved",
        "dismissed",
    }
    assert set(schema["components"]["schemas"]["ReportReason"]["enum"]) == {
        "broken_link",
        "suspicious",
        "expired",
        "incorrect_information",
        "duplicate",
        "other",
    }


# --- concurrency ----------------------------------------------------------


def test_concurrent_decisions_are_serialised(client, world):
    """Two moderators deciding the same report at the same moment.

    `reports` has no version column, so there is no If-Match path as there is
    on jobs — the row lock is the whole defence. Without it both transitions
    read `open`, both succeed, and the audit trail ends up with an entry
    claiming an open->dismissed transition that never happened.
    """
    report_id = _open_report(client, world)

    async def decide(status: str, note: str) -> str:
        from app.core.exceptions import DomainError
        from app.services.auth_service import Principal

        async with SessionFactory() as s:
            admin_id = (
                await s.execute(select(Admin.id).where(Admin.email == ADMIN_EMAIL))
            ).scalar_one()
            principal = Principal(
                admin_id=admin_id,
                email=ADMIN_EMAIL,
                full_name="M5 Admin",
                role_key=SystemRole.ADMIN.value,
                permissions=frozenset({"REPORT_VIEW", "REPORT_RESOLVE"}),
            )
            try:
                await ReportService(s).moderate(
                    report_id,
                    {"status": status, "resolution_note": note},
                    principal=principal,
                )
                await s.commit()
                return "applied"
            except DomainError as exc:
                await s.rollback()
                return exc.code

    async def race() -> list[str]:
        return list(
            await asyncio.gather(
                decide("resolved", "Link was fixed."),
                decide("dismissed", "Nothing wrong with it."),
            )
        )

    outcomes = asyncio.run(asyncio.wait_for(race(), timeout=30))

    assert sorted(outcomes) == ["applied", "invalid_report_transition"], (
        f"expected exactly one decision to land, got {outcomes}"
    )
    actions = [r.action for r in audit_rows(report_id)]
    assert len(actions) == 1, f"the losing decision still wrote to the trail: {actions}"
