/**
 * Authentication types, matching what the API actually returns.
 *
 * The access token is deliberately absent from `AdminUser`: it is held in
 * memory by the auth store and never persisted, so it does not belong in a
 * shape that describes a person.
 */

/** Roles seeded by the backend. Custom roles resolve to their key as a string. */
export const SYSTEM_ROLES = ['super_admin', 'admin', 'editor', 'analyst'] as const
export type SystemRole = (typeof SYSTEM_ROLES)[number]
/** A role key. Not narrowed to `SystemRole` — the backend supports custom roles. */
export type RoleKey = SystemRole | (string & {})

export interface AdminUser {
  id: string
  email: string
  full_name: string
  role: RoleKey
  /**
   * Resolved permission keys, e.g. `JOB_PUBLISH`. The UI gates on these rather
   * than on `role`, so adding a fifth role needs no frontend change.
   */
  permissions: string[]
}

/** `POST /auth/login`. The refresh token is not here — it is an httpOnly cookie. */
export interface LoginResponse {
  access_token: string
  expires_in: number
  expires_at: string
  admin: AdminUser
}

/** `POST /auth/refresh`. Carries no admin payload; the session already knows. */
export interface TokenResponse {
  access_token: string
  expires_in: number
  expires_at: string
}

/**
 * Where the app is in resolving who the visitor is.
 *
 * `unknown` matters: on a reload the access token is gone (it was never
 * persisted) and only the refresh cookie remains, so the app must attempt a
 * silent refresh before it can say "signed out". Without this state every
 * reload of an admin page flashes the login screen.
 */
export type AuthStatus = 'unknown' | 'authenticated' | 'anonymous'
