/**
 * Wire types — exactly what the API returns, in the API's own naming.
 *
 * Deliberately snake_case and deliberately not the shapes the components use.
 * Keeping the wire contract separate from the display model is what stops a
 * backend rename from rippling into fifty JSX files: only `adapters.ts` knows
 * both vocabularies.
 */

export interface PaginatedDto<T> {
  items: T[]
  page: number
  per_page: number
  total: number
  total_pages: number
  has_more: boolean
  search?: SearchMetaDto | null
}

/** Present only on responses that ran a text search. */
export interface SearchMetaDto {
  query: string
  /** Which tier produced the results: exact, broadened, fuzzy, related, none. */
  strategy: string
  degraded: boolean
  response_ms: number
}

export interface CategoryDto {
  id: string
  name: string
  slug: string
  icon: string | null
  job_count: number
}

export interface LocationDto {
  id: string
  slug: string
  display_name: string
  city: string | null
  region: string | null
  country: string
  is_remote: boolean
  job_count: number
}

export interface SourceDto {
  id: string
  name: string
  slug: string
  type: string
  is_active: boolean
}

/** `disclosed: false` means the employer stated nothing — not that pay is zero. */
export interface SalaryDto {
  min: string | null
  max: string | null
  currency: string
  period: "hour" | "month" | "year"
  disclosed: boolean
}

export type WorkTypeDto = "remote" | "on_site" | "hybrid"
export type EmploymentTypeDto = "full_time" | "part_time" | "contract" | "internship"
export type ExperienceLevelDto = "intern" | "entry" | "mid" | "senior" | "lead" | "executive"
export type BadgeDto = "fresh" | "verified" | "featured" | "expiring"

export interface JobSummaryDto {
  id: string
  slug: string
  title: string
  company_name: string
  company_logo: string | null
  logo_palette: number
  category: CategoryDto
  location: LocationDto
  work_type: WorkTypeDto
  employment_type: EmploymentTypeDto
  experience_level: ExperienceLevelDto
  experience_min_years: number | null
  experience_max_years: number | null
  salary: SalaryDto
  badge: BadgeDto
  featured: boolean
  verified: boolean
  published_at: string | null
  expiry_date: string | null
}

export interface JobDetailDto extends JobSummaryDto {
  description: string
  requirements: string[]
  responsibilities: string[]
  benefits: string[]
  apply_url: string
  source: SourceDto
  related: JobSummaryDto[]
}
