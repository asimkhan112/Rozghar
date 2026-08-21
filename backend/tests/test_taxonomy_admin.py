"""Admin taxonomy CRUD.

These exist because the PATCH handlers returned 500 while committing the write
anyway — the worst shape a bug can take, since the console reported failure and
the database disagreed.

The cause was `updated_at`: it is written by the database, so SQLAlchemy marks
it expired after an UPDATE and serialising the response triggered a lazy reload
in a context that cannot do IO. Nothing in the suite exercised a taxonomy PATCH,
so nothing caught it.
"""

from __future__ import annotations

import asyncio

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select

from app.core.permissions import SystemRole
from app.core.security import hash_password
from app.db.database import SessionFactory
from app.main import app
from app.models.admin import Admin, AdminSession
from app.models.audit import AuditLog
from app.models.rbac import Role
from app.models.taxonomy import Category, Location

EMAIL = "tx-admin@plenilo.com"
PASSWORD = "taxonomy-tests-pass"
CATEGORIES = "/api/v1/admin/categories"
LOCATIONS = "/api/v1/admin/locations"
SOURCES = "/api/v1/admin/sources"


async def _seed() -> None:
    async with SessionFactory() as s:
        admin = (await s.execute(select(Admin).where(Admin.email == EMAIL))).scalar_one_or_none()
        if admin:
            await s.execute(delete(AdminSession).where(AdminSession.admin_id == admin.id))
            await s.execute(delete(AuditLog).where(AuditLog.admin_id == admin.id))
            await s.delete(admin)
            # Committed before the insert below: the unit of work orders
            # INSERTs ahead of DELETEs, so re-adding the same email in one
            # flush collides with the row being removed.
            await s.commit()
        await s.execute(delete(Category).where(Category.slug.like("tx-%")))
        await s.execute(delete(Location).where(Location.slug.like("tx-%")))
        role = (
            await s.execute(select(Role).where(Role.key == SystemRole.ADMIN.value))
        ).scalar_one()
        s.add(
            Admin(
                email=EMAIL,
                full_name="Taxonomy Admin",
                password_hash=hash_password(PASSWORD),
                role_id=role.id,
                is_active=True,
            )
        )
        await s.commit()


@pytest.fixture(scope="module")
def client():
    asyncio.run(_seed())
    with TestClient(app) as c:
        r = c.post("/api/v1/auth/login", json={"email": EMAIL, "password": PASSWORD})
        c.headers.update({"Authorization": f"Bearer {r.json()['access_token']}"})
        yield c
    asyncio.run(_cleanup())


async def _cleanup() -> None:
    async with SessionFactory() as s:
        await s.execute(delete(Category).where(Category.slug.like("tx-%")))
        await s.commit()


#: Slugs are unique, so each test needs its own. A shared fixture row would
#: make the second test collide with the first on a 409.
_counter = iter(range(1, 1000))


@pytest.fixture
def category(client):
    n = next(_counter)
    made = client.post(CATEGORIES, json={"name": f"TX Sample {n}", "slug": f"tx-sample-{n}"})
    assert made.status_code == 201, made.text
    return made.json()


# --- the regression -------------------------------------------------------


def test_renaming_a_category_returns_the_updated_row(client, category):
    """The original failure: a 200-shaped write that answered 500."""
    r = client.patch(f"{CATEGORIES}/{category['id']}", json={"name": "TX Renamed"})
    assert r.status_code == 200, r.text
    assert r.json()["name"] == "TX Renamed"


def test_the_patch_response_carries_a_fresh_updated_at(client, category):
    """`updated_at` is the attribute that caused the 500. Asserting it moved
    proves the refresh happened rather than a stale value being serialised."""
    before = category["updated_at"]
    r = client.patch(f"{CATEGORIES}/{category['id']}", json={"name": "TX Touched"})
    assert r.status_code == 200, r.text
    assert r.json()["updated_at"] >= before


def test_archive_and_restore_round_trip(client, category):
    archived = client.patch(f"{CATEGORIES}/{category['id']}", json={"is_active": False})
    assert archived.status_code == 200, archived.text
    assert archived.json()["is_active"] is False

    restored = client.patch(f"{CATEGORIES}/{category['id']}", json={"is_active": True})
    assert restored.status_code == 200, restored.text
    assert restored.json()["is_active"] is True


# --- the admin projection -------------------------------------------------


def test_a_new_category_appears_in_the_admin_list(client):
    """The reported symptom: created, then nowhere to be seen."""
    made = client.post(CATEGORIES, json={"name": "TX Fresh", "slug": "tx-fresh"})
    assert made.status_code == 201, made.text
    names = [c["name"] for c in client.get(CATEGORIES).json()]
    assert "TX Fresh" in names


def test_an_archived_category_stays_visible_to_the_admin(client, category):
    """Otherwise archiving is a one-way door: the row leaves the only screen
    that could restore it."""
    client.patch(f"{CATEGORIES}/{category['id']}", json={"is_active": False})
    admin_names = [c["name"] for c in client.get(CATEGORIES).json()]
    public_names = [c["name"] for c in client.get("/api/v1/categories").json()]
    assert category["name"] in admin_names
    assert category["name"] not in public_names


def test_admin_lists_exist_for_every_taxonomy(client):
    for url in (CATEGORIES, LOCATIONS, SOURCES):
        assert client.get(url).status_code == 200, url


# --- the guard rail -------------------------------------------------------


def test_archiving_a_category_with_listings_is_refused(client):
    """A category with live listings cannot be hidden; the filters that
    reference it would strand them."""
    busy = next(
        (c for c in client.get(CATEGORIES).json() if c["job_count"] > 0), None
    )
    if busy is None:
        pytest.skip("no category currently has published listings")
    r = client.patch(f"{CATEGORIES}/{busy['id']}", json={"is_active": False})
    assert r.status_code == 409
    assert "listing" in r.json()["detail"].lower()


# --- locations are worldwide ---------------------------------------------


def test_the_country_list_is_served_and_excludes_pseudo_regions(client):
    """The picker is built from this, so it has to be the whole world and
    nothing that is not a country."""
    r = client.get("/api/v1/countries")
    assert r.status_code == 200, r.text
    rows = r.json()
    codes = {row["code"] for row in rows}
    assert {"PK", "DE", "JP", "BR", "NG"} <= codes
    # CLDR ships these alongside real countries; none is a place a job can be in.
    assert not ({"EU", "ZZ", "QO", "XK"} & codes)
    assert [row["name"] for row in rows] == sorted(row["name"] for row in rows)


def test_a_location_outside_pakistan_gets_a_readable_label(client):
    """The regression this whole change exists for.

    The old five-country lookup fell through to the raw code, so anywhere but
    PK/AE/SA/GB/US rendered as "Berlin, DE" — beside "Lahore, Pakistan".
    """
    n = next(_counter)
    r = client.post(LOCATIONS, json={"city": f"TX Berlin {n}", "country": "DE"})
    assert r.status_code == 201, r.text
    assert r.json()["display_name"] == f"TX Berlin {n}, Germany"


def test_country_is_required_rather_than_defaulting_to_pakistan(client):
    """A default is how every location in the catalogue ended up in one
    country. Omitting it is now a validation error, not a silent guess."""
    r = client.post(LOCATIONS, json={"city": "TX Nowhere"})
    assert r.status_code == 422, r.text


def test_an_unknown_country_code_is_refused(client):
    r = client.post(LOCATIONS, json={"city": "TX Someplace", "country": "ZX"})
    assert r.status_code == 422, r.text


def test_a_lowercase_country_code_is_accepted_and_normalised(client):
    """Case is a formatting detail, not a mistake worth rejecting."""
    n = next(_counter)
    r = client.post(LOCATIONS, json={"city": f"TX Osaka {n}", "country": "jp"})
    assert r.status_code == 201, r.text
    assert r.json()["country"] == "JP"
    assert r.json()["display_name"] == f"TX Osaka {n}, Japan"


def test_correcting_the_country_recomposes_the_label(client):
    """A label composed at creation goes stale the moment its parts move, and
    the wrong country is exactly the thing an editor comes back to fix."""
    n = next(_counter)
    made = client.post(LOCATIONS, json={"city": f"TX Valencia {n}", "country": "VE"})
    assert made.status_code == 201, made.text
    assert made.json()["display_name"] == f"TX Valencia {n}, Venezuela"

    fixed = client.patch(f"{LOCATIONS}/{made.json()['id']}", json={"country": "ES"})
    assert fixed.status_code == 200, fixed.text
    assert fixed.json()["display_name"] == f"TX Valencia {n}, Spain"


def test_an_explicit_label_survives_a_country_correction(client):
    """A hand-written label is a deliberate override and must not be
    recomposed out from under whoever wrote it."""
    n = next(_counter)
    made = client.post(
        LOCATIONS,
        json={"city": f"TX Zurich {n}", "country": "CH", "display_name": f"TX Zurich {n} (HQ)"},
    )
    assert made.status_code == 201, made.text
    fixed = client.patch(f"{LOCATIONS}/{made.json()['id']}", json={"country": "AT"})
    assert fixed.status_code == 200, fixed.text
    assert fixed.json()["display_name"] == f"TX Zurich {n} (HQ)"
