"""Crawler-facing endpoints: `robots.txt` and `sitemap.xml`.

Served by the API rather than emitted as static files because the interesting
half of the sitemap is the job listings, and those change continuously. A file
written at build time is stale the moment the next listing is published, and a
job board's whole SEO case rests on new listings being indexed quickly.

Mounted outside the versioned prefix: both paths are fixed by convention and a
crawler will never look for `/api/v1/robots.txt`. Under the same-origin reverse
proxy these sit alongside the static frontend at the site root.
"""

from __future__ import annotations

from datetime import UTC, datetime
from xml.sax.saxutils import escape

from fastapi import APIRouter, Response

from app.api.v1.deps import DbSession
from app.core.config import settings
from app.repositories.job_repo import JobRepository
from app.repositories.taxonomy_repo import CategoryRepository, LocationRepository

router = APIRouter(tags=["seo"])

#: A sitemap may hold 50,000 URLs before it must be split into an index. The
#: cap here is lower so one response stays comfortably small; crossing it is
#: the signal to add a sitemap index, not to raise the number.
MAX_SITEMAP_URLS = 20_000

#: Static routes, with how strongly each should be crawled. `changefreq` and
#: `priority` are hints Google largely ignores now, but Bing and smaller
#: crawlers still read them and they cost nothing.
STATIC_ROUTES: tuple[tuple[str, str, str], ...] = (
    ("/", "hourly", "1.0"),
    ("/jobs", "hourly", "0.9"),
    ("/categories", "daily", "0.7"),
    ("/about", "monthly", "0.3"),
    ("/contact", "monthly", "0.3"),
)


def _url(path: str) -> str:
    return f"{settings.site_url.rstrip('/')}{path}"


def _entry(path: str, *, lastmod: datetime | None = None, changefreq: str, priority: str) -> str:
    parts = [f"    <loc>{escape(_url(path))}</loc>"]
    if lastmod is not None:
        stamp = lastmod if lastmod.tzinfo else lastmod.replace(tzinfo=UTC)
        parts.append(f"    <lastmod>{stamp.date().isoformat()}</lastmod>")
    parts.append(f"    <changefreq>{changefreq}</changefreq>")
    parts.append(f"    <priority>{priority}</priority>")
    body = "\n".join(parts)
    return f"  <url>\n{body}\n  </url>"


@router.get("/robots.txt", include_in_schema=False)
async def robots() -> Response:
    """Allow crawling everywhere except the admin console and the API.

    Staging and local advertise `Disallow: /` instead. A staging environment
    that gets indexed competes with production for its own keywords, and the
    duplicate content is attributed to whichever Google crawled first.
    """
    if settings.environment in ("local", "staging", "test"):
        body = "User-agent: *\nDisallow: /\n"
    else:
        body = (
            "User-agent: *\n"
            "Allow: /\n"
            # No value in crawling either, and the admin console would produce
            # a wall of soft 404s as every route redirects to the login page.
            "Disallow: /admin/\n"
            "Disallow: /api/\n"
            "\n"
            f"Sitemap: {_url('/sitemap.xml')}\n"
        )
    return Response(content=body, media_type="text/plain; charset=utf-8")


@router.get("/sitemap.xml", include_in_schema=False)
async def sitemap(session: DbSession) -> Response:
    """Every public URL worth indexing.

    Listing pages, category and location landing pages, then the listings
    themselves. Job detail pages carry `lastmod` from `updated_at` so a
    corrected salary or a re-verified employer prompts a recrawl.
    """
    jobs = JobRepository(session)
    categories = CategoryRepository(session)
    locations = LocationRepository(session)

    entries = [
        _entry(path, changefreq=changefreq, priority=priority)
        for path, changefreq, priority in STATIC_ROUTES
    ]

    # Category and location pages are the landing surfaces for the highest
    # intent queries a job board gets — "design jobs in Lahore" converts far
    # better than a bare homepage visit.
    for category in await categories.list_active():
        entries.append(
            _entry(f"/jobs?category={category.slug}", changefreq="daily", priority="0.8")
        )
    for location in await locations.list_active():
        entries.append(
            _entry(f"/jobs?location={location.slug}", changefreq="daily", priority="0.8")
        )

    remaining = MAX_SITEMAP_URLS - len(entries)
    for slug, updated_at in await jobs.published_slugs(limit=max(remaining, 0)):
        entries.append(
            _entry(f"/jobs/{slug}", lastmod=updated_at, changefreq="weekly", priority="0.6")
        )

    document = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        + "\n".join(entries)
        + "\n</urlset>\n"
    )
    return Response(content=document, media_type="application/xml; charset=utf-8")
