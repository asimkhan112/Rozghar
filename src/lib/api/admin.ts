/**
 * Admin endpoints.
 *
 * Separate from the public ones because they behave differently: every call
 * carries an access token, every mutation writes an audit row, and the
 * responses expose editorial state the public API withholds.
 */

import { api } from '@/lib/http'
import { now, toJob } from './adapters'
import type { Job } from '@/types/job'
import type { PaginatedDto } from './types'
import type {
  AnalyticsOverviewDto,
  AuditEntryDto,
  JobAdminDto,
  JobWriteDto,
  ReportDto,
  ReportStatusDto,
  SearchAnalyticsDto,
  SourceDto,
  SourcePerformanceDto,
} from './admin-types'
import type { CategoryDto, LocationDto } from './types'

// --- jobs -----------------------------------------------------------------

export interface AdminJobQuery {
  status?: string
  category_id?: string
  created_by?: string
  include_deleted?: boolean
  page?: number
  per_page?: number
}

/**
 * The editorial view of a listing.
 *
 * Reuses the public adapter for everything it renders in common, then adds the
 * fields the admin table needs. `version` rides along so a later PATCH can send
 * `If-Match` and be told about a concurrent edit rather than clobbering it.
 */
export interface AdminJob extends Job {
  /** Foreign keys the edit form needs to preselect its dropdowns. The display
   *  adapter reduces category and location to their labels, which is right for
   *  rendering and useless for writing back. */
  categoryId: string
  locationId: string
  version: number
  viewCount: number
  applyClickCount: number
  saveCount: number
  featured: boolean
  verified: boolean
  updatedAt: string
}

export function toAdminJob(dto: JobAdminDto, at = now()): AdminJob {
  return {
    ...toJob(dto, at),
    // The public adapter hardcodes `published`, because the public API only
    // ever returns published listings. Here the real status matters.
    status: dto.status === 'scheduled' ? 'draft' : dto.status,
    description: dto.description,
    requirements: dto.requirements,
    responsibilities: dto.responsibilities,
    benefits: dto.benefits,
    applyUrl: dto.apply_url,
    metrics: {
      views: dto.view_count,
      clicks: dto.apply_click_count,
      saves: dto.save_count,
    },
    categoryId: dto.category.id,
    locationId: dto.location.id,
    version: dto.version,
    viewCount: dto.view_count,
    applyClickCount: dto.apply_click_count,
    saveCount: dto.save_count,
    featured: dto.featured,
    verified: dto.verified,
    updatedAt: dto.updated_at,
  }
}

export interface AdminJobPage {
  items: AdminJob[]
  page: number
  perPage: number
  total: number
  totalPages: number
  hasMore: boolean
}

export async function fetchAdminJobs(
  query: AdminJobQuery,
  signal?: AbortSignal,
): Promise<AdminJobPage> {
  const dto = await api.get<PaginatedDto<JobAdminDto>>('/admin/jobs', { params: query, signal })
  const at = now()
  return {
    items: dto.items.map(item => toAdminJob(item, at)),
    page: dto.page,
    perPage: dto.per_page,
    total: dto.total,
    totalPages: dto.total_pages,
    hasMore: dto.has_more,
  }
}

export async function fetchAdminJob(id: string, signal?: AbortSignal): Promise<AdminJob> {
  return toAdminJob(await api.get<JobAdminDto>(`/admin/jobs/${id}`, { signal }))
}

export async function createJob(body: JobWriteDto): Promise<AdminJob> {
  return toAdminJob(await api.post<JobAdminDto>('/admin/jobs', body))
}

/**
 * `If-Match` carries the version last read.
 *
 * The backend rejects the write when it has moved on, so two editors on the
 * same listing get a conflict they can resolve instead of one silently
 * overwriting the other's work.
 */
export async function updateJob(
  id: string,
  changes: Partial<JobWriteDto>,
  version?: number,
): Promise<AdminJob> {
  return toAdminJob(
    await api.patch<JobAdminDto>(`/admin/jobs/${id}`, changes, {
      headers: version === undefined ? undefined : { 'If-Match': String(version) },
    }),
  )
}

/** Soft delete. The row survives — audit entries and `created_by` reference it. */
export function deleteJob(id: string): Promise<void> {
  return api.delete<void>(`/admin/jobs/${id}`)
}

// --- lifecycle actions ----------------------------------------------------
//
// Each is its own endpoint rather than a status field on PATCH: they carry
// distinct permissions and write distinct audit verbs. The client mirrors that
// rather than flattening them back into one call.

export async function publishJob(id: string, scheduledAt?: string): Promise<AdminJob> {
  return toAdminJob(
    await api.post<JobAdminDto>(`/admin/jobs/${id}/publish`, {
      scheduled_at: scheduledAt ?? null,
    }),
  )
}

export async function verifyJob(id: string, verified: boolean): Promise<AdminJob> {
  return toAdminJob(await api.post<JobAdminDto>(`/admin/jobs/${id}/verify`, { verified }))
}

export async function featureJob(
  id: string,
  featured: boolean,
  until?: string | null,
): Promise<AdminJob> {
  return toAdminJob(
    await api.post<JobAdminDto>(`/admin/jobs/${id}/feature`, { featured, until: until ?? null }),
  )
}

export async function expireJob(id: string, reason?: string): Promise<AdminJob> {
  return toAdminJob(
    await api.post<JobAdminDto>(`/admin/jobs/${id}/expire`, { reason: reason ?? null }),
  )
}

// --- reports --------------------------------------------------------------

export interface ReportQuery {
  status?: ReportStatusDto
  reason?: string
  job_id?: string
  page?: number
  per_page?: number
}

export function fetchReports(
  query: ReportQuery,
  signal?: AbortSignal,
): Promise<PaginatedDto<ReportDto>> {
  return api.get<PaginatedDto<ReportDto>>('/admin/reports', { params: query, signal })
}

export function moderateReport(
  id: string,
  changes: { status?: ReportStatusDto; resolution_note?: string },
): Promise<ReportDto> {
  return api.patch<ReportDto>(`/admin/reports/${id}`, changes)
}

// --- analytics ------------------------------------------------------------

export interface AnalyticsWindow {
  from?: string
  to?: string
}

export function fetchOverview(
  window: AnalyticsWindow,
  signal?: AbortSignal,
): Promise<AnalyticsOverviewDto> {
  return api.get<AnalyticsOverviewDto>('/admin/analytics/overview', { params: window, signal })
}

export function fetchSourcePerformance(
  window: AnalyticsWindow,
  signal?: AbortSignal,
): Promise<SourcePerformanceDto[]> {
  return api.get<SourcePerformanceDto[]>('/admin/analytics/sources', { params: window, signal })
}

export function fetchSearchAnalytics(
  window: AnalyticsWindow,
  signal?: AbortSignal,
): Promise<SearchAnalyticsDto> {
  return api.get<SearchAnalyticsDto>('/admin/analytics/search', { params: window, signal })
}

// --- audit ----------------------------------------------------------------

export function fetchAudit(
  params: { per_page?: number; action?: string },
  signal?: AbortSignal,
): Promise<PaginatedDto<AuditEntryDto>> {
  return api.get<PaginatedDto<AuditEntryDto>>('/admin/audit', { params, signal })
}

// --- taxonomy (admin writes) ---------------------------------------------

export function fetchSources(signal?: AbortSignal): Promise<SourceDto[]> {
  return api.get<SourceDto[]>('/sources', { signal })
}

export function createCategory(body: { name: string; slug: string; icon?: string }) {
  return api.post<CategoryDto>('/admin/categories', body)
}

export function updateCategory(id: string, changes: Record<string, unknown>) {
  return api.patch<CategoryDto>(`/admin/categories/${id}`, changes)
}

export interface NewLocation {
  city?: string
  region?: string
  country?: string
  is_remote?: boolean
  display_name?: string
}

/**
 * Add a location that is not in the list yet.
 *
 * The catalogue cannot enumerate every town in advance, and an editor who
 * cannot name the right place will pick the nearest big city — which is worse
 * than a slightly untidy taxonomy, because the listing then shows up in
 * searches for a city it is not in.
 */
export function createLocation(body: NewLocation) {
  return api.post<LocationDto>('/admin/locations', body)
}

export function updateLocation(id: string, changes: Record<string, unknown>) {
  return api.patch<LocationDto>(`/admin/locations/${id}`, changes)
}
