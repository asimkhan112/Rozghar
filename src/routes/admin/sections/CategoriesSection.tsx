import { useState } from 'react'
import { actionTone, adminStatusTone, color, fontFamily, pillTone, radius, shadow, size, tracking, weight } from '@/design-system'
import { useCategories } from '@/hooks/queries'
import { describeError } from '@/lib/http'
import { ErrorPanel } from '@/components/QueryState'
import { FField, FormSection, FRow, IS, StatusPill } from '@/components/ui/AdminForm'
import { useToast } from '@/stores/useToastStore'

export default function CategoriesSection() {
  const { data, isPending, isError, error, refetch } = useCategories()
  const categories = data ?? []
  // Popularity as a share of the busiest category, so the bar means something
  // relative rather than being a number somebody typed.
  const busiest = Math.max(1, ...categories.map(c => c.count))
  const CATEGORIES_DATA = categories.map(c => ({
    name: c.name,
    count: c.count,
    // Every category the public endpoint returns is active — it filters
    // inactive ones out — so the pill reflects that rather than inventing a
    // second state the data cannot distinguish.
    status: 'Active',
    popularity: Math.round((c.count / busiest) * 100),
  }))

  const showToast = useToast()
  const [adding, setAdding] = useState(false)
  const [newCat, setNewCat] = useState('')

  if (isError) {
    return <ErrorPanel message={describeError(error)} onRetry={() => void refetch()} />
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
        <button onClick={() => setAdding(!adding)} style={{ padding: '8px 16px', background: color.brand.base, border: 'none', borderRadius: radius.xl, color: color.surface.base, fontSize: size.sm, fontWeight: weight.medium, cursor: 'pointer' }}>
          + Add Category
        </button>
      </div>
      {adding && (
        <div style={{ background: color.surface.base, border: `1px solid ${color.brand.alpha40}`, borderRadius: radius['3xl'], padding: '20px 24px', display: 'flex', gap: 12, alignItems: 'flex-end' }}>
          <FField label="Category Name" style={{ flex: 1 }}>
            <input value={newCat} onChange={e => setNewCat(e.target.value)} placeholder="e.g. Legal & Compliance" style={IS} />
          </FField>
          <button onClick={() => { if (newCat) { showToast(`Category "${newCat}" created`); setNewCat(''); setAdding(false) } }} style={{ padding: '10px 20px', background: color.brand.base, border: 'none', borderRadius: radius.xl, color: color.surface.base, fontSize: size.sm, fontWeight: weight.medium, cursor: 'pointer', flexShrink: 0 }}>
            Save
          </button>
          <button onClick={() => setAdding(false)} style={{ padding: '10px 16px', border: `1px solid ${color.border.base}`, borderRadius: radius.xl, background: color.surface.base, color: color.text.secondary, fontSize: size.sm, cursor: 'pointer', flexShrink: 0 }}>Cancel</button>
        </div>
      )}
      <div style={{ background: color.surface.base, border: `1px solid ${color.border.base}`, borderRadius: radius['3xl'], overflow: 'hidden' }}>
        <table style={{ width: '100%', borderCollapse: 'collapse' }}>
          <thead>
            <tr style={{ background: color.surface.subtle }}>
              {['Category', 'Job Count', 'Status', 'Popularity', 'Actions'].map(h => (
                <th key={h} style={{ padding: '10px 16px', textAlign: 'left', fontSize: size['2xs'], fontWeight: weight.semibold, color: color.text.muted, textTransform: 'uppercase', letterSpacing: tracking.wide }}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {CATEGORIES_DATA.map((c, i) => (
              <tr key={i} style={{ borderTop: `1px solid ${color.surface.muted}` }}
                onMouseEnter={e => (e.currentTarget.style.background = color.surface.hover)}
                onMouseLeave={e => (e.currentTarget.style.background = 'none')}
              >
                <td style={{ padding: '12px 16px', fontSize: size.sm, fontWeight: weight.semibold, color: color.text.primary }}>{c.name}</td>
                <td style={{ padding: '12px 16px', fontSize: size.sm, color: color.text.strong }}>{c.count.toLocaleString()}</td>
                <td style={{ padding: '12px 16px' }}>
                  <span style={{ fontSize: size['2xs'], padding: '2px 8px', borderRadius: radius.sm, fontWeight: weight.semibold, background: c.status === 'Active' ? color.success.tint : color.surface.muted, color: c.status === 'Active' ? color.success.text : color.text.muted }}>{c.status}</span>
                </td>
                <td style={{ padding: '12px 16px' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                    <div style={{ flex: 1, height: 4, background: color.surface.muted, borderRadius: radius.xxs, maxWidth: 100 }}>
                      <div style={{ height: '100%', background: color.brand.base, borderRadius: radius.xxs, width: `${c.popularity}%` }} />
                    </div>
                    <span style={{ fontSize: size.xs, color: color.text.secondary, width: 30 }}>{c.popularity}%</span>
                  </div>
                </td>
                <td style={{ padding: '12px 16px' }}>
                  <div style={{ display: 'flex', gap: 6 }}>
                    <button onClick={() => showToast('Category updated')} style={{ fontSize: size['2xs'], padding: '4px 10px', border: `1px solid ${color.border.base}`, borderRadius: radius.smd, background: color.surface.base, color: color.text.strong, cursor: 'pointer' }}>Edit</button>
                    <button onClick={() => showToast(c.status === 'Active' ? 'Category archived' : 'Category restored')} style={{ fontSize: size['2xs'], padding: '4px 10px', border: `1px solid ${color.border.base}`, borderRadius: radius.smd, background: color.surface.base, color: color.text.secondary, cursor: 'pointer' }}>{c.status === 'Active' ? 'Archive' : 'Restore'}</button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

