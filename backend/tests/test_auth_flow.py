"""Milestone 2 behavioural tests.

These exercise the paths the blueprint flagged as highest-risk: replay of a
rotated token, two tabs refreshing at once, and a password change mid-session.
Each one is easy to get subtly wrong and expensive to fix after sessions exist
in the wild.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select, text, update

from app.core.enums import SessionRevokeReason
from app.core.permissions import Permission, SystemRole
from app.core.security import hash_password
from app.db.database import SessionFactory
from app.main import app
from app.models.admin import Admin, AdminSession
from app.models.rbac import Role

EMAIL = "test-admin@rozgar.pk"
PASSWORD = "test-password-1234"
COOKIE = "rozgar_refresh"
LOGIN = "/api/v1/auth/login"
REFRESH = "/api/v1/auth/refresh"
LOGOUT = "/api/v1/auth/logout"
ME = "/api/v1/auth/me"


async def _reset_admin(role_key: str = SystemRole.SUPER_ADMIN.value) -> None:
    async with SessionFactory() as s:
        admin = (await s.execute(select(Admin).where(Admin.email == EMAIL))).scalar_one_or_none()
        if admin is not None:
            await s.execute(delete(AdminSession).where(AdminSession.admin_id == admin.id))
            await s.delete(admin)
            await s.commit()

        role = (await s.execute(select(Role).where(Role.key == role_key))).scalar_one()
        s.add(
            Admin(
                email=EMAIL,
                full_name="Test Admin",
                password_hash=hash_password(PASSWORD),
                role_id=role.id,
                is_active=True,
            )
        )
        await s.commit()


@pytest.fixture
def client():
    asyncio.get_event_loop_policy().new_event_loop()
    asyncio.run(_reset_admin())
    with TestClient(app) as c:
        yield c


def login(client: TestClient, password: str = PASSWORD):
    return client.post(LOGIN, json={"email": EMAIL, "password": password})


# --- happy path -----------------------------------------------------------


def test_login_returns_token_and_sets_httponly_cookie(client):
    r = login(client)
    assert r.status_code == 200
    body = r.json()
    assert body["token_type"] == "bearer"
    assert body["access_token"]
    # The refresh token must never appear in a response body.
    assert "refresh_token" not in body

    cookie_header = r.headers.get("set-cookie", "")
    assert "HttpOnly" in cookie_header
    assert "SameSite=strict" in cookie_header.replace("samesite", "SameSite")
    assert COOKIE in client.cookies


def test_me_returns_resolved_permissions(client):
    token = login(client).json()["access_token"]
    r = client.get(ME, headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    body = r.json()
    assert body["email"] == EMAIL
    assert body["role"] == SystemRole.SUPER_ADMIN.value
    # A super admin holds every permission in the enum.
    assert set(body["permissions"]) == {p.value for p in Permission}


def test_me_requires_a_token(client):
    r = client.get(ME)
    assert r.status_code == 401
    assert r.json()["title"]
    assert r.headers["www-authenticate"].startswith("Bearer")


def test_refresh_rotates_the_cookie(client):
    login(client)
    first = client.cookies[COOKIE]

    r = client.post(REFRESH)
    assert r.status_code == 200
    assert r.json()["access_token"]

    second = client.cookies[COOKIE]
    assert second != first, "the refresh token must rotate on every use"


def test_logout_revokes_and_clears(client):
    login(client)
    assert client.post(LOGOUT).status_code == 204
    # Idempotent: a second logout is still a 204.
    assert client.post(LOGOUT).status_code == 204
    assert client.post(REFRESH).status_code == 401


# --- credential failures --------------------------------------------------


def test_wrong_password_is_rejected(client):
    r = login(client, "wrong-password-entirely")
    assert r.status_code == 401
    assert r.json()["type"].endswith("invalid_credentials")


def test_unknown_account_is_indistinguishable_from_a_wrong_password(client):
    unknown = client.post(LOGIN, json={"email": "nobody@rozgar.pk", "password": PASSWORD})
    wrong = login(client, "wrong-password-entirely")
    assert unknown.status_code == wrong.status_code == 401
    # Identical bodies: response content must not enumerate accounts.
    assert unknown.json()["detail"] == wrong.json()["detail"]


def test_account_locks_after_repeated_failures(client):
    for _ in range(5):
        login(client, "wrong-password-entirely")
    r = login(client)  # correct password, but now locked
    assert r.status_code == 423
    assert r.json()["type"].endswith("account_locked")


# --- the three high-risk paths -------------------------------------------


def test_replaying_a_rotated_token_revokes_the_whole_family(client, no_race_window):
    """Reuse detection: the core security property of rotation.

    The race window is disabled for this test so a replay is unambiguously a
    replay rather than a concurrent refresh.
    """
    login(client)
    stolen = client.cookies[COOKIE]

    assert client.post(REFRESH).status_code == 200
    assert client.post(REFRESH).status_code == 200
    current = client.cookies[COOKIE]

    # Attacker presents the captured token.
    client.cookies.set(COOKIE, stolen, path="/api/v1/auth")
    r = client.post(REFRESH)
    assert r.status_code == 401
    assert r.json()["type"].endswith("refresh_token_reused")

    # The legitimate token is now dead too — the family was revoked.
    client.cookies.set(COOKIE, current, path="/api/v1/auth")
    assert client.post(REFRESH).status_code == 401


def test_concurrent_refresh_is_a_race_not_a_breach(client):
    """Two tabs refreshing together must not look like theft."""
    login(client)
    shared = client.cookies[COOKIE]

    # First tab wins and rotates.
    assert client.post(REFRESH).status_code == 200
    winner = client.cookies[COOKIE]

    # Second tab's request was already in flight with the old token.
    client.cookies.set(COOKIE, shared, path="/api/v1/auth")
    r = client.post(REFRESH)
    assert r.status_code == 401
    assert r.json()["type"].endswith("refresh_race"), "a race must not be treated as reuse"

    # The winner's token still works — the family survived.
    client.cookies.set(COOKIE, winner, path="/api/v1/auth")
    assert client.post(REFRESH).status_code == 200


def test_password_change_invalidates_existing_access_tokens(client):
    token = login(client).json()["access_token"]
    assert client.get(ME, headers={"Authorization": f"Bearer {token}"}).status_code == 200

    async def change_password() -> None:
        async with SessionFactory() as s:
            await s.execute(
                update(Admin)
                .where(Admin.email == EMAIL)
                .values(
                    password_hash=hash_password("a-completely-new-password"),
                    password_changed_at=datetime.now(UTC) + timedelta(seconds=5),
                )
            )
            await s.commit()

    asyncio.run(change_password())

    r = client.get(ME, headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 401
    assert r.json()["type"].endswith("invalid_token")


# --- authorisation --------------------------------------------------------


def test_deactivated_account_loses_access_immediately(client):
    token = login(client).json()["access_token"]

    async def deactivate() -> None:
        async with SessionFactory() as s:
            await s.execute(update(Admin).where(Admin.email == EMAIL).values(is_active=False))
            await s.commit()

    asyncio.run(deactivate())

    r = client.get(ME, headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 401, "deactivation must take effect before the token expires"


def test_permission_dependency_allows_and_denies():
    """`require()` is a set membership test over resolved permissions."""
    from app.services.auth_service import Principal

    editor = Principal(
        admin_id=__import__("uuid").uuid4(),
        email="e@rozgar.pk",
        full_name="Editor",
        role_key="editor",
        permissions=frozenset({Permission.JOB_CREATE.value, Permission.JOB_EDIT.value}),
    )
    assert editor.has(Permission.JOB_CREATE.value)
    assert not editor.has(Permission.JOB_PUBLISH.value)
    assert editor.has_any(Permission.JOB_PUBLISH.value, Permission.JOB_EDIT.value)


def test_expired_token_is_rejected(client):
    """An expired signature must fail closed, with its own error code."""
    from app.core.security import create_access_token

    async def mint_expired() -> str:
        async with SessionFactory() as s:
            admin = (await s.execute(select(Admin).where(Admin.email == EMAIL))).scalar_one()
            token, _ = create_access_token(
                admin_id=admin.id,
                role=SystemRole.SUPER_ADMIN.value,
                password_changed_at=admin.password_changed_at,
                now=datetime.now(UTC) - timedelta(hours=2),
            )
            return token

    token = asyncio.run(mint_expired())
    r = client.get(ME, headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 401
    assert r.json()["type"].endswith("token_expired")


def test_refresh_token_is_not_accepted_as_an_access_token(client):
    """Token type confusion: a refresh token must not authenticate a request."""
    login(client)
    refresh_value = client.cookies[COOKIE]
    r = client.get(ME, headers={"Authorization": f"Bearer {refresh_value}"})
    assert r.status_code == 401


def test_only_the_hash_of_a_refresh_token_is_stored(client):
    login(client)
    raw = client.cookies[COOKIE]

    async def find_raw() -> int:
        async with SessionFactory() as s:
            result = await s.execute(
                text("SELECT count(*) FROM admin_sessions WHERE token_hash = :raw"),
                {"raw": raw},
            )
            return result.scalar_one()

    assert asyncio.run(find_raw()) == 0, "the raw token must never be persisted"


def test_session_rows_track_family_and_rotation(client):
    login(client)
    client.post(REFRESH)

    async def inspect() -> list[tuple]:
        async with SessionFactory() as s:
            admin = (await s.execute(select(Admin).where(Admin.email == EMAIL))).scalar_one()
            rows = (
                await s.execute(
                    select(
                        AdminSession.family_id,
                        AdminSession.revoked_reason,
                        AdminSession.replaced_by,
                    ).where(AdminSession.admin_id == admin.id)
                )
            ).all()
            return list(rows)

    rows = asyncio.run(inspect())
    assert len(rows) == 2, "rotation creates a replacement rather than mutating in place"
    families = {r[0] for r in rows}
    assert len(families) == 1, "a rotation stays inside one family"
    rotated = [r for r in rows if r[1] == SessionRevokeReason.ROTATED]
    assert len(rotated) == 1
    assert rotated[0][2] is not None, "the rotated row must point at its replacement"
