"""Social share asset tests.

The rendering tests deliberately assert on shape and behaviour rather than on
pixels: a byte-comparison against a golden PNG would fail on a Pillow point
release and teach everyone to regenerate the golden without looking. What has
to hold is that a card is produced for every realistic input, that regeneration
is decided correctly, and that a draft never leaks one.
"""

from __future__ import annotations

import asyncio
import io
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import delete, select

from app.core.config import settings
from app.core.enums import SocialVariant
from app.core.permissions import SystemRole
from app.core.security import hash_password
from app.db.database import SessionFactory
from app.main import app
from app.models.admin import Admin, AdminSession
from app.models.audit import AuditLog
from app.models.job import Job
from app.models.rbac import Role
from app.models.social import JobSocialAsset
from app.models.taxonomy import Category, Location, Source
from app.services.caption_service import CaptionInput, build_captions, share_urls
from app.services.social_card_service import SPECS, JobCardData, render_card

ADMIN_EMAIL = "social-admin@plenilo.com"
PASSWORD = "social-asset-password"
LOGIN = "/api/v1/auth/login"
ADMIN_JOBS = "/api/v1/admin/jobs"


async def _seed() -> dict:
    async with SessionFactory() as s:
        existing = (
            await s.execute(select(Admin).where(Admin.email == ADMIN_EMAIL))
        ).scalar_one_or_none()
        if existing:
            await s.execute(delete(AdminSession).where(AdminSession.admin_id == existing.id))
            await s.execute(delete(AuditLog).where(AuditLog.admin_id == existing.id))
            await s.execute(delete(Job).where(Job.created_by == existing.id))
            await s.delete(existing)
        await s.commit()

        role = (
            await s.execute(select(Role).where(Role.key == SystemRole.ADMIN.value))
        ).scalar_one()
        admin = Admin(
            email=ADMIN_EMAIL,
            full_name="Social Admin",
            password_hash=hash_password(PASSWORD),
            role_id=role.id,
            is_active=True,
        )
        s.add(admin)

        category = (
            await s.execute(select(Category).where(Category.slug == "social-tech"))
        ).scalar_one_or_none() or Category(name="Social Tech", slug="social-tech", job_count=0)
        location = (
            await s.execute(select(Location).where(Location.slug == "social-lahore"))
        ).scalar_one_or_none() or Location(
            city="Lahore",
            country="PK",
            slug="social-lahore",
            display_name="Lahore, Pakistan",
            job_count=0,
        )
        s.add_all([category, location])
        source = (await s.execute(select(Source).where(Source.slug == "manual"))).scalar_one()
        await s.flush()

        def job(slug: str, title: str, status: str, **extra) -> Job:
            return Job(
                slug=slug,
                title=title,
                company_name="Systems Limited",
                category_id=category.id,
                location_id=location.id,
                source_id=source.id,
                work_type="hybrid",
                employment_type="full_time",
                experience_level="senior",
                experience_min_years=3,
                experience_max_years=5,
                salary_min=250000,
                salary_max=350000,
                salary_is_disclosed=True,
                description=(
                    "A listing used by the social share asset tests. It needs at least "
                    "fifty characters to satisfy the description length constraint."
                ),
                requirements=["React", "TypeScript", "Next.js"],
                apply_url="https://example.com/apply",
                status=status,
                published_at=datetime.now(UTC) if status == "published" else None,
                created_by=admin.id,
                **extra,
            )

        published = job("social-published", "Senior Frontend Engineer", "published")
        draft = job("social-draft", "Unreleased Role", "draft")
        s.add_all([published, draft])
        await s.commit()
        return {"published": str(published.id), "draft": str(draft.id), "admin_id": str(admin.id)}


@pytest.fixture
def world():
    return asyncio.run(_seed())


@pytest.fixture
def client(world):
    with TestClient(app) as c:
        yield c


def token_for(client: TestClient, email: str = ADMIN_EMAIL) -> str:
    r = client.post(LOGIN, json={"email": email, "password": PASSWORD})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


def auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def sample(**overrides) -> JobCardData:
    base = {
        "title": "Senior Frontend Engineer",
        "company": "Systems Limited",
        "location": "Lahore, Pakistan",
        "employment_type": "Full Time",
        "slug": "senior-frontend-engineer",
        "salary": "PKR 250,000 – 350,000/mo",
        "experience": "3–5 years",
        "skills": ["React", "TypeScript", "Next.js"],
    }
    return JobCardData(**{**base, **overrides})


# --- rendering ------------------------------------------------------------


@pytest.mark.parametrize("variant", list(SocialVariant))
def test_card_renders_at_the_declared_size(variant):
    png = render_card(sample(), variant)
    image = Image.open(io.BytesIO(png))
    spec = SPECS[variant]
    assert image.format == "PNG"
    assert image.size == (spec.width, spec.height)


@pytest.mark.parametrize(
    "case",
    [
        sample(),
        sample(salary=None),  # undisclosed
        sample(skills=[]),  # no requirements entered
        sample(experience=None, salary=None),  # the sparsest possible listing
        sample(title="A" * 120),  # unbroken run, no wrap points
        sample(title="Senior Full Stack Software Development Engineer (React / Node.js) — Remote"),
        sample(company="پاکستان ٹیلی کمیونیکیشن"),  # Urdu, right-to-left
        sample(skills=["Kubernetes", "Terraform", "PostgreSQL", "AWS", "Docker", "Go", "Rust"]),
    ],
    ids=[
        "full",
        "no-salary",
        "no-skills",
        "sparse",
        "unbroken-title",
        "long-title",
        "urdu",
        "many-skills",
    ],
)
def test_every_realistic_input_produces_a_card(case):
    """No input should be able to throw. A listing that cannot be shared is a
    silent gap; a listing that raises takes the endpoint down with it."""
    png = render_card(case, SocialVariant.SQUARE)
    assert len(png) > 5_000, "suspiciously small — likely a blank canvas"
    assert Image.open(io.BytesIO(png)).size == (1080, 1080)


def test_content_hash_covers_only_the_rendered_fields():
    """The hash decides regeneration. If it moves when the image would not
    change, every view-count bump rewrites a file for nothing."""
    assert sample().content_hash() == sample().content_hash()
    assert sample().content_hash() != sample(title="Different Title").content_hash()
    assert sample().content_hash() != sample(salary=None).content_hash()
    assert sample().content_hash() != sample(skills=["React"]).content_hash()


def test_missing_font_fails_loudly(monkeypatch):
    """A silent fallback to a bitmap face renders cards that look like a bug
    report, and nobody notices until a customer shares one."""
    from app.services import social_card_service as svc

    svc._font.cache_clear()
    monkeypatch.setattr(svc, "FONT_DIR", svc.FONT_DIR / "does-not-exist")
    with pytest.raises(FileNotFoundError):
        render_card(sample(), SocialVariant.SQUARE)
    svc._font.cache_clear()


# --- captions -------------------------------------------------------------


def caption_input(**overrides) -> CaptionInput:
    base = {
        "title": "Senior Frontend Engineer",
        "company": "Systems Limited",
        "location": "Lahore",
        "employment_type": "Full Time",
        "slug": "senior-frontend-engineer",
        "salary": "PKR 250,000",
        "experience": "3-5 Years",
        "skills": ("React", "TypeScript", "Next.js"),
    }
    return CaptionInput(**{**base, **overrides})


def test_linkedin_caption_has_the_expected_structure():
    caption = build_captions(caption_input()).linkedin
    assert caption.startswith("🚀 Hiring: Senior Frontend Engineer")
    assert "🏢 Company: Systems Limited" in caption
    assert "📍 Location: Lahore" in caption
    assert "💰 Salary: PKR 250,000" in caption
    assert "Required Skills:\n• React" in caption
    assert "/jobs/senior-frontend-engineer" in caption
    assert "#Hiring #Jobs #PakistanJobs" in caption


def test_undisclosed_salary_is_omitted_not_zeroed():
    caption = build_captions(caption_input(salary=None)).linkedin
    assert "Salary" not in caption


def test_whatsapp_message_carries_no_hashtags():
    """They are inert on WhatsApp and read as spam."""
    message = build_captions(caption_input()).whatsapp
    assert "#" not in message
    assert "*Senior Frontend Engineer*" in message
    assert "/jobs/senior-frontend-engineer" in message


def _tweet_cost(tweet: str, data: CaptionInput) -> int:
    """What X charges for the post: every link wrapped to a fixed width."""
    from app.services.caption_service import TWEET_URL_COST

    links = [data.job_url] + [
        url for url in (settings.whatsapp_channel_url,) if url and url in tweet
    ]
    return len(tweet) - sum(map(len, links)) + TWEET_URL_COST * len(links)


def test_tweet_fits_the_character_budget():
    """A URL costs 23 characters however long it is, so the budget is computed
    against that rather than against the literal string."""
    from app.services.caption_service import TWEET_LIMIT

    for title in (
        "Data Analyst",
        "Senior Full Stack Software Development Engineer — Remote",
        "X" * 150,
    ):
        data = caption_input(title=title)
        tweet = build_captions(data).twitter
        cost = _tweet_cost(tweet, data)
        assert cost <= TWEET_LIMIT, f"{title!r} produced {cost} characters"
        assert data.job_url in tweet, "the link is never sacrificed"


def test_every_caption_carries_the_whatsapp_channel():
    """A post is read once; a channel follower is read every time."""
    channel = settings.whatsapp_channel_url
    assert channel, "the default configuration ships a channel"

    captions = build_captions(caption_input())
    for platform in ("linkedin", "whatsapp", "facebook", "twitter"):
        assert channel in getattr(captions, platform), f"{platform} dropped the channel"


def test_the_channel_line_disappears_when_unconfigured(monkeypatch):
    """Deployments without a channel must not post an empty prompt."""
    monkeypatch.setattr(settings, "whatsapp_channel_url", "")
    captions = build_captions(caption_input())
    for platform in ("linkedin", "whatsapp", "facebook", "twitter"):
        text = getattr(captions, platform)
        assert "channel" not in text.lower(), f"{platform} kept a dangling prompt"
        assert "\n\n\n" not in text, f"{platform} left a blank paragraph behind"


def test_the_channel_is_sacrificed_before_the_tweet_overflows():
    """The budget wins: a listing that cannot fit both posts the job link."""
    from app.services.caption_service import TWEET_LIMIT

    data = caption_input(title="Senior " + "Very Long Title Fragment " * 8)
    tweet = build_captions(data).twitter
    assert _tweet_cost(tweet, data) <= TWEET_LIMIT
    assert data.job_url in tweet
    assert settings.whatsapp_channel_url not in tweet


def test_hashtags_are_derived_from_role_and_skills():
    tags = build_captions(caption_input()).hashtags
    assert tags[:3] == ("Hiring", "Jobs", "PakistanJobs"), "broad tags come first"
    assert "FrontendDeveloper" in tags, "role is derived from the title"
    assert "ReactJobs" in tags

    # Punctuated skills map to the tag people actually follow: a naive
    # `#{skill}` would produce `#Nextjs` and `#C` for `Next.js` and `C++`.
    fewer = build_captions(caption_input(skills=("Next.js",))).hashtags
    assert "NextJS" in fewer


def test_hashtag_count_is_capped():
    """Twenty tags reads as spam on every platform that supports them."""
    tags = build_captions(
        caption_input(skills=("React", "TypeScript", "Next.js", "Node", "AWS", "Docker", "SQL"))
    ).hashtags
    assert len(tags) <= 6


def test_share_urls_encode_correctly():
    captions = build_captions(caption_input())
    urls = share_urls("https://plenilo.com/jobs/x", captions)
    assert urls["linkedin"].startswith("https://www.linkedin.com/sharing/share-offsite/?url=")
    assert "%3A%2F%2F" in urls["linkedin"], "the URL must be percent-encoded"
    assert urls["whatsapp"].startswith("https://wa.me/?text=")
    # LinkedIn dropped prefilled text; sending one would be silently ignored.
    assert "text=" not in urls["linkedin"]


# --- endpoints ------------------------------------------------------------


def test_share_assets_endpoint_returns_the_full_payload(client, world):
    t = token_for(client)
    r = client.get(f"{ADMIN_JOBS}/{world['published']}/share-assets", headers=auth(t))
    assert r.status_code == 200, r.text
    body = r.json()

    for key in ("linkedin_caption", "whatsapp_message", "facebook_caption", "twitter_caption"):
        assert body[key], f"{key} is empty"
    assert body["image_url"].endswith("/social/square.png")
    assert set(body["image_urls"]) == {"square", "landscape"}
    assert set(body["share_urls"]) == {"linkedin", "facebook", "twitter", "whatsapp"}
    assert body["job_url"].endswith("/jobs/social-published")


def test_share_assets_requires_permission(client, world):
    assert client.get(f"{ADMIN_JOBS}/{world['published']}/share-assets").status_code == 401


def test_card_endpoint_serves_a_png(client, world):
    r = client.get("/api/v1/jobs/social-published/social/square.png")
    assert r.status_code == 200
    assert r.headers["content-type"] == "image/png"
    assert "max-age" in r.headers["cache-control"]
    assert Image.open(io.BytesIO(r.content)).size == (1080, 1080)


def test_card_is_generated_once_then_reused(client, world):
    """The second request must not re-render. `generated_at` moving would mean
    every crawler fetch pays 200ms of Pillow."""
    first = client.get("/api/v1/jobs/social-published/social/square.png")
    assert first.status_code == 200

    async def stamp() -> tuple[int, object]:
        async with SessionFactory() as s:
            rows = (
                (
                    await s.execute(
                        select(JobSocialAsset).where(JobSocialAsset.job_id == world["published"])
                    )
                )
                .scalars()
                .all()
            )
            return len(rows), rows[0].generated_at if rows else None

    count, generated_at = asyncio.run(stamp())
    assert count == 1

    second = client.get("/api/v1/jobs/social-published/social/square.png")
    assert second.status_code == 200
    assert second.content == first.content

    count_again, generated_again = asyncio.run(stamp())
    assert count_again == 1
    assert generated_again == generated_at, "the card was re-rendered on a cache hit"


def test_editing_the_job_regenerates_the_card(client, world):
    """A retitled listing must not keep advertising its old title."""
    client.get("/api/v1/jobs/social-published/social/square.png")

    async def hash_now() -> str:
        async with SessionFactory() as s:
            row = (
                (
                    await s.execute(
                        select(JobSocialAsset).where(JobSocialAsset.job_id == world["published"])
                    )
                )
                .scalars()
                .one()
            )
            return row.content_hash

    before = asyncio.run(hash_now())

    t = token_for(client)
    r = client.patch(
        f"{ADMIN_JOBS}/{world['published']}",
        json={"title": "Principal Frontend Engineer"},
        headers=auth(t),
    )
    assert r.status_code == 200, r.text

    client.get("/api/v1/jobs/social-published/social/square.png")
    assert asyncio.run(hash_now()) != before


def test_draft_listings_have_no_public_card(client, world):
    """A draft's card would be a readable preview of unreleased editorial work,
    retrievable by anyone who guesses the slug."""
    assert client.get("/api/v1/jobs/social-draft/social/square.png").status_code == 404


def test_unknown_slug_is_a_404(client):
    assert client.get("/api/v1/jobs/no-such-listing/social/square.png").status_code == 404


def test_landscape_variant_is_addressable(client, world):
    """Phase 7 points `og:image` at this without the endpoint changing."""
    r = client.get("/api/v1/jobs/social-published/social/landscape.png")
    assert r.status_code == 200
    assert Image.open(io.BytesIO(r.content)).size == (1200, 627)
