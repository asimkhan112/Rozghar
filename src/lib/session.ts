/**
 * Anonymous session identifier.
 *
 * Analytics events and search telemetry both carry one, which is what lets the
 * backend answer "did this visitor search, then view, then apply?" — a funnel
 * that per-event rows alone cannot reconstruct.
 *
 * It identifies a browser, not a person: no account is required and none
 * exists. It rotates whenever storage is cleared, which is the intended
 * privacy property rather than a limitation.
 */

import { safeStorage, storageKey } from '@/lib/storage'

const KEY = storageKey('session-id')

function generate(): string {
  // `randomUUID` is unavailable on http:// origins other than localhost, which
  // includes any staging box reached by IP. The fallback keeps telemetry
  // working there rather than throwing on first paint.
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID()
  }
  const bytes = new Uint8Array(16)
  crypto.getRandomValues(bytes)
  // RFC 4122 version 4 layout.
  bytes[6] = (bytes[6] & 0x0f) | 0x40
  bytes[8] = (bytes[8] & 0x3f) | 0x80
  const hex = [...bytes].map(b => b.toString(16).padStart(2, '0')).join('')
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`
}

let cached: string | null = null

/** The current session id, created on first use and reused for the visit. */
export function getSessionId(): string {
  if (cached) return cached
  const stored = safeStorage.getItem(KEY)
  if (stored) {
    cached = stored
    return stored
  }
  const created = generate()
  safeStorage.setItem(KEY, created)
  cached = created
  return created
}
