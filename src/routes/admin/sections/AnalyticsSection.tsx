import { useState } from 'react'
import { actionTone, adminStatusTone, color, fontFamily, pillTone, radius, shadow, size, tracking, weight } from '@/design-system'
import { ACTIVITY_FEED, CATEGORIES_DATA, CONVERSION_DATA, LOCATIONS_DATA, METRIC_CARDS, REPORTS_DATA, SEARCH_KEYWORDS, SOURCES_DATA, TOP_JOBS_TABLE, TOP_LOCATION_SHARE } from '@/data/admin.mock'
import { FField, FormSection, FRow, IS, StatusPill } from '@/components/ui/AdminForm'
import { useToast } from '@/stores/useToastStore'

export default function AnalyticsSection() {
  const CONV_DATA = CONVERSION_DATA
  const TOP_LOCS = TOP_LOCATION_SHARE

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
      {/* Traffic */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: 14 }}>
        {[
          { label: 'Total Page Views', value: '284,920', sub: 'All time' },
          { label: 'Unique Sessions', value: '162,000', sub: 'This month' },
          { label: 'Avg. Session Duration', value: '3m 24s', sub: 'Per visit' },
          { label: 'Bounce Rate', value: '42%', sub: 'Below avg 58%' },
        ].map(s => (
          <div key={s.label} style={{ background: color.surface.base, border: `1px solid ${color.border.base}`, borderRadius: radius['3xl'], padding: '18px 20px' }}>
            <div style={{ fontSize: size['2xs'], color: color.text.muted, fontWeight: weight.semibold, textTransform: 'uppercase', letterSpacing: tracking.wide, marginBottom: 8 }}>{s.label}</div>
            <div style={{ fontSize: size['5xl'], fontWeight: weight.extrabold, color: color.text.primary, letterSpacing: tracking.tighter, marginBottom: 4 }}>{s.value}</div>
            <div style={{ fontSize: size['2xs'], color: color.brand.base, fontWeight: weight.medium }}>{s.sub}</div>
          </div>
        ))}
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 20 }}>
        {/* Conversion */}
        <div style={{ background: color.surface.base, border: `1px solid ${color.border.base}`, borderRadius: radius['3xl'], padding: '20px 24px' }}>
          <div style={{ fontSize: size.base, fontWeight: weight.bold, color: color.text.primary, marginBottom: 4 }}>Conversion Metrics</div>
          <div style={{ fontSize: size.xs, color: color.text.muted, marginBottom: 20 }}>How users move through the funnel</div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
            {CONV_DATA.map(c => (
              <div key={c.label}>
                <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 6 }}>
                  <div>
                    <div style={{ fontSize: size.sm, fontWeight: weight.semibold, color: color.text.primary }}>{c.label}</div>
                    <div style={{ fontSize: size['2xs'], color: color.text.muted }}>{c.count}</div>
                  </div>
                  <span style={{ fontSize: size['2xl'], fontWeight: weight.extrabold, color: color.brand.base }}>{c.rate}</span>
                </div>
                <div style={{ height: 6, background: color.surface.muted, borderRadius: radius.xs }}>
                  <div style={{ height: '100%', background: color.brand.base, borderRadius: radius.xs, width: `${c.bar}%` }} />
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Top locations */}
        <div style={{ background: color.surface.base, border: `1px solid ${color.border.base}`, borderRadius: radius['3xl'], padding: '20px 24px' }}>
          <div style={{ fontSize: size.base, fontWeight: weight.bold, color: color.text.primary, marginBottom: 4 }}>Top Locations</div>
          <div style={{ fontSize: size.xs, color: color.text.muted, marginBottom: 20 }}>By job search volume</div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
            {TOP_LOCS.map(l => (
              <div key={l.loc}>
                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: size.sm, marginBottom: 5 }}>
                  <span style={{ fontWeight: weight.medium, color: color.text.strong }}>{l.loc}</span>
                  <span style={{ color: color.text.muted }}>{l.pct}%</span>
                </div>
                <div style={{ height: 6, background: color.surface.muted, borderRadius: radius.xs }}>
                  <div style={{ height: '100%', background: l.loc === 'Lahore' ? color.brand.base : l.loc === 'Karachi' ? color.accent.violet : color.success.base, borderRadius: radius.xs, width: `${l.pct}%` }} />
                </div>
              </div>
            ))}
          </div>
          <div style={{ marginTop: 20, paddingTop: 16, borderTop: `1px solid ${color.surface.muted}` }}>
            <div style={{ fontSize: size.xs, fontWeight: weight.bold, color: color.text.primary, marginBottom: 10 }}>Top Search Keywords</div>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
              {SEARCH_KEYWORDS.slice(0, 6).map(k => (
                <span key={k.kw} style={{ fontSize: size['2xs'], padding: '4px 10px', borderRadius: radius.pill, background: color.surface.muted, color: color.text.strong, fontWeight: weight.medium }}>{k.kw}</span>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}

