import { Link } from 'react-router'
import Navbar from '@/components/Navbar'
import { CATEGORIES } from '@/data/categories.mock'
import { getAllJobs } from '@/data/queries'
import { color, linkReset, radius, size, tracking, weight } from '@/design-system'

/**
 * Category index.
 *
 * Reuses the homepage category tile exactly — same border, radius, padding,
 * icon size and hover treatment — so the page introduces no new visual
 * language. Each tile links into the jobs list with the category pre-applied.
 */
export default function CategoriesPage() {
  const jobs = getAllJobs()
  const liveCount = (name: string) => jobs.filter(job => job.category === name).length

  return (
    <div style={{ minHeight: '100vh', background: color.surface.canvas }}>
      <Navbar />
      <div style={{ maxWidth: 1200, margin: '0 auto', padding: '40px 24px 80px' }}>
        <div style={{ marginBottom: 32 }}>
          <h1 style={{ fontSize: size['5xl'], fontWeight: weight.bold, color: color.text.primary, margin: '0 0 6px', letterSpacing: tracking.tight }}>Browse by Category</h1>
          <p style={{ fontSize: size.base, color: color.text.secondary, margin: 0 }}>
            {CATEGORIES.length} categories across technology, government, finance and more
          </p>
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))', gap: 12 }}>
          {CATEGORIES.map(cat => (
            <Link
              key={cat.name}
              to={`/jobs?category=${encodeURIComponent(cat.name)}`}
              style={{
                ...linkReset,
                background: color.surface.base, border: `1px solid ${color.border.base}`, borderRadius: radius['3xl'],
                padding: '20px 24px', cursor: 'pointer', textAlign: 'left',
                transition: 'all 0.15s', display: 'flex', alignItems: 'center', gap: 14,
              }}
              onMouseEnter={e => {
                e.currentTarget.style.borderColor = color.brand.alpha40
                e.currentTarget.style.background = color.brand.tint
              }}
              onMouseLeave={e => {
                e.currentTarget.style.borderColor = color.border.base
                e.currentTarget.style.background = color.surface.base
              }}
            >
              <span style={{ fontSize: size['5xl'], flexShrink: 0 }}>{cat.icon}</span>
              <div style={{ minWidth: 0 }}>
                <div style={{ fontSize: size.md, fontWeight: weight.semibold, color: color.text.primary, marginBottom: 3 }}>{cat.name}</div>
                <div style={{ fontSize: size.xs, color: color.text.muted }}>
                  {cat.count.toLocaleString()} jobs
                  {liveCount(cat.name) > 0 && (
                    <span style={{ color: color.brand.base, fontWeight: weight.medium }}> · {liveCount(cat.name)} live now</span>
                  )}
                </div>
              </div>
            </Link>
          ))}
        </div>
      </div>
    </div>
  )
}
