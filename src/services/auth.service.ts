import type { LoginResult, Session } from '@/types/auth'

/**
 * Authentication service.
 *
 * The signature is the one the real endpoint will satisfy
 * (`POST /api/v1/admin/auth/login`), so Phase 8 replaces the body of `login`
 * and nothing else changes.
 *
 * This is NOT security. Credentials checked in the browser are visible to
 * anyone who opens devtools — this only makes the structure correct so that a
 * real backend drops in cleanly. Phase 6 moves the check server-side.
 */

/** DEV ONLY — seeded credentials for the prototype. Removed in Phase 6. */
const DEV_CREDENTIALS = {
  email: 'admin@rozgar.pk',
  password: 'admin123',
} as const

/** Matches the artificial latency the sign-in form was already simulating. */
const MOCK_LATENCY_MS = 1200

const SESSION_TTL_MS = 1000 * 60 * 60 * 8

export async function login(email: string, password: string): Promise<LoginResult> {
  await new Promise(resolve => setTimeout(resolve, MOCK_LATENCY_MS))

  if (email !== DEV_CREDENTIALS.email || password !== DEV_CREDENTIALS.password) {
    // Wording preserved verbatim from the prototype. Phase 6 removes the
    // credentials from this string — echoing a password back is a real leak.
    return { ok: false, error: `Invalid email or password. Try ${DEV_CREDENTIALS.email} / ${DEV_CREDENTIALS.password}` }
  }

  const session: Session = {
    token: `mock.${btoa(email)}.${Date.now()}`,
    user: { id: 'admin-1', email, role: 'admin' },
    expiresAt: Date.now() + SESSION_TTL_MS,
  }
  return { ok: true, session }
}
