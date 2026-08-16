import { useEffect, useMemo, useState } from "react"
import { useQuery } from "@tanstack/react-query"
import {
  type AdminSuggestions,
  EMPTY_SUGGESTIONS,
  fetchAdminSuggestions,
  fetchSuggestions,
} from "@/lib/api"
import { queryKeys } from "./keys"

/** Characters below which every listing matches and the dropdown is noise. */
export const MIN_QUERY_LENGTH = 2

/** Keystroke-to-request delay. Long enough that typing a word costs one
 *  request rather than eight, short enough to feel instant. */
export const DEBOUNCE_MS = 300

/**
 * Trails `value` by `delay`, resetting the timer on every change.
 *
 * The debounce lives here rather than inside the query hook so the input stays
 * fully controlled: the field updates on every keystroke and only the *fetch*
 * waits, which is what makes typing feel immediate while the network stays
 * quiet.
 */
export function useDebounced<T>(value: T, delay = DEBOUNCE_MS): T {
  const [settled, setSettled] = useState(value)
  useEffect(() => {
    const timer = setTimeout(() => setSettled(value), delay)
    return () => clearTimeout(timer)
  }, [value, delay])
  return settled
}

/**
 * Grouped suggestions for what is being typed.
 *
 * `placeholderData` keeps the previous groups on screen while the next request
 * is in flight. Without it the dropdown empties and re-fills on every settled
 * keystroke, which reads as flicker rather than as progress.
 */
export function useSuggest(raw: string, { admin = false } = {}) {
  const q = useDebounced(raw.trim())
  const enabled = q.length >= MIN_QUERY_LENGTH
  const query = useQuery({
    queryKey: queryKeys.suggest.query(admin ? "admin" : "public", q),
    queryFn: ({ signal }) =>
      admin ? fetchAdminSuggestions(q, signal) : fetchSuggestions(q, signal),
    enabled,
    placeholderData: previous => previous,
    // A vocabulary does not change between two keystrokes, and the server
    // already caches. This stops a re-opened dropdown from refetching.
    staleTime: 60_000,
    retry: false,
  })

  // Memoised on the response, not rebuilt per render. A fresh object literal
  // here would give every consumer a new identity on every render, and the
  // dropdown derives its keyboard cursor from that identity — an unstable
  // `groups` silently resets the highlighted row to the top on each render,
  // so the arrow keys appear to do nothing.
  const groups = useMemo<AdminSuggestions>(
    () => (enabled ? { ...EMPTY_SUGGESTIONS, ...(query.data ?? {}) } : EMPTY_SUGGESTIONS),
    [enabled, query.data],
  )

  return { ...query, q, enabled, groups }
}
