import { useState } from 'react'
import { actionTone, adminStatusTone, color, fontFamily, pillTone, radius, shadow, size, tracking, weight } from '@/design-system'
import { FField, FormSection, FRow, IS, StatusPill } from '@/components/ui/AdminForm'
import { useToast } from '@/stores/useToastStore'
import { IconBadge } from '@/components/Icon'

export default function SettingsSection() {
  const showToast = useToast()
  const [tab, setTab] = useState('site')
  const TABS = [
    { k: 'site', label: 'Site Settings' },
    { k: 'branding', label: 'Branding' },
    { k: 'seo', label: 'SEO Defaults' },
    { k: 'social', label: 'Social Links' },
  ]
  const [site, setSite] = useState({ name: 'Plenilo.com', tagline: "Trusted job discovery, worldwide", email: 'hello@plenilo.com', phone: '+00 000 0000000' })
  const [seo, setSeo] = useState({ title: 'Plenilo.com – Find Jobs Worldwide', desc: 'Browse thousands of verified job listings worldwide. Remote, hybrid and on-site opportunities.', keywords: 'jobs worldwide, remote jobs, global job search, tech jobs' })

  return (
    <div style={{ maxWidth: 680 }}>
      {/* Tab bar */}
      <div style={{ display: 'flex', gap: 2, marginBottom: 20, background: color.surface.base, border: `1px solid ${color.border.base}`, borderRadius: radius['2xl'], padding: 4, width: 'fit-content' }}>
        {TABS.map(t => (
          <button key={t.k} onClick={() => setTab(t.k)} style={{
            padding: '7px 16px', border: 'none', borderRadius: radius.lg, cursor: 'pointer',
            fontSize: size.sm, fontWeight: weight.medium,
            background: tab === t.k ? color.brand.base : 'transparent',
            color: tab === t.k ? color.surface.base : color.text.secondary,
          }}>{t.label}</button>
        ))}
      </div>

      <div style={{ background: color.surface.base, border: `1px solid ${color.border.base}`, borderRadius: radius['5xl'], padding: '28px 32px', display: 'flex', flexDirection: 'column', gap: 20 }}>
        {tab === 'site' && (
          <>
            <FField label="Site Name"><input value={site.name} onChange={e => setSite(p => ({ ...p, name: e.target.value }))} style={IS} /></FField>
            <FField label="Tagline"><input value={site.tagline} onChange={e => setSite(p => ({ ...p, tagline: e.target.value }))} style={IS} /></FField>
            <FField label="Contact Email"><input value={site.email} onChange={e => setSite(p => ({ ...p, email: e.target.value }))} type="email" style={IS} /></FField>
            <FField label="Phone Number"><input value={site.phone} onChange={e => setSite(p => ({ ...p, phone: e.target.value }))} style={IS} /></FField>
          </>
        )}
        {tab === 'branding' && (
          <>
            <FField label="Logo">
              <div style={{ border: `2px dashed ${color.border.base}`, borderRadius: radius['2xl'], padding: '24px', textAlign: 'center', cursor: 'pointer' }}>
                <div style={{ display: 'flex', justifyContent: 'center', marginBottom: 8 }}>
                  <IconBadge name='folder' size='md' />
                </div>
                <div style={{ fontSize: size.sm, color: color.text.secondary }}>Drag & drop or click to upload</div>
                <div style={{ fontSize: size['2xs'], color: color.text.muted, marginTop: 4 }}>SVG, PNG up to 2MB</div>
              </div>
            </FField>
            <FField label="Primary Color">
              <div style={{ display: 'flex', gap: 10, alignItems: 'center' }}>
                <input type="color" defaultValue={color.brand.base} style={{ width: 48, height: 40, border: `1px solid ${color.border.base}`, borderRadius: radius.md, cursor: 'pointer', padding: 2 }} />
                <input defaultValue={color.brand.base} style={{ ...IS, flex: 1, fontFamily: 'monospace' }} />
              </div>
            </FField>
          </>
        )}
        {tab === 'seo' && (
          <>
            <FField label="Default Page Title"><input value={seo.title} onChange={e => setSeo(p => ({ ...p, title: e.target.value }))} style={IS} /></FField>
            <FField label="Meta Description"><textarea value={seo.desc} onChange={e => setSeo(p => ({ ...p, desc: e.target.value }))} rows={3} style={{ ...IS, resize: 'vertical' }} /></FField>
            <FField label="Default Keywords"><input value={seo.keywords} onChange={e => setSeo(p => ({ ...p, keywords: e.target.value }))} style={IS} /></FField>
          </>
        )}
        {tab === 'social' && (
          <>
            {[
              { label: 'Facebook', placeholder: 'https://facebook.com/plenilo' },
              { label: 'LinkedIn', placeholder: 'https://linkedin.com/company/plenilo' },
              { label: 'Twitter / X', placeholder: 'https://x.com/plenilo' },
              { label: 'Instagram', placeholder: 'https://instagram.com/plenilo' },
            ].map(s => (
              <FField key={s.label} label={s.label}>
                <input placeholder={s.placeholder} style={IS} />
              </FField>
            ))}
          </>
        )}

        {/* There is no settings endpoint yet, so this button cannot do anything
            a reload would keep. It stays visible and disabled rather than
            reporting a success the server never returned. */}
        <div style={{ paddingTop: 8, borderTop: `1px solid ${color.surface.muted}` }}>
          <button
            disabled
            title="Site settings are not stored yet"
            style={{ padding: '10px 24px', background: color.surface.muted, border: `1px solid ${color.border.base}`, borderRadius: radius.xl, color: color.text.muted, fontSize: size.base, fontWeight: weight.semibold, cursor: 'not-allowed' }}
          >
            Save Changes
          </button>
          <div style={{ fontSize: size.xs, color: color.text.muted, marginTop: 8 }}>
            These fields are not saved anywhere yet — the site-settings API has not been
            built. Nothing typed here survives a reload.
          </div>
        </div>
      </div>
    </div>
  )
}

