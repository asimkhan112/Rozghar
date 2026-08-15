export const ADMIN_ROLES = ['admin', 'editor'] as const
export type AdminRole = (typeof ADMIN_ROLES)[number]

export interface AdminUser {
  id: string
  email: string
  role: AdminRole
}

/**
 * An authenticated admin session.
 *
 * Shaped to match what the FastAPI login endpoint will return in Phase 8, so
 * swapping the mock for a real JWT changes only `auth.service.ts`. `expiresAt`
 * is an epoch millisecond timestamp — a session that cannot lapse is not a
 * session.
 */
export interface Session {
  token: string
  user: AdminUser
  expiresAt: number
}

export interface LoginResult {
  ok: boolean
  session?: Session
  error?: string
}
