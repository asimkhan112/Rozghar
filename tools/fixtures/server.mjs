/**
 * A fake API for the snapshot harness.
 *
 * Snapshots exist to catch unintended visual change, which requires the same
 * input every run. Pointing them at a live backend would make the baseline
 * depend on whatever happens to be in the database.
 *
 * This stubs Axios at the adapter level rather than seeding the React Query
 * cache. Two reasons: query keys stay free to change without breaking the
 * harness, and the adapters — the formatters that turn structured salary and
 * timestamps into display strings — actually run, so a bug in `formatSalary`
 * shows up as a snapshot diff instead of passing unnoticed.
 *
 * The fixtures are the pre-integration seed data, converted to the wire shape.
 */

const WORK_TYPE = { Remote: "remote", "On-site": "on_site", Hybrid: "hybrid" }
const EMPLOYMENT_TYPE = {
  "Full-time": "full_time",
  "Part-time": "part_time",
  Contract: "contract",
  Internship: "internship",
}

/** Fixed instant so `2 hours ago` does not drift between runs. */
const TOP_QUERIES = [
  { query: "software engineer", count: 3820, zero_result_count: 12 },
  { query: "data analyst", count: 2140, zero_result_count: 4 },
  { query: "remote jobs", count: 1980, zero_result_count: 0 },
  { query: "marketing manager", count: 1540, zero_result_count: 31 },
  { query: "fresh graduate", count: 1320, zero_result_count: 8 },
  { query: "government jobs", count: 1280, zero_result_count: 2 },
]

export const FIXED_NOW = Date.parse("2026-08-13T11:00:00Z")

function slugify(value) {
  return value
    .toLowerCase()
    .replace(/&/g, " and ")
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-|-$/g, "")
}

function levelFor(job) {
  if (job.employmentType === "Internship" || job.experienceMax <= 1)
    return "intern"
  if (job.experienceMin >= 5) return "senior"
  if (job.experienceMin >= 3) return "mid"
  return "entry"
}

/** Frontend fixture → the shape `GET /jobs` actually returns. */
export function toDto(job, categories) {
  const category = categories.find((c) => c.name === job.category)
  return {
    id: job.id,
    slug: job.slug,
    title: job.title,
    company_name: job.company,
    company_logo: null,
    logo_palette: job.logoPalette,
    category: {
      id: `cat-${slugify(job.category)}`,
      name: job.category,
      slug: slugify(job.category),
      icon: category?.icon ?? null,
      job_count: category?.count ?? 0,
    },
    location: {
      id: `loc-${slugify(job.location)}`,
      slug: slugify(job.location),
      display_name: job.location,
      city: job.location.split(",")[0]?.trim() ?? null,
      region: null,
      country: "PK",
      is_remote: job.workType === "Remote",
      job_count: 0,
    },
    work_type: WORK_TYPE[job.workType],
    employment_type: EMPLOYMENT_TYPE[job.employmentType],
    experience_level: levelFor(job),
    experience_min_years: job.experienceMin,
    experience_max_years: job.experienceMax,
    salary: {
      min: job.salaryMin ? String(job.salaryMin.toFixed(2)) : null,
      max: job.salaryMax ? String(job.salaryMax.toFixed(2)) : null,
      currency: job.salaryCurrency,
      period: job.salaryPeriod,
      disclosed: Boolean(job.salaryMin || job.salaryMax),
    },
    badge: job.badge,
    featured: job.badge === "featured",
    verified: job.badge === "verified",
    published_at: job.publishedAt ? `${job.publishedAt}T09:00:00Z` : null,
    expiry_date: job.expiresAt,
  }
}

export function toDetailDto(job, categories, all) {
  const related = all
    .filter(
      (o) =>
        o.id !== job.id &&
        (o.category === job.category || o.workType === job.workType),
    )
    .slice(0, 3)
  return {
    ...toDto(job, categories),
    company_website: job.companyWebsite ?? null,
    description: job.description,
    requirements: job.requirements,
    responsibilities: job.responsibilities,
    benefits: job.benefits,
    apply_url: job.applyUrl,
    source: {
      id: "src-manual",
      name: "Manual Entry",
      slug: "manual",
      type: "manual",
      is_active: true,
    },
    related: related.map((o) => toDto(o, categories)),
  }
}

function page(items, params = {}) {
  const perPage = Number(params.per_page ?? 20)
  const current = Number(params.page ?? 1)
  const start = (current - 1) * perPage
  const slice = items.slice(start, start + perPage)
  return {
    items: slice,
    page: current,
    per_page: perPage,
    total: items.length,
    total_pages: Math.max(1, Math.ceil(items.length / perPage)),
    has_more: start + slice.length < items.length,
    search: params.q
      ? { query: params.q, strategy: "exact", degraded: false, response_ms: 12 }
      : null,
  }
}

/**
 * Applies the filters the API would apply. Kept deliberately simple — enough
 * that filtered snapshots differ from unfiltered ones, which is what the
 * `jobs-filtered` case is checking.
 */
function filter(jobs, params) {
  let out = jobs
  if (params.q) {
    const q = String(params.q).toLowerCase()
    out = out.filter(
      (j) =>
        j.title.toLowerCase().includes(q) ||
        j.company_name.toLowerCase().includes(q),
    )
  }
  if (params.category)
    out = out.filter((j) => j.category.slug === params.category)
  if (params.location)
    out = out.filter((j) => j.location.slug === params.location)
  if (params.work_type)
    out = out.filter((j) => j.work_type === params.work_type)
  if (params.employment_type)
    out = out.filter((j) => j.employment_type === params.employment_type)
  if (params.featured !== undefined)
    out = out.filter(
      (j) =>
        j.featured === (params.featured === true || params.featured === "true"),
    )
  if (params.ids) {
    const wanted = new Set(
      Array.isArray(params.ids) ? params.ids : [params.ids],
    )
    out = out.filter((j) => wanted.has(j.id))
  }
  if (params.sort === "salary_desc") {
    out = [...out].sort(
      (a, b) => Number(b.salary.min ?? 0) - Number(a.salary.min ?? 0),
    )
  } else if (params.sort === "salary_asc") {
    out = [...out].sort(
      (a, b) => Number(a.salary.min ?? 0) - Number(b.salary.min ?? 0),
    )
  }
  return out
}

/**
 * An Axios adapter that answers from fixtures.
 *
 * Returns an already-resolved promise so a single `await act()` flushes every
 * request; a delayed one would need the harness to poll for settlement.
 */
export function makeAdapter({ jobs, categories }) {
  const summaries = jobs.map((job) => toDto(job, categories))

  return async function fixtureAdapter(config) {
    const url = config.url ?? ""
    const params = config.params ?? {}
    const ok = (data) => ({
      data,
      status: 200,
      statusText: "OK",
      headers: {},
      config,
    })

    if (url === "/categories") {
      return ok(
        categories.map((c) => ({
          id: `cat-${slugify(c.name)}`,
          name: c.name,
          slug: slugify(c.name),
          icon: c.icon,
          job_count: c.count,
        })),
      )
    }

    if (url === "/locations") {
      const seen = new Map()
      for (const job of jobs) {
        if (!seen.has(job.location)) {
          seen.set(job.location, {
            id: `loc-${slugify(job.location)}`,
            slug: slugify(job.location),
            display_name: job.location,
            city: job.location.split(",")[0]?.trim() ?? null,
            region: null,
            country: "PK",
            is_remote: job.workType === "Remote",
            job_count: 0,
          })
        }
      }
      return ok([...seen.values()])
    }

    if (url === "/jobs") return ok(page(filter(summaries, params), params))

    // --- admin -----------------------------------------------------------
    // The editorial endpoints return the same listings with the state the
    // public API withholds, so the admin snapshots exercise the real table
    // rather than an error panel.
    if (url === "/admin/jobs") {
      const admin = jobs.map((job, i) => ({
        ...toDetailDto(job, categories, jobs),
        // A spread of states, so the status pill and the per-row action set
        // are both covered.
        status: i % 5 === 0 ? "draft" : i % 7 === 0 ? "expired" : "published",
        featured_until: null,
        verified_at: null,
        verified_by: null,
        view_count: 100 + i * 37,
        apply_click_count: 10 + i * 5,
        save_count: 3 + i,
        created_by: "admin-1",
        updated_by: null,
        version: 1,
        created_at: "2026-08-01T09:00:00Z",
        updated_at: "2026-08-12T09:00:00Z",
        deleted_at: null,
      }))
      const wanted = params.status ? admin.filter((j) => j.status === params.status) : admin
      return ok(page(wanted, params))
    }

    if (url === "/admin/reports") {
      const open =
        params.status === "resolved"
          ? []
          : jobs.slice(0, 3).map((job, i) => ({
              id: `report-${i + 1}`,
              reason: ["broken_link", "suspicious", "expired"][i] ?? "other",
              comment: [
                "The apply button leads to a 404 page on the company site.",
                "This looks like a fake posting — no company information anywhere.",
                "I applied and was told the position was filled weeks ago.",
              ][i] ?? "",
              status: "open",
              resolution_note: null,
              resolved_by: null,
              resolved_at: null,
              created_at: "2026-08-12T09:00:00Z",
              job: { id: job.id, slug: job.slug, title: job.title, company_name: job.company },
            }))
      return ok(page(open, params))
    }

    if (url === "/admin/analytics/overview") {
      return ok({
        range: { from: "2026-07-15", to: "2026-08-13" },
        totals: {
          job_views: 18420, apply_clicks: 1362, shares: 331, source_clicks: 208,
          saves: 754, reports: 12, searches: 3840, zero_result_searches: 216,
        },
        rates: { view_to_apply: 0.0739, zero_result_rate: 0.0563, save_rate: 0.0409 },
        series: Array.from({ length: 14 }, (_, i) => ({
          date: `2026-08-${String(i + 1).padStart(2, "0")}`,
          job_views: 900 + i * 40,
          apply_clicks: 60 + i * 3,
        })),
        top_jobs: jobs.slice(0, 5).map((job, i) => ({
          job_id: job.id, slug: job.slug, title: job.title, company_name: job.company,
          views: 1840 - i * 210, apply_clicks: 312 - i * 40, ctr: 0.17 - i * 0.01,
        })),
        top_queries: TOP_QUERIES,
      })
    }

    if (url === "/admin/analytics/search") {
      return ok({
        range: { from: "2026-07-15", to: "2026-08-13" },
        total_searches: 3840, zero_result_searches: 216, zero_result_rate: 0.0563,
        latency_p50_ms: 42, latency_p95_ms: 118,
        top_queries: TOP_QUERIES,
        zero_result_queries: [
          { query: "blockchain developer karachi", count: 31 },
          { query: "urdu content writer remote", count: 18 },
        ],
      })
    }

    if (url === "/admin/analytics/sources") {
      return ok([
        {
          source_id: "src-manual", name: "Manual Entry", slug: "manual",
          jobs: jobs.length, views: 18420, apply_clicks: 1362, source_clicks: 208,
          reports: 12, ctr: 0.074, apply_rate_per_job: 113.5, report_rate: 1.0,
        },
      ])
    }

    if (url === "/admin/audit") {
      const actions = [
        "job.publish", "job.create", "report.resolve", "job.verify",
        "job.expire", "admin.create", "job.feature",
      ]
      return ok(
        page(
          actions.map((action, i) => ({
            id: 100 - i,
            admin_id: "admin-1",
            actor: { id: "admin-1", email: "owner@plenilo.com", full_name: "Site Owner" },
            action,
            entity_type: action.split(".")[0],
            entity_id: jobs[i % jobs.length]?.id ?? null,
            before: null,
            after: null,
            created_at: "2026-08-13T10:00:00Z",
          })),
          params,
        ),
      )
    }

    if (url === "/sources") {
      return ok([
        { id: "src-manual", name: "Manual Entry", slug: "manual", type: "manual", is_active: true },
      ])
    }

    if (url.startsWith("/jobs/")) {
      const slug = decodeURIComponent(url.slice("/jobs/".length))
      const job = jobs.find((j) => j.slug === slug)
      if (!job) {
        const error = new Error("Not Found")
        error.response = {
          status: 404,
          statusText: "Not Found",
          data: {
            type: "https://plenilo.com/errors/not_found",
            title: "Resource not found",
            status: 404,
          },
          headers: {},
          config,
        }
        error.config = config
        throw error
      }
      return ok(toDetailDto(job, categories, jobs))
    }

    throw new Error(`fixture server has no route for ${url}`)
  }
}
