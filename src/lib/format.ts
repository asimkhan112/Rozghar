/** Display formatting helpers. Pure functions, no React. */

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

/** Placeholder rendered wherever a date is absent. */
export const EMPTY_DATE = '—'

/** `2026-08-13` -> `13 Aug 2026`. Returns an em dash for null/invalid input. */
export function formatDate(iso: string | null | undefined): string {
  if (!iso) return EMPTY_DATE
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(iso)
  if (!match) return EMPTY_DATE
  const [, year, month, day] = match
  const monthName = MONTHS[Number(month) - 1]
  if (!monthName) return EMPTY_DATE
  return `${Number(day)} ${monthName} ${year}`
}

/**
 * Reduces a full location to its city label for dense table cells:
 * `Lahore, Pakistan` -> `Lahore`, `Remote – Worldwide` -> `Remote`.
 */
export function cityLabel(location: string): string {
  return location.split(/[,–—-]/)[0]?.trim() ?? location
}

/** Thousands separators for counter values. */
export function formatCount(value: number): string {
  return value.toLocaleString('en-US')
}
