import { create } from 'zustand'
import { installAuthHooks } from '@/lib/http'
import * as authApi from '@/services/auth.service'
import type { AdminUser, AuthStatus } from '@/types/auth'

/**
 * Admin session state.
 *
 * **Nothing here is persisted.** The access token lives in memory for the life
 * of the tab and is deliberately not written to `localStorage`: anything
 * readable by JavaScript is readable by injected JavaScript, and the whole
 * point of keeping the refresh token in an httpOnly cookie is defeated if its
 * short-lived counterpart is sitting in storage next to it.
 *
 * Durability comes from the cookie instead. On a reload the token is gone and
 * `bootstrap()` exchanges the cookie for a new one — which is why `status`
 * starts as `unknown` rather than `anonymous`.
 */

interface AuthState {
  status: AuthStatus
  user: AdminUser | null
  accessToken: string | null

  bootstrap: () => Promise<void>
  signIn: (email: string, password: string) => Promise<void>
  signOut: () => Promise<void>
  refresh: () => Promise<string | null>
}

/**
 * The in-flight refresh, if any.
 *
 * Module-level rather than in the store because it is machinery, not state:
 * nothing renders from it. Sharing one promise across concurrent callers is
 * the point — the backend treats a second rotation of an already-rotated token
 * as theft and revokes **every session in the family**. Five parallel 401s
 * must produce one rotation, not five.
 */
let inFlightRefresh: Promise<string | null> | null = null

export const useAuthStore = create<AuthState>()((set, get) => ({
  status: 'unknown',
  user: null,
  accessToken: null,

  async bootstrap() {
    // Called once at startup. A failure here is the normal path for a visitor
    // who is simply not signed in, so it resolves to anonymous rather than
    // throwing.
    const token = await get().refresh()
    if (!token) set({ status: 'anonymous', user: null, accessToken: null })
  },

  async signIn(email, password) {
    const result = await authApi.login(email, password)
    set({
      status: 'authenticated',
      user: result.admin,
      accessToken: result.access_token,
    })
  },

  async signOut() {
    try {
      // Revokes the session server-side. Without this the refresh cookie stays
      // valid for thirty days and "sign out" is a lie told to one browser.
      await authApi.logout()
    } catch {
      // A failed logout must still clear local state — the user asked to
      // leave, and stranding them signed-in is the worse outcome.
    } finally {
      set({ status: 'anonymous', user: null, accessToken: null })
    }
  },

  async refresh() {
    if (inFlightRefresh) return inFlightRefresh

    inFlightRefresh = (async () => {
      try {
        const { access_token } = await authApi.refresh()
        set({ accessToken: access_token, status: 'authenticated' })

        // The refresh response carries no admin payload, so the permission set
        // is fetched separately when it is missing — after a reload it always
        // is. Permissions may also have changed while the tab was open.
        if (!get().user) {
          try {
            set({ user: await authApi.me() })
          } catch {
            // The token works but the profile call failed. Staying
            // authenticated with no user would render an admin console that
            // cannot decide what to show, so treat it as not signed in.
            set({ status: 'anonymous', user: null, accessToken: null })
            return null
          }
        }
        return access_token
      } catch {
        set({ status: 'anonymous', user: null, accessToken: null })
        return null
      } finally {
        inFlightRefresh = null
      }
    })()

    return inFlightRefresh
  },
}))

// Wires the store into the HTTP layer. Injected rather than imported by
// `http.ts` so the dependency runs one way only — a cycle between the two
// surfaces as "cannot access before initialisation" at module load.
installAuthHooks({
  getAccessToken: () => useAuthStore.getState().accessToken,
  refresh: () => useAuthStore.getState().refresh(),
  onAuthFailure: () => {
    useAuthStore.setState({ status: 'anonymous', user: null, accessToken: null })
  },
})

export const useAuthStatus = () => useAuthStore(state => state.status)
export const useCurrentAdmin = () => useAuthStore(state => state.user)
export const useIsAuthenticated = () => useAuthStore(state => state.status === 'authenticated')
export const useSignIn = () => useAuthStore(state => state.signIn)
export const useSignOut = () => useAuthStore(state => state.signOut)

/**
 * Permission check.
 *
 * Gates on capability rather than role, mirroring how the API decides. A
 * button the caller cannot use should not be rendered — the backend enforces
 * this regardless, so the only thing an ungated button achieves is a 403 the
 * user cannot act on.
 */
export const useHasPermission = (permission: string): boolean =>
  useAuthStore(state => state.user?.permissions.includes(permission) ?? false)

export const useHasAnyPermission = (...permissions: string[]): boolean =>
  useAuthStore(state =>
    permissions.some(permission => state.user?.permissions.includes(permission) ?? false),
  )
