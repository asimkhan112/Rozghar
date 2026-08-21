/**
 * Reference data: categories and locations.
 *
 * Both are small, rarely change, and are needed by almost every page — which
 * is why the query layer caches them far longer than listings.
 */

import { api } from "@/lib/http"
import { toCategory, toLocation, type LocationOption } from "./adapters"
import type { CategoryDto, CountryDto, LocationDto } from "./types"
import type { JobCategory } from "@/types/job"

export async function fetchCategories(
  signal?: AbortSignal,
): Promise<JobCategory[]> {
  const dto = await api.get<CategoryDto[]>("/categories", { signal })
  return dto.map(toCategory)
}

export async function fetchLocations(
  signal?: AbortSignal,
): Promise<LocationOption[]> {
  const dto = await api.get<LocationDto[]>("/locations", { signal })
  return dto.map(toLocation)
}

/**
 * Every country a location may belong to, already sorted by name.
 *
 * Fetched rather than generated in the browser. `Intl.DisplayNames` could
 * produce a list here, but it would be a *different* list — ICU ships
 * pseudo-regions the API rejects, and the versions differ per browser. One
 * authority means the picker can never offer a value the API refuses.
 */
export async function fetchCountries(
  signal?: AbortSignal,
): Promise<CountryDto[]> {
  return api.get<CountryDto[]>("/countries", { signal })
}
