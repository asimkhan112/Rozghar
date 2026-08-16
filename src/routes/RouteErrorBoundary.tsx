import { isRouteErrorResponse, useRouteError } from 'react-router'
import NotFoundPage from './NotFoundPage'
import { color, radius, size, weight } from '@/design-system'
import { IconBadge } from '@/components/Icon'

/**
 * Catches render and loader failures so a single broken component cannot blank
 * the whole application — which is what happened before routing, since there
 * was no boundary anywhere in the tree.
 */
export default function RouteErrorBoundary() {
  const error = useRouteError()

  if (isRouteErrorResponse(error) && error.status === 404) {
    return <NotFoundPage />
  }

  const detail = error instanceof Error ? error.message : String(error ?? 'Unknown error')

  return (
    <div style={{ minHeight: '100vh', background: color.surface.canvas, display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '40px 24px' }}>
      <div style={{ maxWidth: 480, textAlign: 'center', background: color.surface.base, border: `1px solid ${color.border.base}`, borderRadius: radius['5xl'], padding: '48px 32px' }}>
        <div style={{ display: 'flex', justifyContent: 'center', marginBottom: 16 }}>
          <IconBadge name='alert' size='xl' tone='danger' />
        </div>
        <h1 style={{ fontSize: size['3xl'], fontWeight: weight.bold, color: color.text.primary, margin: '0 0 8px' }}>Something went wrong</h1>
        <p style={{ fontSize: size.md, color: color.text.secondary, margin: '0 0 20px' }}>
          The page could not be displayed. Reloading usually fixes it.
        </p>
        <p style={{ fontSize: size.xs, color: color.text.muted, margin: '0 0 24px', fontFamily: 'monospace', wordBreak: 'break-word' }}>
          {detail}
        </p>
        <button
          onClick={() => window.location.reload()}
          style={{ padding: '10px 24px', background: color.brand.base, border: 'none', borderRadius: radius.xl, color: color.surface.base, fontSize: size.base, fontWeight: weight.medium, cursor: 'pointer' }}
        >
          Reload page
        </button>
      </div>
    </div>
  )
}
