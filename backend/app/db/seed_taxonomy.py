"""Real reference data for categories and locations.

Kept out of a migration on purpose. Migrations describe the *shape* of the
database; this is editable content an operator curates through the admin UI
afterwards. Baking it into `alembic upgrade` would make a later rename look
like schema drift.

Idempotent by slug: running it twice adds nothing and overwrites nothing an
admin has since edited.

    python -m app.cli seed-taxonomy
    python -m app.cli seed-taxonomy --purge-test-data
"""

from __future__ import annotations

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.taxonomy import Category, Location

#: (name, slug, icon). The domains a Pakistani job board actually lists.
#:
#: These describe *what the work is*, not how senior it is. Seniority is a
#: separate field on every listing (`experience_level`: intern → executive),
#: which is why there is no "Fresher" category here — a fresh-graduate role in
#: design and one in finance belong to different categories and the same level.
CATEGORIES: tuple[tuple[str, str, str], ...] = (
    ("IT & Technology", "it-technology", "💻"),
    ("Engineering", "engineering", "⚙️"),
    ("Data & Analytics", "data-analytics", "📈"),
    ("Design & Creative", "design-creative", "🎨"),
    ("Sales & Business Development", "sales-business-development", "🤝"),
    ("Marketing & PR", "marketing-pr", "📣"),
    ("Finance & Accounting", "finance-accounting", "📊"),
    ("Human Resources", "human-resources", "👥"),
    ("Customer Support", "customer-support", "🎧"),
    ("Operations & Supply Chain", "operations-supply-chain", "📦"),
    ("Healthcare & Medical", "healthcare-medical", "🩺"),
    ("Education & Training", "education-training", "🎓"),
    ("Government & Public Sector", "government-public-sector", "🏛️"),
    ("Legal", "legal", "⚖️"),
    ("Media & Content", "media-content", "✍️"),
    ("Hospitality & Travel", "hospitality-travel", "✈️"),
    ("Construction & Real Estate", "construction-real-estate", "🏗️"),
    ("Manufacturing", "manufacturing", "🏭"),
    ("Logistics & Transport", "logistics-transport", "🚚"),
    ("Internships & Trainee Programs", "internships-trainee", "🌱"),
)

#: (city, region, slug). Every district-level city with a real labour market,
#: so an editor is not forced to pick the nearest big city and be wrong.
CITIES: tuple[tuple[str, str, str], ...] = (
    ("Karachi", "Sindh", "karachi"),
    ("Lahore", "Punjab", "lahore"),
    ("Islamabad", "Federal", "islamabad"),
    ("Rawalpindi", "Punjab", "rawalpindi"),
    ("Faisalabad", "Punjab", "faisalabad"),
    ("Multan", "Punjab", "multan"),
    ("Gujranwala", "Punjab", "gujranwala"),
    ("Sialkot", "Punjab", "sialkot"),
    ("Gujrat", "Punjab", "gujrat"),
    ("Sargodha", "Punjab", "sargodha"),
    ("Bahawalpur", "Punjab", "bahawalpur"),
    ("Sahiwal", "Punjab", "sahiwal"),
    ("Rahim Yar Khan", "Punjab", "rahim-yar-khan"),
    ("Jhelum", "Punjab", "jhelum"),
    ("Okara", "Punjab", "okara"),
    ("Hyderabad", "Sindh", "hyderabad"),
    ("Sukkur", "Sindh", "sukkur"),
    ("Larkana", "Sindh", "larkana"),
    ("Nawabshah", "Sindh", "nawabshah"),
    ("Mirpurkhas", "Sindh", "mirpurkhas"),
    ("Peshawar", "Khyber Pakhtunkhwa", "peshawar"),
    ("Mardan", "Khyber Pakhtunkhwa", "mardan"),
    ("Abbottabad", "Khyber Pakhtunkhwa", "abbottabad"),
    ("Swat", "Khyber Pakhtunkhwa", "swat"),
    ("Kohat", "Khyber Pakhtunkhwa", "kohat"),
    ("Dera Ismail Khan", "Khyber Pakhtunkhwa", "dera-ismail-khan"),
    ("Quetta", "Balochistan", "quetta"),
    ("Gwadar", "Balochistan", "gwadar"),
    ("Turbat", "Balochistan", "turbat"),
    ("Muzaffarabad", "Azad Kashmir", "muzaffarabad"),
    ("Mirpur", "Azad Kashmir", "mirpur-ajk"),
    ("Gilgit", "Gilgit-Baltistan", "gilgit"),
    ("Skardu", "Gilgit-Baltistan", "skardu"),
)

#: Remote options, which have no city by design.
REMOTE: tuple[tuple[str, str, str], ...] = (
    ("Remote – Pakistan", "remote-pakistan", "PK"),
    ("Remote – Worldwide", "remote-worldwide", "PK"),
    ("Hybrid – Karachi", "hybrid-karachi", "PK"),
    ("Hybrid – Lahore", "hybrid-lahore", "PK"),
    ("Hybrid – Islamabad", "hybrid-islamabad", "PK"),
)


async def seed_categories(session: AsyncSession) -> int:
    existing = set((await session.execute(select(Category.slug))).scalars().all())
    added = 0
    for order, (name, slug, icon) in enumerate(CATEGORIES):
        if slug in existing:
            continue
        session.add(Category(name=name, slug=slug, icon=icon, sort_order=order, job_count=0))
        added += 1
    await session.flush()
    return added


async def seed_locations(session: AsyncSession) -> int:
    existing = set((await session.execute(select(Location.slug))).scalars().all())
    added = 0

    for city, region, slug in CITIES:
        if slug in existing:
            continue
        session.add(
            Location(
                city=city,
                region=region,
                country="PK",
                slug=slug,
                display_name=f"{city}, Pakistan",
                is_remote=False,
                job_count=0,
            )
        )
        added += 1

    for display, slug, country in REMOTE:
        if slug in existing:
            continue
        session.add(
            Location(
                city=None,
                region=None,
                country=country,
                slug=slug,
                display_name=display,
                is_remote=True,
                job_count=0,
            )
        )
        added += 1

    await session.flush()
    return added


async def purge_test_data(session: AsyncSession) -> dict[str, int]:
    """Remove the taxonomy the test suites left behind.

    Test fixtures create `M3 Tech`, `m5-karachi` and friends against the same
    database a developer browses. They are harmless to the suite and confusing
    to everyone else.

    Rows still referenced by a listing are left alone — a foreign key is a
    better judge of what is in use than a naming convention.
    """
    removed = {}
    for table, pattern in (("categories", "m_-%"), ("locations", "m_-%")):
        column = "category_id" if table == "categories" else "location_id"
        result = await session.execute(
            text(
                f"""
                DELETE FROM {table}
                 WHERE slug LIKE :pattern
                   AND NOT EXISTS (SELECT 1 FROM jobs WHERE jobs.{column} = {table}.id)
                """
            ),
            {"pattern": pattern},
        )
        removed[table] = result.rowcount or 0
    return removed


async def recount(session: AsyncSession) -> None:
    """Rebuild `job_count` from the listings themselves.

    The counters are maintained incrementally, which drifts when rows are
    removed outside the service layer — the benchmark's hundred thousand
    synthetic listings left counts of 368 and 91 behind after a bulk delete.
    """
    for table, column in (("categories", "category_id"), ("locations", "location_id")):
        await session.execute(
            text(
                f"""
                UPDATE {table} t
                   SET job_count = (
                       SELECT count(*) FROM jobs j
                        WHERE j.{column} = t.id
                          AND j.status = 'published'
                          AND j.deleted_at IS NULL
                   )
                """
            )
        )


__all__ = ["purge_test_data", "recount", "seed_categories", "seed_locations"]
