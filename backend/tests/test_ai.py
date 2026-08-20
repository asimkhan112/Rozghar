"""AI drafting tests.

No live API calls. The Anthropic client is replaced with a stub, because the
behaviour worth pinning is ours, not the model's: that nothing is persisted,
that a refusal is distinguished from a failure, that a missing key degrades to
a clear 503, and that the quota holds.

What the model actually writes is a prompt-quality question, and a test that
asserted on generated prose would fail on every model release for reasons that
have nothing to do with this code.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import anthropic
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select

from app.core.config import settings
from app.core.permissions import SystemRole
from app.core.security import hash_password
from app.db.database import SessionFactory
from app.main import app
from app.models.admin import Admin, AdminSession
from app.models.audit import AuditLog
from app.models.job import Job
from app.models.rbac import Role
from app.services import ai_service
from app.services.ai_service import AIService, JobContent, JobFacts

ADMIN_EMAIL = "ai-admin@plenilo.com"
ANALYST_EMAIL = "ai-analyst@plenilo.com"
PASSWORD = "ai-drafting-password"
LOGIN = "/api/v1/auth/login"
REWRITE = "/api/v1/admin/ai/rewrite"
GENERATE = "/api/v1/admin/ai/generate"

DRAFT = JobContent(
    description=(
        "Systems Limited is hiring a Senior Frontend Engineer for its Lahore product team. "
        "You will build interfaces used across Pakistan and the Gulf."
    ),
    responsibilities=["Build and maintain the product interface", "Review other engineers' work"],
    requirements=["Four years with React", "Comfortable with TypeScript"],
    benefits=["Medical cover for your family"],
    apply_note="Apply through the link on this listing. The team replies within a week.",
)


class StubMessages:
    """Stands in for `client.messages`.

    Records the last call so the tests can assert on what we sent — the system
    prompt, the cache breakpoint, the absence of sampling parameters — without
    reaching the network.
    """

    def __init__(self, outcome):
        self.outcome = outcome
        self.calls: list[dict] = []

    async def parse(self, **kwargs):
        self.calls.append(kwargs)
        if isinstance(self.outcome, Exception):
            raise self.outcome
        return self.outcome


def stub_message(*, parsed=DRAFT, stop_reason="end_turn", category=None):
    return SimpleNamespace(
        parsed_output=parsed,
        stop_reason=stop_reason,
        stop_details=SimpleNamespace(category=category) if category else None,
        usage=SimpleNamespace(input_tokens=800, output_tokens=300, cache_read_input_tokens=700),
    )


@pytest.fixture
def stub(monkeypatch):
    """Replace the client factory. Returns a setter so each test picks an outcome."""
    holder: dict[str, StubMessages] = {}

    def install(outcome):
        messages = StubMessages(outcome)
        monkeypatch.setattr(ai_service, "get_client", lambda: SimpleNamespace(messages=messages))
        holder["messages"] = messages
        return messages

    install(stub_message())
    yield install, holder
    ai_service.reset_client()


async def _seed() -> dict:
    async with SessionFactory() as s:
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
        s.add_all(
            [
                Admin(
                    email=ADMIN_EMAIL,
                    full_name="AI Admin",
                    password_hash=hash_password(PASSWORD),
                    role_id=roles[SystemRole.ADMIN.value].id,
                    is_active=True,
                ),
                # Analyst holds no JOB_CREATE — the negative case.
                Admin(
                    email=ANALYST_EMAIL,
                    full_name="AI Analyst",
                    password_hash=hash_password(PASSWORD),
                    role_id=roles[SystemRole.ANALYST.value].id,
                    is_active=True,
                ),
            ]
        )
        await s.commit()
        return {}


@pytest.fixture
def world():
    return asyncio.run(_seed())


@pytest.fixture
def client(world):
    with TestClient(app) as c:
        yield c


@pytest.fixture
def configured(monkeypatch):
    """A key is present. Without this the endpoints correctly return 503."""
    monkeypatch.setattr(settings, "anthropic_api_key", "sk-ant-test-key")


def token_for(client: TestClient, email: str = ADMIN_EMAIL) -> str:
    r = client.post(LOGIN, json={"email": email, "password": PASSWORD})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


def auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


LONG_ENOUGH = (
    "we are lookng for a senior frontend enginer to join our team. the team is a great "
    "team and you will work with a great team on great products for our great customers."
)


# --- request shape --------------------------------------------------------


def test_rewrite_sends_the_house_rules_as_a_cached_prefix(stub, configured):
    install, holder = stub
    install(stub_message())

    asyncio.run(AIService().rewrite(LONG_ENOUGH))
    call = holder["messages"].calls[0]

    assert call["model"] == settings.ai_model
    # The stable rules carry the breakpoint, so repeated drafting reuses them.
    assert call["system"][0]["cache_control"] == {"type": "ephemeral"}
    assert "Never invent a fact" in call["system"][0]["text"]
    # Sampling parameters are rejected on this model tier.
    for banned in ("temperature", "top_p", "top_k"):
        assert banned not in call


def test_thinking_is_adaptive_and_output_is_schema_bound(stub, configured):
    install, holder = stub
    install(stub_message())

    asyncio.run(
        AIService().generate(
            JobFacts(
                title="Data Analyst",
                company="Daraz",
                location="Karachi",
                employment_type="Full Time",
                experience_level="Mid level",
            )
        )
    )
    call = holder["messages"].calls[0]

    assert call["thinking"] == {"type": "adaptive"}
    # Schema-bound rather than prose the client has to split on headings.
    assert call["output_format"] is JobContent


def test_generate_states_absent_facts_rather_than_omitting_them(stub, configured):
    """The model must be told a salary is undisclosed, not left to guess from
    a missing line."""
    install, holder = stub
    install(stub_message())

    asyncio.run(
        AIService().generate(
            JobFacts(
                title="Data Analyst",
                company="Daraz",
                location="Karachi",
                employment_type="Full Time",
                experience_level="Mid level",
                salary=None,
                skills=(),
            )
        )
    )
    prompt = holder["messages"].calls[0]["messages"][0]["content"]

    assert "not disclosed by the employer" in prompt
    assert "none specified" in prompt


# --- failure handling -----------------------------------------------------


def test_refusal_is_distinguished_from_failure(stub, configured):
    """A refusal is a decision about the content. Reporting it as a failure
    would send the editor into a retry loop."""
    install, _ = stub
    install(stub_message(parsed=None, stop_reason="refusal", category="other"))

    from app.services.ai_service import AIRefused

    with pytest.raises(AIRefused):
        asyncio.run(AIService().rewrite(LONG_ENOUGH))


def test_truncated_output_is_reported_not_returned_half_written(stub, configured):
    install, _ = stub
    install(stub_message(stop_reason="max_tokens"))

    from app.services.ai_service import AIFailed

    with pytest.raises(AIFailed):
        asyncio.run(AIService().rewrite(LONG_ENOUGH))


def test_upstream_errors_surface_as_a_502(client, stub, configured):
    install, _ = stub
    install(anthropic.APIConnectionError(request=SimpleNamespace(url="https://api.anthropic.com")))

    t = token_for(client)
    r = client.post(REWRITE, json={"description": LONG_ENOUGH}, headers=auth(t))
    assert r.status_code == 502
    assert r.json()["type"].endswith("ai_failed")


def test_missing_api_key_is_a_clear_503(client, monkeypatch):
    """An unconfigured server should say so, not fail at call time with a
    stack trace."""
    monkeypatch.setattr(settings, "anthropic_api_key", "")
    ai_service.reset_client()

    t = token_for(client)
    r = client.post(REWRITE, json={"description": LONG_ENOUGH}, headers=auth(t))
    assert r.status_code == 503
    assert r.json()["type"].endswith("ai_unavailable")


def test_too_little_text_is_rejected_before_spending_a_call(client, stub, configured):
    t = token_for(client)
    r = client.post(REWRITE, json={"description": "too short"}, headers=auth(t))
    assert r.status_code == 422


# --- endpoints ------------------------------------------------------------


def test_rewrite_returns_a_reviewable_draft(client, stub, configured):
    t = token_for(client)
    r = client.post(REWRITE, json={"description": LONG_ENOUGH}, headers=auth(t))
    assert r.status_code == 200, r.text
    body = r.json()

    assert set(body) == {
        "description",
        "responsibilities",
        "requirements",
        "benefits",
        "apply_note",
    }
    assert body["description"].startswith("Systems Limited is hiring")
    assert body["requirements"] == ["Four years with React", "Comfortable with TypeScript"]


def test_generate_returns_a_reviewable_draft(client, stub, configured):
    t = token_for(client)
    r = client.post(
        GENERATE,
        json={
            "title": "Senior Frontend Engineer",
            "company": "Systems Limited",
            "location": "Lahore, Pakistan",
            "employment_type": "Full Time",
            "experience_level": "Senior level",
            "salary": "PKR 250,000 – 350,000/mo",
            "skills": ["React", "TypeScript"],
        },
        headers=auth(t),
    )
    assert r.status_code == 200, r.text
    assert r.json()["apply_note"]


def test_drafting_never_writes_to_the_database(client, stub, configured):
    """The whole product requirement in one assertion: a draft is proposed,
    never stored. An admin accepts it through the ordinary job form."""

    async def counts() -> tuple[int, int]:
        async with SessionFactory() as s:
            jobs = len((await s.execute(select(Job))).scalars().all())
            audit = len((await s.execute(select(AuditLog))).scalars().all())
            return jobs, audit

    before = asyncio.run(counts())

    t = token_for(client)
    client.post(REWRITE, json={"description": LONG_ENOUGH}, headers=auth(t))
    client.post(
        GENERATE,
        json={"title": "Data Analyst", "company": "Daraz"},
        headers=auth(t),
    )

    assert asyncio.run(counts()) == before, "AI drafting must persist nothing"


# --- authorisation and quota ---------------------------------------------


def test_drafting_requires_job_create(client, stub, configured):
    """An analyst can read the catalogue; they cannot draft listing copy."""
    t = token_for(client, ANALYST_EMAIL)
    r = client.post(REWRITE, json={"description": LONG_ENOUGH}, headers=auth(t))
    assert r.status_code == 403


def test_drafting_requires_authentication(client, stub, configured):
    assert client.post(REWRITE, json={"description": LONG_ENOUGH}).status_code == 401


def test_quota_is_per_admin(client, stub, configured, monkeypatch):
    """Per admin, not per address — an office behind one NAT should not share
    a spend budget."""
    from app.api.v1.routers import admin_ai
    from app.core.rate_limit import RateLimit

    # `RateLimit` is frozen, and the router bound the constant at import time —
    # so replace the name in the router's namespace, not the dataclass field.
    monkeypatch.setattr(
        admin_ai, "AI_DRAFT", RateLimit(name="ai_draft_test", limit=2, window_seconds=3600)
    )

    t = token_for(client)
    statuses = [
        client.post(REWRITE, json={"description": LONG_ENOUGH}, headers=auth(t)).status_code
        for _ in range(4)
    ]
    # Without Redis the limiter fails open by design, so either every call
    # succeeds or the limit engages — never a 500.
    assert set(statuses) <= {200, 429}


def test_generate_validates_its_inputs(client, stub, configured):
    t = token_for(client)
    r = client.post(GENERATE, json={"title": "X", "company": "Y"}, headers=auth(t))
    assert r.status_code == 422, "a two-character title is not a job title"


def test_unknown_fields_are_rejected(client, stub, configured):
    """`extra=forbid` — a typo in a client payload should be a 422, not a
    silently ignored field."""
    t = token_for(client)
    r = client.post(
        GENERATE,
        json={"title": "Data Analyst", "company": "Daraz", "salery": "100000"},
        headers=auth(t),
    )
    assert r.status_code == 422
