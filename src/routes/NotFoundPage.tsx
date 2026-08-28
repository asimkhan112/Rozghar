import { Link } from 'react-router'
import Navbar from '@/components/Navbar'
import { color, linkReset, radius, size, weight } from '@/design-system'
import { IconBadge } from '@/components/Icon'
import SiteFooter from '@/components/SiteFooter'
import { usePageMeta } from '@/lib/seo'
import { NOT_FOUND_META } from '@/lib/pageMeta'

/**
 * 404 surface.
 *
 * Built from the same empty-state vocabulary the jobs list already uses —
 * centred stack, emoji mark, heading, supporting copy, primary action — so it
 * introduces no new visual language.
 */
export default function NotFoundPage() {
  usePageMeta(NOT_FOUND_META)

  return (
    <div style={{ minHeight: '100vh', background: color.surface.canvas }}>
      <Navbar />
      <div style={{ maxWidth: 900, margin: '0 auto', padding: '40px 24px 80px' }}>
        <div style={{ textAlign: 'center', padding: '80px 24px', background: color.surface.base, border: `1px solid ${color.border.base}`, borderRadius: radius['5xl'] }}>
          <div style={{ display: 'flex', justifyContent: 'center', marginBottom: 16 }}>
            <IconBadge name='compass' size='xl' />
          </div>
          <h1 style={{ fontSize: size['3xl'], fontWeight: weight.bold, color: color.text.primary, margin: '0 0 8px' }}>Page not found</h1>
          <p style={{ fontSize: size.md, color: color.text.secondary, margin: '0 0 24px', maxWidth: 360, marginInline: 'auto' }}>
            This page may have moved, or the job listing has expired and been removed.
          </p>
          <div style={{ display: 'flex', gap: 8, justifyContent: 'center', flexWrap: 'wrap' }}>
            <Link
              to="/jobs"
              style={{ ...linkReset, display: 'inline-block', padding: '10px 24px', background: color.brand.base, border: 'none', borderRadius: radius.xl, color: color.surface.base, fontSize: size.base, fontWeight: weight.medium, cursor: 'pointer' }}
            >
              Browse Jobs
            </Link>
            <Link
              to="/"
              style={{ ...linkReset, display: 'inline-block', padding: '10px 24px', background: color.surface.base, border: `1px solid ${color.border.base}`, borderRadius: radius.xl, color: color.text.primary, fontSize: size.base, fontWeight: weight.medium, cursor: 'pointer' }}
            >
              Back to Home
            </Link>
          </div>
        </div>
      </div>
      <SiteFooter />
    </div>
  )
}
