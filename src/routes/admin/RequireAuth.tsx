import type { ReactNode } from 'react'
import { Navigate, useLocation } from 'react-router'
import { useIsAuthenticated } from '@/stores/useAuthStore'

/**
 * Route guard for the admin branch.
 *
 * Sends unauthenticated visitors to the login page carrying the path they were
 * trying to reach, so signing in returns them there instead of dropping them on
 * the dashboard index.
 *
 * This is a navigation guard, not a security boundary — everything it protects
 * still ships to the browser. Real enforcement arrives with the API in Phase 6.
 */
export default function RequireAuth({ children }: { children: ReactNode }) {
  const isAuthenticated = useIsAuthenticated()
  const location = useLocation()

  if (!isAuthenticated) {
    const next = `${location.pathname}${location.search}`
    return <Navigate to={`/admin/login?next=${encodeURIComponent(next)}`} replace />
  }

  return <>{children}</>
}
