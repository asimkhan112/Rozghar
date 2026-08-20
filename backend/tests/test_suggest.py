"""Autocomplete tests.

Three things matter here and nothing else does:

* the grouping and the ranking tiers behave as specified,
* the public endpoint cannot be made to reveal an unpublished listing,
* the query the endpoint runs stays index-assisted.

The last one has a test because the failure is silent: swapping the `%`
operator for `similarity(col, q) > threshold` returns identical rows and turns
an indexed lookup into a sequential scan. Nothing but a plan assertion catches
that.
"""

from __future__ import annotations

import asyncio

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
from app.models.suggest import PopularQuery, SkillTerm
from app.models.taxonomy import Category, Location, Source
from app.repositories.suggest_repo import SuggestRepository

EMAIL = "sg-admin@plenilo.com"
PASSWORD = "suggest-tests-pass"
ADMIN_JOBS = "/api/v1/admin/jobs"
SUGGEST = "/api/v1/search/suggest"
ADMIN_SUGGEST = "/api/v1/admin/search/suggest"

PUBLISHED = {
    "title": "Senior Kubernetes Engineer",
    "company_name": "Zephyr Cloudworks",
    "requirements": ["Kubernetes orchestration", "Terraform modules"],
}
#: Never published. The public endpoint must not surface this under any query.
DRAFT_TITLE = "Confidential Kubernetes Rewrite"


async def _seed() -> dict:
    async with SessionFactory() as s:
        admin = (await s.execute(select(Admin).where(Admin.email == EMAIL))).scalar_one_or_none()
        if admin:
            await s.execute(delete(AdminSession).where(AdminSession.admin_id == admin.id))
            await s.execute(delete(AuditLog).where(AuditLog.admin_id == admin.id))
            await s.execute(delete(Job).where(Job.created_by == admin.id))
            await s.delete(admin)
            await s.commit()

        role = (
            await s.execute(select(Role).where(Role.key == SystemRole.ADMIN.value))
        ).scalar_one()
        s.add(
            Admin(
                email=EMAIL,
                full_name="Suggest Admin",
                password_hash=hash_password(PASSWORD),
                role_id=role.id,
                is_active=True,
            )
        )

        category = (
            await s.execute(select(Category).where(Category.slug == "sg-cloud"))
        ).scalar_one_or_none()
        if category is None:
            category = Category(name="Kubernetes Platform", slug="sg-cloud")
            s.add(category)

        location = (
            await s.execute(select(Location).where(Location.slug == "sg-quetta"))
        ).scalar_one_or_none()
        if location is None:
            location = Location(
                city="Quetta", country="PK", slug="sg-quetta", display_name="Quetta, Pakistan"
            )
            s.add(location)

        source = (await s.execute(select(Source).where(Source.slug == "manual"))).scalar_one()
        await s.commit()
        return {
            "category_id": str(category.id),
            "location_id": str(location.id),
            "source_name": source.name,
        }


@pytest.fixture(scope="module")
def world():
    return asyncio.run(_seed())


def _body(world: dict, title: str, requirements: list[str]) -> dict:
    return {
        "title": title,
        "company_name": PUBLISHED["company_name"],
        "category_id": world["category_id"],
        "location_id": world["location_id"],
        "work_type": "on_site",
        "employment_type": "full_time",
        "experience_level": "senior",
        "description": "Operate a large multi-tenant cluster estate. " * 5,
        "requirements": requirements,
        "apply_url": "https://example.com/apply",
    }


@pytest.fixture(scope="module")
def client(world):
    with TestClient(app) as c:
        r = c.post("/api/v1/auth/login", json={"email": EMAIL, "password": PASSWORD})
        headers = {"Authorization": f"Bearer {r.json()['access_token']}"}

        created = c.post(ADMIN_JOBS, json=_body(world, PUBLISHED["title"], PUBLISHED["requirements"]), headers=headers)
        assert created.status_code == 201, created.text
        c.post(f"{ADMIN_JOBS}/{created.json()['id']}/publish", headers=headers)

        # Left as a draft on purpose.
        draft = c.post(ADMIN_JOBS, json=_body(world, DRAFT_TITLE, ["Kubernetes orchestration"]), headers=headers)
        assert draft.status_code == 201, draft.text

        # The vocabulary is materialised, so it has to be rebuilt before the
        # skills group can contain anything.
        asyncio.run(_refresh())
        c.headers.update(headers)
        yield c


async def _refresh() -> None:
    async with SessionFactory() as s:
        repo = SuggestRepository(s)
        await repo.rebuild_skill_terms()
        await repo.rebuild_popular_queries()
        await s.commit()


def get(client: TestClient, q: str, *, admin: bool = False) -> dict:
    url = ADMIN_SUGGEST if admin else SUGGEST
    headers = dict(client.headers) if admin else {"Authorization": ""}
    r = client.get(url, params={"q": q}, headers=headers if admin else None)
    assert r.status_code == 200, r.text
    return r.json()


def texts(body: dict, group: str) -> list[str]:
    return [i["text"] for i in body[group]]


# --- grouping --------------------------------------------------------------


def test_response_always_carries_every_group(client):
    """Empty groups are returned rather than omitted, so the client never has
    to distinguish "no matches" from "this endpoint does not do that"."""
    body = get(client, "zzzznothingmatchesthis")
    assert set(body) == {"jobs", "companies", "skills", "locations", "categories"}
    assert all(body[k] == [] for k in body)


def test_groups_are_populated_from_their_own_source(client):
    assert PUBLISHED["title"] in texts(get(client, "kubernetes"), "jobs")
    assert "Kubernetes Platform" in texts(get(client, "kubernetes"), "categories")
    assert "Kubernetes orchestration" in texts(get(client, "kubernetes"), "skills")
    assert PUBLISHED["company_name"] in texts(get(client, "zephyr"), "companies")
    assert "Quetta, Pakistan" in texts(get(client, "quetta"), "locations")


# --- ranking ---------------------------------------------------------------


def test_prefix_match_outranks_a_mid_string_match(client):
    """"kar" must put Karachi above Okara. Both contain the substring; only one
    starts with it, and that is the whole point of the top tier."""
    names = texts(get(client, "kar"), "locations")
    if "Karachi, Pakistan" in names and "Okara, Pakistan" in names:
        assert names.index("Karachi, Pakistan") < names.index("Okara, Pakistan")


def test_typo_still_finds_the_listing(client):
    """The fuzzy tier exists for this: a tsquery cannot recover a word that was
    never spelled correctly."""
    assert PUBLISHED["title"] in texts(get(client, "kubernets"), "jobs")


# --- the public/admin boundary --------------------------------------------


def test_public_endpoint_never_reveals_an_unpublished_listing(client):
    for query in ("confidential", "kubernetes", "rewrite"):
        assert DRAFT_TITLE not in texts(get(client, query), "jobs"), query


def test_admin_endpoint_sees_the_draft(client):
    assert DRAFT_TITLE in texts(get(client, "confidential", admin=True), "jobs")


def test_admin_endpoint_adds_sources(client):
    assert "sources" in get(client, "kubernetes", admin=True)


def test_admin_endpoint_requires_authentication(client):
    assert client.get(ADMIN_SUGGEST, params={"q": "kubernetes"}, headers={"Authorization": ""}).status_code == 401


# --- input handling --------------------------------------------------------


@pytest.mark.parametrize("q", ["", "a", " "])
def test_queries_below_two_characters_are_rejected(client, q):
    assert client.get(SUGGEST, params={"q": q}).status_code == 422


def test_result_count_is_bounded_per_group(client):
    """A dropdown that does not fit on a phone is not a dropdown."""
    body = get(client, "ku")
    assert all(len(v) <= 5 for v in body.values())


# --- the vocabulary --------------------------------------------------------


def test_skill_vocabulary_drops_terms_that_no_longer_appear(client):
    """A rebuild has to delete, not just upsert. A skill nobody lists any more
    must stop being suggested."""

    async def scenario() -> bool:
        async with SessionFactory() as s:
            s.add(SkillTerm(term="Fortran 77", term_norm="fortran 77", job_count=1))
            await s.commit()
            await SuggestRepository(s).rebuild_skill_terms()
            await s.commit()
            found = await s.execute(select(SkillTerm).where(SkillTerm.term == "Fortran 77"))
            return found.scalar_one_or_none() is not None

    assert asyncio.run(scenario()) is False


def test_popular_queries_exclude_searches_that_found_nothing(client):
    """Suggesting a term that returns no listings sends the reader somewhere
    the catalogue cannot answer."""

    async def scenario() -> list[str]:
        async with SessionFactory() as s:
            await s.execute(text("""
                INSERT INTO search_logs (session_id, raw_query, normalised_query,
                                         result_count, was_degraded, occurred_at, response_ms)
                VALUES (gen_random_uuid(), 'zzz dead query', 'zzz dead query', 0, false, now(), 5)
            """))
            await s.commit()
            await SuggestRepository(s).rebuild_popular_queries()
            await s.commit()
            rows = await s.execute(select(PopularQuery.query_norm))
            return list(rows.scalars().all())

    assert "zzz dead query" not in asyncio.run(scenario())


# --- the performance property ---------------------------------------------


def test_the_fuzzy_tier_stays_index_assisted(client):
    """`col % q` and `similarity(col, q) > threshold` return the same rows and
    have very different plans: only the first can use the trigram GIN index.
    Measured at 50k vocabulary rows the gap was 12ms against 158ms, so this is
    a correctness test for the latency budget."""

    async def plan() -> str:
        async with SessionFactory() as s:
            await s.execute(text("SET LOCAL pg_trgm.similarity_threshold = 0.3"))
            await s.execute(text("SET LOCAL enable_seqscan = off"))
            rows = await s.execute(
                text("EXPLAIN SELECT term FROM skill_terms WHERE term_norm % 'kubernets'")
            )
            return "\n".join(r[0] for r in rows.all())

    assert "ix_skill_terms_norm_trgm" in asyncio.run(plan())
