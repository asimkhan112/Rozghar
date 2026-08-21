import { useState } from 'react'
import { color, radius, size, weight } from '@/design-system'
import { useAdminLocations, useCountries, useCreateLocation, useUpdateLocation } from '@/hooks/queries'
import { describeError } from '@/lib/http'
import { ErrorPanel } from '@/components/QueryState'
import { FField, IS } from '@/components/ui/AdminForm'
import { useToast } from '@/stores/useToastStore'

export default function LocationsSection() {
  const showToast = useToast()
  // The admin projection, so an archived location can still be restored.
  const { data, isPending, isError, error, refetch } = useAdminLocations()
  const createLocation = useCreateLocation()
  const updateLocation = useUpdateLocation()
  const countries = useCountries()

  const [adding, setAdding] = useState(false)
  const [city, setCity] = useState('')
  const [region, setRegion] = useState('')
  // No default. A pre-selected country is how every location in the catalogue
  // ended up in one place — an editor in a hurry accepts whatever is already
  // there. An empty value forces the choice to be made.
  const [country, setCountry] = useState('')
  const [busy, setBusy] = useState<string | null>(null)

  const locations = data ?? []

  /** Code -> readable name, for the cards. Rows store `PK`; nobody reads that. */
  const countryName = new Map((countries.data ?? []).map(c => [c.code, c.name]))

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

  const canSave = Boolean(city.trim() && country)

  const save = async () => {
    const name = city.trim()
    if (!canSave) return
    const ok = await run(
      'create',
      () => createLocation.mutateAsync({
        city: name,
        region: region.trim() || undefined,
        country,
      }),
      `${name}, ${countryName.get(country) ?? country} added`,
    )
    if (ok) {
      setCity('')
      setRegion('')
      setCountry('')
      setAdding(false)
    }
  }

  if (isError) {
    return <ErrorPanel message={describeError(error)} onRetry={() => void refetch()} />
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
        <button onClick={() => setAdding(!adding)} style={{ padding: '8px 16px', background: color.brand.base, border: 'none', borderRadius: radius.xl, color: color.surface.base, fontSize: size.sm, fontWeight: weight.medium, cursor: 'pointer' }}>+ Add Location</button>
      </div>

      {adding && (
        <div style={{ background: color.surface.base, border: `1px solid ${color.brand.alpha40}`, borderRadius: radius['3xl'], padding: '20px 24px', display: 'flex', gap: 12, alignItems: 'flex-end' }}>
          <FField label="City" style={{ flex: 1 }}>
            <input value={city} onChange={e => setCity(e.target.value)} onKeyDown={e => e.key === 'Enter' && void save()} autoFocus placeholder="e.g. Berlin" style={IS} />
          </FField>
          <FField label="State / Province / Region" style={{ flex: 1 }}>
            <input value={region} onChange={e => setRegion(e.target.value)} onKeyDown={e => e.key === 'Enter' && void save()} placeholder="e.g. Bavaria (optional)" style={IS} />
          </FField>
          <FField label="Country" style={{ flex: 1 }}>
            <select
              value={country}
              onChange={e => setCountry(e.target.value)}
              disabled={countries.isPending}
              style={IS}
            >
              <option value="">
                {countries.isPending ? 'Loading…' : countries.isError ? 'Unavailable' : 'Select a country…'}
              </option>
              {(countries.data ?? []).map(c => (
                <option key={c.code} value={c.code}>{c.name}</option>
              ))}
            </select>
          </FField>
          <button onClick={() => void save()} disabled={!canSave || busy === 'create'} style={{ padding: '10px 20px', background: color.brand.base, border: 'none', borderRadius: radius.xl, color: color.surface.base, fontSize: size.sm, fontWeight: weight.medium, cursor: canSave ? 'pointer' : 'not-allowed', opacity: canSave ? 1 : 0.5, flexShrink: 0 }}>
            {busy === 'create' ? 'Saving…' : 'Save'}
          </button>
          <button onClick={() => setAdding(false)} style={{ padding: '10px 16px', border: `1px solid ${color.border.base}`, borderRadius: radius.xl, background: color.surface.base, color: color.text.secondary, fontSize: size.sm, cursor: 'pointer', flexShrink: 0 }}>Cancel</button>
        </div>
      )}

      {isPending && <div style={{ fontSize: size.sm, color: color.text.muted }}>Loading locations…</div>}

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))', gap: 12 }}>
        {locations.map(l => (
          <div key={l.id} style={{ background: color.surface.base, border: `1px solid ${color.border.base}`, borderRadius: radius['3xl'], padding: '16px 20px', display: 'flex', alignItems: 'center', justifyContent: 'space-between', opacity: l.is_active ? 1 : 0.55 }}>
            <div style={{ minWidth: 0 }}>
              <div style={{ fontSize: size.base, fontWeight: weight.semibold, color: color.text.primary, marginBottom: 2 }}>{l.city ?? l.display_name}</div>
              <div style={{ display: 'flex', gap: 6, alignItems: 'center', flexWrap: 'wrap' }}>
                <span style={{ fontSize: size['2xs'], color: color.text.muted }}>
                  {[l.region, countryName.get(l.country) ?? l.country].filter(Boolean).join(' · ') || '—'}
                </span>
                <span style={{ width: 3, height: 3, borderRadius: radius.full, background: color.text.disabled }} />
                <span style={{ fontSize: size['2xs'], padding: '1px 6px', borderRadius: radius.sm, background: l.is_remote ? color.brand.tint : color.surface.subtle, color: l.is_remote ? color.brand.base : color.text.secondary, fontWeight: weight.medium }}>{l.is_remote ? 'Remote' : 'City'}</span>
                {!l.is_active && (
                  <span style={{ fontSize: size['2xs'], padding: '1px 6px', borderRadius: radius.sm, background: color.surface.muted, color: color.text.muted, fontWeight: weight.medium }}>Archived</span>
                )}
              </div>
              <button
                onClick={() => void run(
                  l.id,
                  () => updateLocation.mutateAsync({ id: l.id, changes: { is_active: !l.is_active } }),
                  l.is_active ? `${l.display_name} archived` : `${l.display_name} restored`,
                )}
                disabled={busy === l.id}
                style={{ marginTop: 8, fontSize: size['2xs'], padding: '3px 9px', border: `1px solid ${color.border.base}`, borderRadius: radius.smd, background: color.surface.base, color: color.text.secondary, cursor: 'pointer' }}
              >
                {busy === l.id ? '…' : l.is_active ? 'Archive' : 'Restore'}
              </button>
            </div>
            <div style={{ textAlign: 'right', flexShrink: 0 }}>
              <div style={{ fontSize: size.lg, fontWeight: weight.bold, color: color.text.primary }}>{l.job_count.toLocaleString()}</div>
              <div style={{ fontSize: size['2xs'], color: color.text.muted }}>jobs</div>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
