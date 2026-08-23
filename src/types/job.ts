/**
 * Domain types for job listings.
 *
 * Unions are derived from `as const` arrays so that the filter option lists
 * rendered in the UI and the types that validate them can never drift apart —
 * adding a work type in one place is a compile error everywhere it is handled.
 */

export const WORK_TYPES = ["Remote", "On-site", "Hybrid"] as const
export type WorkType = typeof WORK_TYPES[number]

export const EMPLOYMENT_TYPES = [
  "Full-time",
  "Part-time",
  "Contract",
  "Internship",
] as const
export type EmploymentType = typeof EMPLOYMENT_TYPES[number]

/** Public-facing marketing badge shown on cards and detail pages. */
export const JOB_BADGES = ["fresh", "verified", "featured", "expiring"] as const
export type JobBadge = typeof JOB_BADGES[number]

/** Editorial lifecycle state, owned by the admin. Never shown on the public site. */
export const JOB_STATUSES = [
  "draft",
  "published",
  "expired",
  "archived",
] as const
export type JobStatus = typeof JOB_STATUSES[number]

export const SALARY_PERIODS = ["month", "year", "hour"] as const
export type SalaryPeriod = typeof SALARY_PERIODS[number]

/**
 * Currencies an editor can pick from, most-used first.
 *
 * The API stores any ISO-4217 code, so this list is a convenience rather than
 * a constraint — a listing that arrives carrying a code not named here still
 * renders, and the admin form offers it back as its own option rather than
 * silently rewriting it. Ordered by where the listings actually come from, not
 * alphabetically: a picker that opens on AED when nine in ten jobs are PKR
 * costs every editor a scroll.
 */
export const CURRENCIES = [
  "PKR", "USD", "EUR", "GBP", "AED", "SAR", "QAR", "OMR", "KWD", "BHD",
  "INR", "CAD", "AUD", "NZD", "SGD", "MYR", "HKD", "CNY", "JPY", "CHF",
  "TRY", "ZAR", "NGN", "KES", "EGP", "BDT", "LKR", "NPR", "PHP", "IDR",
  "THB", "VND", "SEK", "NOK", "DKK", "PLN", "BRL", "MXN",
] as const
export type Currency = typeof CURRENCIES[number]

/** Full names for the picker — "AED" alone does not tell an editor much. */
export const CURRENCY_LABEL: Record<Currency, string> = {
  PKR: "Pakistani rupee", USD: "US dollar", EUR: "Euro", GBP: "Pound sterling",
  AED: "UAE dirham", SAR: "Saudi riyal", QAR: "Qatari riyal", OMR: "Omani rial",
  KWD: "Kuwaiti dinar", BHD: "Bahraini dinar", INR: "Indian rupee",
  CAD: "Canadian dollar", AUD: "Australian dollar", NZD: "New Zealand dollar",
  SGD: "Singapore dollar", MYR: "Malaysian ringgit", HKD: "Hong Kong dollar",
  CNY: "Chinese yuan", JPY: "Japanese yen", CHF: "Swiss franc",
  TRY: "Turkish lira", ZAR: "South African rand", NGN: "Nigerian naira",
  KES: "Kenyan shilling", EGP: "Egyptian pound", BDT: "Bangladeshi taka",
  LKR: "Sri Lankan rupee", NPR: "Nepalese rupee", PHP: "Philippine peso",
  IDR: "Indonesian rupiah", THB: "Thai baht", VND: "Vietnamese dong",
  SEK: "Swedish krona", NOK: "Norwegian krone", DKK: "Danish krone",
  PLN: "Polish zloty", BRL: "Brazilian real", MXN: "Mexican peso",
}

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
  /** The employer's own site, when the listing records one. Detail pages only:
   *  the API does not send it on list rows, so a card always sees null. */
  companyWebsite: string | null
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
  /** ISO-4217 code as the API stated it — not narrowed to `Currency`, because
   *  the wire is allowed to carry a code this build has never heard of. */
  salaryCurrency: string
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
export type JobInput = Omit<Job, "id" | "slug" | "metrics" | "postedDate">

export interface JobCategory {
  /** Primary key. Needed when writing — the job form assigns a category by id. */
  id: string
  name: string
  count: number
  /** The taxonomy's stored glyph. Mapped to a line icon by `categoryIcon`;
   *  null when the category was created without one. */
  icon: string | null
  /** URL segment the API filters on. Owned by the backend, never derived. */
  slug: string
}
