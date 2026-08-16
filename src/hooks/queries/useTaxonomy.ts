/**
 * Category and location queries.
 *
 * Cached far longer than listings: both change only when an admin edits them,
 * and both are needed by nearly every page. Refetching them per navigation
 * would be the most wasteful request the app makes.
 */

import { useQuery } from "@tanstack/react-query"
import { fetchCategories, fetchLocations } from "@/lib/api"
import { STALE_TAXONOMY } from "@/app/queryClient"
import { queryKeys } from "./keys"

export function useCategories() {
  return useQuery({
    queryKey: queryKeys.taxonomy.categories(),
    queryFn: ({ signal }) => fetchCategories(signal),
    staleTime: STALE_TAXONOMY,
  })
}

export function useLocations() {
  return useQuery({
    queryKey: queryKeys.taxonomy.locations(),
    queryFn: ({ signal }) => fetchLocations(signal),
    staleTime: STALE_TAXONOMY,
  })
}
