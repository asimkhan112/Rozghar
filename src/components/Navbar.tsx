import { Link, useLocation } from 'react-router'
import { color, countPill, linkReset, radius, size, tracking, weight } from '@/design-system'
import { useSavedCount } from '@/stores/useSavedJobsStore'
import BrandMark from '@/components/BrandMark'

/**
 * Site header.
 *
 * Every destination is a real `<a href>` so listings are crawlable and every
 * nav target supports middle-click and link preview. The saved count comes
 * from the store via a selector, so adding a bookmark re-renders this badge
 * without re-rendering the page beneath it.
 */
export default function Navbar() {
  const savedCount = useSavedCount()
  const { pathname, search } = useLocation()

  // Each item is a distinct destination. They all pointed at a bare /jobs
  // before filters lived in the URL, which is why all three used to highlight
  // at once — there was nothing to tell them apart.
  const navItems = [
    { label: 'Browse Jobs', to: '/jobs' },
    { label: 'Remote', to: '/jobs?workType=Remote' },
    { label: 'Internships', to: '/jobs?employmentType=Internship' },
  ]

  const current = `${pathname}${search}`
  // "Browse Jobs" covers the jobs list generally, but yields to a sibling when
  // that sibling's exact filter is the one applied.
  const isActive = (to: string) =>
    to === '/jobs'
      ? pathname === '/jobs' && !navItems.some(item => item.to !== '/jobs' && item.to === current)
      : current === to

  return (
    <header style={{ background: color.surface.base, borderBottom: `1px solid ${color.border.base}`, position: 'sticky', top: 0, zIndex: 100 }}>
      <div style={{ maxWidth: 1200, margin: '0 auto', padding: '0 24px', height: 60, display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        {/* Logo */}
        <Link
          to="/"
          style={{ ...linkReset, display: 'flex', alignItems: 'center', gap: 8, background: 'none', border: 'none', cursor: 'pointer', padding: 0 }}
        >
          <BrandMark size={32} />
          <span style={{ fontSize: size.lg, fontWeight: weight.semibold, color: color.text.primary, letterSpacing: tracking.tight }}>Plenilo.com</span>
        </Link>

        {/* Desktop Nav */}
        <nav style={{ display: 'flex', alignItems: 'center', gap: 4 }} className="desktop-nav">
          {navItems.map(item => (
            <Link
              key={item.label}
              to={item.to}
              style={{
                ...linkReset,
                background: 'none', border: 'none', cursor: 'pointer', padding: '6px 12px',
                fontSize: size.base, fontWeight: weight.medium, color: isActive(item.to) ? color.brand.base : color.text.secondary,
                borderRadius: radius.md, transition: 'color 0.15s',
              }}
            >
              {item.label}
            </Link>
          ))}
        </nav>

        {/* Right actions */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <Link
            to="/saved-jobs"
            style={{
              ...linkReset,
              position: 'relative', background: savedCount > 0 ? color.brand.tint : 'none',
              border: savedCount > 0 ? `1px solid ${color.brand.alpha30}` : `1px solid ${color.border.base}`,
              borderRadius: radius.xl, cursor: 'pointer', padding: '6px 12px',
              display: 'flex', alignItems: 'center', gap: 6,
              fontSize: size.base, fontWeight: weight.medium, color: savedCount > 0 ? color.brand.base : color.text.secondary,
            }}
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill={savedCount > 0 ? color.brand.base : 'none'} stroke="currentColor" strokeWidth="2">
              <path d="M19 21l-7-5-7 5V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2z" />
            </svg>
            <span className="hide-mobile">Saved</span>
            {savedCount > 0 && (
              <span style={countPill}>
                {savedCount}
              </span>
            )}
          </Link>
          <Link
            to="/admin/login"
            style={{
              ...linkReset,
              background: 'none', border: `1px solid ${color.border.base}`, borderRadius: radius.xl,
              cursor: 'pointer', padding: '6px 14px',
              fontSize: size.sm, fontWeight: weight.medium, color: color.text.secondary,
              display: 'flex', alignItems: 'center', gap: 6,
              transition: 'all 0.15s',
            }}
            onMouseEnter={e => { e.currentTarget.style.borderColor = color.brand.alpha40; e.currentTarget.style.color = color.brand.base }}
            onMouseLeave={e => { e.currentTarget.style.borderColor = color.border.base; e.currentTarget.style.color = color.text.secondary }}
            title="Admin Sign In"
          >
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/>
            </svg>
            <span className="hide-mobile">Admin</span>
          </Link>
        </div>
      </div>

      <style>{`
        @media (max-width: 640px) {
          .desktop-nav { display: none !important; }
          .hide-mobile { display: none; }
        }
      `}</style>
    </header>
  )
}
