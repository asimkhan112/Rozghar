import { api } from "../http"

/** One row in a suggestion group. */
export interface SuggestionItem {
  text: string
  /** Where selecting it navigates. Null for skills, which are a query rather
   *  than a destination. */
  slug: string | null
  /** Listings behind the suggestion. */
  count: number
}

/** The public groups. Always all five, empty rather than absent. */
export interface Suggestions {
  jobs: SuggestionItem[]
  companies: SuggestionItem[]
  skills: SuggestionItem[]
  locations: SuggestionItem[]
  categories: SuggestionItem[]
}

/** Admin adds sources, and its job group includes drafts. */
export interface AdminSuggestions extends Suggestions {
  sources: SuggestionItem[]
}

export const EMPTY_SUGGESTIONS: AdminSuggestions = {
  jobs: [], companies: [], skills: [], locations: [], categories: [], sources: [],
}

export function fetchSuggestions(q: string, signal?: AbortSignal): Promise<Suggestions> {
  return api.get<Suggestions>("/search/suggest", { params: { q }, signal })
}

export function fetchAdminSuggestions(
  q: string,
  signal?: AbortSignal,
): Promise<AdminSuggestions> {
  return api.get<AdminSuggestions>("/admin/search/suggest", { params: { q }, signal })
}
