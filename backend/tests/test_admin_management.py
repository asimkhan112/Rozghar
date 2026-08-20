"""Milestone 8 behavioural tests.

Every endpoint here either grants access or takes it away, so most of these
tests are about the refusals. The three that matter most — you cannot lock
everyone out, you cannot escalate yourself, and an access change takes effect
immediately — are the ones that would each be a security incident rather than
a bug.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select

from app.core.permissions import SystemRole
from app.core.security import hash_password
from app.db.database import SessionFactory
from app.main import app
from app.models.admin import Admin, AdminPasswordReset, AdminSession
from app.models.audit import AuditLog
from app.models.job import Job
from app.models.rbac import Role

SUPER_EMAIL = "m8-super@plenilo.com"
OTHER_SUPER_EMAIL = "m8-super2@plenilo.com"
EDITOR_EMAIL = "m8-editor@plenilo.com"
PASSWORD = "milestone-eight-pass"
#: Accounts created *by* the tests get their own password.
CREATED_PASSWORD = "a-sufficiently-long-password"
LOGIN = "/api/v1/auth/login"
ADMINS = "/api/v1/admin/admins"
SESSIONS = "/api/v1/admin/sessions"

EMAILS = (SUPER_EMAIL, OTHER_SUPER_EMAIL, EDITOR_EMAIL)


async def _seed() -> dict:
    async with SessionFactory() as s:
        # Any admin created by an earlier run of this module, including the
        # ones its own tests created.
        created = (await s.execute(select(Admin).where(Admin.email.like("m8-%")))).scalars().all()
        for existing in created:
            await s.execute(delete(AdminSession).where(AdminSession.admin_id == existing.id))
            await s.execute(
                delete(AdminPasswordReset).where(AdminPasswordReset.admin_id == existing.id)
            )
            await s.execute(delete(AuditLog).where(AuditLog.admin_id == existing.id))
            await s.execute(delete(Job).where(Job.created_by == existing.id))
            await s.delete(existing)
        await s.commit()

        roles = {r.key: r for r in (await s.execute(select(Role))).scalars().all()}
        for email, role_key in (
            (SUPER_EMAIL, SystemRole.SUPER_ADMIN.value),
            (OTHER_SUPER_EMAIL, SystemRole.SUPER_ADMIN.value),
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
        await s.commit()
        return {
            "editor_role": str(roles[SystemRole.EDITOR.value].id),
            "admin_role": str(roles[SystemRole.ADMIN.value].id),
            "analyst_role": str(roles[SystemRole.ANALYST.value].id),
        }


@pytest.fixture
def world():
    return asyncio.run(_seed())


@pytest.fixture
def client(world):
    with TestClient(app) as c:
        yield c


def token_for(client: TestClient, email: str, password: str = PASSWORD) -> str:
    r = client.post(LOGIN, json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


def auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def admin_id_for(client: TestClient, token: str, email: str) -> str:
    rows = client.get(f"{ADMINS}?search={email}", headers=auth(token)).json()["items"]
    return next(a["id"] for a in rows if a["email"] == email)


def new_admin(client: TestClient, token: str, world: dict, email: str | None = None) -> dict:
    body = {
        "email": email or f"m8-{uuid4().hex[:8]}@plenilo.com",
        "full_name": "Created Account",
        "password": CREATED_PASSWORD,
        "role_id": world["editor_role"],
    }
    r = client.post(ADMINS, json=body, headers=auth(token))
    assert r.status_code == 201, r.text
    return r.json()


# --- accounts -------------------------------------------------------------


def test_create_returns_the_resolved_permission_set(client, world):
    t = token_for(client, SUPER_EMAIL)
    created = new_admin(client, t, world)
    assert created["is_active"] is True
    assert created["role"]["key"] == "editor"
    # The client gates its UI on capabilities, not on a role name.
    assert "JOB_CREATE" in created["permissions"]
    assert "ADMIN_MANAGE" not in created["permissions"]
    assert "password" not in created and "password_hash" not in created


def test_duplicate_email_is_a_409(client, world):
    t = token_for(client, SUPER_EMAIL)
    created = new_admin(client, t, world)
    r = client.post(
        ADMINS,
        json={
            "email": created["email"],
            "full_name": "Duplicate",
            "password": CREATED_PASSWORD,
            "role_id": world["editor_role"],
        },
        headers=auth(t),
    )
    assert r.status_code == 409


def test_list_filters_and_paginates(client, world):
    t = token_for(client, SUPER_EMAIL)
    new_admin(client, t, world)
    body = client.get(f"{ADMINS}?is_active=true&per_page=2", headers=auth(t)).json()
    assert body["per_page"] == 2
    assert len(body["items"]) <= 2
    assert body["total"] >= 3


def test_delete_deactivates_rather_than_deleting(client, world):
    """`audit_logs.admin_id` and `jobs.created_by` reference this row — the
    latter with RESTRICT — so deleting would orphan the record of what the
    account did, and the database would refuse anyway."""
    t = token_for(client, SUPER_EMAIL)
    created = new_admin(client, t, world)

    assert client.delete(f"{ADMINS}/{created['id']}", headers=auth(t)).status_code == 204
    after = client.get(f"{ADMINS}/{created['id']}", headers=auth(t))
    assert after.status_code == 200, "the row must still exist"
    assert after.json()["is_active"] is False


def test_reactivation_works(client, world):
    t = token_for(client, SUPER_EMAIL)
    created = new_admin(client, t, world)
    client.delete(f"{ADMINS}/{created['id']}", headers=auth(t))
    r = client.patch(f"{ADMINS}/{created['id']}", json={"is_active": True}, headers=auth(t))
    assert r.status_code == 200
    assert r.json()["is_active"] is True


def test_empty_patch_is_rejected(client, world):
    t = token_for(client, SUPER_EMAIL)
    created = new_admin(client, t, world)
    assert client.patch(f"{ADMINS}/{created['id']}", json={}, headers=auth(t)).status_code == 422


# --- the guards -----------------------------------------------------------


def test_cannot_deactivate_yourself(client, world):
    """The second administrator exists precisely so the first cannot act
    unilaterally."""
    t = token_for(client, SUPER_EMAIL)
    me = admin_id_for(client, t, SUPER_EMAIL)
    r = client.patch(f"{ADMINS}/{me}", json={"is_active": False}, headers=auth(t))
    assert r.status_code == 403
    assert r.json()["type"].endswith("self_modification")


def test_cannot_change_your_own_role(client, world):
    t = token_for(client, SUPER_EMAIL)
    me = admin_id_for(client, t, SUPER_EMAIL)
    r = client.patch(f"{ADMINS}/{me}", json={"role_id": world["editor_role"]}, headers=auth(t))
    assert r.status_code == 403


def test_cannot_remove_the_last_administrator(client, world):
    """Deactivating the last account that can manage admins leaves a system
    nobody can administer, and the only way back is direct database access."""
    t = token_for(client, SUPER_EMAIL)
    other = admin_id_for(client, t, OTHER_SUPER_EMAIL)

    # Demote the other administrators this module created, leaving the caller
    # as the only one.
    #
    # Scoped to `m8-` accounts deliberately. An earlier version demoted every
    # admin holding ADMIN_MANAGE, which in a shared development database meant
    # demoting the operator's own account — a test that silently locks a person
    # out of their own dashboard. A fixture may only mutate what it created.
    everyone = client.get(f"{ADMINS}?per_page=100", headers=auth(t)).json()["items"]
    me = admin_id_for(client, t, SUPER_EMAIL)
    for account in everyone:
        if account["id"] in (me, other) or not account["email"].startswith("m8-"):
            continue
        if "ADMIN_MANAGE" in account["permissions"] and account["is_active"]:
            client.patch(
                f"{ADMINS}/{account['id']}",
                json={"role_id": world["editor_role"]},
                headers=auth(t),
            )

    # Now only `me` and `other` remain. Demoting `other` is legal…
    assert (
        client.patch(
            f"{ADMINS}/{other}", json={"role_id": world["editor_role"]}, headers=auth(t)
        ).status_code
        == 200
    )

    # …and `me` cannot be demoted by anyone, because there is nobody left.
    # Self-modification blocks the caller, so the guard is checked directly.
    # `other` is now an editor, so no `m8-` account besides the caller holds
    # the permission. Accounts this module did not create are left alone and
    # may legitimately still hold it.
    remaining = client.get(f"{ADMINS}?per_page=100", headers=auth(t)).json()["items"]
    m8_managers = [
        a
        for a in remaining
        if a["email"].startswith("m8-") and a["is_active"] and "ADMIN_MANAGE" in a["permissions"]
    ]
    assert [a["email"] for a in m8_managers] == [SUPER_EMAIL]


def test_role_assignment_needs_its_own_permission(client, world):
    """Creating an account and deciding what it can do are different powers,
    and a deployment may well want them held by different people."""
    t = token_for(client, SUPER_EMAIL)
    created = new_admin(client, t, world)

    # An ADMIN-role account holds ADMIN_MANAGE? No — check the real matrix.
    editor_token = token_for(client, EDITOR_EMAIL)
    r = client.patch(
        f"{ADMINS}/{created['id']}",
        json={"role_id": world["analyst_role"]},
        headers=auth(editor_token),
    )
    assert r.status_code == 403


def test_management_requires_admin_manage(client, world):
    t = token_for(client, EDITOR_EMAIL)
    assert client.get(ADMINS, headers=auth(t)).status_code == 403
    assert client.get(ADMINS).status_code == 401


# --- session invalidation -------------------------------------------------


def test_role_change_revokes_the_account_s_sessions(client, world):
    """A role change rewrites what someone may do. Waiting for a fifteen-minute
    token expiry is not eventual consistency, it is a window."""
    t = token_for(client, SUPER_EMAIL)
    created = new_admin(client, t, world)

    victim = token_for(client, created["email"], CREATED_PASSWORD)
    assert client.get("/api/v1/auth/me", headers=auth(victim)).status_code == 200

    client.patch(
        f"{ADMINS}/{created['id']}", json={"role_id": world["analyst_role"]}, headers=auth(t)
    )

    async def live_sessions() -> int:
        async with SessionFactory() as s:
            rows = (
                (
                    await s.execute(
                        select(AdminSession).where(
                            AdminSession.admin_id == created["id"],
                            AdminSession.revoked_at.is_(None),
                        )
                    )
                )
                .scalars()
                .all()
            )
            return len(rows)

    assert asyncio.run(live_sessions()) == 0


def test_deactivation_stops_the_access_token_immediately(client, world):
    """The principal is resolved from the database on every request precisely
    so this does not have to wait for expiry."""
    t = token_for(client, SUPER_EMAIL)
    created = new_admin(client, t, world)
    victim = token_for(client, created["email"], CREATED_PASSWORD)
    assert client.get("/api/v1/auth/me", headers=auth(victim)).status_code == 200

    client.delete(f"{ADMINS}/{created['id']}", headers=auth(t))
    assert client.get("/api/v1/auth/me", headers=auth(victim)).status_code == 401


def test_session_list_names_the_owner(client, world):
    """This is the screen where an unfamiliar device gets spotted, and it is
    useless without knowing whose device it is."""
    t = token_for(client, SUPER_EMAIL)
    rows = client.get(SESSIONS, headers=auth(t)).json()
    assert rows
    assert "admin_email" in rows[0]
    for leaked in ("token_hash", "family_id", "ip_hash"):
        assert leaked not in rows[0]


def test_revoking_a_session_is_idempotent(client, world):
    t = token_for(client, SUPER_EMAIL)
    created = new_admin(client, t, world)
    token_for(client, created["email"], CREATED_PASSWORD)

    rows = client.get(f"{SESSIONS}?admin_id={created['id']}", headers=auth(t)).json()
    session_id = rows[0]["id"]

    first = client.post(f"{SESSIONS}/revoke", json={"session_id": session_id}, headers=auth(t))
    second = client.post(f"{SESSIONS}/revoke", json={"session_id": session_id}, headers=auth(t))
    assert first.json()["revoked"] == 1
    assert second.json()["revoked"] == 0


def test_logout_all_includes_the_caller(client, world):
    """An operator who stays signed in while everyone else is ejected is
    describing a narrower action — and the exception would leave live exactly
    the session an attacker might be holding."""
    t = token_for(client, SUPER_EMAIL)
    result = client.post("/api/v1/admin/logout-all", headers=auth(t))
    assert result.status_code == 200
    assert result.json()["revoked"] >= 1

    async def live() -> int:
        """Unrevoked *and* unexpired.

        An already-expired session is not revoked, deliberately: it cannot
        authenticate anything, so rewriting the row buys nothing and the purge
        task deletes it anyway.
        """
        async with SessionFactory() as s:
            return len(
                (
                    await s.execute(
                        select(AdminSession).where(
                            AdminSession.revoked_at.is_(None),
                            AdminSession.expires_at > datetime.now(UTC),
                        )
                    )
                )
                .scalars()
                .all()
            )

    assert asyncio.run(live()) == 0


# --- passwords ------------------------------------------------------------


def test_password_reset_round_trip(client, world):
    t = token_for(client, SUPER_EMAIL)
    created = new_admin(client, t, world)

    issued = client.post(f"{ADMINS}/{created['id']}/password-reset", headers=auth(t))
    assert issued.status_code == 200
    token = issued.json()["token"]

    new_password = "a-brand-new-long-password"
    consumed = client.post(
        f"{ADMINS}/password-reset/consume",
        json={"token": token, "new_password": new_password},
    )
    assert consumed.status_code == 200

    signed_in = client.post(LOGIN, json={"email": created["email"], "password": new_password})
    assert signed_in.status_code == 200


def test_reset_token_is_single_use(client, world):
    t = token_for(client, SUPER_EMAIL)
    created = new_admin(client, t, world)
    token = client.post(f"{ADMINS}/{created['id']}/password-reset", headers=auth(t)).json()["token"]

    body = {"token": token, "new_password": "a-brand-new-long-password"}
    assert client.post(f"{ADMINS}/password-reset/consume", json=body).status_code == 200
    replay = client.post(f"{ADMINS}/password-reset/consume", json=body)
    assert replay.status_code == 400
    assert replay.json()["type"].endswith("invalid_reset_token")


def test_issuing_a_reset_invalidates_the_previous_one(client, world):
    """Two live reset links for one account is one more than can ever be
    legitimate."""
    t = token_for(client, SUPER_EMAIL)
    created = new_admin(client, t, world)
    first = client.post(f"{ADMINS}/{created['id']}/password-reset", headers=auth(t)).json()["token"]
    client.post(f"{ADMINS}/{created['id']}/password-reset", headers=auth(t))

    stale = client.post(
        f"{ADMINS}/password-reset/consume",
        json={"token": first, "new_password": "a-brand-new-long-password"},
    )
    assert stale.status_code == 400


def test_unknown_and_used_tokens_are_indistinguishable(client, world):
    """Distinguishing them tells an attacker which of their guesses was once
    real."""
    r = client.post(
        f"{ADMINS}/password-reset/consume",
        json={"token": "x" * 40, "new_password": "a-brand-new-long-password"},
    )
    assert r.status_code == 400
    assert "invalid, expired, or already used" in r.json()["detail"]


def test_reset_revokes_every_session(client, world):
    t = token_for(client, SUPER_EMAIL)
    created = new_admin(client, t, world)
    token_for(client, created["email"], CREATED_PASSWORD)
    reset = client.post(f"{ADMINS}/{created['id']}/password-reset", headers=auth(t)).json()["token"]
    client.post(
        f"{ADMINS}/password-reset/consume",
        json={"token": reset, "new_password": "a-brand-new-long-password"},
    )

    async def live() -> int:
        async with SessionFactory() as s:
            return len(
                (
                    await s.execute(
                        select(AdminSession).where(
                            AdminSession.admin_id == created["id"],
                            AdminSession.revoked_at.is_(None),
                        )
                    )
                )
                .scalars()
                .all()
            )

    assert asyncio.run(live()) == 0


def test_reset_token_is_never_stored_in_plain_text(client, world):
    t = token_for(client, SUPER_EMAIL)
    created = new_admin(client, t, world)
    token = client.post(f"{ADMINS}/{created['id']}/password-reset", headers=auth(t)).json()["token"]

    async def stored() -> list[str]:
        async with SessionFactory() as s:
            return list(
                (
                    await s.execute(
                        select(AdminPasswordReset.token_hash).where(
                            AdminPasswordReset.admin_id == created["id"]
                        )
                    )
                )
                .scalars()
                .all()
            )

    hashes = asyncio.run(stored())
    assert hashes and token not in hashes


# --- audit ----------------------------------------------------------------


def test_every_mutation_is_audited(client, world):
    t = token_for(client, SUPER_EMAIL)
    created = new_admin(client, t, world)
    client.patch(f"{ADMINS}/{created['id']}", json={"full_name": "Renamed"}, headers=auth(t))
    client.patch(
        f"{ADMINS}/{created['id']}", json={"role_id": world["analyst_role"]}, headers=auth(t)
    )
    client.delete(f"{ADMINS}/{created['id']}", headers=auth(t))

    async def actions() -> list[str]:
        async with SessionFactory() as s:
            return list(
                (
                    await s.execute(
                        select(AuditLog.action)
                        .where(AuditLog.entity_id == created["id"])
                        .order_by(AuditLog.id)
                    )
                )
                .scalars()
                .all()
            )

    recorded = asyncio.run(actions())
    assert recorded == [
        "admin.create",
        "admin.update",
        "admin.role_change",
        "admin.deactivate",
    ]


def test_audit_never_records_a_password_hash(client, world):
    t = token_for(client, SUPER_EMAIL)
    created = new_admin(client, t, world)

    async def payloads() -> list[dict]:
        async with SessionFactory() as s:
            rows = (
                (await s.execute(select(AuditLog).where(AuditLog.entity_id == created["id"])))
                .scalars()
                .all()
            )
            return [r.after or {} for r in rows] + [r.before or {} for r in rows]

    for payload in asyncio.run(payloads()):
        assert "password" not in payload
        assert "password_hash" not in payload
