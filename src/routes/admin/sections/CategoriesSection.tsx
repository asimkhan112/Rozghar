import { useState } from 'react'
import { color, radius, size, tracking, weight } from '@/design-system'
import { useAdminCategories, useCreateCategory, useUpdateCategory } from '@/hooks/queries'
import { describeError } from '@/lib/http'
import { ErrorPanel } from '@/components/QueryState'
import { FField, IS } from '@/components/ui/AdminForm'
import { useToast } from '@/stores/useToastStore'
import Icon from '@/components/Icon'

/**
 * Slug for a new category.
 *
 * Derived here rather than server-side because the create endpoint requires
 * one and an editor should not have to think about URL segments. Accented
 * characters are folded so "Diseño" produces `diseno` rather than an empty
 * slug.
 */
function slugify(name: string): string {
  return name
    .normalize('NFD')
    .replace(/[̀-ͯ]/g, '')
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '')
    .slice(0, 60)
}

export default function CategoriesSection() {
  const showToast = useToast()
  // The admin projection: archived categories included, so "Restore" has
  // something to act on.
  const { data, isPending, isError, error, refetch } = useAdminCategories()
  const createCategory = useCreateCategory()
  const updateCategory = useUpdateCategory()

  const [adding, setAdding] = useState(false)
  const [newCat, setNewCat] = useState('')
  /** The row being renamed, and the name typed so far. */
  const [editing, setEditing] = useState<{ id: string; name: string } | null>(null)
  const [busy, setBusy] = useState<string | null>(null)

  const categories = data ?? []
  // Popularity relative to the busiest category, so the bar means something.
  const busiest = Math.max(1, ...categories.map(c => c.job_count))

  /** Runs a mutation, reports what the server actually said, and never claims
   *  success the request did not return. */
  async function run(key: string, action: () => Promise<unknown>, done: string) {
    setBusy(key)
    try {
      await action()
      showToast(done)
      return true
    } catch (err) {
      showToast(describeError(err))
      return false
    } finally {
      setBusy(null)
    }
  }

  const save = async () => {
    const name = newCat.trim()
    if (!name) return
    const ok = await run(
      'create',
      () => createCategory.mutateAsync({ name, slug: slugify(name) }),
      `Category “${name}” created`,
    )
    if (ok) {
      setNewCat('')
      setAdding(false)
    }
  }

  const rename = async () => {
    if (!editing) return
    const name = editing.name.trim()
    if (!name) return
    const ok = await run(
      editing.id,
      () => updateCategory.mutateAsync({ id: editing.id, changes: { name } }),
      `Renamed to “${name}”`,
    )
    if (ok) setEditing(null)
  }

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
            <input
              value={newCat}
              onChange={e => setNewCat(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && void save()}
              autoFocus
              placeholder="e.g. Legal & Compliance"
              style={IS}
            />
            {newCat.trim() && (
              <div style={{ fontSize: size['2xs'], color: color.text.muted, marginTop: 4 }}>
                URL: /jobs?category={slugify(newCat)}
              </div>
            )}
          </FField>
          <button
            onClick={() => void save()}
            disabled={!newCat.trim() || busy === 'create'}
            style={{ padding: '10px 20px', background: color.brand.base, border: 'none', borderRadius: radius.xl, color: color.surface.base, fontSize: size.sm, fontWeight: weight.medium, cursor: newCat.trim() ? 'pointer' : 'not-allowed', opacity: newCat.trim() ? 1 : 0.5, flexShrink: 0 }}
          >
            {busy === 'create' ? 'Saving…' : 'Save'}
          </button>
          <button onClick={() => { setAdding(false); setNewCat('') }} style={{ padding: '10px 16px', border: `1px solid ${color.border.base}`, borderRadius: radius.xl, background: color.surface.base, color: color.text.secondary, fontSize: size.sm, cursor: 'pointer', flexShrink: 0 }}>Cancel</button>
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
            {isPending && (
              <tr><td colSpan={5} style={{ padding: '28px 16px', textAlign: 'center', fontSize: size.sm, color: color.text.muted }}>Loading categories…</td></tr>
            )}
            {!isPending && categories.length === 0 && (
              <tr><td colSpan={5} style={{ padding: '28px 16px', textAlign: 'center', fontSize: size.sm, color: color.text.muted }}>No categories yet. Add the first one above.</td></tr>
            )}
            {categories.map(c => {
              const popularity = Math.round((c.job_count / busiest) * 100)
              const rowBusy = busy === c.id
              const isEditing = editing?.id === c.id
              return (
                <tr key={c.id} style={{ borderTop: `1px solid ${color.surface.muted}`, opacity: c.is_active ? 1 : 0.55 }}
                  onMouseEnter={e => (e.currentTarget.style.background = color.surface.hover)}
                  onMouseLeave={e => (e.currentTarget.style.background = 'none')}
                >
                  <td style={{ padding: '12px 16px', fontSize: size.sm, fontWeight: weight.semibold, color: color.text.primary }}>
                    {isEditing && editing ? (
                      <input
                        value={editing.name}
                        onChange={e => setEditing({ id: c.id, name: e.target.value })}
                        onKeyDown={e => {
                          if (e.key === 'Enter') void rename()
                          if (e.key === 'Escape') setEditing(null)
                        }}
                        autoFocus
                        style={{ ...IS, padding: '6px 10px', maxWidth: 280 }}
                      />
                    ) : (
                      c.name
                    )}
                  </td>
                  <td style={{ padding: '12px 16px', fontSize: size.sm, color: color.text.strong }}>{c.job_count.toLocaleString()}</td>
                  <td style={{ padding: '12px 16px' }}>
                    <span style={{ fontSize: size['2xs'], padding: '2px 8px', borderRadius: radius.sm, fontWeight: weight.semibold, background: c.is_active ? color.success.tint : color.surface.muted, color: c.is_active ? color.success.text : color.text.muted }}>
                      {c.is_active ? 'Active' : 'Archived'}
                    </span>
                  </td>
                  <td style={{ padding: '12px 16px' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                      <div style={{ flex: 1, height: 4, background: color.surface.muted, borderRadius: radius.xxs, maxWidth: 100 }}>
                        <div style={{ height: '100%', background: color.brand.base, borderRadius: radius.xxs, width: `${popularity}%` }} />
                      </div>
                      <span style={{ fontSize: size.xs, color: color.text.secondary, width: 30 }}>{popularity}%</span>
                    </div>
                  </td>
                  <td style={{ padding: '12px 16px' }}>
                    <div style={{ display: 'flex', gap: 6 }}>
                      {isEditing ? (
                        <>
                          <button onClick={() => void rename()} disabled={rowBusy} style={{ display: 'inline-flex', alignItems: 'center', gap: 5, fontSize: size['2xs'], padding: '4px 10px', border: `1px solid ${color.success.border}`, borderRadius: radius.smd, background: color.success.tintAlt, color: color.success.text, cursor: 'pointer' }}>
                            <Icon name="check" size={12} />{rowBusy ? 'Saving…' : 'Save'}
                          </button>
                          <button onClick={() => setEditing(null)} style={{ fontSize: size['2xs'], padding: '4px 10px', border: `1px solid ${color.border.base}`, borderRadius: radius.smd, background: color.surface.base, color: color.text.secondary, cursor: 'pointer' }}>Cancel</button>
                        </>
                      ) : (
                        <>
                          <button onClick={() => setEditing({ id: c.id, name: c.name })} disabled={rowBusy} style={{ fontSize: size['2xs'], padding: '4px 10px', border: `1px solid ${color.border.base}`, borderRadius: radius.smd, background: color.surface.base, color: color.text.strong, cursor: 'pointer' }}>Edit</button>
                          <button
                            onClick={() => void run(
                              c.id,
                              () => updateCategory.mutateAsync({ id: c.id, changes: { is_active: !c.is_active } }),
                              c.is_active ? `“${c.name}” archived` : `“${c.name}” restored`,
                            )}
                            disabled={rowBusy}
                            style={{ fontSize: size['2xs'], padding: '4px 10px', border: `1px solid ${color.border.base}`, borderRadius: radius.smd, background: color.surface.base, color: color.text.secondary, cursor: 'pointer' }}
                          >
                            {rowBusy ? '…' : c.is_active ? 'Archive' : 'Restore'}
                          </button>
                        </>
                      )}
                    </div>
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </div>
  )
}
