/**
 * Wire shapes → display shapes.
 *
 * The components were written against a model with pre-formatted strings
 * (`'PKR 250,000 – 350,000/mo'`, `'2 hours ago'`). The API returns structured
 * values instead, which is the right thing for it to return — a formatted
 * string cannot be sorted, converted, or re-localised.
 *
 * This module is where the two meet, and it exists so that Phase 3 changes the
 * data source without changing a single line of JSX. Every formatter here
 * reproduces the exact string the UI was built around, punctuation included:
 * the salary range uses an en dash with spaces, the experience range an en
 * dash without.
 */

import type { Job, JobCategory } from "@/types/job"
import type {
  CategoryDto,
  JobDetailDto,
  JobSummaryDto,
  LocationDto,
  SalaryDto,
} from "./types"

const WORK_TYPE_LABEL = {
  remote: "Remote",
  on_site: "On-site",
  hybrid: "Hybrid",
} as const

const EMPLOYMENT_TYPE_LABEL = {
  full_time: "Full-time",
  part_time: "Part-time",
  contract: "Contract",
  internship: "Internship",
} as const

/** Used only when a listing states no year range. */
const EXPERIENCE_LEVEL_LABEL = {
  intern: "Internship",
  entry: "Entry level",
  mid: "Mid level",
  senior: "Senior level",
  lead: "Lead",
  executive: "Executive",
} as const

const PERIOD_SUFFIX = { hour: "/hr", month: "/mo", year: "/yr" } as const

/** Rendered wherever an employer stated no figure. */
export const SALARY_UNDISCLOSED = "Salary not disclosed"

/**
 * Company initials for the avatar monogram.
 *
 * Two letters from two words, or the first two of a single word. Derived
 * rather than stored: the API has no `logo` field and inventing one would put
 * a presentation decision in the database.
 */
export function initials(company: string): string {
  const words = company.trim().split(/\s+/).filter(Boolean)
  if (words.length === 0) return "??"
  if (words.length === 1) return words[0]!.slice(0, 2).toUpperCase()
  return (words[0]![0]! + words[1]![0]!).toUpperCase()
}

function groupDigits(value: number): string {
  return Math.round(value).toLocaleString("en-US")
}

/**
 * `PKR 250,000 – 350,000/mo`, or `$3,000 – $4,500/mo` for USD.
 *
 * USD repeats the symbol on both bounds because that is how the prototype
 * rendered it; PKR carries the code once as a prefix.
 */
export function formatSalary(salary: SalaryDto): string {
  if (!salary.disclosed) return SALARY_UNDISCLOSED

  const min = salary.min === null ? null : Number(salary.min)
  const max = salary.max === null ? null : Number(salary.max)
  if (min === null && max === null) return SALARY_UNDISCLOSED

  const suffix = PERIOD_SUFFIX[salary.period] ?? ""
  const isUsd = salary.currency === "USD"
  const money = (value: number) =>
    isUsd ? `$${groupDigits(value)}` : groupDigits(value)
  const prefix = isUsd ? "" : `${salary.currency} `

  if (min !== null && max !== null && min !== max) {
    return `${prefix}${money(min)} – ${money(max)}${suffix}`
  }
  const single = (min ?? max) as number
  return `${prefix}${money(single)}${suffix}`
}

/** `4–6 years`, `5+ years`, or the level label when no range is stated. */
export function formatExperience(job: JobSummaryDto): string {
  const min = job.experience_min_years
  const max = job.experience_max_years

  if (min !== null && max !== null) {
    if (min === max) return min === 1 ? "1 year" : `${min} years`
    return `${min}–${max} years`
  }
  if (min !== null) return `${min}+ years`
  if (max !== null) return `Up to ${max} years`
  return EXPERIENCE_LEVEL_LABEL[job.experience_level] ?? "Not specified"
}

/**
 * The clock, injectable.
 *
 * Production reads the real one. The snapshot harness pins it, because
 * "2 hours ago" recomputed at render time would make every baseline differ
 * from the last by however long it took to run.
 */
let clock: () => number = () => Date.now()

/** Test seam. Pass `null` to restore the real clock. */
export function setClock(fixed: number | null): void {
  clock = fixed === null ? () => Date.now() : () => fixed
}

export function now(): number {
  return clock()
}

const MINUTE = 60_000
const HOUR = 60 * MINUTE
const DAY = 24 * HOUR
const WEEK = 7 * DAY

/**
 * `2 hours ago`, `1 day ago`, `3 weeks ago`.
 *
 * `now` is injectable so the snapshot harness can render a fixed instant —
 * otherwise every snapshot would differ from the last by the time between runs.
 */
export function relativeTime(iso: string | null, at: number = clock()): string {
  if (!iso) return "Recently"
  const then = Date.parse(iso)
  if (Number.isNaN(then)) return "Recently"

  const elapsed = Math.max(0, at - then)
  if (elapsed < HOUR) {
    const minutes = Math.max(1, Math.floor(elapsed / MINUTE))
    return minutes === 1 ? "1 minute ago" : `${minutes} minutes ago`
  }
  if (elapsed < DAY) {
    const hours = Math.floor(elapsed / HOUR)
    return hours === 1 ? "1 hour ago" : `${hours} hours ago`
  }
  if (elapsed < WEEK) {
    const days = Math.floor(elapsed / DAY)
    return days === 1 ? "1 day ago" : `${days} days ago`
  }
  const weeks = Math.floor(elapsed / WEEK)
  return weeks === 1 ? "1 week ago" : `${weeks} weeks ago`
}

/** ISO timestamp → `YYYY-MM-DD`, the form the display model expects. */
function dateOnly(iso: string | null): string | null {
  return iso ? (iso.split("T")[0] ?? null) : null
}

/**
 * A list row.
 *
 * `JobSummary` carries no description, requirements or apply URL — a list of
 * twenty must not ship twenty job descriptions. Those fields are filled with
 * empties here and populated properly by `toJobDetail`; only the detail page
 * reads them.
 */
export function toJob(dto: JobSummaryDto, now?: number): Job {
  return {
    id: dto.id,
    slug: dto.slug,
    title: dto.title,
    company: dto.company_name,
    logo: initials(dto.company_name),
    logoPalette: dto.logo_palette,
    location: dto.location.display_name,
    category: dto.category.name,
    workType: WORK_TYPE_LABEL[dto.work_type],
    employmentType: EMPLOYMENT_TYPE_LABEL[dto.employment_type],
    salary: formatSalary(dto.salary),
    salaryMin: dto.salary.min === null ? 0 : Number(dto.salary.min),
    salaryMax: dto.salary.max === null ? 0 : Number(dto.salary.max),
    salaryCurrency: dto.salary.currency === "USD" ? "USD" : "PKR",
    salaryPeriod: dto.salary.period,
    experience: formatExperience(dto),
    experienceMin: dto.experience_min_years ?? 0,
    experienceMax: dto.experience_max_years ?? 0,
    postedDate: relativeTime(dto.published_at, now),
    publishedAt: dateOnly(dto.published_at),
    expiresAt: dto.expiry_date,
    badge: dto.badge,
    // The public API only ever returns published listings, so this is a
    // constant rather than a field the wire needs to carry.
    status: "published",
    description: "",
    requirements: [],
    responsibilities: [],
    benefits: [],
    applyUrl: "",
    // Engagement counters are editorial and deliberately absent from public
    // responses. Nothing on the public site renders them.
    metrics: { views: 0, clicks: 0, saves: 0 },
  }
}

export function toJobDetail(dto: JobDetailDto, now?: number): Job {
  return {
    ...toJob(dto, now),
    description: dto.description,
    requirements: dto.requirements,
    responsibilities: dto.responsibilities,
    benefits: dto.benefits,
    applyUrl: dto.apply_url,
  }
}

/** The homepage category tiles. The stored glyph is passed through untouched —
 *  `categoryIcon` in the icon set decides which line icon renders it. */
export function toCategory(dto: CategoryDto): JobCategory {
  return {
    id: dto.id,
    name: dto.name,
    slug: dto.slug,
    count: dto.job_count,
    icon: dto.icon,
  }
}

export interface LocationOption {
  id: string
  slug: string
  label: string
  count: number
}

export function toLocation(dto: LocationDto): LocationOption {
  return { id: dto.id, slug: dto.slug, label: dto.display_name, count: dto.job_count }
}
