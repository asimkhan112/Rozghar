import { useState } from 'react'
import { actionTone, adminStatusTone, color, fontFamily, pillTone, radius, shadow, size, tracking, weight } from '@/design-system'
import { useLocations } from '@/hooks/queries'
import { describeError } from '@/lib/http'
import { ErrorPanel } from '@/components/QueryState'
import { FField, FormSection, FRow, IS, StatusPill } from '@/components/ui/AdminForm'
import { useToast } from '@/stores/useToastStore'

export default function LocationsSection() {
  const showToast = useToast()
  const { data, isError, error, refetch } = useLocations()
  const LOCATIONS = (data ?? []).map(l => {
    const [city, region] = l.label.split(',').map(part => part.trim())
    return {
      name: city ?? l.label,
      region: region ?? '—',
      type: l.slug.startsWith('remote') ? 'Remote' : 'City',
      jobs: l.count,
    }
  })

  if (isError) {
    return <ErrorPanel message={describeError(error)} onRetry={() => void refetch()} />
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
        <button onClick={() => showToast('Location added')} style={{ padding: '8px 16px', background: color.brand.base, border: 'none', borderRadius: radius.xl, color: color.surface.base, fontSize: size.sm, fontWeight: weight.medium, cursor: 'pointer' }}>+ Add Location</button>
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))', gap: 12 }}>
        {LOCATIONS.map((l, i) => (
          <div key={i} style={{ background: color.surface.base, border: `1px solid ${color.border.base}`, borderRadius: radius['3xl'], padding: '16px 20px', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
            <div>
              <div style={{ fontSize: size.base, fontWeight: weight.semibold, color: color.text.primary, marginBottom: 2 }}>{l.name}</div>
              <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
                <span style={{ fontSize: size['2xs'], color: color.text.muted }}>{l.region}</span>
                <span style={{ width: 3, height: 3, borderRadius: radius.full, background: color.text.disabled }} />
                <span style={{ fontSize: size['2xs'], padding: '1px 6px', borderRadius: radius.sm, background: l.type === 'Remote' ? color.brand.tint : color.surface.subtle, color: l.type === 'Remote' ? color.brand.base : color.text.secondary, fontWeight: weight.medium }}>{l.type}</span>
              </div>
            </div>
            <div style={{ textAlign: 'right' }}>
              <div style={{ fontSize: size.lg, fontWeight: weight.bold, color: color.text.primary }}>{l.jobs.toLocaleString()}</div>
              <div style={{ fontSize: size['2xs'], color: color.text.muted }}>jobs</div>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

