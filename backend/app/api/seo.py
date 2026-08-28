"""Crawler-facing endpoints: `robots.txt` and `sitemap.xml`.

Served by the API rather than emitted as static files because the interesting
half of the sitemap is the job listings, and those change continuously. A file
written at build time is stale the moment the next listing is published, and a
job board's whole SEO case rests on new listings being indexed quickly.

Mounted outside the versioned prefix: both paths are fixed by convention and a
crawler will never look for `/api/v1/robots.txt`. Under the same-origin reverse
proxy these sit alongside the static frontend at the site root.

## What belongs in the sitemap

Only URLs that are canonical and that have something on them. Two rules follow
from that, and both were learned the hard way:

*Canonical.* The sitemap used to list every facet as a query string —
`/jobs?category=design` and one per location. Meanwhile `usePageMeta` in the
frontend builds each page's canonical link from the pathname alone, so all of
those URLs declared `/jobs` as their canonical. The sitemap was asking Google to
index a few hundred addresses that the pages themselves disowned on arrival.
Facets now have real paths (`landingPages.ts`), and those are what is submitted.

*Non-empty.* The counts come from `published_facet_counts`, not from the
taxonomy's `is_active` flag. Most categories and nearly every location in the
taxonomy currently hold zero live listings, and a sitemap full of empty pages
does not merely waste crawl budget — a site that submits hundreds of thin pages
is assessed on them.
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

#: Below this many live listings a landing page is not worth submitting. One
#: job behind a page titled "Design Jobs" is a page that disappoints whoever
#: arrives on it, and pages like that are how a domain's overall quality
#: assessment goes down rather than up.
MIN_LISTINGS_PER_LANDING = 3

#: Country landing pages. Must stay in step with `COUNTRY_LANDINGS` in
#: `src/lib/landingPages.ts` — that file owns the URL grammar and the copy, this
#: one only decides which of them are populated enough to submit. Keyed by the
#: URL segment, valued by the ISO 3166-1 alpha-2 code the listings carry.
COUNTRY_LANDINGS: tuple[tuple[str, str], ...] = (
    ("pakistan", "PK"),
    ("usa", "US"),
    ("uk", "GB"),
    ("uae", "AE"),
    ("saudi-arabia", "SA"),
    ("canada", "CA"),
)

#: Static routes, with how strongly each should be crawled. `changefreq` and
#: `priority` are hints Google largely ignores now, but Bing and smaller
#: crawlers still read them and they cost nothing.
#:
#: `/saved-jobs` is deliberately absent: it renders from ids in the visitor's
#: own browser storage, so to a crawler it is permanently empty.
STATIC_ROUTES: tuple[tuple[str, str, str], ...] = (
    ("/", "hourly", "1.0"),
    ("/jobs", "hourly", "0.9"),
    ("/remote-jobs", "daily", "0.9"),
    ("/categories", "daily", "0.7"),
    ("/about", "monthly", "0.3"),
    ("/contact", "monthly", "0.3"),
    ("/privacy", "yearly", "0.1"),
    ("/terms", "yearly", "0.1"),
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
            # Filtered views of the jobs list (`/jobs?category=…`) are
            # deliberately *not* disallowed. They all canonicalise to `/jobs`,
            # and it is tempting to block them to save crawl budget — but a
            # crawler that is forbidden to fetch a URL never reads the canonical
            # tag on it either, and a blocked URL discovered through an internal
            # link gets indexed as a bare address with no content behind it.
            # Letting them be crawled is what lets them be consolidated.
            "\n"
            f"Sitemap: {_url('/sitemap.xml')}\n"
        )
    return Response(content=body, media_type="text/plain; charset=utf-8")


@router.get("/sitemap.xml", include_in_schema=False)
async def sitemap(session: DbSession) -> Response:
    """Every public URL worth indexing.

    Static pages, then the landing pages that have enough listings behind them
    to be worth a visit, then the listings themselves. Job detail pages carry
    `lastmod` from `updated_at` so a corrected salary or a re-verified employer
    prompts a recrawl.
    """
    jobs = JobRepository(session)
    categories = CategoryRepository(session)
    locations = LocationRepository(session)
    counts = await jobs.published_facet_counts()

    entries = [
        _entry(path, changefreq=changefreq, priority=priority)
        for path, changefreq, priority in STATIC_ROUTES
    ]

    # Landing pages are where the high-intent queries land — "design jobs in
    # Lahore" converts far better than a bare homepage visit — but only the
    # populated ones are submitted.
    for segment, code in COUNTRY_LANDINGS:
        if counts.countries.get(code, 0) >= MIN_LISTINGS_PER_LANDING:
            entries.append(
                _entry(f"/jobs-in-{segment}", changefreq="daily", priority="0.8")
            )

    for category in await categories.list_active():
        if counts.categories.get(category.slug, 0) >= MIN_LISTINGS_PER_LANDING:
            entries.append(
                _entry(f"/{category.slug}-jobs", changefreq="daily", priority="0.8")
            )

    for location in await locations.list_active():
        if counts.locations.get(location.slug, 0) >= MIN_LISTINGS_PER_LANDING:
            entries.append(
                _entry(f"/jobs-in-{location.slug}", changefreq="daily", priority="0.7")
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
