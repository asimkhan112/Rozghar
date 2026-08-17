/**
 * Query keys, in one place.
 *
 * Every key is built from these factories rather than written inline, because
 * invalidation depends on prefix structure: `['jobs']` must invalidate every
 * job list, and it only does so if every list key genuinely starts with it. A
 * stray `['job-list']` somewhere is a cache entry nothing can ever clear.
 *
 * The shape is hierarchical — broadest first, narrowing left to right:
 *
 *   ['jobs']                    every job query
 *   ['jobs', 'list']            every list
 *   ['jobs', 'list', {…}]       one filtered list
 *   ['jobs', 'detail', slug]    one listing
 */

import type { JobQuery } from "@/lib/api"
import type { AdminJobQuery, AnalyticsWindow, ReportQuery } from "@/lib/api/admin"

export const queryKeys = {
  jobs: {
    all: ["jobs"] as const,
    lists: () => [...queryKeys.jobs.all, "list"] as const,
    /** Filters are part of the key: two filter sets are two cache entries. */
    list: (query: JobQuery) => [...queryKeys.jobs.lists(), query] as const,
    details: () => [...queryKeys.jobs.all, "detail"] as const,
    detail: (slug: string) => [...queryKeys.jobs.details(), slug] as const,
    /** The saved-jobs page: an explicit id set rather than a filter. */
    byIds: (ids: string[]) =>
      [...queryKeys.jobs.all, "by-ids", [...ids].sort()] as const,
  },
  /** Grouped autocomplete. Keyed by scope as well as query: the admin variant
   *  includes drafts, and must never serve its rows to a public reader from a
   *  shared cache entry. */
  suggest: {
    all: ["suggest"] as const,
    query: (scope: "public" | "admin", q: string) => ["suggest", scope, q] as const,
  },
  admin: {
    all: ['admin'] as const,
    /** Admin taxonomy reads. Kept apart from `taxonomy`, which is the public
     *  projection: the two return different rows, and sharing a key would let
     *  an archived category leak into a public dropdown. */
    taxonomy: {
      all: ['admin', 'taxonomy'] as const,
      categories: () => ['admin', 'taxonomy', 'categories'] as const,
      locations: () => ['admin', 'taxonomy', 'locations'] as const,
      sources: () => ['admin', 'taxonomy', 'sources'] as const,
    },
    jobs: {
      all: ['admin', 'jobs'] as const,
      lists: () => [...queryKeys.admin.jobs.all, 'list'] as const,
      list: (query: AdminJobQuery) => [...queryKeys.admin.jobs.lists(), query] as const,
      detail: (id: string) => [...queryKeys.admin.jobs.all, 'detail', id] as const,
    },
    reports: {
      all: ['admin', 'reports'] as const,
      list: (query: ReportQuery) => [...queryKeys.admin.reports.all, 'list', query] as const,
    },
    analytics: {
      all: ['admin', 'analytics'] as const,
      overview: (window: AnalyticsWindow) =>
        [...queryKeys.admin.analytics.all, 'overview', window] as const,
      sources: (window: AnalyticsWindow) =>
        [...queryKeys.admin.analytics.all, 'sources', window] as const,
      search: (window: AnalyticsWindow) =>
        [...queryKeys.admin.analytics.all, 'search', window] as const,
    },
    audit: {
      all: ['admin', 'audit'] as const,
      list: (params: object) => [...queryKeys.admin.audit.all, 'list', params] as const,
    },
    sources: () => ['admin', 'sources'] as const,
    shareAssets: (jobId: string) => ['admin', 'share-assets', jobId] as const,
  },
  taxonomy: {
    all: ["taxonomy"] as const,
    categories: () => [...queryKeys.taxonomy.all, "categories"] as const,
    locations: () => [...queryKeys.taxonomy.all, "locations"] as const,
  },
} as const
