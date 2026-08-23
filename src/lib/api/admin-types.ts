/**
 * Admin wire types.
 *
 * `JobAdminDto` extends the public detail shape with the editorial state the
 * public API deliberately withholds: lifecycle status, counters, provenance
 * and the optimistic-locking version.
 */

import type { JobDetailDto, PaginatedDto } from './types'

export type JobStatusDto = 'draft' | 'scheduled' | 'published' | 'expired' | 'archived'

export interface JobAdminDto extends JobDetailDto {
  status: JobStatusDto
  featured_until: string | null
  verified_at: string | null
  verified_by: string | null
  view_count: number
  apply_click_count: number
  save_count: number
  created_by: string
  updated_by: string | null
  /** Incremented on every write. Sent back as `If-Match` to detect a
   * concurrent edit rather than silently overwriting one. */
  version: number
  created_at: string
  updated_at: string
  deleted_at: string | null
}

export type JobAdminPageDto = PaginatedDto<JobAdminDto>

/** What `POST /admin/jobs` accepts. Ids, enums and numbers — never labels. */
export interface JobWriteDto {
  title: string
  company_name: string
  /** Absent leaves the stored link untouched on a PATCH; explicit null clears it. */
  company_website?: string | null
  category_id: string
  location_id: string
  source_id?: string | null
  work_type: 'remote' | 'on_site' | 'hybrid'
  employment_type: 'full_time' | 'part_time' | 'contract' | 'internship'
  experience_level: 'intern' | 'entry' | 'mid' | 'senior' | 'lead' | 'executive'
  experience_min_years?: number | null
  experience_max_years?: number | null
  salary_min?: number | null
  salary_max?: number | null
  salary_currency?: string
  salary_period?: 'hour' | 'month' | 'year'
  salary_is_disclosed?: boolean
  description: string
  requirements: string[]
  responsibilities: string[]
  benefits: string[]
  apply_url: string
  expiry_date?: string | null
  logo_palette?: number
  status?: 'draft' | 'published'
}

export interface ReportJobRefDto {
  id: string
  slug: string
  title: string
  company_name: string
}

export type ReportStatusDto = 'open' | 'under_review' | 'resolved' | 'dismissed'
export type ReportReasonDto =
  | 'broken_link'
  | 'suspicious'
  | 'expired'
  | 'incorrect_information'
  | 'duplicate'
  | 'other'

export interface ReportDto {
  id: string
  reason: ReportReasonDto
  comment: string | null
  status: ReportStatusDto
  resolution_note: string | null
  resolved_by: string | null
  resolved_at: string | null
  created_at: string
  job: ReportJobRefDto
}

export interface AuditActorDto {
  id: string
  email: string
  full_name: string
}

export interface AuditEntryDto {
  id: number
  admin_id: string | null
  actor: AuditActorDto | null
  action: string
  entity_type: string
  entity_id: string | null
  before: Record<string, unknown> | null
  after: Record<string, unknown> | null
  created_at: string
}

export interface AnalyticsOverviewDto {
  range: { from: string; to: string }
  totals: {
    job_views: number
    apply_clicks: number
    shares: number
    source_clicks: number
    saves: number
    reports: number
    searches: number
    zero_result_searches: number
  }
  rates: { view_to_apply: number; zero_result_rate: number; save_rate: number }
  series: { date: string; job_views: number; apply_clicks: number }[]
  top_jobs: {
    job_id: string
    slug: string
    title: string
    company_name: string
    views: number
    apply_clicks: number
    ctr: number
  }[]
  top_queries: { query: string; count: number; zero_result_count: number }[]
}

/**
 * Session-grained traffic. A separate call from the overview because it is a
 * separate grain: the overview counts what happened to *listings*, this counts
 * what happened in *visits*.
 */
export interface TrafficSummaryDto {
  range: { from: string; to: string }
  page_views: number
  unique_sessions: number
  /** Last event minus first, averaged over sessions. Single-event visits
   *  measure zero and stay in the average. */
  avg_session_seconds: number
  /** Sessions that produced exactly one event. */
  bounce_rate: number
  views_per_session: number
  top_locations: {
    location_id: string
    name: string
    slug: string
    views: number
    apply_clicks: number
    /** Share of all located views in the window — the denominator counts every
     *  location with traffic, so a truncated list sums to less than 1. */
    share: number
  }[]
}

export interface VisitorPeriodDto {
  visitors: number
  page_views: number
  views_per_session: number
  previous_visitors: number
  /** `null` when the previous period had no visitors — growth from zero is
   *  undefined, not infinite, and the UI has to say so rather than print it. */
  change: number | null
}

/**
 * Visitors by period, each against the period before it.
 *
 * Takes no window: "vs last week" only means anything relative to now. Each
 * period is a distinct-session count in its own right — a week is not the sum
 * of its days, because a reader who returns is one weekly visitor and several
 * daily ones.
 */
export interface VisitorTrendsDto {
  as_of: string
  daily: VisitorPeriodDto
  weekly: VisitorPeriodDto
  monthly: VisitorPeriodDto
}

export interface SourcePerformanceDto {
  source_id: string
  name: string
  slug: string
  jobs: number
  views: number
  apply_clicks: number
  source_clicks: number
  reports: number
  ctr: number
  apply_rate_per_job: number
  report_rate: number
}

export interface SearchAnalyticsDto {
  range: { from: string; to: string }
  total_searches: number
  zero_result_searches: number
  zero_result_rate: number
  latency_p50_ms: number
  latency_p95_ms: number
  top_queries: { query: string; count: number; zero_result_count: number }[]
  zero_result_queries: { query: string; count: number }[]
}

export interface SourceDto {
  id: string
  name: string
  slug: string
  type: string
  is_active: boolean
}
