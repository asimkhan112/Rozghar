/**
 * Reference data: categories and locations.
 *
 * Both are small, rarely change, and are needed by almost every page — which
 * is why the query layer caches them far longer than listings.
 */

import { api } from "@/lib/http"
import { toCategory, toLocation, type LocationOption } from "./adapters"
import type { CategoryDto, LocationDto } from "./types"
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
