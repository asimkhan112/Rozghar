/**
 * Safe localStorage access.
 *
 * Storage can be unavailable (Safari private mode, disabled cookies), full
 * (quota exceeded), or hold data written by an older build. None of those are
 * worth crashing a render over, so every operation is guarded and failures
 * degrade to "no persistence" rather than throwing.
 *
 * Exposed as a `StateStorage`-shaped object so Zustand's `persist` middleware
 * can use it directly, which keeps versioning and migration in one place.
 */

const NAMESPACE = 'plenilo'

/** Namespaced key for a store. Keeps all our entries greppable in devtools. */
export function storageKey(name: string): string {
  return `${NAMESPACE}.${name}`
}

/** Feature-detects storage rather than assuming it exists. */
function probe(): boolean {
  try {
    const key = `${NAMESPACE}.__probe__`
    window.localStorage.setItem(key, '1')
    window.localStorage.removeItem(key)
    return true
  } catch {
    return false
  }
}

/** True when persistence actually works in this browser session. */
export const isStorageAvailable = typeof window !== 'undefined' && probe()

export const safeStorage = {
  getItem(name: string): string | null {
    if (!isStorageAvailable) return null
    try {
      return window.localStorage.getItem(name)
    } catch {
      return null
    }
  },

  setItem(name: string, value: string): void {
    if (!isStorageAvailable) return
    try {
      window.localStorage.setItem(name, value)
    } catch {
      // Quota exceeded. Non-fatal by design — the session keeps working,
      // it just will not survive a reload.
    }
  },

  removeItem(name: string): void {
    if (!isStorageAvailable) return
    try {
      window.localStorage.removeItem(name)
    } catch {
      // nothing useful to do here
    }
  },
}
