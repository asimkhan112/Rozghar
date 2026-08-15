import { useMemo, useState } from 'react'
import { Link, useNavigate } from 'react-router'
import { actionTone, adminStatusTone, bareInput, color, linkReset, pillTone, radius, size, tracking, weight } from '@/design-system'
import { StatusPill } from '@/components/ui/AdminForm'
import { useToast } from '@/stores/useToastStore'
import { getAllJobs } from '@/data/queries'
import { toAdminRow } from '../adminRow'
import type { AdminJobRow } from '@/types/admin'

/**
 * Admin jobs table.
 *
 * Previously received thirteen loosely-typed props from the parent page. All of
 * that state is local to this table, so it owns it now and the `any` goes away.
 */
export default function JobsSection() {
  const showToast = useToast()
  const navigate = useNavigate()

  const [search, setSearch] = useState('')
  const [statusFilter, setStatusFilter] = useState('All')
  const [selected, setSelected] = useState<number[]>([])
  const [deleteConfirm, setDeleteConfirm] = useState<number | null>(null)
  const [page, setPage] = useState(1)
  const perPage = 8

  const rows = useMemo(() => getAllJobs().map(toAdminRow), [])

  const jobs = useMemo(() => {
    const term = search.toLowerCase()
    return rows.filter(j => {
      const matchSearch = j.title.toLowerCase().includes(term) || j.company.toLowerCase().includes(term)
      const matchStatus = statusFilter === 'All' || j.status === statusFilter.toLowerCase()
      return matchSearch && matchStatus
    })
  }, [rows, search, statusFilter])

  const paginated = jobs.slice(0, page * perPage)
  const setSection = (section: string) => navigate(`/admin/dashboard/${section}`)

  const STATUS_FILTERS = ['All', 'Published', 'Featured', 'Verified', 'Draft', 'Expiring', 'Expired']
  const allSelected = paginated.length > 0 && paginated.every((_: any, i: number) => selected.includes(i))

  const toggleAll = () => setSelected(allSelected ? [] : paginated.map((_: any, i: number) => i))

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      {/* Toolbar */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
        <div style={{ flex: 1, minWidth: 200, display: 'flex', alignItems: 'center', gap: 8, border: `1px solid ${color.border.base}`, borderRadius: radius.xl, padding: '8px 14px', background: color.surface.base }}>
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke={color.text.muted} strokeWidth="2"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>
          <input value={search} onChange={e => setSearch(e.target.value)} placeholder="Search jobs or companies…" style={bareInput(size.sm, { width: '100%' })} />
        </div>
        {selected.length > 0 && (
          <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
            <span style={{ fontSize: size.sm, color: color.text.secondary }}>{selected.length} selected</span>
            {[
              { label: 'Feature', color: color.warning.text },
              { label: 'Verify', color: color.info.text },
              { label: 'Expire', color: color.warning.base },
              { label: 'Delete', color: color.danger.base },
            ].map(a => (
              <button key={a.label} onClick={() => { setSelected([]); showToast(`${a.label}d ${selected.length} job${selected.length > 1 ? 's' : ''}`) }}
                style={{ padding: '6px 12px', border: `1px solid ${a.color}30`, background: `${a.color}0A`, borderRadius: radius.md, fontSize: size.xs, fontWeight: weight.medium, color: a.color, cursor: 'pointer' }}>
                {a.label}
              </button>
            ))}
          </div>
        )}
        <button onClick={() => setSection('add-job')} style={{ padding: '8px 16px', background: color.brand.base, border: 'none', borderRadius: radius.xl, color: color.surface.base, fontSize: size.sm, fontWeight: weight.medium, cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 6 }}>
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
          Add Job
        </button>
      </div>

      {/* Status filter pills */}
      <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
        {STATUS_FILTERS.map(f => (
          <button key={f} onClick={() => setStatusFilter(f)} style={{
            padding: '5px 14px', ...pillTone(statusFilter === f),
            borderRadius: radius.pill, fontSize: size.xs, fontWeight: statusFilter === f ? weight.semibold : weight.regular, cursor: 'pointer',
          }}>{f}</button>
        ))}
        <span style={{ marginLeft: 'auto', fontSize: size.xs, color: color.text.muted, alignSelf: 'center' }}>{jobs.length} results</span>
      </div>

      {/* Table */}
      <div style={{ background: color.surface.base, border: `1px solid ${color.border.base}`, borderRadius: radius['3xl'], overflow: 'hidden' }}>
        <div style={{ overflowX: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', minWidth: 900 }}>
            <thead>
              <tr style={{ background: color.surface.subtle }}>
                <th style={{ padding: '10px 16px', width: 36 }}>
                  <div onClick={toggleAll} style={{ width: 16, height: 16, borderRadius: radius.sm, border: `2px solid ${allSelected ? color.brand.base : color.text.disabled}`, background: allSelected ? color.brand.base : color.surface.base, cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                    {allSelected && <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke={color.surface.base} strokeWidth="3"><polyline points="20 6 9 17 4 12"/></svg>}
                  </div>
                </th>
                {['Job Title', 'Category', 'Location', 'Status', 'Published', 'Expiry', 'Clicks', 'Views', 'Actions'].map(h => (
                  <th key={h} style={{ padding: '10px 12px', textAlign: 'left', fontSize: size['2xs'], fontWeight: weight.semibold, color: color.text.muted, textTransform: 'uppercase', letterSpacing: tracking.wide, whiteSpace: 'nowrap' }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {paginated.map((j: AdminJobRow, i: number) => {
                const isSelected = selected.includes(i)
                return (
                  <tr key={i} style={{ borderTop: `1px solid ${color.surface.muted}`, background: isSelected ? color.brand.tint : 'none' }}
                    onMouseEnter={e => { if (!isSelected) e.currentTarget.style.background = color.surface.hover }}
                    onMouseLeave={e => { if (!isSelected) e.currentTarget.style.background = 'none' }}
                  >
                    <td style={{ padding: '12px 16px' }}>
                      <div onClick={() => setSelected((prev: number[]) => isSelected ? prev.filter(x => x !== i) : [...prev, i])}
                        style={{ width: 16, height: 16, borderRadius: radius.sm, border: `2px solid ${isSelected ? color.brand.base : color.text.disabled}`, background: isSelected ? color.brand.base : color.surface.base, cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                        {isSelected && <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke={color.surface.base} strokeWidth="3"><polyline points="20 6 9 17 4 12"/></svg>}
                      </div>
                    </td>
                    <td style={{ padding: '12px 12px' }}>
                      <div style={{ fontSize: size.sm, fontWeight: weight.semibold, color: color.text.primary }}>{j.title}</div>
                      <div style={{ fontSize: size['2xs'], color: color.text.muted }}>{j.company}</div>
                    </td>
                    <td style={{ padding: '12px 12px', fontSize: size.xs, color: color.text.secondary, whiteSpace: 'nowrap' }}>{j.category}</td>
                    <td style={{ padding: '12px 12px', fontSize: size.xs, color: color.text.secondary, whiteSpace: 'nowrap' }}>{j.location}</td>
                    <td style={{ padding: '12px 12px' }}><StatusPill status={j.status} /></td>
                    <td style={{ padding: '12px 12px', fontSize: size.xs, color: color.text.secondary, whiteSpace: 'nowrap' }}>{j.published}</td>
                    <td style={{ padding: '12px 12px', fontSize: size.xs, color: j.expiry !== '—' && new Date(j.expiry) < new Date('2026-08-20') ? color.danger.base : color.text.secondary, whiteSpace: 'nowrap', fontWeight: j.expiry !== '—' && new Date(j.expiry) < new Date('2026-08-20') ? weight.semibold : weight.regular }}>{j.expiry}</td>
                    <td style={{ padding: '12px 12px', fontSize: size.sm, fontWeight: weight.bold, color: color.brand.base }}>{j.clicks}</td>
                    <td style={{ padding: '12px 12px', fontSize: size.sm, color: color.text.strong }}>{j.views.toLocaleString()}</td>
                    <td style={{ padding: '12px 12px' }}>
                      {deleteConfirm === i ? (
                        <div style={{ display: 'flex', gap: 6 }}>
                          <button onClick={() => { setDeleteConfirm(null); showToast('Job deleted') }} style={{ fontSize: size['2xs'], padding: '4px 8px', border: `1px solid ${color.danger.base}`, background: color.danger.tint, color: color.danger.base, borderRadius: radius.smd, cursor: 'pointer', fontWeight: weight.semibold }}>Confirm</button>
                          <button onClick={() => setDeleteConfirm(null)} style={{ fontSize: size['2xs'], padding: '4px 8px', border: `1px solid ${color.border.base}`, background: color.surface.base, color: color.text.secondary, borderRadius: radius.smd, cursor: 'pointer' }}>Cancel</button>
                        </div>
                      ) : (
                        <div style={{ display: 'flex', gap: 4 }}>
                          {[
                            { label: 'Edit', title: 'Edit' },
                            { label: '⭐', title: 'Feature' },
                            { label: '✓', title: 'Verify' },
                          ].map(a => (
                            <button key={a.title} title={a.title} onClick={() => showToast(`${a.title} action applied`)}
                              style={{ fontSize: size['2xs'], padding: '4px 8px', border: `1px solid ${color.border.base}`, background: color.surface.base, color: color.text.secondary, borderRadius: radius.smd, cursor: 'pointer' }}>
                              {a.label}
                            </button>
                          ))}
                          <button title="Delete" onClick={() => setDeleteConfirm(i)}
                            style={{ fontSize: size['2xs'], padding: '4px 8px', border: `1px solid ${color.danger.border}`, background: color.danger.tint, color: color.danger.base, borderRadius: radius.smd, cursor: 'pointer' }}>
                            ✕
                          </button>
                        </div>
                      )}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>

        {/* Pagination */}
        <div style={{ padding: '12px 20px', borderTop: `1px solid ${color.surface.muted}`, display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <span style={{ fontSize: size.xs, color: color.text.muted }}>Showing {Math.min(paginated.length, jobs.length)} of {jobs.length}</span>
          {jobs.length > paginated.length && (
            <button onClick={() => setPage((p: number) => p + 1)} style={{ fontSize: size.sm, padding: '6px 16px', border: `1px solid ${color.border.base}`, borderRadius: radius.lg, background: color.surface.base, color: color.text.strong, cursor: 'pointer', fontWeight: weight.medium }}>
              Load more
            </button>
          )}
        </div>
      </div>
    </div>
  )
}

