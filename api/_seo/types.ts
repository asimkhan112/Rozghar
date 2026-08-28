/**
 * The API's public wire shape, as the prerenderer sees it.
 *
 * Deliberately *not* imported from `src/types/job.ts`. That file describes the
 * adapted, display-ready domain object the React app works with — pre-formatted
 * salary strings, relative "2 hours ago" dates, a `logo` monogram. The
 * prerenderer never runs the adapter: it reads the API response directly and
 * emits structured data from it, so it needs the wire vocabulary
 * (`company_name`, `work_type`, `salary.disclosed`) rather than the UI's.
 *
 * Keeping the two apart is what lets `lib/format.ts` change how a salary reads
 * on a card without silently rewriting what we tell Google the salary is.
 *
 * Only the fields structured data actually consumes are modelled. The API sends
 * more; anything not named here is ignored rather than mistyped.
 */

export type WorkType = 'remote' | 'on_site' | 'hybrid'
export type EmploymentType = 'full_time' | 'part_time' | 'contract' | 'internship'
export type SalaryPeriod = 'hour' | 'month' | 'year'

export interface WireCategory {
  name: string
  slug: string
  job_count?: number
}

export interface WireLocation {
  slug: string
  display_name: string
  city: string | null
  region: string | null
  /** ISO 3166-1 alpha-2, which is what schema.org's `addressCountry` wants. */
  country: string | null
  is_remote: boolean
  job_count?: number
}

export interface WireSalary {
  /** Decimals arrive as strings — asyncpg/pydantic will not round-trip a
   *  Decimal through JSON as a number, and we must not re-introduce float
   *  error into a figure a person is deciding a job on. */
  min: string | null
  max: string | null
  currency: string
  period: SalaryPeriod
  disclosed: boolean
}

export interface WireJobSummary {
  id: string
  slug: string
  title: string
  company_name: string
  company_logo: string | null
  category: WireCategory
  location: WireLocation
  work_type: WorkType
  employment_type: EmploymentType
  salary: WireSalary
  published_at: string | null
  expiry_date: string | null
}

export interface WireJobDetail extends WireJobSummary {
  company_website: string | null
  description: string
  requirements: string[]
  responsibilities: string[]
  benefits: string[]
  apply_url: string
}

export interface WireJobList {
  items: WireJobSummary[]
  total?: number
}
