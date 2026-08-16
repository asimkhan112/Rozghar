/**
 * React Query configuration.
 *
 * The defaults here are chosen for a job board read by anonymous visitors:
 * listings change on the order of minutes, reference data on the order of
 * days, and nothing on the public site is worth refetching because someone
 * alt-tabbed back to the window.
 */

import { QueryClient } from "@tanstack/react-query"
import { ApiError } from "@/lib/http"

/** Listings move often enough that a minute is the honest ceiling. */
export const STALE_JOBS = 60_000
/** Categories and locations change when an admin edits them — rarely. */
export const STALE_TAXONOMY = 30 * 60_000

export function createQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: {
        staleTime: STALE_JOBS,
        gcTime: 5 * 60_000,
        // A visitor returning to the tab does not need a refetch; on a job
        // board it produces a flash of re-render for content that has almost
        // certainly not changed.
        refetchOnWindowFocus: false,
        retry: (failureCount, error) => {
          // Retrying a 404 or a 422 cannot succeed — the request itself is
          // what is wrong. Only transient failures are worth a second attempt.
          if (error instanceof ApiError && !error.isTransient) return false
          return failureCount < 2
        },
        retryDelay: (attempt) => Math.min(1000 * 2 ** attempt, 8000),
      },
    },
  })
}
