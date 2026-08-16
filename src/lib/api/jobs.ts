/**
 * Job endpoints.
 *
 * Each function owns one request and returns display-ready shapes — callers
 * never see a DTO. Filters are translated here too: the UI speaks in labels
 * ("On-site", "This week") and the API in enums and day counts.
 */

import { api } from "@/lib/http"
import { getSessionId } from "@/lib/session"
import { now, toJob, toJobDetail } from "./adapters"
import type {
  JobDetailDto,
  JobSummaryDto,
  PaginatedDto,
  SearchMetaDto,
} from "./types"
import type { Job } from "@/types/job"

/** Everything `GET /jobs` accepts, in the API's own vocabulary. */
export interface JobQuery {
  q?: string
  category?: string
  location?: string
  work_type?: "remote" | "on_site" | "hybrid"
  employment_type?: "full_time" | "part_time" | "contract" | "internship"
  experience?: "intern" | "entry" | "mid" | "senior" | "lead" | "executive"
  posted_within_days?: number
  salary_min?: number
  featured?: boolean
  verified?: boolean
  ids?: string[]
  sort?: "recent" | "salary_desc" | "salary_asc" | "title"
  page?: number
  per_page?: number
}

export interface JobPage {
  items: Job[]
  page: number
  perPage: number
  total: number
  totalPages: number
  hasMore: boolean
  /** Present only when the request carried `q`; lets the UI be honest about
   * degraded results instead of presenting fallbacks as exact matches. */
  search: SearchMetaDto | null
}

export async function fetchJobs(
  query: JobQuery,
  signal?: AbortSignal,
): Promise<JobPage> {
  const params: Record<string, unknown> = { ...query }
  // Only searches carry a session id — it is what lets the backend reconstruct
  // "searched, then viewed, then applied" rather than counting events in
  // isolation. Sending it on an unfiltered browse would be noise.
  if (query.q) params.session_id = getSessionId()

  const dto = await api.get<PaginatedDto<JobSummaryDto>>("/jobs", {
    params,
    signal,
  })
  const at = now()
  return {
    items: dto.items.map((item) => toJob(item, at)),
    page: dto.page,
    perPage: dto.per_page,
    total: dto.total,
    totalPages: dto.total_pages,
    hasMore: dto.has_more,
    search: dto.search ?? null,
  }
}

export interface JobWithRelated {
  job: Job
  related: Job[]
}

export async function fetchJob(
  slug: string,
  signal?: AbortSignal,
): Promise<JobWithRelated> {
  const dto = await api.get<JobDetailDto>(`/jobs/${encodeURIComponent(slug)}`, {
    signal,
  })
  const at = now()
  return {
    job: toJobDetail(dto, at),
    related: dto.related.map((item) => toJob(item, at)),
  }
}

/** Typeahead. Returns bare strings — a suggestion needs no more than its text. */
export function fetchSuggestions(
  q: string,
  signal?: AbortSignal,
): Promise<string[]> {
  return api.get<string[]>("/jobs/suggest", { params: { q }, signal })
}
