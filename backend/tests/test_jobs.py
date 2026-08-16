"""Milestone 3 behavioural tests.

Covers the rules that are easy to get wrong and expensive to discover late:
the status machine, slug freezing, counter arithmetic, ownership scoping, and
the query count on the list endpoint — which looks fine on a handful of rows
and is a problem at a hundred thousand.
"""

from __future__ import annotations

import asyncio
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select, text

from app.core.permissions import SystemRole
from app.core.security import hash_password
from app.db.database import SessionFactory
from app.main import app
from app.models.admin import Admin, AdminSession
from app.models.audit import AuditLog
from app.models.job import Job
from app.models.rbac import Role
from app.models.taxonomy import Category, Location, Source

ADMIN_EMAIL = "m3-admin@rozgar.pk"
EDITOR_EMAIL = "m3-editor@rozgar.pk"
PASSWORD = "milestone-three-pass"
LOGIN = "/api/v1/auth/login"
JOBS = "/api/v1/jobs"
ADMIN_JOBS = "/api/v1/admin/jobs"


async def _seed() -> dict:
    """A clean world: two admins, one category, one location."""
    async with SessionFactory() as s:
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
        for email, role_key in (
            (ADMIN_EMAIL, SystemRole.ADMIN.value),
            (EDITOR_EMAIL, SystemRole.EDITOR.value),
        ):
            s.add(
                Admin(
                    email=email,
                    full_name=email,
                    password_hash=hash_password(PASSWORD),
                    role_id=roles[role_key].id,
                    is_active=True,
                )
            )

        category = (
            await s.execute(select(Category).where(Category.slug == "m3-tech"))
        ).scalar_one_or_none()
        if category is None:
            category = Category(name="M3 Tech", slug="m3-tech", job_count=0)
            s.add(category)
        location = (
            await s.execute(select(Location).where(Location.slug == "m3-lahore"))
        ).scalar_one_or_none()
        if location is None:
            location = Location(
                city="Lahore",
                country="PK",
                slug="m3-lahore",
                display_name="Lahore, Pakistan",
                job_count=0,
            )
            s.add(location)
        source = (await s.execute(select(Source).where(Source.slug == "manual"))).scalar_one()
        await s.commit()
        return {
            "category_id": str(category.id),
            "location_id": str(location.id),
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


def payload(world: dict, **overrides) -> dict:
    body = {
        "title": "Senior Backend Engineer",
        "company_name": "Systems Limited",
        "category_id": world["category_id"],
        "location_id": world["location_id"],
        "work_type": "hybrid",
        "employment_type": "full_time",
        "experience_level": "senior",
        "description": "A" * 60,
        "apply_url": "https://systemslimited.com/careers/backend",
    }
    body.update(overrides)
    return body


# --- creation and validation ---------------------------------------------


def test_create_derives_a_slug_and_starts_as_draft(client, world):
    t = token_for(client, ADMIN_EMAIL)
    r = client.post(ADMIN_JOBS, json=payload(world), headers=auth(t))
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["slug"] == "senior-backend-engineer-at-systems-limited"
    assert body["status"] == "draft"
    assert body["version"] == 1
    assert r.headers["location"].endswith(body["id"])


def test_duplicate_title_gets_a_discriminated_slug(client, world):
    t = token_for(client, ADMIN_EMAIL)
    first = client.post(ADMIN_JOBS, json=payload(world), headers=auth(t)).json()
    second = client.post(ADMIN_JOBS, json=payload(world), headers=auth(t)).json()
    assert first["slug"] != second["slug"]
    assert second["slug"].endswith("-2")


def test_unknown_category_is_a_422_naming_the_field(client, world):
    t = token_for(client, ADMIN_EMAIL)
    bad = payload(world, category_id="00000000-0000-0000-0000-000000000000")
    r = client.post(ADMIN_JOBS, json=bad, headers=auth(t))
    assert r.status_code == 422
    assert "category_id" in r.json()["errors"]


def test_link_shortener_apply_url_is_rejected(client, world):
    t = token_for(client, ADMIN_EMAIL)
    r = client.post(
        ADMIN_JOBS, json=payload(world, apply_url="https://bit.ly/abc"), headers=auth(t)
    )
    assert r.status_code == 422
    assert "apply_url" in r.json()["errors"]


def test_past_expiry_date_is_rejected(client, world):
    t = token_for(client, ADMIN_EMAIL)
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    r = client.post(ADMIN_JOBS, json=payload(world, expiry_date=yesterday), headers=auth(t))
    assert r.status_code == 422
    assert "expiry_date" in r.json()["errors"]


def test_source_defaults_to_manual_when_omitted(client, world):
    t = token_for(client, ADMIN_EMAIL)
    body = client.post(ADMIN_JOBS, json=payload(world), headers=auth(t)).json()
    assert body["source"]["slug"] == "manual"


# --- lifecycle ------------------------------------------------------------


def test_publish_makes_a_job_publicly_visible(client, world):
    t = token_for(client, ADMIN_EMAIL)
    job = client.post(ADMIN_JOBS, json=payload(world), headers=auth(t)).json()

    # A draft is invisible to the public and 404s rather than leaking existence.
    assert client.get(f"{JOBS}/{job['slug']}").status_code == 404

    r = client.post(f"{ADMIN_JOBS}/{job['id']}/publish", headers=auth(t))
    assert r.status_code == 200
    assert r.json()["status"] == "published"
    assert r.json()["published_at"] is not None

    public = client.get(f"{JOBS}/{job['slug']}")
    assert public.status_code == 200
    assert public.json()["slug"] == job["slug"]
    # The public projection must not leak editorial fields.
    assert "created_by" not in public.json()
    assert "status" not in public.json()


def test_expired_job_returns_410_not_404(client, world):
    """A crawler should drop a 410 permanently but retry a 404."""
    t = token_for(client, ADMIN_EMAIL)
    job = client.post(ADMIN_JOBS, json=payload(world), headers=auth(t)).json()
    client.post(f"{ADMIN_JOBS}/{job['id']}/publish", headers=auth(t))
    client.post(f"{ADMIN_JOBS}/{job['id']}/expire", json={"reason": "filled"}, headers=auth(t))

    r = client.get(f"{JOBS}/{job['slug']}")
    assert r.status_code == 410
    assert client.get(f"{JOBS}/never-existed-anywhere").status_code == 404


def test_illegal_transition_is_rejected(client, world):
    t = token_for(client, ADMIN_EMAIL)
    job = client.post(ADMIN_JOBS, json=payload(world), headers=auth(t)).json()
    # draft -> expired is not a legal move.
    r = client.post(f"{ADMIN_JOBS}/{job['id']}/expire", json={}, headers=auth(t))
    assert r.status_code == 422
    assert r.json()["type"].endswith("invalid_transition")


def test_featuring_requires_a_published_job(client, world):
    t = token_for(client, ADMIN_EMAIL)
    job = client.post(ADMIN_JOBS, json=payload(world), headers=auth(t)).json()
    r = client.post(f"{ADMIN_JOBS}/{job['id']}/feature", json={"featured": True}, headers=auth(t))
    assert r.status_code == 422, "the database CHECK must be mirrored as a clean 422"


def test_unpublishing_clears_featured(client, world):
    t = token_for(client, ADMIN_EMAIL)
    job = client.post(ADMIN_JOBS, json=payload(world), headers=auth(t)).json()
    client.post(f"{ADMIN_JOBS}/{job['id']}/publish", headers=auth(t))
    client.post(f"{ADMIN_JOBS}/{job['id']}/feature", json={"featured": True}, headers=auth(t))
    r = client.post(f"{ADMIN_JOBS}/{job['id']}/expire", json={}, headers=auth(t))
    assert r.json()["featured"] is False, "a listing off the site cannot stay featured"


def test_slug_freezes_once_published(client, world):
    t = token_for(client, ADMIN_EMAIL)
    job = client.post(ADMIN_JOBS, json=payload(world), headers=auth(t)).json()

    renamed = client.patch(
        f"{ADMIN_JOBS}/{job['id']}", json={"title": "Staff Backend Engineer"}, headers=auth(t)
    ).json()
    assert renamed["slug"] != job["slug"], "a draft slug follows the title"

    client.post(f"{ADMIN_JOBS}/{job['id']}/publish", headers=auth(t))
    published_slug = renamed["slug"]

    after = client.patch(
        f"{ADMIN_JOBS}/{job['id']}",
        json={"title": "Principal Backend Engineer"},
        headers=auth(t),
    ).json()
    assert after["slug"] == published_slug, "a published slug must never move"


def test_verify_records_the_verifier(client, world):
    t = token_for(client, ADMIN_EMAIL)
    job = client.post(ADMIN_JOBS, json=payload(world), headers=auth(t)).json()
    r = client.post(
        f"{ADMIN_JOBS}/{job['id']}/verify", json={"verified": True}, headers=auth(t)
    ).json()
    assert r["verified"] is True
    assert r["verified_by"] is not None and r["verified_at"] is not None

    cleared = client.post(
        f"{ADMIN_JOBS}/{job['id']}/verify", json={"verified": False}, headers=auth(t)
    ).json()
    assert cleared["verified_by"] is None, "the CHECK requires verifier and flag to agree"


def test_soft_delete_hides_the_job_and_frees_the_slug(client, world):
    t = token_for(client, ADMIN_EMAIL)
    job = client.post(ADMIN_JOBS, json=payload(world), headers=auth(t)).json()
    client.post(f"{ADMIN_JOBS}/{job['id']}/publish", headers=auth(t))

    assert client.delete(f"{ADMIN_JOBS}/{job['id']}", headers=auth(t)).status_code == 204
    assert client.get(f"{JOBS}/{job['slug']}").status_code == 404

    # The slug is released, so the same title can be posted again.
    again = client.post(ADMIN_JOBS, json=payload(world), headers=auth(t)).json()
    assert again["slug"] == job["slug"]


# --- counters -------------------------------------------------------------


def test_publishing_and_expiring_move_the_category_counter(client, world):
    t = token_for(client, ADMIN_EMAIL)

    async def counter() -> int:
        async with SessionFactory() as s:
            return (
                await s.execute(select(Category.job_count).where(Category.slug == "m3-tech"))
            ).scalar_one()

    start = asyncio.run(counter())
    job = client.post(ADMIN_JOBS, json=payload(world), headers=auth(t)).json()
    assert asyncio.run(counter()) == start, "a draft does not count"

    client.post(f"{ADMIN_JOBS}/{job['id']}/publish", headers=auth(t))
    assert asyncio.run(counter()) == start + 1

    client.post(f"{ADMIN_JOBS}/{job['id']}/expire", json={}, headers=auth(t))
    assert asyncio.run(counter()) == start, "expiring must give the count back"


# --- filtering, sorting, pagination --------------------------------------


def test_filters_and_pagination(client, world):
    t = token_for(client, ADMIN_EMAIL)
    for i in range(5):
        job = client.post(
            ADMIN_JOBS,
            json=payload(
                world,
                title=f"Filter Role {i}",
                work_type="remote" if i % 2 == 0 else "on_site",
                employment_type="internship" if i == 0 else "full_time",
            ),
            headers=auth(t),
        ).json()
        client.post(f"{ADMIN_JOBS}/{job['id']}/publish", headers=auth(t))

    remote = client.get(JOBS, params={"work_type": "remote", "per_page": 50}).json()
    assert remote["total"] >= 3
    assert all(j["work_type"] == "remote" for j in remote["items"])

    interns = client.get(JOBS, params={"employment_type": "internship"}).json()
    assert all(j["employment_type"] == "internship" for j in interns["items"])

    by_cat = client.get(JOBS, params={"category": "m3-tech", "per_page": 50}).json()
    assert by_cat["total"] >= 5

    first = client.get(JOBS, params={"per_page": 2, "page": 1}).json()
    second = client.get(JOBS, params={"per_page": 2, "page": 2}).json()
    assert len(first["items"]) == 2
    assert first["has_more"] is True
    # A stable tiebreaker means no row appears on two pages.
    assert {j["id"] for j in first["items"]}.isdisjoint({j["id"] for j in second["items"]})


def test_unknown_filter_slug_returns_empty_not_error(client):
    r = client.get(JOBS, params={"category": "no-such-category"})
    assert r.status_code == 200
    assert r.json()["total"] == 0


def test_sort_by_salary(client, world):
    t = token_for(client, ADMIN_EMAIL)
    for title, salary in (("Low Pay Role", 50000), ("High Pay Role", 500000)):
        job = client.post(
            ADMIN_JOBS,
            json=payload(world, title=title, salary_min=salary, salary_max=salary + 10000),
            headers=auth(t),
        ).json()
        client.post(f"{ADMIN_JOBS}/{job['id']}/publish", headers=auth(t))

    desc = client.get(JOBS, params={"sort": "salary_desc", "per_page": 50}).json()["items"]
    salaries = [j["title"] for j in desc if "Pay Role" in j["title"]]
    assert salaries[0] == "High Pay Role"


def test_badge_is_computed_not_stored(client, world):
    t = token_for(client, ADMIN_EMAIL)
    soon = (date.today() + timedelta(days=3)).isoformat()
    job = client.post(
        ADMIN_JOBS,
        json=payload(world, title="Expiring Soon Role", expiry_date=soon),
        headers=auth(t),
    ).json()
    client.post(f"{ADMIN_JOBS}/{job['id']}/publish", headers=auth(t))

    detail = client.get(f"{JOBS}/{job['slug']}").json()
    assert detail["badge"] == "expiring"

    client.post(f"{ADMIN_JOBS}/{job['id']}/feature", json={"featured": True}, headers=auth(t))
    # Featured wins: it is the placement that was paid for.
    assert client.get(f"{JOBS}/{job['slug']}").json()["badge"] == "featured"


# --- permissions ----------------------------------------------------------


def test_editor_cannot_publish(client, world):
    t = token_for(client, EDITOR_EMAIL)
    job = client.post(ADMIN_JOBS, json=payload(world), headers=auth(t)).json()
    r = client.post(f"{ADMIN_JOBS}/{job['id']}/publish", headers=auth(t))
    assert r.status_code == 403
    assert r.json()["type"].endswith("permission_denied")


def test_editor_cannot_create_a_published_job(client, world):
    t = token_for(client, EDITOR_EMAIL)
    r = client.post(ADMIN_JOBS, json=payload(world, status="published"), headers=auth(t))
    assert r.status_code == 403


def test_editor_cannot_edit_another_admins_job(client, world):
    admin_t = token_for(client, ADMIN_EMAIL)
    job = client.post(ADMIN_JOBS, json=payload(world), headers=auth(admin_t)).json()

    editor_t = token_for(client, EDITOR_EMAIL)
    r = client.patch(
        f"{ADMIN_JOBS}/{job['id']}", json={"title": "Hijacked Title"}, headers=auth(editor_t)
    )
    assert r.status_code == 403, "ownership scoping is enforced in the service"


def test_anonymous_cannot_reach_admin_endpoints(client, world):
    assert client.get(ADMIN_JOBS).status_code == 401
    assert client.post(ADMIN_JOBS, json=payload(world)).status_code == 401


# --- concurrency ----------------------------------------------------------


def test_if_match_rejects_a_stale_write(client, world):
    t = token_for(client, ADMIN_EMAIL)
    job = client.post(ADMIN_JOBS, json=payload(world), headers=auth(t)).json()
    stale = job["version"]

    client.patch(f"{ADMIN_JOBS}/{job['id']}", json={"title": "First Edit"}, headers=auth(t))

    r = client.patch(
        f"{ADMIN_JOBS}/{job['id']}",
        json={"title": "Second Edit"},
        headers={**auth(t), "If-Match": str(stale)},
    )
    assert r.status_code == 409
    assert r.json()["type"].endswith("version_conflict")


# --- audit ----------------------------------------------------------------


def test_every_mutation_writes_an_audit_entry(client, world):
    t = token_for(client, ADMIN_EMAIL)
    job = client.post(ADMIN_JOBS, json=payload(world), headers=auth(t)).json()
    client.patch(f"{ADMIN_JOBS}/{job['id']}", json={"title": "Audited Title"}, headers=auth(t))
    client.post(f"{ADMIN_JOBS}/{job['id']}/publish", headers=auth(t))
    client.post(f"{ADMIN_JOBS}/{job['id']}/verify", json={"verified": True}, headers=auth(t))
    client.post(f"{ADMIN_JOBS}/{job['id']}/feature", json={"featured": True}, headers=auth(t))
    client.post(f"{ADMIN_JOBS}/{job['id']}/expire", json={}, headers=auth(t))
    client.delete(f"{ADMIN_JOBS}/{job['id']}", headers=auth(t))

    async def actions() -> list[str]:
        async with SessionFactory() as s:
            rows = await s.execute(
                select(AuditLog.action)
                .where(AuditLog.entity_id == __import__("uuid").UUID(job["id"]))
                .order_by(AuditLog.created_at)
            )
            return list(rows.scalars().all())

    recorded = asyncio.run(actions())
    assert recorded == [
        "job.create",
        "job.update",
        "job.publish",
        "job.verify",
        "job.feature",
        "job.expire",
        "job.delete",
    ]


def test_a_no_op_patch_writes_no_audit_entry(client, world):
    t = token_for(client, ADMIN_EMAIL)
    job = client.post(ADMIN_JOBS, json=payload(world), headers=auth(t)).json()
    client.patch(f"{ADMIN_JOBS}/{job['id']}", json={"title": job["title"]}, headers=auth(t))

    async def count() -> int:
        async with SessionFactory() as s:
            return (
                await s.execute(
                    select(text("count(*)"))
                    .select_from(AuditLog)
                    .where(AuditLog.entity_id == __import__("uuid").UUID(job["id"]))
                )
            ).scalar_one()

    assert asyncio.run(count()) == 1, "only the create; an unchanged PATCH is not an event"


# --- performance ----------------------------------------------------------


def test_list_endpoint_does_not_n_plus_one(client, world):
    """Query count must not grow with page size.

    Eager loading is the fix; this test is what stops it silently regressing
    the next time someone adds a field to the list projection.
    """
    t = token_for(client, ADMIN_EMAIL)
    for i in range(12):
        job = client.post(
            ADMIN_JOBS, json=payload(world, title=f"N Plus One Role {i}"), headers=auth(t)
        ).json()
        client.post(f"{ADMIN_JOBS}/{job['id']}/publish", headers=auth(t))

    async def count_queries(per_page: int) -> int:
        from sqlalchemy import event

        from app.db.database import engine

        counter = {"n": 0}

        def before(conn, cursor, statement, *args):
            if statement.lstrip().upper().startswith("SELECT"):
                counter["n"] += 1

        sync_engine = engine.sync_engine
        event.listen(sync_engine, "before_cursor_execute", before)
        try:
            from app.repositories.job_repo import JobFilters
            from app.services.job_service import JobService

            async with SessionFactory() as s:
                await JobService(s).list_public(
                    JobFilters(), sort="recent", page=1, per_page=per_page
                )
        finally:
            event.remove(sync_engine, "before_cursor_execute", before)
        return counter["n"]

    small = asyncio.run(count_queries(2))
    large = asyncio.run(count_queries(10))
    assert small == large, (
        f"query count grew with page size ({small} -> {large}); a relation is lazy-loading per row"
    )
    assert large <= 6, f"expected count + page + 4 eager loads, got {large}"


# --- reference data -------------------------------------------------------


def test_reference_endpoints_are_public(client):
    for path in ("/api/v1/categories", "/api/v1/locations", "/api/v1/sources"):
        r = client.get(path)
        assert r.status_code == 200
        assert isinstance(r.json(), list)


def test_source_config_is_not_exposed_publicly(client):
    sources = client.get("/api/v1/sources").json()
    assert sources, "the manual source should be listed"
    assert "config" not in sources[0], "scraper config must not be public"


def test_category_slug_conflict_is_a_409(client):
    t = token_for(client, ADMIN_EMAIL)
    body = {"name": "M3 Tech Duplicate", "slug": "m3-tech"}
    r = client.post("/api/v1/admin/categories", json=body, headers=auth(t))
    assert r.status_code == 409


def test_manual_source_cannot_be_deactivated(client):
    t = token_for(client, ADMIN_EMAIL)
    sources = client.get("/api/v1/sources").json()
    manual = next(s for s in sources if s["slug"] == "manual")
    r = client.patch(
        f"/api/v1/admin/sources/{manual['id']}", json={"is_active": False}, headers=auth(t)
    )
    assert r.status_code == 409


def test_non_remote_location_requires_a_city(client):
    t = token_for(client, ADMIN_EMAIL)
    r = client.post(
        "/api/v1/admin/locations",
        json={"country": "PK", "is_remote": False},
        headers=auth(t),
    )
    assert r.status_code == 422


# --- public payload completeness ------------------------------------------


def test_list_carries_salary_so_a_card_renders_from_one_request(client, world):
    """A job card shows salary. Omitting it from the list forces the client to
    fetch every detail page to render one screen of results.
    """
    t = token_for(client, ADMIN_EMAIL)
    job = client.post(
        ADMIN_JOBS,
        json=payload(world, title="Salaried Role", salary_min=250000, salary_max=350000),
        headers=auth(t),
    ).json()
    client.post(f"{ADMIN_JOBS}/{job['id']}/publish", headers=auth(t))

    listed = client.get(JOBS, params={"per_page": 50}).json()["items"]
    row = next(i for i in listed if i["slug"] == job["slug"])

    assert row["salary"]["min"] == "250000.00"
    assert row["salary"]["max"] == "350000.00"
    assert row["salary"]["currency"] == "PKR"
    assert row["salary"]["period"] == "month"
    assert row["salary"]["disclosed"] is True


def test_undisclosed_salary_withholds_the_bounds(client, world):
    """The columns can still hold a figure — a scraper may have guessed one.
    Returning it would publish a number nobody agreed to publish.
    """
    t = token_for(client, ADMIN_EMAIL)
    job = client.post(
        ADMIN_JOBS,
        json=payload(
            world,
            title="Undisclosed Pay Role",
            salary_min=100000,
            salary_max=200000,
            salary_is_disclosed=False,
        ),
        headers=auth(t),
    ).json()
    client.post(f"{ADMIN_JOBS}/{job['id']}/publish", headers=auth(t))

    detail = client.get(f"{JOBS}/{job['slug']}").json()
    assert detail["salary"]["disclosed"] is False
    assert detail["salary"]["min"] is None
    assert detail["salary"]["max"] is None


def test_public_payload_never_exposes_editorial_counters(client, world):
    """View and apply counts are editorial signals. The public UI does not
    render them, and publishing them hands competitors a traffic report.
    """
    t = token_for(client, ADMIN_EMAIL)
    job = client.post(ADMIN_JOBS, json=payload(world, title="Counter Role"), headers=auth(t)).json()
    client.post(f"{ADMIN_JOBS}/{job['id']}/publish", headers=auth(t))

    detail = client.get(f"{JOBS}/{job['slug']}").json()
    for leaked in ("view_count", "apply_click_count", "save_count", "created_by", "status"):
        assert leaked not in detail, f"{leaked} must not appear on a public response"


# --- suggest ---------------------------------------------------------------


def test_suggest_returns_matching_titles(client, world):
    t = token_for(client, ADMIN_EMAIL)
    for title in ("Suggestable Engineer", "Suggestable Designer"):
        job = client.post(ADMIN_JOBS, json=payload(world, title=title), headers=auth(t)).json()
        client.post(f"{ADMIN_JOBS}/{job['id']}/publish", headers=auth(t))

    results = client.get(f"{JOBS}/suggest", params={"q": "Suggestable"}).json()
    assert "Suggestable Engineer" in results
    assert "Suggestable Designer" in results


def test_suggest_is_not_swallowed_by_the_slug_route(client):
    """`/jobs/suggest` and `/jobs/{slug}` are the same shape. Declaration order
    is what keeps them apart, and nothing else would catch a reorder.
    """
    r = client.get(f"{JOBS}/suggest", params={"q": "engineer"})
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_suggest_requires_a_usable_prefix(client):
    assert client.get(f"{JOBS}/suggest", params={"q": "a"}).status_code == 422


def test_ids_filter_resolves_a_client_held_collection(client, world):
    """The saved-jobs page keeps ids in local storage. Without this it would
    need one request per saved listing.
    """
    t = token_for(client, ADMIN_EMAIL)
    created = []
    for title in ("Saved Role A", "Saved Role B", "Unsaved Role C"):
        job = client.post(ADMIN_JOBS, json=payload(world, title=title), headers=auth(t)).json()
        client.post(f"{ADMIN_JOBS}/{job['id']}/publish", headers=auth(t))
        created.append(job)

    wanted = [created[0]["id"], created[1]["id"]]
    got = client.get(JOBS, params=[("ids", i) for i in wanted] + [("per_page", 50)]).json()

    assert got["total"] == 2
    assert {i["id"] for i in got["items"]} == set(wanted)


def test_ids_filter_still_hides_unpublished_listings(client, world):
    """The id set narrows the public query; it does not bypass it. A draft id
    held from an earlier session must not become readable by asking for it.
    """
    t = token_for(client, ADMIN_EMAIL)
    draft = client.post(ADMIN_JOBS, json=payload(world, title="Draft Role"), headers=auth(t)).json()

    got = client.get(JOBS, params={"ids": draft["id"]}).json()
    assert got["total"] == 0
