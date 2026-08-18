/**
 * Reports, analytics, audit and sources.
 *
 * Read-mostly, so these are thin. The one mutation — moderating a report —
 * invalidates rather than patching: the workflow has server-side rules
 * (reopening clears the resolution, terminal states demand a note) whose result
 * the client should not try to predict.
 */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  createCategory,
  createLocation,
  fetchAdminCategories,
  fetchAdminLocations,
  fetchAdminSources,
  fetchAudit,
  fetchOverview,
  fetchReports,
  fetchSearchAnalytics,
  fetchTraffic,
  fetchVisitorTrends,
  fetchSourcePerformance,
  fetchSources,
  moderateReport,
  updateCategory,
  updateLocation,
  updateSource,
  type AnalyticsWindow,
  type NewLocation,
  type ReportQuery,
} from '@/lib/api/admin'
import type { ReportStatusDto } from '@/lib/api/admin-types'
import { fetchShareAssets } from '@/lib/api/share'
import { generateDescription, rewriteDescription, type GenerateInput } from '@/lib/api/ai'
import { STALE_TAXONOMY } from '@/app/queryClient'
import { queryKeys } from './keys'

export function useReports(query: ReportQuery) {
  return useQuery({
    queryKey: queryKeys.admin.reports.list(query),
    queryFn: ({ signal }) => fetchReports(query, signal),
  })
}

export function useModerateReport() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: ({
      id,
      changes,
    }: {
      id: string
      changes: { status?: ReportStatusDto; resolution_note?: string }
    }) => moderateReport(id, changes),
    onSuccess: () =>
      Promise.all([
        client.invalidateQueries({ queryKey: queryKeys.admin.reports.all }),
        // A resolved report is an audited action, and the dashboard counts
        // open reports.
        client.invalidateQueries({ queryKey: queryKeys.admin.audit.all }),
        client.invalidateQueries({ queryKey: queryKeys.admin.analytics.all }),
      ]),
  })
}

export function useAnalyticsOverview(window: AnalyticsWindow = {}) {
  return useQuery({
    queryKey: queryKeys.admin.analytics.overview(window),
    queryFn: ({ signal }) => fetchOverview(window, signal),
  })
}

export function useVisitorTrends() {
  return useQuery({
    queryKey: queryKeys.admin.analytics.visitors(),
    queryFn: ({ signal }) => fetchVisitorTrends(signal),
  })
}

export function useTraffic(window: AnalyticsWindow = {}) {
  return useQuery({
    queryKey: queryKeys.admin.analytics.traffic(window),
    queryFn: ({ signal }) => fetchTraffic(window, signal),
  })
}

export function useSourcePerformance(window: AnalyticsWindow = {}) {
  return useQuery({
    queryKey: queryKeys.admin.analytics.sources(window),
    queryFn: ({ signal }) => fetchSourcePerformance(window, signal),
  })
}

export function useSearchAnalytics(window: AnalyticsWindow = {}) {
  return useQuery({
    queryKey: queryKeys.admin.analytics.search(window),
    queryFn: ({ signal }) => fetchSearchAnalytics(window, signal),
  })
}

export function useAuditFeed(perPage = 12) {
  return useQuery({
    queryKey: queryKeys.admin.audit.list({ per_page: perPage }),
    queryFn: ({ signal }) => fetchAudit({ per_page: perPage }, signal),
  })
}

/**
 * Create a location and make it immediately selectable.
 *
 * Invalidates the taxonomy so every open dropdown picks it up, rather than
 * leaving the editor to reload the page to use the thing they just added.
 */
export function useCreateLocation() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (body: NewLocation) => createLocation(body),
    onSuccess: () => client.invalidateQueries({ queryKey: queryKeys.taxonomy.all }),
  })
}

/**
 * Share captions and image URLs for one listing.
 *
 * Only fetched when the modal is open — the payload is useless until then, and
 * requesting it on every publish would generate captions nobody reads.
 */
export function useShareAssets(jobId: string | null) {
  return useQuery({
    queryKey: queryKeys.admin.shareAssets(jobId ?? ""),
    queryFn: ({ signal }) => fetchShareAssets(jobId!, signal),
    enabled: Boolean(jobId),
    // Captions are derived from the listing; they change only when it does.
    staleTime: STALE_TAXONOMY,
  })
}

/**
 * AI drafting mutations.
 *
 * No cache invalidation, because nothing on the server changed — the draft is
 * returned to the caller and goes nowhere else until the editor accepts it.
 */
export function useRewriteDescription() {
  return useMutation({ mutationFn: (description: string) => rewriteDescription(description) })
}

export function useGenerateDescription() {
  return useMutation({ mutationFn: (input: GenerateInput) => generateDescription(input) })
}

export function useSources() {
  return useQuery({
    queryKey: queryKeys.admin.sources(),
    queryFn: ({ signal }) => fetchSources(signal),
    staleTime: STALE_TAXONOMY,
  })
}

// --- taxonomy administration ---------------------------------------------

/**
 * Taxonomy as the console sees it: archived rows included.
 *
 * These read the admin projections rather than the public ones. A screen that
 * offers "archive" has to be able to show what it archived, and the public
 * endpoints filter inactive rows out — so a console built on them can put a
 * category beyond reach with one click.
 */
export function useAdminCategories() {
  return useQuery({
    queryKey: queryKeys.admin.taxonomy.categories(),
    queryFn: ({ signal }) => fetchAdminCategories(signal),
  })
}

export function useAdminLocations() {
  return useQuery({
    queryKey: queryKeys.admin.taxonomy.locations(),
    queryFn: ({ signal }) => fetchAdminLocations(signal),
  })
}

export function useAdminSources() {
  return useQuery({
    queryKey: queryKeys.admin.taxonomy.sources(),
    queryFn: ({ signal }) => fetchAdminSources(signal),
  })
}

/** Both the admin list and every public dropdown are stale after a write. */
function invalidateTaxonomy(client: ReturnType<typeof useQueryClient>) {
  void client.invalidateQueries({ queryKey: queryKeys.admin.taxonomy.all })
  void client.invalidateQueries({ queryKey: queryKeys.taxonomy.all })
}

export function useCreateCategory() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (body: { name: string; slug: string; icon?: string }) => createCategory(body),
    onSuccess: () => invalidateTaxonomy(client),
  })
}

export function useUpdateCategory() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: ({ id, changes }: { id: string; changes: Record<string, unknown> }) =>
      updateCategory(id, changes),
    onSuccess: () => invalidateTaxonomy(client),
  })
}

export function useUpdateLocation() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: ({ id, changes }: { id: string; changes: Record<string, unknown> }) =>
      updateLocation(id, changes),
    onSuccess: () => invalidateTaxonomy(client),
  })
}

export function useUpdateSource() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: ({ id, changes }: { id: string; changes: Record<string, unknown> }) =>
      updateSource(id, changes),
    onSuccess: () => invalidateTaxonomy(client),
  })
}
