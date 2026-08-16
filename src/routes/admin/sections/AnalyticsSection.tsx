import { useState } from 'react'
import { actionTone, adminStatusTone, color, fontFamily, pillTone, radius, shadow, size, tracking, weight } from '@/design-system'
import { useAnalyticsOverview, useLocations, useSearchAnalytics } from '@/hooks/queries'
import { describeError } from '@/lib/http'
import { ErrorPanel } from '@/components/QueryState'

const pct = (rate: number) => `${(rate * 100).toFixed(1)}%`
import { FField, FormSection, FRow, IS, StatusPill } from '@/components/ui/AdminForm'
import { useToast } from '@/stores/useToastStore'

export default function AnalyticsSection() {
  const overview = useAnalyticsOverview()
  const search = useSearchAnalytics()
  const locations = useLocations()

  const totals = overview.data?.totals
  const rates = overview.data?.rates

  /**
   * The funnel, computed from the totals rather than stored.
   *
   * The mock carried a hardcoded "vs industry avg 12%" comparison. There is no
   * industry benchmark in this system and inventing one on a dashboard people
   * make decisions from would be worse than omitting it.
   */
  const CONV_DATA = [
    {
      label: 'Views → Apply Click',
      rate: pct(rates?.view_to_apply ?? 0),
      count: `${(totals?.apply_clicks ?? 0).toLocaleString()} clicks`,
      bar: Math.min(100, Math.round((rates?.view_to_apply ?? 0) * 100)),
    },
    {
      label: 'Save Rate',
      rate: pct(rates?.save_rate ?? 0),
      count: `${(totals?.saves ?? 0).toLocaleString()} saves`,
      bar: Math.min(100, Math.round((rates?.save_rate ?? 0) * 100)),
    },
    {
      label: 'Share Rate',
      rate: pct(totals?.job_views ? (totals.shares ?? 0) / totals.job_views : 0),
      count: `${(totals?.shares ?? 0).toLocaleString()} shares`,
      bar: Math.min(100, Math.round(totals?.job_views ? ((totals.shares ?? 0) / totals.job_views) * 100 : 0)),
    },
    {
      label: 'Searches With No Results',
      rate: pct(rates?.zero_result_rate ?? 0),
      count: `${(search.data?.zero_result_searches ?? 0).toLocaleString()} searches`,
      bar: Math.min(100, Math.round((rates?.zero_result_rate ?? 0) * 100)),
    },
  ]

  /**
   * Share of listings by location.
   *
   * Derived from the maintained `job_count` on each location rather than from
   * events: it answers "where is the catalogue" — which is the question the
   * panel's title asks — and does not go blank on a quiet traffic day.
   */
  const locationTotal = (locations.data ?? []).reduce((sum, l) => sum + l.count, 0)
  const TOP_LOCS = (locations.data ?? [])
    .filter(l => l.count > 0)
    .sort((a, b) => b.count - a.count)
    .slice(0, 5)
    .map(l => ({
      loc: l.label.split(',')[0]?.trim() ?? l.label,
      pct: locationTotal ? Math.round((l.count / locationTotal) * 100) : 0,
    }))

  const SEARCH_KEYWORDS = (search.data?.top_queries ?? []).map(q => ({ kw: q.query, count: q.count }))

  if (overview.isError) {
    return <ErrorPanel message={describeError(overview.error)} onRetry={() => void overview.refetch()} />
  }

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

