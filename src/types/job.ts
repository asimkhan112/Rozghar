/**
 * Domain types for job listings.
 *
 * Unions are derived from `as const` arrays so that the filter option lists
 * rendered in the UI and the types that validate them can never drift apart —
 * adding a work type in one place is a compile error everywhere it is handled.
 */

export const WORK_TYPES = ['Remote', 'On-site', 'Hybrid'] as const
export type WorkType = (typeof WORK_TYPES)[number]

export const EMPLOYMENT_TYPES = ['Full-time', 'Part-time', 'Contract', 'Internship'] as const
export type EmploymentType = (typeof EMPLOYMENT_TYPES)[number]

/** Public-facing marketing badge shown on cards and detail pages. */
export const JOB_BADGES = ['fresh', 'verified', 'featured', 'expiring'] as const
export type JobBadge = (typeof JOB_BADGES)[number]

/** Editorial lifecycle state, owned by the admin. Never shown on the public site. */
export const JOB_STATUSES = ['draft', 'published', 'expired', 'archived'] as const
export type JobStatus = (typeof JOB_STATUSES)[number]

export const SALARY_PERIODS = ['month', 'year', 'hour'] as const
export type SalaryPeriod = (typeof SALARY_PERIODS)[number]

export const CURRENCIES = ['PKR', 'USD'] as const
export type Currency = (typeof CURRENCIES)[number]

/** Aggregate engagement counters. Served by the analytics endpoint in Phase 8. */
export interface JobMetrics {
  views: number
  clicks: number
  saves: number
}

export interface Job {
  /** Stable identifier. Becomes a database UUID once Postgres lands. */
  id: string
  /** URL segment for `/jobs/:slug`. Unique, immutable once published. */
  slug: string

  title: string
  company: string
  /** Two-letter monogram rendered in the company avatar. */
  logo: string
  /**
   * Index into the logo colour palette, 0-5. Stored rather than derived from
   * `id` so that changing an identifier can never reshuffle the visual
   * appearance of every card. Moves onto the `companies` table in Phase 8.
   */
  logoPalette: number

  location: string
  category: string
  workType: WorkType
  employmentType: EmploymentType

  /** Pre-formatted salary for display, e.g. `PKR 250,000 – 350,000/mo`. */
  salary: string
  /** Structured salary, used for sorting and range filtering. */
  salaryMin: number
  salaryMax: number
  salaryCurrency: Currency
  salaryPeriod: SalaryPeriod

  /** Pre-formatted experience for display, e.g. `4–6 years`. */
  experience: string
  /** Structured experience in years, used for level filtering. */
  experienceMin: number
  experienceMax: number

  /** Pre-formatted relative time for display, e.g. `2 hours ago`. */
  postedDate: string
  /** ISO-8601 date. Null while the job is still a draft. */
  publishedAt: string | null
  /** ISO-8601 date. Null when the listing has no expiry. */
  expiresAt: string | null

  badge: JobBadge
  status: JobStatus

  description: string
  requirements: string[]
  responsibilities: string[]
  benefits: string[]
  applyUrl: string

  metrics: JobMetrics
}

/** Payload accepted by the admin create/edit form. */
export type JobInput = Omit<Job, 'id' | 'slug' | 'metrics' | 'postedDate'>

export interface JobCategory {
  name: string
  count: number
  icon: string
}
