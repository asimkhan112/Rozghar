"""Bulk job operations: purge every expired listing, publish every draft.

Both act on rows the admin pressing the button cannot see — the whole
catalogue, not the page in front of them — and one of them is a hard delete
with no undo. That combination is why these have their own file: the things
worth asserting are not "did it return 200" but "did it touch exactly what it
said it would, and nothing else".
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select

from app.core.enums import JobStatus
from app.core.permissions import SystemRole
from app.core.security import hash_password
from app.db.database import SessionFactory
from app.main import app
from app.models.admin import Admin, AdminSession
from app.models.audit import AuditLog
from app.models.job import Job
from app.models.rbac import Role
from app.models.taxonomy import Category, Location, Source

ADMIN_EMAIL = "bulk-admin@plenilo.com"
EDITOR_EMAIL = "bulk-editor@plenilo.com"
PASSWORD = "bulk-operations-pass"
LOGIN = "/api/v1/auth/login"
ADMIN_JOBS = "/api/v1/admin/jobs"
PURGE = f"{ADMIN_JOBS}/bulk/purge-expired"
PUBLISH_DRAFTS = f"{ADMIN_JOBS}/bulk/publish-drafts"


async def _seed() -> dict:
    """A world with no listings in it, so counts are unambiguous.

    Every job in the database is cleared, not just this module's: both
    endpoints act on *every* expired or draft listing, so a stray row from
    another test would land in the result and make the assertions lie.
    """
    async with SessionFactory() as s:
        await s.execute(delete(Job))
        for email in (ADMIN_EMAIL, EDITOR_EMAIL):
            existing = (
                await s.execute(select(Admin).where(Admin.email == email))
            ).scalar_one_or_none()
            if existing:
                await s.execute(delete(AdminSession).where(AdminSession.admin_id == existing.id))
                await s.execute(delete(AuditLog).where(AuditLog.admin_id == existing.id))
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
            await s.execute(select(Category).where(Category.slug == "bulk-tech"))
        ).scalar_one_or_none()
        if category is None:
            category = Category(name="Bulk Tech", slug="bulk-tech", job_count=0)
            s.add(category)
        else:
            category.job_count = 0
        location = (
            await s.execute(select(Location).where(Location.slug == "bulk-lahore"))
        ).scalar_one_or_none()
        if location is None:
            location = Location(
                city="Lahore",
                country="PK",
                slug="bulk-lahore",
                display_name="Lahore, Pakistan",
                job_count=0,
            )
            s.add(location)
        else:
            location.job_count = 0
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


def payload(world: dict, title: str) -> dict:
    return {
        "title": title,
        "company_name": "Systems Limited",
        "category_id": world["category_id"],
        "location_id": world["location_id"],
        "work_type": "hybrid",
        "employment_type": "full_time",
        "experience_level": "senior",
        "description": "A" * 60,
        "apply_url": "https://systemslimited.com/careers/backend",
    }


def make(client: TestClient, token: str, world: dict, title: str, state: str) -> str:
    """Creates one listing and walks it to `state` through the real endpoints.

    `expired` is reached via `published` on purpose — it is the only route the
    status machine allows, and it is what makes every expired listing in the
    database one that was counted live and then decremented.
    """
    r = client.post(ADMIN_JOBS, json=payload(world, title), headers=auth(token))
    assert r.status_code == 201, r.text
    job_id = r.json()["id"]
    if state in ("published", "expired"):
        assert client.post(f"{ADMIN_JOBS}/{job_id}/publish", headers=auth(token)).status_code == 200
    if state == "expired":
        r = client.post(f"{ADMIN_JOBS}/{job_id}/expire", json={}, headers=auth(token))
        assert r.status_code == 200, r.text
    return job_id


async def _statuses() -> dict[str, str]:
    async with SessionFactory() as s:
        rows = (await s.execute(select(Job.id, Job.status, Job.deleted_at))).all()
        return {str(r[0]): r[1] for r in rows}


async def _counts(world: dict) -> tuple[int, int]:
    async with SessionFactory() as s:
        cat = (await s.execute(select(Category.job_count))).scalars().all()
        loc = (
            await s.execute(select(Location.job_count).where(Location.slug == "bulk-lahore"))
        ).scalar_one()
        del cat
        c = (
            await s.execute(select(Category.job_count).where(Category.slug == "bulk-tech"))
        ).scalar_one()
        return c, loc


# --- purging expired listings --------------------------------------------


def test_purge_removes_expired_rows_outright_not_softly(client, world):
    """The row must be gone, not flagged.

    A soft delete would pass a naive "is it still in the admin list?" check
    while leaving the data exactly where the admin asked for it not to be.
    """
    t = token_for(client, ADMIN_EMAIL)
    gone = make(client, t, world, "Expired Role", "expired")
    kept = make(client, t, world, "Live Role", "published")

    r = client.post(PURGE, headers=auth(t))
    assert r.status_code == 200, r.text
    assert r.json()["deleted"] == 1
    assert r.json()["remaining"] == 0

    statuses = asyncio.run(_statuses())
    assert gone not in statuses, "expired listing should not exist in any form"
    assert statuses[kept] == JobStatus.PUBLISHED


def test_purge_leaves_drafts_and_published_alone(client, world):
    t = token_for(client, ADMIN_EMAIL)
    draft = make(client, t, world, "Draft Role", "draft")
    live = make(client, t, world, "Live Role", "published")
    make(client, t, world, "Expired Role", "expired")

    assert client.post(PURGE, headers=auth(t)).json()["deleted"] == 1

    statuses = asyncio.run(_statuses())
    assert statuses[draft] == JobStatus.DRAFT
    assert statuses[live] == JobStatus.PUBLISHED


def test_purge_reports_the_remainder_when_it_hits_the_cap(client, world):
    """The cap is what stops one press opening a transaction over everything.

    Exercised through the service with a limit of one rather than by creating
    five hundred listings: the behaviour under test is "stop, and say how many
    are left", which does not depend on the number being 500.
    """
    t = token_for(client, ADMIN_EMAIL)
    for i in range(3):
        make(client, t, world, f"Expired Role {i}", "expired")

    async def run() -> dict:
        from app.services.auth_service import Principal
        from app.services.job_service import JobService

        async with SessionFactory() as s:
            admin = (
                await s.execute(select(Admin).where(Admin.email == ADMIN_EMAIL))
            ).scalar_one()
            service = JobService(s)
            principal = Principal(
                admin_id=admin.id,
                email=admin.email,
                full_name=admin.full_name,
                role_key=SystemRole.ADMIN.value,
                permissions=frozenset({"JOB_DELETE", "JOB_BULK"}),
            )
            result = await service.purge_expired(principal=principal, limit=1)
            await s.commit()
            return result

    result = asyncio.run(run())
    assert result["deleted"] == 1
    assert result["remaining"] == 2


def test_purge_repairs_counters_that_drifted(client, world):
    """`expire_jobs` used to bypass the state machine, inflating these.

    The purge rebuilds them from the jobs table, so a cleanup leaves the
    category and location counts telling the truth rather than carrying old
    drift forward into a catalogue where the rows behind it no longer exist.
    """
    t = token_for(client, ADMIN_EMAIL)
    make(client, t, world, "Live Role", "published")
    make(client, t, world, "Expired Role", "expired")

    async def inflate() -> None:
        async with SessionFactory() as s:
            cat = (
                await s.execute(select(Category).where(Category.slug == "bulk-tech"))
            ).scalar_one()
            loc = (
                await s.execute(select(Location).where(Location.slug == "bulk-lahore"))
            ).scalar_one()
            cat.job_count = 99
            loc.job_count = 99
            await s.commit()

    asyncio.run(inflate())
    assert client.post(PURGE, headers=auth(t)).status_code == 200

    category_count, location_count = asyncio.run(_counts(world))
    assert category_count == 1, "only the one published listing should be counted"
    assert location_count == 1


def test_purge_is_refused_without_the_bulk_permission(client, world):
    """An editor holds neither JOB_DELETE nor JOB_BULK."""
    t = token_for(client, EDITOR_EMAIL)
    assert client.post(PURGE, headers=auth(t)).status_code == 403


# --- publishing drafts ----------------------------------------------------


def test_publish_drafts_publishes_only_drafts(client, world):
    t = token_for(client, ADMIN_EMAIL)
    draft_a = make(client, t, world, "Draft A", "draft")
    draft_b = make(client, t, world, "Draft B", "draft")
    expired = make(client, t, world, "Expired Role", "expired")

    r = client.post(PUBLISH_DRAFTS, headers=auth(t))
    assert r.status_code == 200, r.text
    assert r.json()["published"] == 2
    assert r.json()["remaining"] == 0

    statuses = asyncio.run(_statuses())
    assert statuses[draft_a] == JobStatus.PUBLISHED
    assert statuses[draft_b] == JobStatus.PUBLISHED
    assert statuses[expired] == JobStatus.EXPIRED, "expired listings must be left alone"


def test_publish_drafts_moves_the_counters(client, world):
    """Publishing in bulk goes through the same state machine as one at a time.

    If it did not, the category tiles would undercount every listing that went
    live this way — the mirror of the bug the purge test covers.
    """
    t = token_for(client, ADMIN_EMAIL)
    make(client, t, world, "Draft A", "draft")
    make(client, t, world, "Draft B", "draft")

    assert asyncio.run(_counts(world)) == (0, 0)
    assert client.post(PUBLISH_DRAFTS, headers=auth(t)).json()["published"] == 2
    assert asyncio.run(_counts(world)) == (2, 2)


def test_publish_drafts_does_not_reset_an_existing_published_at(client, world):
    """A listing that has been live before keeps its original date.

    `_transition` stamps `published_at` only when it is null. Without that, a
    bulk publish would reset the age of everything it touched and shunt it all
    to the top of the recency ordering, burying genuinely new listings under
    old ones that happened to be re-published together.

    The draft is given a `published_at` directly because no endpoint moves a
    listing from `published` back to `draft` — the transition is allowed by the
    status machine but nothing exposes it — so the state has to be built rather
    than walked to.
    """
    t = token_for(client, ADMIN_EMAIL)
    job_id = make(client, t, world, "Returning Role", "draft")
    stamped = datetime(2020, 1, 2, 3, 4, 5, tzinfo=UTC)

    async def backdate() -> None:
        async with SessionFactory() as s:
            job = (await s.execute(select(Job).where(Job.id == UUID(job_id)))).scalar_one()
            job.published_at = stamped
            await s.commit()

    asyncio.run(backdate())
    assert client.post(PUBLISH_DRAFTS, headers=auth(t)).json()["published"] == 1

    async def read_back() -> tuple[str, object]:
        async with SessionFactory() as s:
            job = (await s.execute(select(Job).where(Job.id == UUID(job_id)))).scalar_one()
            return job.status, job.published_at

    status, published_at = asyncio.run(read_back())
    assert status == JobStatus.PUBLISHED
    assert published_at == stamped, "publishing must not restamp a listing that had a date"


def test_publish_drafts_is_refused_without_the_bulk_permission(client, world):
    t = token_for(client, EDITOR_EMAIL)
    assert client.post(PUBLISH_DRAFTS, headers=auth(t)).status_code == 403


def test_both_endpoints_are_reachable_and_not_shadowed_by_the_id_route(client, world):
    """`/bulk/...` must not be parsed as `/{job_id}/...`.

    A 422 here would mean "bulk" was read as a listing id — the failure the
    route ordering in `admin_jobs.py` exists to prevent.
    """
    t = token_for(client, ADMIN_EMAIL)
    for url in (PURGE, PUBLISH_DRAFTS):
        assert client.post(url, headers=auth(t)).status_code == 200, url
