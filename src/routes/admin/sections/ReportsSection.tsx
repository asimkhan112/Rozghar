import { useState } from 'react'
import { actionTone, adminStatusTone, color, fontFamily, pillTone, radius, shadow, size, tracking, weight } from '@/design-system'
import { ACTIVITY_FEED, CATEGORIES_DATA, CONVERSION_DATA, LOCATIONS_DATA, METRIC_CARDS, REPORTS_DATA, SEARCH_KEYWORDS, SOURCES_DATA, TOP_JOBS_TABLE, TOP_LOCATION_SHARE } from '@/data/admin.mock'
import { FField, FormSection, FRow, IS, StatusPill } from '@/components/ui/AdminForm'
import { useToast } from '@/stores/useToastStore'

export default function ReportsSection() {
  const showToast = useToast()
  const reports = REPORTS_DATA
  const [resolved, setResolved] = useState<number[]>([])

  const REASON_COLORS: Record<string, string> = {
    'Broken Link': color.danger.base, 'Spam': color.accent.purple, 'Expired': color.warning.base, 'Wrong Information': color.info.base, 'Duplicate': color.text.secondary,
  }
  const pending = reports.filter((r: any) => !resolved.includes(r.id))

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 16, flexWrap: 'wrap' }}>
        <div style={{ display: 'flex', gap: 10 }}>
          <div style={{ background: color.surface.base, border: `1px solid ${color.border.base}`, borderRadius: radius['2xl'], padding: '12px 20px', textAlign: 'center' }}>
            <div style={{ fontSize: size['3xl'], fontWeight: weight.extrabold, color: color.danger.base }}>{pending.length}</div>
            <div style={{ fontSize: size['2xs'], color: color.text.muted, marginTop: 2 }}>Pending</div>
          </div>
          <div style={{ background: color.surface.base, border: `1px solid ${color.border.base}`, borderRadius: radius['2xl'], padding: '12px 20px', textAlign: 'center' }}>
            <div style={{ fontSize: size['3xl'], fontWeight: weight.extrabold, color: color.success.base }}>{resolved.length}</div>
            <div style={{ fontSize: size['2xs'], color: color.text.muted, marginTop: 2 }}>Resolved</div>
          </div>
        </div>
      </div>

      {pending.length === 0 ? (
        <div style={{ background: color.surface.base, border: `1px solid ${color.border.base}`, borderRadius: radius['3xl'], padding: '60px 24px', textAlign: 'center' }}>
          <div style={{ fontSize: size['7xl'], marginBottom: 12 }}>✅</div>
          <div style={{ fontSize: size.lg, fontWeight: weight.bold, color: color.text.primary, marginBottom: 6 }}>All reports resolved</div>
          <div style={{ fontSize: size.sm, color: color.text.muted }}>No pending reports to review</div>
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          {pending.map((r: typeof REPORTS_DATA[0]) => (
            <div key={r.id} style={{ background: color.surface.base, border: `1px solid ${color.border.base}`, borderRadius: radius['3xl'], padding: '20px 24px' }}>
              <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 16, flexWrap: 'wrap' }}>
                <div style={{ flex: 1, minWidth: 250 }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 6 }}>
                    <span style={{ fontSize: size.sm, fontWeight: weight.bold, color: color.text.primary }}>{r.job}</span>
                    <span style={{ fontSize: size['2xs'], color: color.text.secondary }}>· {r.company}</span>
                    <span style={{ fontSize: size['2xs'], padding: '2px 8px', borderRadius: radius.sm, fontWeight: weight.semibold, background: `${REASON_COLORS[r.category]}18`, color: REASON_COLORS[r.category] }}>
                      {r.category}
                    </span>
                  </div>
                  <p style={{ margin: '0 0 8px', fontSize: size.sm, color: color.text.strong, lineHeight: 1.5, fontStyle: 'italic' }}>"{r.comment}"</p>
                  <span style={{ fontSize: size['2xs'], color: color.text.muted }}>Reported {r.date}</span>
                </div>
                <div style={{ display: 'flex', gap: 8, flexShrink: 0 }}>
                  <button onClick={() => { setResolved((p: number[]) => [...p, r.id]); showToast('Report resolved') }}
                    style={{ padding: '7px 14px', border: `1px solid ${color.success.border}`, background: color.success.tintAlt, color: color.success.text, borderRadius: radius.lg, fontSize: size.xs, fontWeight: weight.semibold, cursor: 'pointer' }}>
                    ✓ Resolve
                  </button>
                  <button onClick={() => showToast('Job expired')} style={{ padding: '7px 14px', border: `1px solid ${color.warning.tintSoft}`, background: color.warning.tintAlt, color: color.warning.amber, borderRadius: radius.lg, fontSize: size.xs, fontWeight: weight.medium, cursor: 'pointer' }}>Expire</button>
                  <button onClick={() => showToast('Job deleted')} style={{ padding: '7px 14px', border: `1px solid ${color.danger.border}`, background: color.danger.tint, color: color.danger.base, borderRadius: radius.lg, fontSize: size.xs, fontWeight: weight.medium, cursor: 'pointer' }}>Delete</button>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

