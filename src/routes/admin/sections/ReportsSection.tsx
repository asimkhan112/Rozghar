import { useState } from 'react'
import { actionTone, adminStatusTone, color, fontFamily, pillTone, radius, shadow, size, tracking, weight } from '@/design-system'
import { useToast } from '@/stores/useToastStore'
import { useExpireJob, useModerateReport, useReports } from '@/hooks/queries'
import { describeError } from '@/lib/http'
import { EmptyPanel, ErrorPanel } from '@/components/QueryState'
import { formatDate } from '@/lib/format'

/** The API's reason values, with the wording a moderator reads. */
const REASON_LABEL: Record<string, string> = {
  broken_link: 'Broken Link',
  suspicious: 'Suspicious',
  expired: 'Expired',
  incorrect_information: 'Incorrect Information',
  duplicate: 'Duplicate',
  other: 'Other',
}

export default function ReportsSection() {
  const showToast = useToast()
  // The open queue. Resolved reports leave it server-side, so there is no
  // local "resolved" list to keep in step with the server's own view.
  const open = useReports({ status: 'open', per_page: 50 })
  const resolvedQuery = useReports({ status: 'resolved', per_page: 1 })
  const moderate = useModerateReport()
  const expire = useExpireJob()
  const [busy, setBusy] = useState<string | null>(null)

  const REASON_COLORS: Record<string, string> = {
    broken_link: color.danger.base, suspicious: color.accent.purple, expired: color.warning.base, incorrect_information: color.info.base, duplicate: color.text.secondary, other: color.text.secondary,
  }

  const pending = (open.data?.items ?? []).map(r => ({
    id: r.id,
    jobId: r.job.id,
    job: r.job.title,
    company: r.job.company_name,
    reason: REASON_LABEL[r.reason] ?? r.reason,
    category: r.reason,
    comment: r.comment ?? '',
    date: formatDate(r.created_at.split('T')[0] ?? null),
  }))
  const resolved = { length: resolvedQuery.data?.total ?? 0 }

  async function act(id: string, label: string, action: () => Promise<unknown>) {
    setBusy(id)
    try {
      await action()
      showToast(label)
    } catch (err) {
      showToast(describeError(err))
    } finally {
      setBusy(null)
    }
  }

  if (open.isError) {
    return <ErrorPanel message={describeError(open.error)} onRetry={() => void open.refetch()} />
  }

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
          {pending.map(r => (
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
                  <button
                    disabled={busy === r.id}
                    onClick={() => void act(r.id, 'Report resolved', () =>
                      moderate.mutateAsync({
                        id: r.id,
                        changes: { status: 'resolved', resolution_note: 'Reviewed and resolved from the moderation queue.' },
                      }),
                    )}
                    style={{ padding: '7px 14px', border: `1px solid ${color.success.border}`, background: color.success.tintAlt, color: color.success.text, borderRadius: radius.lg, fontSize: size.xs, fontWeight: weight.semibold, cursor: 'pointer' }}>
                    ✓ Resolve
                  </button>
                  <button
                    disabled={busy === r.id}
                    onClick={() => void act(r.id, 'Listing expired', async () => {
                      await expire.mutateAsync({ id: r.jobId, reason: 'Expired following a user report' })
                      await moderate.mutateAsync({
                        id: r.id,
                        changes: { status: 'resolved', resolution_note: 'Listing expired following this report.' },
                      })
                    })}
                    style={{ padding: '7px 14px', border: `1px solid ${color.warning.tintSoft}`, background: color.warning.tintAlt, color: color.warning.amber, borderRadius: radius.lg, fontSize: size.xs, fontWeight: weight.medium, cursor: 'pointer' }}>Expire</button>
                  <button
                    disabled={busy === r.id}
                    onClick={() => void act(r.id, 'Report dismissed', () =>
                      moderate.mutateAsync({
                        id: r.id,
                        changes: { status: 'dismissed', resolution_note: 'Dismissed — no action needed.' },
                      }),
                    )}
                    style={{ padding: '7px 14px', border: `1px solid ${color.danger.border}`, background: color.danger.tint, color: color.danger.base, borderRadius: radius.lg, fontSize: size.xs, fontWeight: weight.medium, cursor: 'pointer' }}>Dismiss</button>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

