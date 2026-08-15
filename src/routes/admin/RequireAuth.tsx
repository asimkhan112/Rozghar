import type { ReactNode } from 'react'
import { Navigate, useLocation } from 'react-router'
import { color, size } from '@/design-system'
import { useAuthStatus } from '@/stores/useAuthStore'

/**
 * Route guard for the admin branch.
 *
 * Three states, not two. The access token is held in memory only, so after a
 * reload the app genuinely does not know who the visitor is until the silent
 * refresh finishes. Treating that moment as "signed out" would bounce every
 * refresh of an admin page to the login screen and back — the flash of login
 * that makes an app feel broken.
 *
 * This is a navigation guard, not a security boundary: everything it protects
 * still ships to the browser. The API enforces the real thing on every request.
 */
export default function RequireAuth({ children }: { children: ReactNode }) {
  const status = useAuthStatus()
  const location = useLocation()

  if (status === 'unknown') {
    return (
      <div
        style={{
          minHeight: '100vh',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          background: color.surface.canvas,
          color: color.text.muted,
          fontSize: size.sm,
        }}
      >
        Checking your session…
      </div>
    )
  }

  if (status === 'anonymous') {
    const next = `${location.pathname}${location.search}`
    return <Navigate to={`/admin/login?next=${encodeURIComponent(next)}`} replace />
  }

  return <>{children}</>
}
