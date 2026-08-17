import { useState } from 'react'
import { color, radius, size, tracking, weight } from '@/design-system'
import { useAdminSources, useSourcePerformance, useUpdateSource } from '@/hooks/queries'
import { describeError } from '@/lib/http'
import { ErrorPanel } from '@/components/QueryState'
import { IS } from '@/components/ui/AdminForm'
import { useToast } from '@/stores/useToastStore'
import Icon from '@/components/Icon'

export default function SourcesSection() {
  const showToast = useToast()
  // Two reads, deliberately: the admin list is the set of sources and their
  // paused state, the performance query is what each one actually earned.
  // Neither endpoint can answer both questions.
  const sources = useAdminSources()
  const { data: performance, isError, error, refetch } = useSourcePerformance()
  const updateSource = useUpdateSource()

  const [editing, setEditing] = useState<{ id: string; name: string } | null>(null)
  const [busy, setBusy] = useState<string | null>(null)

  const stats = new Map((performance ?? []).map(p => [p.slug, p]))

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

  const rename = async () => {
    if (!editing) return
    const name = editing.name.trim()
    if (!name) return
    const ok = await run(
      editing.id,
      () => updateSource.mutateAsync({ id: editing.id, changes: { name } }),
      `Renamed to “${name}”`,
    )
    if (ok) setEditing(null)
  }

  if (isError) {
    return <ErrorPanel message={describeError(error)} onRetry={() => void refetch()} />
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <div style={{ background: color.surface.base, border: `1px solid ${color.border.base}`, borderRadius: radius['3xl'], overflow: 'hidden' }}>
        <div style={{ padding: '16px 20px', borderBottom: `1px solid ${color.border.base}` }}>
          <div style={{ fontSize: size.base, fontWeight: weight.bold, color: color.text.primary }}>Job Sources</div>
          <div style={{ fontSize: size.xs, color: color.text.muted, marginTop: 2 }}>Performance metrics by job source</div>
        </div>
        <table style={{ width: '100%', borderCollapse: 'collapse' }}>
          <thead>
            <tr style={{ background: color.surface.subtle }}>
              {['Source', 'Jobs Indexed', 'Total Clicks', 'CTR', 'Status', 'Actions'].map(h => (
                <th key={h} style={{ padding: '10px 16px', textAlign: 'left', fontSize: size['2xs'], fontWeight: weight.semibold, color: color.text.muted, textTransform: 'uppercase', letterSpacing: tracking.wide }}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {sources.isPending && (
              <tr><td colSpan={6} style={{ padding: '28px 16px', textAlign: 'center', fontSize: size.sm, color: color.text.muted }}>Loading sources…</td></tr>
            )}
            {(sources.data ?? []).map(s => {
              const stat = stats.get(s.slug)
              const jobs = stat?.jobs ?? 0
              const clicks = stat?.apply_clicks ?? 0
              // Apply clicks per view as a whole-number percentage. A feed that
              // publishes thousands of listings nobody clicks shows up here and
              // nowhere else.
              const ctr = Math.round((stat?.ctr ?? 0) * 100)
              const rowBusy = busy === s.id
              const isEditing = editing?.id === s.id
              return (
                <tr key={s.id} style={{ borderTop: `1px solid ${color.surface.muted}`, opacity: s.is_active ? 1 : 0.55 }}
                  onMouseEnter={e => (e.currentTarget.style.background = color.surface.hover)}
                  onMouseLeave={e => (e.currentTarget.style.background = 'none')}
                >
                  <td style={{ padding: '14px 16px' }}>
                    {isEditing && editing ? (
                      <input
                        value={editing.name}
                        onChange={e => setEditing({ id: s.id, name: e.target.value })}
                        onKeyDown={e => {
                          if (e.key === 'Enter') void rename()
                          if (e.key === 'Escape') setEditing(null)
                        }}
                        autoFocus
                        style={{ ...IS, padding: '6px 10px', maxWidth: 240 }}
                      />
                    ) : (
                      <>
                        <div style={{ fontSize: size.sm, fontWeight: weight.semibold, color: color.text.primary }}>{s.name}</div>
                        <div style={{ fontSize: size['2xs'], color: color.text.muted }}>{s.type === 'manual' ? 'Manual' : 'Scraper'}</div>
                      </>
                    )}
                  </td>
                  <td style={{ padding: '14px 16px', fontSize: size.sm, color: color.text.strong }}>{jobs.toLocaleString()}</td>
                  <td style={{ padding: '14px 16px', fontSize: size.sm, fontWeight: weight.semibold, color: color.text.primary }}>{clicks.toLocaleString()}</td>
                  <td style={{ padding: '14px 16px' }}>
                    <span style={{ fontSize: size.sm, fontWeight: weight.bold, color: ctr > 15 ? color.success.base : color.brand.base }}>{ctr}%</span>
                  </td>
                  <td style={{ padding: '14px 16px' }}>
                    <span style={{ fontSize: size['2xs'], padding: '2px 8px', borderRadius: radius.sm, fontWeight: weight.semibold, background: s.is_active ? color.success.tint : color.surface.muted, color: s.is_active ? color.success.text : color.text.muted }}>
                      {s.is_active ? 'Active' : 'Paused'}
                    </span>
                  </td>
                  <td style={{ padding: '14px 16px' }}>
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
                          <button onClick={() => setEditing({ id: s.id, name: s.name })} disabled={rowBusy} style={{ fontSize: size['2xs'], padding: '4px 10px', border: `1px solid ${color.border.base}`, borderRadius: radius.smd, background: color.surface.base, color: color.text.strong, cursor: 'pointer' }}>Edit</button>
                          <button
                            onClick={() => void run(
                              s.id,
                              () => updateSource.mutateAsync({ id: s.id, changes: { is_active: !s.is_active } }),
                              s.is_active ? `${s.name} paused` : `${s.name} resumed`,
                            )}
                            disabled={rowBusy}
                            style={{ fontSize: size['2xs'], padding: '4px 10px', border: `1px solid ${s.is_active ? color.danger.border : color.border.base}`, borderRadius: radius.smd, background: s.is_active ? color.danger.tint : color.surface.base, color: s.is_active ? color.danger.base : color.text.secondary, cursor: 'pointer' }}
                          >
                            {rowBusy ? '…' : s.is_active ? 'Pause' : 'Resume'}
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
