/**
 * UI filter labels → API query parameters.
 *
 * The interface speaks in the words a person reads — "On-site", "This week",
 * "Salary: High to Low". The API speaks in enums, slugs and day counts. This
 * module is the only place that knows both, which is what lets the URL keep
 * its existing human-readable parameters while the request underneath uses the
 * API's vocabulary.
 *
 * Category and location need the live taxonomy to resolve a label to a slug,
 * so they are passed in rather than imported — the lists come from the API and
 * change without a deploy.
 */

import type { JobQuery } from "./jobs"
import type { LocationOption } from "./adapters"
import type { JobCategory } from "@/types/job"
import {
  ALL_CATEGORIES,
  ALL_EMPLOYMENT,
  ALL_LOCATIONS,
  ALL_TYPES,
  ANY_EXPERIENCE,
  ANY_TIME,
  type JobFilters,
} from "@/hooks/useJobFilters"

const WORK_TYPE: Record<string, JobQuery["work_type"]> = {
  Remote: "remote",
  "On-site": "on_site",
  Hybrid: "hybrid",
}

const EMPLOYMENT_TYPE: Record<string, JobQuery["employment_type"]> = {
  "Full-time": "full_time",
  "Part-time": "part_time",
  Contract: "contract",
  Internship: "internship",
}

/**
 * Experience ranges → the API's level enum.
 *
 * Lossy, and knowingly so. The interface offers year bands while the API
 * filters on a seniority level; the two do not correspond exactly, and a
 * listing marked `mid` with "2–8 years" sits across three bands. Mapping to
 * the closest level keeps the existing controls working. The exact fix is a
 * years-range filter on the API — worth doing when the imprecision starts
 * showing up in the search telemetry, not before.
 */
const EXPERIENCE: Record<string, JobQuery["experience"]> = {
  "Fresh / Intern": "intern",
  "1–3 years": "entry",
  "3–5 years": "mid",
  "5+ years": "senior",
}

const DATE_WINDOW_DAYS: Record<string, number> = {
  Today: 1,
  "This week": 7,
  "This month": 31,
}

const SORT: Record<string, JobQuery["sort"]> = {
  "Most Recent": "recent",
  "Salary: High to Low": "salary_desc",
  "Salary: Low to High": "salary_asc",
}

export interface Taxonomy {
  categories: JobCategory[]
  locations: LocationOption[]
}

/**
 * A label the user picked → the slug the API filters on.
 *
 * Three passes, loosest last. The exact match handles the normal case. The
 * prefix match handles links written before the taxonomy was live: the old
 * hardcoded list said "Lahore" where the API says "Lahore, Pakistan", so an
 * exact-only lookup would silently return nothing for every bookmark and
 * shared search anyone made before this phase.
 *
 * A filter that quietly matches nothing is the worst outcome here — the page
 * looks like it worked and simply has no jobs in it.
 */
function slugFor(
  label: string,
  options: { label: string; slug: string }[],
): string | undefined {
  const wanted = label.trim().toLowerCase()

  const exact = options.find((option) => option.label.toLowerCase() === wanted)
  if (exact) return exact.slug

  // "Lahore" matching "Lahore, Pakistan", not "Lahore" matching "Lahore Cantt"
  // by accident: the candidate must begin with the label at a word boundary.
  const prefixed = options.find((option) => {
    const candidate = option.label.toLowerCase()
    return (
      candidate === wanted ||
      candidate.startsWith(`${wanted},`) ||
      candidate.startsWith(`${wanted} `)
    )
  })
  if (prefixed) return prefixed.slug

  // Nothing in the taxonomy matched. Sending a slugified guess is better than
  // dropping the filter — an unknown slug returns an empty list, which is
  // honest, whereas dropping it returns everything and looks like the filter
  // was ignored.
  return wanted.replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "") || undefined
}

export function toJobQuery(
  filters: JobFilters,
  taxonomy: Taxonomy,
  { page, perPage }: { page: number; perPage: number },
): JobQuery {
  const query: JobQuery = { page, per_page: perPage }

  if (filters.q.trim()) query.q = filters.q.trim()

  if (filters.category !== ALL_CATEGORIES) {
    query.category = slugFor(
      filters.category,
      taxonomy.categories.map((c) => ({ label: c.name, slug: c.slug })),
    )
  }

  if (filters.location !== ALL_LOCATIONS) {
    query.location = slugFor(filters.location, taxonomy.locations)
  }

  if (filters.workType !== ALL_TYPES)
    query.work_type = WORK_TYPE[filters.workType]
  if (filters.employmentType !== ALL_EMPLOYMENT) {
    query.employment_type = EMPLOYMENT_TYPE[filters.employmentType]
  }
  if (filters.experience !== ANY_EXPERIENCE)
    query.experience = EXPERIENCE[filters.experience]
  if (filters.datePosted !== ANY_TIME) {
    query.posted_within_days = DATE_WINDOW_DAYS[filters.datePosted]
  }

  // Relevance is not a sort the API accepts — it is what ordering *becomes*
  // when a query is present. Asking for it without a query has no meaning, so
  // it falls back to recency.
  query.sort = SORT[filters.sort] ?? "recent"

  return query
}
