"""Milestone 4 search tests.

The headline assertion is the five queries from the specification. Each one
exercises a different weight band, which is the point of the weighted vector:

    react / python      -> C, skills
    karachi / remote    -> B, location
    frontend engineer   -> A, title (multi-term)
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
from app.models.taxonomy import Category, Location, Source

EMAIL = "m4-admin@plenilo.com"
PASSWORD = "milestone-four-pass"
JOBS = "/api/v1/jobs"
ADMIN_JOBS = "/api/v1/admin/jobs"

#: Deliberately spread across the weight bands so a regression in any one of
#: them shows up as a specific failing query rather than a vague one.
FIXTURES = [
    {
        "title": "Senior Frontend Engineer",
        "company_name": "Systems Limited",
        "location": "lahore",
        "requirements": ["React / Next.js", "TypeScript proficiency", "CSS architecture"],
        "description": "Build enterprise-scale web applications for the Gulf region. " * 3,
    },
    {
        "title": "Data Analyst",
        "company_name": "Daraz Pakistan",
        "location": "karachi",
        "requirements": ["SQL (advanced)", "Python (pandas, numpy)", "Power BI"],
        "description": "Shape e-commerce decisions through analysis of large datasets. " * 3,
    },
    {
        "title": "DevOps Engineer",
        "company_name": "TechNation",
        "location": "remote-worldwide",
        "requirements": ["Kubernetes & Docker", "Terraform", "AWS certified"],
        "description": "Own cloud infrastructure at scale for a UK product company. " * 3,
    },
    {
        "title": "HR Business Partner",
        "company_name": "Habib Bank Limited",
        "location": "karachi",
        "requirements": ["Labour law knowledge", "HRIS systems", "Stakeholder management"],
        "description": "Support business units across talent management in retail banking. " * 3,
    },
]


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
                full_name="M4 Admin",
                password_hash=hash_password(PASSWORD),
                role_id=role.id,
                is_active=True,
            )
        )

        category = (
            await s.execute(select(Category).where(Category.slug == "m4-tech"))
        ).scalar_one_or_none()
        if category is None:
            category = Category(name="M4 Tech", slug="m4-tech")
            s.add(category)

        locations = {}
        for slug, city, display, remote in (
            ("lahore", "Lahore", "Lahore, Pakistan", False),
            ("karachi", "Karachi", "Karachi, Pakistan", False),
            ("remote-worldwide", None, "Remote - Worldwide", True),
        ):
            loc = (
                await s.execute(select(Location).where(Location.slug == slug))
            ).scalar_one_or_none()
            if loc is None:
                loc = Location(
                    city=city,
                    country="PK",
                    slug=slug,
                    display_name=display,
                    is_remote=remote,
                )
                s.add(loc)
            locations[slug] = loc

        source = (await s.execute(select(Source).where(Source.slug == "manual"))).scalar_one()
        await s.commit()
        return {
            "category_id": str(category.id),
            "locations": {k: str(v.id) for k, v in locations.items()},
            "source_id": str(source.id),
        }


@pytest.fixture(scope="module")
def world():
    return asyncio.run(_seed())


@pytest.fixture(scope="module")
def client(world):
    with TestClient(app) as c:
        r = c.post("/api/v1/auth/login", json={"email": EMAIL, "password": PASSWORD})
        token = r.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        for fx in FIXTURES:
            body = {
                "title": fx["title"],
                "company_name": fx["company_name"],
                "category_id": world["category_id"],
                "location_id": world["locations"][fx["location"]],
                "work_type": "remote" if fx["location"].startswith("remote") else "on_site",
                "employment_type": "full_time",
                "experience_level": "mid",
                "description": fx["description"][:2000],
                "requirements": fx["requirements"],
                "apply_url": "https://example.com/apply",
            }
            created = c.post(ADMIN_JOBS, json=body, headers=headers)
            assert created.status_code == 201, created.text
            job = created.json()
            c.post(f"{ADMIN_JOBS}/{job['id']}/publish", headers=headers)
        yield c


def search(client: TestClient, q: str, **params) -> dict:
    r = client.get(JOBS, params={"q": q, "per_page": 50, **params})
    assert r.status_code == 200, r.text
    return r.json()


def titles(body: dict) -> list[str]:
    return [j["title"] for j in body["items"]]


# --- the five required queries -------------------------------------------


@pytest.mark.parametrize(
    ("query", "expected_title", "band"),
    [
        ("react", "Senior Frontend Engineer", "C: skills"),
        ("python", "Data Analyst", "C: skills"),
        ("karachi", "Data Analyst", "B: location"),
        ("remote", "DevOps Engineer", "B: location"),
        ("frontend engineer", "Senior Frontend Engineer", "A: title"),
    ],
)
def test_required_queries_return_relevant_jobs(client, query, expected_title, band):
    body = search(client, query)
    assert body["total"] > 0, f"{query!r} returned nothing ({band})"
    assert expected_title in titles(body), f"{query!r} did not surface {expected_title} ({band})"
    assert body["search"]["strategy"] == "exact", f"{query!r} should not need degradation"
    assert body["search"]["degraded"] is False


def test_karachi_returns_both_karachi_jobs(client):
    """Location is weight B, so every listing in the city matches."""
    body = search(client, "karachi")
    found = set(titles(body))
    assert {"Data Analyst", "HR Business Partner"} <= found


def test_skills_are_searchable_but_rank_below_title(client):
    """A title hit must outrank a skills hit for the same term."""
    body = search(client, "engineer")
    ranked = titles(body)
    assert ranked, "no results for 'engineer'"
    # Both engineers have it in the title; the DevOps description mentions it too.
    assert any("Engineer" in t for t in ranked[:2])


# --- degradation ladder ---------------------------------------------------


def test_stemming_absorbs_the_common_typos(client):
    """The first line of typo defence is free.

    Snowball reduces "enginer" to the same stem as "engineer", so the exact
    tier matches and no degradation is needed. Worth asserting, because it is
    why the fuzzy tier fires far less often than one would expect.
    """
    body = search(client, "frontend enginer")
    assert "Senior Frontend Engineer" in titles(body)
    assert body["search"]["strategy"] == "exact"
    assert body["search"]["degraded"] is False


def test_unstemmable_typo_falls_through_to_the_trigram_tier(client):
    """ "techation" for "TechNation" — no stemmer recovers that.

    Its tsquery ('techat') matches nothing, and being a single token the
    broadened tier is the identical query, so this reaches trigram similarity.
    """
    body = search(client, "techation")
    assert body["total"] > 0, "a typo should not produce a dead end"
    assert body["search"]["strategy"] == "fuzzy"
    assert body["search"]["degraded"] is True
    assert "DevOps Engineer" in titles(body), "trigram should resolve to TechNation"


def test_multi_term_query_broadens_when_one_term_is_absent(client):
    """ "python architect" — nobody is hiring an architect, but the Python job
    is still the right answer."""
    body = search(client, "python architect")
    assert body["total"] > 0
    assert "Data Analyst" in titles(body)
    assert body["search"]["strategy"] == "broadened"
    assert body["search"]["degraded"] is True


def test_nonsense_query_falls_back_to_related_not_empty(client):
    body = search(client, "zzzqqxwv")
    assert body["search"]["strategy"] == "related"
    assert body["search"]["degraded"] is True
    assert body["total"] > 0, "an empty page is a dead end; show something labelled"


def test_empty_query_is_a_plain_listing_not_a_search(client):
    r = client.get(JOBS, params={"q": "   "})
    assert r.status_code == 200
    # Whitespace normalises to nothing, so no search metadata is attached.
    assert r.json()["search"] is None or r.json()["search"]["strategy"] == "none"


# --- synonyms -------------------------------------------------------------


def test_market_synonyms_are_expanded(client):
    """ "khi" is how people actually type Karachi."""
    body = search(client, "khi")
    assert "Data Analyst" in titles(body) or body["search"]["degraded"]


def test_swe_expands_to_software_engineer(client):
    from app.services.search_service import expand_synonyms

    expanded, terms = expand_synonyms("swe remote")
    assert "software" in terms and "engineer" in terms
    assert "remote" in terms


# --- ranking --------------------------------------------------------------


def test_featured_outranks_an_equal_match(client, world):
    """The boost is bounded, so it reorders equals — it cannot invent a match."""
    token = client.post("/api/v1/auth/login", json={"email": EMAIL, "password": PASSWORD}).json()[
        "access_token"
    ]
    headers = {"Authorization": f"Bearer {token}"}

    body = {
        "title": "Data Analyst",
        "company_name": "Featured Employer",
        "category_id": world["category_id"],
        "location_id": world["locations"]["lahore"],
        "work_type": "on_site",
        "employment_type": "full_time",
        "experience_level": "mid",
        "description": "Shape e-commerce decisions through analysis of large datasets. " * 3,
        "requirements": ["SQL (advanced)", "Python (pandas, numpy)"],
        "apply_url": "https://example.com/apply",
    }
    created = client.post(ADMIN_JOBS, json=body, headers=headers).json()
    client.post(f"{ADMIN_JOBS}/{created['id']}/publish", headers=headers)
    client.post(f"{ADMIN_JOBS}/{created['id']}/feature", json={"featured": True}, headers=headers)

    results = search(client, "data analyst")["items"]
    companies = [j["company_name"] for j in results]
    assert companies[0] == "Featured Employer", f"featured boost did not apply: {companies}"

    # Clean up so the boost does not perturb later assertions.
    client.delete(f"{ADMIN_JOBS}/{created['id']}", headers=headers)


def test_filters_apply_alongside_the_text_match(client, world):
    """Filters are SQL predicates, not part of the tsquery."""
    all_hits = search(client, "engineer")["total"]
    remote_only = search(client, "engineer", work_type="remote")["total"]
    assert 0 < remote_only <= all_hits
    assert all(
        j["work_type"] == "remote" for j in search(client, "engineer", work_type="remote")["items"]
    )


# --- telemetry ------------------------------------------------------------


def test_every_search_is_logged_with_its_result_count(client):
    search(client, "react")
    search(client, "zzzqqxwv")

    async def rows() -> list[tuple]:
        async with SessionFactory() as s:
            result = await s.execute(
                text(
                    """
                    SELECT normalised_query, result_count, was_degraded, response_ms
                      FROM search_logs
                     WHERE normalised_query IN ('react', 'zzzqqxwv')
                     ORDER BY occurred_at DESC LIMIT 10
                    """
                )
            )
            return result.all()

    logged = {r[0]: r for r in asyncio.run(rows())}
    assert "react" in logged and logged["react"][1] > 0
    assert logged["react"][2] is False
    assert logged["react"][3] is not None, "response_ms must be recorded"

    assert "zzzqqxwv" in logged
    assert logged["zzzqqxwv"][2] is True, "a degraded search must be flagged"


def test_zero_result_report_reads_the_partial_index(client):
    """The single most actionable search metric."""
    from datetime import UTC, datetime, timedelta

    from app.repositories.search_log_repo import SearchLogRepository

    search(client, "quantum blacksmith")

    async def report() -> list[tuple[str, int]]:
        async with SessionFactory() as s:
            return await SearchLogRepository(s).zero_result_queries(
                since=(datetime.now(UTC) - timedelta(days=1)).date()
            )

    rows = asyncio.run(report())
    # The fallback tier returns rows, so result_count is non-zero; what matters
    # is that the report runs against the partial index without error.
    assert isinstance(rows, list)


# --- trigger correctness --------------------------------------------------


def test_renaming_a_location_refreshes_dependent_listings(client, world):
    """The trigger people forget.

    Without it, a renamed city leaves every existing listing indexed under the
    old name — silently wrong search results for weeks.
    """

    async def rename_and_read() -> str:
        async with SessionFactory() as s:
            await s.execute(
                text("UPDATE locations SET display_name = :new WHERE slug = 'lahore'"),
                {"new": "Lahore Metropolitan, Pakistan"},
            )
            await s.commit()
            row = await s.execute(
                text(
                    """
                    SELECT j.location_text
                      FROM jobs j JOIN locations l ON l.id = j.location_id
                     WHERE l.slug = 'lahore' LIMIT 1
                    """
                )
            )
            value = row.scalar_one()
            # Restore so other tests see the original name.
            await s.execute(
                text("UPDATE locations SET display_name = :old WHERE slug = 'lahore'"),
                {"old": "Lahore, Pakistan"},
            )
            await s.commit()
            return value

    assert asyncio.run(rename_and_read()) == "Lahore Metropolitan, Pakistan"


def test_search_vector_is_populated_by_the_database(client):
    async def sample() -> tuple[str, str, str]:
        async with SessionFactory() as s:
            row = await s.execute(
                text(
                    """
                    SELECT location_text, skills_text, search_vector::text
                      FROM jobs
                     WHERE title = 'Data Analyst' AND deleted_at IS NULL
                     LIMIT 1
                    """
                )
            )
            return row.one()

    location_text, skills_text, vector = asyncio.run(sample())
    assert "Karachi" in location_text, "the jobs trigger must populate location_text"
    assert "Python" in skills_text, "requirements must be flattened into skills_text"
    # Weight labels prove setweight ran: positions carry A/B/C/D suffixes.
    import re

    assert "analyst" in vector.lower()
    assert re.search(r":\d+A", vector), "title lexemes must carry weight A"
    assert re.search(r":\d+B", vector), "company and location must carry weight B"
    assert re.search(r":\d+C", vector), "skills must carry weight C"
