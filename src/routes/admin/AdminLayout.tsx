import { Link, NavLink, Outlet, useLocation, useNavigate } from 'react-router'
import { color, fontFamily, linkReset, radius, shadow, size, weight } from '@/design-system'
import { NAV_ITEMS } from '@/data/admin.mock'
import { useAdminSidebarOpen, useSetAdminSidebarOpen } from '@/stores/usePreferencesStore'
import { useSignOut } from '@/stores/useAuthStore'
import { useToastMessage } from '@/stores/useToastStore'

/** Section key -> URL segment. The dashboard is the index route. */
const SECTION_PATH: Record<string, string> = {
  dashboard: '',
  jobs: 'jobs',
  'add-job': 'add-job',
  reports: 'reports',
  analytics: 'analytics',
  categories: 'categories',
  locations: 'locations',
  sources: 'sources',
  settings: 'settings',
}

const ADMIN_ROOT = '/admin/dashboard'

/**
 * Admin shell.
 *
 * The nine sections used to be a `useState` switch inside a 994-line
 * component. They are child routes now, which makes every section
 * deep-linkable and independently lazy-loadable.
 */
export default function AdminLayout() {
  const sidebarOpen = useAdminSidebarOpen()
  const setSidebarOpen = useSetAdminSidebarOpen()
  const signOut = useSignOut()
  const navigate = useNavigate()
  const { pathname } = useLocation()
  const toast = useToastMessage()

  const current = NAV_ITEMS.find(item => {
    const path = SECTION_PATH[item.key]
    return path ? pathname === `${ADMIN_ROOT}/${path}` : pathname === ADMIN_ROOT
  })

  const handleSignOut = () => {
    signOut()
    navigate('/')
  }

  return (
    <div style={{ display: 'flex', height: '100vh', overflow: 'hidden', background: color.surface.canvas, fontFamily: fontFamily.sans }}>
      {/* Sidebar */}
      <aside style={{
        width: sidebarOpen ? 220 : 60, flexShrink: 0,
        background: color.surface.base, borderRight: `1px solid ${color.border.base}`,
        display: 'flex', flexDirection: 'column',
        transition: 'width 0.2s', overflow: 'hidden',
      }}>
        {/* Logo */}
        <div style={{ height: 60, borderBottom: `1px solid ${color.border.base}`, display: 'flex', alignItems: 'center', padding: '0 16px', gap: 10, flexShrink: 0 }}>
          <div style={{ width: 32, height: 32, background: color.brand.base, borderRadius: radius.xl, display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
            <span style={{ color: color.text.inverse, fontSize: size.sm, fontWeight: weight.bold }}>RZ</span>
          </div>
          {sidebarOpen && <span style={{ fontSize: size.base, fontWeight: weight.semibold, color: color.text.primary, whiteSpace: 'nowrap' }}>Rozgar Admin</span>}
        </div>

        {/* Nav */}
        <nav style={{ flex: 1, overflowY: 'auto', padding: '12px 8px' }}>
          {NAV_ITEMS.map(item => {
            const segment = SECTION_PATH[item.key]
            const to = segment ? `${ADMIN_ROOT}/${segment}` : ADMIN_ROOT
            return (
              <NavLink
                key={item.key}
                to={to}
                end={segment === ''}
                title={!sidebarOpen ? item.label : undefined}
                style={({ isActive }) => ({
                  ...linkReset,
                  display: 'flex', alignItems: 'center', gap: 10,
                  width: '100%', padding: '9px 10px', borderRadius: radius.xl,
                  background: isActive ? color.brand.tint : 'none',
                  border: 'none', cursor: 'pointer',
                  color: isActive ? color.brand.base : color.text.secondary,
                  marginBottom: 2, transition: 'all 0.1s',
                  whiteSpace: 'nowrap', overflow: 'hidden',
                })}
              >
                {({ isActive }) => (
                  <>
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" style={{ flexShrink: 0 }}>
                      <path d={item.icon} />
                    </svg>
                    {sidebarOpen && <span style={{ fontSize: size.sm, fontWeight: isActive ? weight.semibold : weight.regular }}>{item.label}</span>}
                    {isActive && sidebarOpen && <span style={{ marginLeft: 'auto', width: 6, height: 6, borderRadius: radius.full, background: color.brand.base, flexShrink: 0 }} />}
                  </>
                )}
              </NavLink>
            )
          })}
        </nav>

        {/* Bottom */}
        <div style={{ borderTop: `1px solid ${color.border.base}`, padding: 8, flexShrink: 0 }}>
          <button
            onClick={handleSignOut}
            style={{ display: 'flex', alignItems: 'center', gap: 10, width: '100%', padding: '9px 10px', borderRadius: radius.xl, background: 'none', border: 'none', cursor: 'pointer', color: color.text.secondary, whiteSpace: 'nowrap' }}
            onMouseEnter={e => e.currentTarget.style.background = color.danger.tint}
            onMouseLeave={e => e.currentTarget.style.background = 'none'}
          >
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" style={{ flexShrink: 0 }}>
              <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4M16 17l5-5-5-5M21 12H9"/>
            </svg>
            {sidebarOpen && <span style={{ fontSize: size.sm }}>Sign Out</span>}
          </button>
        </div>
      </aside>

      {/* Main area */}
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
        {/* Topbar */}
        <header style={{ height: 60, background: color.surface.base, borderBottom: `1px solid ${color.border.base}`, display: 'flex', alignItems: 'center', padding: '0 24px', gap: 16, flexShrink: 0 }}>
          <button
            onClick={() => setSidebarOpen(!sidebarOpen)}
            style={{ background: 'none', border: 'none', cursor: 'pointer', color: color.text.secondary, padding: 4 }}
          >
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <line x1="3" y1="12" x2="21" y2="12"/><line x1="3" y1="6" x2="21" y2="6"/><line x1="3" y1="18" x2="21" y2="18"/>
            </svg>
          </button>
          <div style={{ fontSize: size.md, fontWeight: weight.semibold, color: color.text.primary }}>
            {current?.label}
          </div>
          <div style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: 12 }}>
            <Link
              to="/"
              style={{ ...linkReset, fontSize: size.sm, color: color.text.secondary, background: 'none', border: `1px solid ${color.border.base}`, borderRadius: radius.lg, padding: '5px 12px', cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 6 }}
            >
              <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/><polyline points="15 3 21 3 21 9"/><line x1="10" y1="14" x2="21" y2="3"/></svg>
              View Site
            </Link>
            <div style={{ width: 32, height: 32, background: color.brand.base, borderRadius: radius.xl, display: 'flex', alignItems: 'center', justifyContent: 'center', color: color.text.inverse, fontSize: size.sm, fontWeight: weight.bold }}>A</div>
          </div>
        </header>

        {/* Content */}
        <main style={{ flex: 1, overflowY: 'auto', padding: '28px 28px 60px' }}>
          <Outlet />
        </main>
      </div>

      {/* Toast */}
      {toast && (
        <div style={{
          position: 'fixed', bottom: 28, left: '50%', transform: 'translateX(-50%)',
          background: color.text.primary, color: color.text.inverse, borderRadius: radius['2xl'], padding: '12px 20px',
          fontSize: size.base, fontWeight: weight.medium, zIndex: 999, boxShadow: shadow.toast,
          display: 'flex', alignItems: 'center', gap: 10, animation: 'slideUp 0.2s ease',
        }}>
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke={color.success.base} strokeWidth="2.5"><polyline points="20 6 9 17 4 12"/></svg>
          {toast}
        </div>
      )}

      <style>{`@keyframes slideUp { from { opacity:0; transform:translateX(-50%) translateY(12px); } to { opacity:1; transform:translateX(-50%) translateY(0); } }`}</style>
    </div>
  )
}
