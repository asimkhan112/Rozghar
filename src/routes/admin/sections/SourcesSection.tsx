import { useState } from 'react'
import { actionTone, adminStatusTone, color, fontFamily, pillTone, radius, shadow, size, tracking, weight } from '@/design-system'
import { ACTIVITY_FEED, CATEGORIES_DATA, CONVERSION_DATA, LOCATIONS_DATA, METRIC_CARDS, REPORTS_DATA, SEARCH_KEYWORDS, SOURCES_DATA, TOP_JOBS_TABLE, TOP_LOCATION_SHARE } from '@/data/admin.mock'
import { FField, FormSection, FRow, IS, StatusPill } from '@/components/ui/AdminForm'
import { useToast } from '@/stores/useToastStore'

export default function SourcesSection() {
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
            {SOURCES_DATA.map((s, i) => (
              <tr key={i} style={{ borderTop: `1px solid ${color.surface.muted}` }}
                onMouseEnter={e => (e.currentTarget.style.background = color.surface.hover)}
                onMouseLeave={e => (e.currentTarget.style.background = 'none')}
              >
                <td style={{ padding: '14px 16px' }}>
                  <div style={{ fontSize: size.sm, fontWeight: weight.semibold, color: color.text.primary }}>{s.name}</div>
                </td>
                <td style={{ padding: '14px 16px', fontSize: size.sm, color: color.text.strong }}>{s.jobs.toLocaleString()}</td>
                <td style={{ padding: '14px 16px', fontSize: size.sm, fontWeight: weight.semibold, color: color.text.primary }}>{s.clicks.toLocaleString()}</td>
                <td style={{ padding: '14px 16px' }}>
                  <span style={{ fontSize: size.sm, fontWeight: weight.bold, color: parseFloat(s.ctr) > 15 ? color.success.base : color.brand.base }}>{s.ctr}</span>
                </td>
                <td style={{ padding: '14px 16px' }}>
                  <span style={{ fontSize: size['2xs'], padding: '2px 8px', borderRadius: radius.sm, fontWeight: weight.semibold, background: color.success.tint, color: color.success.text }}>{s.status}</span>
                </td>
                <td style={{ padding: '14px 16px' }}>
                  <div style={{ display: 'flex', gap: 6 }}>
                    <button style={{ fontSize: size['2xs'], padding: '4px 10px', border: `1px solid ${color.border.base}`, borderRadius: radius.smd, background: color.surface.base, color: color.text.strong, cursor: 'pointer' }}>Edit</button>
                    <button style={{ fontSize: size['2xs'], padding: '4px 10px', border: `1px solid ${color.danger.border}`, borderRadius: radius.smd, background: color.danger.tint, color: color.danger.base, cursor: 'pointer' }}>Pause</button>
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

