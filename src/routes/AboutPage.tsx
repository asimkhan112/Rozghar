import { Link } from 'react-router'
import Navbar from '@/components/Navbar'
import { color, linkReset, radius, size, tracking, weight } from '@/design-system'
import { IconBadge } from '@/components/Icon'
import SiteFooter from '@/components/SiteFooter'
import { usePageMeta } from '@/lib/seo'
import { STATIC_PAGE_META } from '@/lib/pageMeta'

/** Trust claims already made on the homepage, restated as the about copy. */
const PRINCIPLES = [
  { icon: 'zap', label: 'Updated Daily', body: 'Listings are refreshed every 24 hours. Expired postings are removed rather than left to rot.' },
  { icon: 'shield', label: 'Verified Sources', body: 'Jobs come from company career pages and trusted boards, and every listing links back to its source.' },
  { icon: 'external', label: 'Direct Apply', body: 'Applications go straight to the employer. We never sit between you and the hiring team.' },
  { icon: 'lock', label: 'No Registration', body: 'Browse and apply without an account. Saved jobs stay on your device, not on our servers.' },
] as const

export default function AboutPage() {
  usePageMeta(STATIC_PAGE_META['/about'])

  return (
    <div style={{ minHeight: '100vh', background: color.surface.canvas, display: 'flex', flexDirection: 'column' }}>
      <Navbar />
      <div style={{ maxWidth: 720, width: '100%', margin: '0 auto', padding: '40px 24px 80px' }}>
        <div style={{ marginBottom: 32 }}>
          <h1 style={{ fontSize: size['5xl'], fontWeight: weight.bold, color: color.text.primary, margin: '0 0 6px', letterSpacing: tracking.tight }}>About Plenilo.com</h1>
          <p style={{ fontSize: size.base, color: color.text.secondary, margin: 0 }}>
            Curated jobs from top employers around the world.
          </p>
        </div>

        <div style={{ background: color.surface.base, border: `1px solid ${color.border.base}`, borderRadius: radius['5xl'], padding: '28px 32px', marginBottom: 20 }}>
          <p style={{ fontSize: size.md, color: color.text.strong, lineHeight: 1.7, margin: '0 0 14px' }}>
            Job hunting means checking a dozen portals, most of them full of listings that
            closed months ago. Plenilo.com exists to make that a single, honest search.
          </p>
          <p style={{ fontSize: size.md, color: color.text.strong, lineHeight: 1.7, margin: 0 }}>
            We aggregate openings from company career pages, established job boards, university portals
            and government commissions, then check that each one is still open before it goes live.
          </p>
        </div>

        <div style={{ display: 'flex', flexDirection: 'column', gap: 12, marginBottom: 32 }}>
          {PRINCIPLES.map(item => (
            <div key={item.label} style={{ background: color.surface.base, border: `1px solid ${color.border.base}`, borderRadius: radius['3xl'], padding: '18px 22px', display: 'flex', gap: 14, alignItems: 'flex-start' }}>
              <IconBadge name={item.icon} size='sm' />
              <div>
                <div style={{ fontSize: size.base, fontWeight: weight.semibold, color: color.text.primary, marginBottom: 3 }}>{item.label}</div>
                <div style={{ fontSize: size.sm, color: color.text.secondary, lineHeight: 1.6 }}>{item.body}</div>
              </div>
            </div>
          ))}
        </div>

        <div style={{ background: color.brand.tint, border: `1px solid ${color.brand.alpha30}`, borderRadius: radius['3xl'], padding: '24px 28px', textAlign: 'center' }}>
          <h2 style={{ fontSize: size['2xl'], fontWeight: weight.bold, color: color.text.primary, margin: '0 0 6px' }}>Found a problem with a listing?</h2>
          <p style={{ fontSize: size.sm, color: color.text.secondary, margin: '0 0 18px' }}>
            Broken links and expired posts get fixed fastest when readers tell us.
          </p>
          <Link
            to="/contact"
            style={{ ...linkReset, display: 'inline-block', padding: '10px 24px', background: color.brand.base, border: 'none', borderRadius: radius.xl, color: color.surface.base, fontSize: size.base, fontWeight: weight.medium, cursor: 'pointer' }}
          >
            Get in touch
          </Link>
        </div>
      </div>
      <SiteFooter />
    </div>
  )
}
