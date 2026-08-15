/**
 * Authentication API calls.
 *
 * Every call here is `anonymous: true` — they must not carry an access token
 * and must never trigger the HTTP layer's 401-refresh path, which would
 * recurse through `refresh` while `refresh` is what is failing.
 */

import { api } from '@/lib/http'
import type { AdminUser, LoginResponse, TokenResponse } from '@/types/auth'

export function login(email: string, password: string): Promise<LoginResponse> {
  return api.post<LoginResponse>('/auth/login', { email, password }, { anonymous: true })
}

/**
 * Rotates the refresh cookie and mints a new access token.
 *
 * Takes no arguments: the cookie is httpOnly, so JavaScript cannot read or
 * send it explicitly — the browser attaches it because the request is
 * same-origin and the cookie's path matches.
 */
export function refresh(): Promise<TokenResponse> {
  return api.post<TokenResponse>('/auth/refresh', undefined, { anonymous: true })
}

/** Idempotent server-side. Revokes the session and clears the cookie. */
export function logout(): Promise<void> {
  return api.post<void>('/auth/logout', undefined, { anonymous: true })
}

/** The signed-in admin and their resolved permissions. Requires a live token. */
export function me(): Promise<AdminUser> {
  return api.get<AdminUser>('/auth/me')
}
