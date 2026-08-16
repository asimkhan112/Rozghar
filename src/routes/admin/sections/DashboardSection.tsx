import { useState } from 'react'
import { actionTone, activityTone, adminStatusTone, color, fontFamily, pillTone, radius, shadow, size, tracking, weight } from '@/design-system'
import {
  useAdminJobs,
  useAnalyticsOverview,
  useAuditFeed,
  useReports,
} from '@/hooks/queries'
import { describeError } from '@/lib/http'
import { ErrorPanel } from '@/components/QueryState'

/**
 * Audit verbs → the sentence a person reads.
 *
 * The trail stores `job.publish`; a dashboard that renders that literally is a
 * log viewer, not a feed. Anything unmapped falls back to the raw verb rather
 * than being hidden — an unrecognised action is exactly what someone should
 * see.
 */
const ACTION_TEXT: Record<string, string> = {
  'job.create': 'created a listing',
  'job.update': 'edited a listing',
  'job.publish': 'published a listing',
  'job.expire': 'expired a listing',
  'job.verify': 'verified a listing',
  'job.feature': 'featured a listing',
  'job.delete': 'removed a listing',
  'report.review': 'picked up a report',
  'report.resolve': 'resolved a report',
  'report.dismiss': 'dismissed a report',
  'report.reopen': 'reopened a report',
  'admin.create': 'created an admin account',
  'admin.role_change': 'changed an account role',
  'admin.deactivate': 'deactivated an account',
}

const ACTION_TONE: Record<string, 'success' | 'brand' | 'warning' | 'danger' | 'accent'> = {
  'job.create': 'success',
  'job.publish': 'success',
  'job.expire': 'warning',
  'job.delete': 'danger',
  'report.resolve': 'success',
  'report.dismiss': 'warning',
  'report.reopen': 'danger',
}

/** `2026-08-16T09:12:00Z` → `18 min ago`. */
function ago(iso: string): string {
  const elapsed = Date.now() - Date.parse(iso)
  const minutes = Math.floor(elapsed / 60000)
  if (minutes < 1) return 'just now'
  if (minutes < 60) return `${minutes} min ago`
  const hours = Math.floor(minutes / 60)
  if (hours < 24) return `${hours} hr ago`
  return `${Math.floor(hours / 24)} d ago`
}
import { FField, FormSection, FRow, IS, StatusPill } from '@/components/ui/AdminForm'
import { useToast } from '@/stores/useToastStore'

export default function Dashboard() {
  const showToast = useToast()
  const overview = useAnalyticsOverview()
  const audit = useAuditFeed(7)
  const openReports = useReports({ status: 'open', per_page: 1 })
  const allJobs = useAdminJobs({ per_page: 1 })
  const publishedJobs = useAdminJobs({ per_page: 1, status: 'published' })

  const totals = overview.data?.totals
  const loading = overview.isPending || allJobs.isPending

  /** Counters the dashboard has real numbers for. The mock's per-card change
   *  lines ("+1,240 this month") were invented; where the API cannot supply a
   *  comparison, the card carries a fact it does have. */
  const METRIC_CARDS = [
    { label: 'Total Jobs', value: allJobs.data?.total, change: `${publishedJobs.data?.total ?? 0} published`, trend: 'up' as const, icon: '📋' },
    { label: 'Job Views', value: totals?.job_views, change: 'Last 30 days', trend: 'up' as const, icon: '👀' },
    { label: 'Apply Clicks', value: totals?.apply_clicks, change: overview.data ? `${Math.round((overview.data.rates.view_to_apply ?? 0) * 100)}% of views` : '—', trend: 'up' as const, icon: '👆' },
    { label: 'Searches', value: totals?.searches, change: `${totals?.zero_result_searches ?? 0} with no results`, trend: (totals?.zero_result_searches ? 'warn' : 'up') as 'up' | 'warn', icon: '🔍' },
    { label: 'Saves', value: totals?.saves, change: 'Last 30 days', trend: 'up' as const, icon: '🔖' },
    { label: 'Open Reports', value: openReports.data?.total, change: openReports.data?.total ? 'Need review' : 'Queue clear', trend: (openReports.data?.total ? 'warn' : 'up') as 'up' | 'warn', icon: '🚩' },
  ]

  const TOP_JOBS_TABLE = (overview.data?.top_jobs ?? []).map(j => ({
    title: j.title, company: j.company_name, clicks: j.apply_clicks, views: j.views, saved: 0, status: 'published',
  }))

  const ACTIVITY_FEED = (audit.data?.items ?? []).map(entry => ({
    type: entry.action,
    msg: `${entry.actor?.full_name ?? 'System'} ${ACTION_TEXT[entry.action] ?? entry.action}`,
    time: ago(entry.created_at),
    tone: ACTION_TONE[entry.action] ?? 'brand',
  }))

  const SEARCH_KEYWORDS = (overview.data?.top_queries ?? []).map(q => ({ kw: q.query, count: q.count }))

  if (overview.isError) {
    return <ErrorPanel message={describeError(overview.error)} onRetry={() => void overview.refetch()} />
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 24 }}>
      {/* Metric grid */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: 14 }}>
        {METRIC_CARDS.map(m => (
          <div key={m.label} style={{ background: color.surface.base, border: `1px solid ${color.border.base}`, borderRadius: radius['3xl'], padding: '18px 20px' }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 10 }}>
              <span style={{ fontSize: size.xs, color: color.text.secondary, fontWeight: weight.medium }}>{m.label}</span>
              <span style={{ fontSize: size.lg }}>{m.icon}</span>
            </div>
            <div style={{ fontSize: size['6xl'], fontWeight: weight.extrabold, color: color.text.primary, letterSpacing: tracking.tighter, marginBottom: 4 }}>{loading ? '—' : (m.value ?? 0).toLocaleString()}</div>
            <div style={{ fontSize: size['2xs'], color: m.trend === 'warn' ? color.warning.base : color.success.base, fontWeight: weight.medium }}>
              {m.trend === 'up' ? '↑ ' : '⚠ '}{m.change}
            </div>
          </div>
        ))}
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 300px', gap: 20 }}>
        {/* Top jobs */}
        <div style={{ background: color.surface.base, border: `1px solid ${color.border.base}`, borderRadius: radius['3xl'], overflow: 'hidden' }}>
          <div style={{ padding: '16px 20px', borderBottom: `1px solid ${color.border.base}` }}>
            <div style={{ fontSize: size.base, fontWeight: weight.bold, color: color.text.primary }}>Top Performing Jobs</div>
            <div style={{ fontSize: size.xs, color: color.text.muted, marginTop: 2 }}>by apply clicks this week</div>
          </div>
          <table style={{ width: '100%', borderCollapse: 'collapse' }}>
            <thead>
              <tr style={{ background: color.surface.subtle }}>
                {['Job', 'Views', 'Clicks', 'Saved', 'Status'].map(h => (
                  <th key={h} style={{ padding: '9px 16px', textAlign: 'left', fontSize: size['2xs'], fontWeight: weight.semibold, color: color.text.muted, textTransform: 'uppercase', letterSpacing: tracking.wide }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {TOP_JOBS_TABLE.map((j, i) => (
                <tr key={i} style={{ borderTop: `1px solid ${color.surface.muted}` }}
                  onMouseEnter={e => (e.currentTarget.style.background = color.surface.hover)}
                  onMouseLeave={e => (e.currentTarget.style.background = 'none')}
                >
                  <td style={{ padding: '12px 16px' }}>
                    <div style={{ fontSize: size.sm, fontWeight: weight.semibold, color: color.text.primary }}>{j.title}</div>
                    <div style={{ fontSize: size['2xs'], color: color.text.muted }}>{j.company}</div>
                  </td>
                  <td style={{ padding: '12px 16px', fontSize: size.sm, color: color.text.strong }}>{j.views.toLocaleString()}</td>
                  <td style={{ padding: '12px 16px', fontSize: size.sm, fontWeight: weight.bold, color: color.brand.base }}>{j.clicks}</td>
                  <td style={{ padding: '12px 16px', fontSize: size.sm, color: color.text.strong }}>{j.saved}</td>
                  <td style={{ padding: '12px 16px' }}>
                    <StatusPill status={j.status} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {/* Right column: activity + keywords */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          {/* Activity */}
          <div style={{ background: color.surface.base, border: `1px solid ${color.border.base}`, borderRadius: radius['3xl'], overflow: 'hidden' }}>
            <div style={{ padding: '14px 18px', borderBottom: `1px solid ${color.border.base}`, fontSize: size.sm, fontWeight: weight.bold, color: color.text.primary }}>Recent Activity</div>
            <div style={{ maxHeight: 280, overflowY: 'auto' }}>
              {ACTIVITY_FEED.map((a, i) => (
                <div key={i} style={{ display: 'flex', gap: 10, padding: '12px 18px', borderBottom: i < ACTIVITY_FEED.length - 1 ? `1px solid ${color.surface.subtle}` : 'none', alignItems: 'flex-start' }}>
                  <span style={{ width: 8, height: 8, borderRadius: radius.full, background: activityTone[a.tone], marginTop: 5, flexShrink: 0 }} />
                  <div>
                    <p style={{ margin: 0, fontSize: size.xs, color: color.text.strong, lineHeight: 1.4 }}>{a.msg}</p>
                    <p style={{ margin: '2px 0 0', fontSize: size['2xs'], color: color.text.muted }}>{a.time}</p>
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Top keywords */}
          <div style={{ background: color.surface.base, border: `1px solid ${color.border.base}`, borderRadius: radius['3xl'], overflow: 'hidden' }}>
            <div style={{ padding: '14px 18px', borderBottom: `1px solid ${color.border.base}`, fontSize: size.sm, fontWeight: weight.bold, color: color.text.primary }}>Top Search Keywords</div>
            <div style={{ padding: '12px 18px', display: 'flex', flexDirection: 'column', gap: 10 }}>
              {SEARCH_KEYWORDS.map(k => (
                <div key={k.kw}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4, fontSize: size.xs }}>
                    <span style={{ color: color.text.strong, fontWeight: weight.medium }}>{k.kw}</span>
                    <span style={{ color: color.text.muted }}>{k.count.toLocaleString()}</span>
                  </div>
                  <div style={{ height: 4, background: color.surface.muted, borderRadius: radius.xxs }}>
                    <div style={{ height: '100%', background: color.brand.base, borderRadius: radius.xxs, width: `${(k.count / 4000) * 100}%`, transition: 'width 0.4s' }} />
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>

      {/* Traffic quick stats */}
      <div style={{ background: color.surface.base, border: `1px solid ${color.border.base}`, borderRadius: radius['3xl'], padding: '20px 24px' }}>
        <div style={{ fontSize: size.sm, fontWeight: weight.bold, color: color.text.primary, marginBottom: 16 }}>Traffic Overview</div>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 0, borderLeft: `1px solid ${color.border.base}` }}>
          {[
            { label: 'Daily Visitors', value: '6,240', sub: 'Avg. 3.2 pages/session' },
            { label: 'Weekly Visitors', value: '38,480', sub: '+8.4% vs last week' },
            { label: 'Monthly Visitors', value: '162,000', sub: '+14.2% vs last month' },
          ].map((s, i) => (
            <div key={i} style={{ padding: '0 24px', borderRight: `1px solid ${color.border.base}` }}>
              <div style={{ fontSize: size['2xs'], color: color.text.muted, fontWeight: weight.semibold, textTransform: 'uppercase', letterSpacing: tracking.wide, marginBottom: 6 }}>{s.label}</div>
              <div style={{ fontSize: size['5xl'], fontWeight: weight.extrabold, color: color.text.primary, letterSpacing: tracking.tighter, marginBottom: 2 }}>{s.value}</div>
              <div style={{ fontSize: size['2xs'], color: color.success.base, fontWeight: weight.medium }}>{s.sub}</div>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}

