/**
 * Job queries.
 *
 * Hooks return React Query results unchanged — `data`, `isPending`, `isError`
 * and the rest — so pages read the same three states everywhere rather than
 * each inventing its own loading flag.
 */

import { useQuery, keepPreviousData } from "@tanstack/react-query"
import { fetchJob, fetchJobs, fetchSuggestions, type JobQuery } from "@/lib/api"
import { STALE_TAXONOMY } from "@/app/queryClient"
import { queryKeys } from "./keys"

export function useJobs(query: JobQuery, options?: { enabled?: boolean }) {
  return useQuery({
    queryKey: queryKeys.jobs.list(query),
    queryFn: ({ signal }) => fetchJobs(query, signal),
    enabled: options?.enabled ?? true,
    // Paging and filtering keep the previous page on screen while the next
    // loads. Without it every filter change blanks the results area, which
    // reads as breakage rather than as progress.
    placeholderData: keepPreviousData,
  })
}

export function useJob(slug: string | undefined) {
  return useQuery({
    queryKey: queryKeys.jobs.detail(slug ?? ""),
    queryFn: ({ signal }) => fetchJob(slug!, signal),
    enabled: Boolean(slug),
  })
}

/**
 * Resolve a client-held set of ids — the saved-jobs page.
 *
 * Disabled when nothing is saved: an empty `ids` list would either be an
 * unconstrained query returning the whole catalogue, or a request whose answer
 * is known in advance to be empty. Neither is worth a round trip.
 */
export function useJobsByIds(ids: string[]) {
  return useQuery({
    queryKey: queryKeys.jobs.byIds(ids),
    queryFn: ({ signal }) => fetchJobs({ ids, per_page: 50 }, signal),
    enabled: ids.length > 0,
  })
}

/** Typeahead. Idle below two characters, where every listing would match. */
export function useSuggestions(q: string) {
  const trimmed = q.trim()
  return useQuery({
    queryKey: queryKeys.jobs.suggestions(trimmed),
    queryFn: ({ signal }) => fetchSuggestions(trimmed, signal),
    enabled: trimmed.length >= 2,
    staleTime: STALE_TAXONOMY,
  })
}
