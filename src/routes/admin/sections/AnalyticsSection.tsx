import { useState } from 'react'
import { actionTone, adminStatusTone, color, fontFamily, pillTone, radius, shadow, size, tracking, weight } from '@/design-system'
import { useAnalyticsOverview, useSearchAnalytics, useTraffic } from '@/hooks/queries'
import { describeError } from '@/lib/http'
import { ErrorPanel } from '@/components/QueryState'
import { FField, FormSection, FRow, IS, StatusPill } from '@/components/ui/AdminForm'
import { useToast } from '@/stores/useToastStore'

const pct = (rate: number) => `${(rate * 100).toFixed(1)}%`

/**
 * A tile with no data yet reads as an em dash, never as zero.
 *
 * Nothing on this screen distinguishes "the query is still in flight" from
 * "nobody visited" once a number is rendered, and the two mean opposite
 * things to whoever is reading it.
 */
const orPending = <T,>(value: T | undefined, render: (v: T) => string) =>
  value === undefined ? '—' : render(value)

/** Seconds as a duration a person reads rather than a number they convert. */
const duration = (seconds: number) => {
  if (seconds < 60) return `${seconds}s`
  const minutes = Math.floor(seconds / 60)
  if (minutes < 60) return `${minutes}m ${seconds % 60}s`
  return `${Math.floor(minutes / 60)}h ${minutes % 60}m`
}

/** The window the API actually answered for, not the one we asked for. */
const windowLabel = (range?: { from: string; to: string }) => {
  if (!range) return 'Selected window'
  const days = Math.round((Date.parse(range.to) - Date.parse(range.from)) / 86_400_000) + 1
  return days <= 1 ? 'Today' : `Last ${days} days`
}

/** Bar colours by rank. Cycled rather than keyed to a city name — the ranking
 *  changes with the traffic, and a hardcoded city eventually colours the wrong
 *  row. */
const BAR_COLORS = [color.brand.base, color.accent.violet, color.success.base]
export default function AnalyticsSection() {
  const overview = useAnalyticsOverview()
  const search = useSearchAnalytics()
  const traffic = useTraffic()

  const totals = overview.data?.totals
  const rates = overview.data?.rates
  const visits = traffic.data

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
   * Where the audience is, by views on the listings in each location.
   *
   * Read from traffic rather than from `locations.job_count`, which is what
   * this panel used to show. The two answer different questions and the
   * subtitle asks for this one: a catalogue concentrated in one city would
   * report that city at 100% no matter where anybody actually read.
   *
   * `share` is computed server-side against every location with traffic, not
   * only the five returned, so a truncated list correctly sums to less than
   * 100%.
   */
  const TOP_LOCS = (visits?.top_locations ?? []).map(l => ({
    loc: l.name,
    pct: Math.round(l.share * 100),
    views: l.views,
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
          {
            label: 'Total Page Views',
            value: orPending(visits?.page_views, v => v.toLocaleString()),
            sub: windowLabel(visits?.range),
          },
          {
            label: 'Unique Sessions',
            value: orPending(visits?.unique_sessions, v => v.toLocaleString()),
            sub: orPending(visits?.views_per_session, v => `${v.toFixed(1)} views per visit`),
          },
          {
            label: 'Avg. Session Duration',
            value: orPending(visits?.avg_session_seconds, duration),
            sub: 'First to last event',
          },
          // The mock carried a "below avg 58%" comparison. There is no
          // benchmark in this system, and inventing one on a screen people
          // make decisions from is worse than leaving it out.
          {
            label: 'Bounce Rate',
            value: orPending(visits?.bounce_rate, pct),
            sub: 'Visits with one page view',
          },
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
          <div style={{ fontSize: size.xs, color: color.text.muted, marginBottom: 20 }}>By listing views</div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
            {TOP_LOCS.length === 0 && (
              <div style={{ fontSize: size.xs, color: color.text.muted }}>
                {traffic.isPending
                  ? 'Loading…'
                  : 'No listing views recorded in this window yet.'}
              </div>
            )}
            {TOP_LOCS.map((l, i) => (
              <div key={l.loc}>
                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: size.sm, marginBottom: 5 }}>
                  <span style={{ fontWeight: weight.medium, color: color.text.strong }}>{l.loc}</span>
                  <span style={{ color: color.text.muted }}>{l.views.toLocaleString()} views · {l.pct}%</span>
                </div>
                <div style={{ height: 6, background: color.surface.muted, borderRadius: radius.xs }}>
                  <div style={{ height: '100%', background: BAR_COLORS[i % BAR_COLORS.length], borderRadius: radius.xs, width: `${l.pct}%` }} />
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

