import { useSearchParams } from "react-router"

/**
 * Job list filter state, backed by the URL.
 *
 * Filters live in search params rather than component state so a result set is
 * shareable, bookmarkable, and survives the back button.
 *
 * The values here are the labels a person reads — "On-site", "This week" —
 * which is what keeps existing links working and the controls unchanged.
 * Translation to the API's enums and slugs happens in `lib/api/filters.ts`;
 * this hook deliberately knows nothing about the wire format.
 *
 * Filtering itself is the server's job. The client used to hold every listing
 * in memory and filter it locally, which cannot survive a catalogue that does
 * not fit in a browser tab.
 */

export const ALL_LOCATIONS = "All Locations"
export const ALL_CATEGORIES = "All Categories"
export const ALL_TYPES = "All Types"
export const ALL_EMPLOYMENT = "All Employment"
export const ANY_EXPERIENCE = "Any Experience"
export const ANY_TIME = "Any time"
export const SORT_RECENT = "Most Recent"

/**
 * Fallbacks, used only until the taxonomy query resolves — and if it fails.
 * A select with no options reads as a broken control, so the first paint gets
 * a plausible list rather than an empty one. The live values replace these.
 */
export const LOCATIONS = [
  ALL_LOCATIONS,
  "Lahore",
  "Karachi",
  "Islamabad",
  "Remote",
]
export const CATEGORIES_LIST = [
  ALL_CATEGORIES,
  "IT & Technology",
  "Design",
  "Finance & Accounting",
  "Marketing",
  "Human Resources",
  "Government",
  "Data & Analytics",
  "Content & Writing",
]
export const WORK_TYPES = [ALL_TYPES, "Remote", "Hybrid", "On-site"]
export const EMPLOYMENT_TYPES_LIST = [
  ALL_EMPLOYMENT,
  "Full-time",
  "Part-time",
  "Contract",
  "Internship",
]
export const EXP_LEVELS = [
  ANY_EXPERIENCE,
  "Fresh / Intern",
  "1–3 years",
  "3–5 years",
  "5+ years",
]
export const DATE_FILTERS = [ANY_TIME, "Today", "This week", "This month"]
export const SORT_OPTIONS = [
  SORT_RECENT,
  "Most Relevant",
  "Salary: High to Low",
  "Salary: Low to High",
]

export interface JobFilters {
  q: string
  location: string
  category: string
  workType: string
  employmentType: string
  experience: string
  datePosted: string
  sort: string
}

export function useJobFilters() {
  const [params, setParams] = useSearchParams()

  const filters: JobFilters = {
    q: params.get("q") ?? "",
    location: params.get("location") ?? ALL_LOCATIONS,
    category: params.get("category") ?? ALL_CATEGORIES,
    workType: params.get("workType") ?? ALL_TYPES,
    employmentType: params.get("employmentType") ?? ALL_EMPLOYMENT,
    experience: params.get("experience") ?? ANY_EXPERIENCE,
    datePosted: params.get("datePosted") ?? ANY_TIME,
    sort: params.get("sort") ?? SORT_RECENT,
  }

  const page = Math.max(1, Number(params.get("page") ?? "1") || 1)

  const defaults: Record<keyof JobFilters, string> = {
    q: "",
    location: ALL_LOCATIONS,
    category: ALL_CATEGORIES,
    workType: ALL_TYPES,
    employmentType: ALL_EMPLOYMENT,
    experience: ANY_EXPERIENCE,
    datePosted: ANY_TIME,
    sort: SORT_RECENT,
  }

  /** Writes one filter and resets pagination, dropping default values. */
  function setFilter(key: keyof JobFilters, value: string) {
    setParams(
      (prev) => {
        const next = new URLSearchParams(prev)
        if (!value || value === defaults[key]) next.delete(key)
        else next.set(key, value)
        next.delete("page")
        return next
      },
      { replace: true },
    )
  }

  function setPage(next: number) {
    setParams(
      (prev) => {
        const p = new URLSearchParams(prev)
        if (next <= 1) p.delete("page")
        else p.set("page", String(next))
        return p
      },
      { replace: true },
    )
  }

  function reset(keys?: (keyof JobFilters)[]) {
    setParams(
      (prev) => {
        const next = new URLSearchParams(prev)
        for (const key of keys ?? Object.keys(defaults) as (keyof JobFilters)[])
          next.delete(key)
        next.delete("page")
        return next
      },
      { replace: true },
    )
  }

  const hasAdvancedFilters =
    filters.workType !== ALL_TYPES ||
    filters.employmentType !== ALL_EMPLOYMENT ||
    filters.category !== ALL_CATEGORIES ||
    filters.experience !== ANY_EXPERIENCE ||
    filters.datePosted !== ANY_TIME

  return { filters, page, setFilter, setPage, reset, hasAdvancedFilters }
}
