"""Search benchmark at scale.

Generates synthetic listings, then times representative queries against the
real index. The point is not a vanity number: it is to confirm the GIN index is
actually used and that latency does not grow with catalogue size, which is the
assumption behind choosing PostgreSQL over Elasticsearch.

    python -m tools.bench_search --rows 100000

Synthetic rows are tagged with a company prefix so they can be removed again:

    python -m tools.bench_search --cleanup
"""

from __future__ import annotations

import argparse
import asyncio
import statistics
import time

from sqlalchemy import text

from app.db.database import SessionFactory, dispose_engine

BENCH_MARKER = "BENCHCO"

# Term selectivity is the whole ballgame for full-text performance, so the
# generator composes titles and skill sets rather than cycling a short list.
# An earlier version reused twelve titles across 100k rows, which made "react"
# match 16% of the catalogue — a benchmark of a situation that does not occur.
SENIORITY = ["Junior", "Associate", "Mid-level", "Senior", "Staff", "Principal", "Lead", "Head of"]
DISCIPLINE = [
    "Frontend",
    "Backend",
    "Fullstack",
    "Mobile",
    "Platform",
    "Data",
    "Machine Learning",
    "Security",
    "Cloud",
    "Embedded",
    "Site Reliability",
    "Quality",
    "Solutions",
    "Product",
    "Growth",
    "Content",
    "Brand",
    "Field",
    "Technical",
    "Business",
]
ROLE = [
    "Engineer",
    "Developer",
    "Analyst",
    "Designer",
    "Manager",
    "Architect",
    "Specialist",
    "Consultant",
    "Partner",
    "Lead",
    "Officer",
    "Administrator",
]
SKILL_POOL = [
    "React",
    "Vue",
    "Angular",
    "Svelte",
    "TypeScript",
    "JavaScript",
    "Python",
    "Django",
    "FastAPI",
    "Flask",
    "Java",
    "Spring",
    "Kotlin",
    "Swift",
    "Go",
    "Rust",
    "Ruby",
    "PostgreSQL",
    "MySQL",
    "MongoDB",
    "Redis",
    "Elasticsearch",
    "Kafka",
    "RabbitMQ",
    "Kubernetes",
    "Docker",
    "Terraform",
    "Ansible",
    "AWS",
    "GCP",
    "Azure",
    "Figma",
    "Sketch",
    "Illustrator",
    "SQL",
    "Power BI",
    "Tableau",
    "Excel",
    "SPSS",
    "SEO",
    "SEM",
    "HubSpot",
    "Salesforce",
    "Jira",
    "Confluence",
    "GraphQL",
    "gRPC",
]
CITIES = [
    "Lahore",
    "Karachi",
    "Islamabad",
    "Rawalpindi",
    "Faisalabad",
    "Multan",
    "Peshawar",
    "Quetta",
    "Sialkot",
    "Hyderabad",
]

QUERIES = [
    ("react", "skills, weight C"),
    ("python", "skills, weight C"),
    ("karachi", "location, weight B"),
    ("remote", "location, weight B"),
    ("frontend engineer", "title, weight A, multi-term"),
    ("senior backend engineer", "title, three terms"),
    ("kubernetes terraform", "two skills, weight C"),
    ("techation", "unstemmable typo -> trigram tier"),
]


async def seed(rows: int) -> None:
    async with SessionFactory() as s:
        ref = (
            await s.execute(
                text(
                    """
                    SELECT (SELECT id FROM categories ORDER BY created_at LIMIT 1),
                           (SELECT id FROM locations  ORDER BY created_at LIMIT 1),
                           (SELECT id FROM sources WHERE slug = 'manual'),
                           (SELECT id FROM admins ORDER BY created_at LIMIT 1)
                    """
                )
            )
        ).one()
        category_id, location_id, source_id, admin_id = ref
        if not all((category_id, location_id, source_id, admin_id)):
            raise SystemExit("seed the database first: alembic upgrade head + bootstrap-admin")

        existing = (
            await s.execute(
                text("SELECT count(*) FROM jobs WHERE company_name LIKE :p"),
                {"p": f"{BENCH_MARKER}%"},
            )
        ).scalar_one()
        if existing >= rows:
            print(f"  {existing:,} synthetic rows already present")
            return

        to_insert = rows - existing
        print(f"  inserting {to_insert:,} rows…")
        started = time.perf_counter()

        # One statement rather than a loop: the trigger and the generated
        # column run per row either way, but the round trips do not.
        await s.execute(
            text(
                """
                INSERT INTO jobs (
                    slug, title, company_name, category_id, location_id, source_id,
                    work_type, employment_type, experience_level,
                    description, requirements, apply_url,
                    status, published_at, created_by,
                    salary_min, salary_max, verified, verified_at, verified_by, featured
                )
                SELECT
                    'bench-' || g || '-' || md5(random()::text),
                    (CAST(:seniority AS text[]))[1 + (g % :n_sen)] || ' ' ||
                        (CAST(:discipline AS text[]))[1 + ((g / 7) % :n_dis)] || ' ' ||
                        (CAST(:role AS text[]))[1 + ((g / 13) % :n_role)],
                    :marker || '-' || (g % 4000),
                    :category_id, :location_id, :source_id,
                    (ARRAY['remote','on_site','hybrid']::work_type[])[1 + (g % 3)],
                    (ARRAY['full_time','part_time','contract','internship']::employment_type[])[1 + (g % 4)],
                    (ARRAY['intern','entry','mid','senior','lead']::experience_level[])[1 + (g % 5)],
                    'Role based in ' || (CAST(:cities AS text[]))[1 + ((g / 3) % :n_cities)] ||
                        '. Synthetic benchmark listing number ' || g ||
                        '. Build and maintain production systems for a growing team. ' ||
                        repeat('Additional descriptive filler text. ', 5),
                    jsonb_build_array(
                        (CAST(:skills AS text[]))[1 + (g % :n_skills)],
                        (CAST(:skills AS text[]))[1 + ((g / 11) % :n_skills)],
                        (CAST(:skills AS text[]))[1 + ((g / 29) % :n_skills)]
                    ),
                    'https://example.com/apply/' || g,
                    'published',
                    now() - (g % 120) * interval '1 day',
                    :admin_id,
                    50000 + (g % 40) * 5000,
                    90000 + (g % 40) * 5000,
                    (g % 4 = 0),
                    -- ck_jobs_verified_requires_verifier: the flag and its
                    -- attribution must move together.
                    CASE WHEN g % 4 = 0 THEN now() END,
                    CASE WHEN g % 4 = 0 THEN CAST(:admin_id AS uuid) END,
                    (g % 50 = 0)
                FROM generate_series(1, :count) AS g
                """
            ),
            {
                "seniority": SENIORITY,
                "n_sen": len(SENIORITY),
                "discipline": DISCIPLINE,
                "n_dis": len(DISCIPLINE),
                "role": ROLE,
                "n_role": len(ROLE),
                "skills": SKILL_POOL,
                "n_skills": len(SKILL_POOL),
                "cities": CITIES,
                "n_cities": len(CITIES),
                "marker": BENCH_MARKER,
                "category_id": category_id,
                "location_id": location_id,
                "source_id": source_id,
                "admin_id": admin_id,
                "count": to_insert,
            },
        )
        await s.commit()
        print(f"  inserted in {time.perf_counter() - started:.1f}s")

        print("  ANALYZE…")
        await s.execute(text("ANALYZE jobs"))
        await s.commit()


async def measure(runs: int) -> None:
    from app.repositories.job_repo import JobFilters
    from app.services.search_service import SearchService

    async with SessionFactory() as s:
        total = (
            await s.execute(text("SELECT count(*) FROM jobs WHERE deleted_at IS NULL"))
        ).scalar_one()
        published = (
            await s.execute(
                text("SELECT count(*) FROM jobs WHERE status='published' AND deleted_at IS NULL")
            )
        ).scalar_one()
        size = (
            await s.execute(text("SELECT pg_size_pretty(pg_total_relation_size('jobs'))"))
        ).scalar_one()
        index_size = (
            await s.execute(
                text("SELECT pg_size_pretty(pg_relation_size('ix_jobs_search_vector'))")
            )
        ).scalar_one()

    print(f"\n  catalogue: {total:,} jobs ({published:,} published)")
    print(f"  table {size} · GIN index {index_size}\n")
    print(f"  {'query':<26} {'band':<34} {'p50':>7} {'p95':>7} {'strategy':>10}")
    print(f"  {'-' * 26} {'-' * 34} {'-' * 7} {'-' * 7} {'-' * 10}")

    worst = 0.0
    for query, band in QUERIES:
        timings: list[float] = []
        strategy = ""
        # One session for the whole set: acquiring a connection per iteration
        # measured the pool, not the query.
        async with SessionFactory() as s:
            service = SearchService(s)
            await service.search(query, JobFilters(), page=1, per_page=20, log=False)  # warm
            for _ in range(runs):
                started = time.perf_counter()
                outcome = await service.search(query, JobFilters(), page=1, per_page=20, log=False)
                timings.append((time.perf_counter() - started) * 1000)
                strategy = outcome.strategy.value
        p50 = statistics.median(timings)
        p95 = sorted(timings)[int(len(timings) * 0.95) - 1]
        worst = max(worst, p95)
        print(f"  {query:<26} {band:<34} {p50:>6.1f}ms {p95:>6.1f}ms {strategy:>10}")

    target = 100.0
    verdict = "PASS" if worst < target else "FAIL"
    print(f"\n  worst p95: {worst:.1f}ms · target <{target:.0f}ms · {verdict}")


async def explain() -> None:
    """Confirm the planner actually chooses the GIN index.

    A benchmark that passes on a sequential scan is measuring the wrong thing.
    """
    async with SessionFactory() as s:
        rows = await s.execute(
            text(
                """
                EXPLAIN (ANALYZE, BUFFERS)
                SELECT id FROM jobs
                 WHERE deleted_at IS NULL AND status = 'published'
                   AND search_vector @@ websearch_to_tsquery('english', 'react')
                 ORDER BY ts_rank_cd(search_vector,
                          websearch_to_tsquery('english','react'), 32) DESC
                 LIMIT 20
                """
            )
        )
        plan = "\n".join(f"    {r[0]}" for r in rows.all())
    print("\n  query plan for 'react':\n")
    print(plan)
    print(f"\n  uses GIN index: {'ix_jobs_search_vector' in plan}")


async def cleanup() -> None:
    async with SessionFactory() as s:
        deleted = (
            await s.execute(
                text("DELETE FROM jobs WHERE company_name LIKE :p RETURNING id"),
                {"p": f"{BENCH_MARKER}%"},
            )
        ).rowcount
        await s.commit()
        print(f"  removed {deleted:,} synthetic rows")


async def main(args: argparse.Namespace) -> None:
    """Seed, measure, then always remove the synthetic rows.

    The benchmark shares a database with the test suite, and 100k synthetic
    listings drown out the handful of fixtures the tests assert on. Leaving
    them behind turns every subsequent test run into a puzzle, so cleanup is in
    a `finally` rather than left to the operator remembering.
    """
    try:
        if args.cleanup:
            await cleanup()
            return
        await seed(args.rows)
        await measure(args.runs)
        await explain()
    finally:
        if not args.cleanup and not args.keep:
            print()
            await cleanup()
        await dispose_engine()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Search benchmark")
    parser.add_argument("--rows", type=int, default=100_000)
    parser.add_argument("--runs", type=int, default=20)
    parser.add_argument("--cleanup", action="store_true", help="only remove synthetic rows")
    parser.add_argument(
        "--keep",
        action="store_true",
        help="leave the synthetic rows in place (will break the test suite)",
    )
    asyncio.run(main(parser.parse_args()))
