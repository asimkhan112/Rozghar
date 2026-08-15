import { useState } from 'react'
import { actionTone, adminStatusTone, color, fontFamily, pillTone, radius, shadow, size, tracking, weight } from '@/design-system'
import { ACTIVITY_FEED, CATEGORIES_DATA, CONVERSION_DATA, LOCATIONS_DATA, METRIC_CARDS, REPORTS_DATA, SEARCH_KEYWORDS, SOURCES_DATA, TOP_JOBS_TABLE, TOP_LOCATION_SHARE } from '@/data/admin.mock'
import { FField, FormSection, FRow, IS, StatusPill } from '@/components/ui/AdminForm'
import { useToast } from '@/stores/useToastStore'

export default function AddJobSection() {
  const showToast = useToast()
  const [form, setForm] = useState({ title: '', company: '', category: '', location: '', workType: 'On-site', employmentType: 'Full-time', experience: '', salary: '', description: '', requirements: '', responsibilities: '', benefits: '', sourceUrl: '', publishMode: 'publish', expiry: '' })
  const [step, setStep] = useState(0)
  const up = (k: string, v: string) => setForm(p => ({ ...p, [k]: v }))
  const STEPS = ['Basic Info', 'Job Details', 'Content', 'Source & Publish']

  const handleSubmit = () => {
    showToast(form.publishMode === 'draft' ? 'Job saved as draft' : form.publishMode === 'schedule' ? 'Job scheduled for publishing' : 'Job published successfully!')
    setForm({ title: '', company: '', category: '', location: '', workType: 'On-site', employmentType: 'Full-time', experience: '', salary: '', description: '', requirements: '', responsibilities: '', benefits: '', sourceUrl: '', publishMode: 'publish', expiry: '' })
    setStep(0)
  }

  return (
    <div style={{ maxWidth: 720 }}>
      {/* Step indicator */}
      <div style={{ display: 'flex', gap: 0, marginBottom: 28, background: color.surface.base, border: `1px solid ${color.border.base}`, borderRadius: radius['2xl'], overflow: 'hidden' }}>
        {STEPS.map((s, i) => (
          <button key={s} onClick={() => setStep(i)} style={{
            flex: 1, padding: '11px 8px', border: 'none', cursor: 'pointer', fontSize: size.sm, fontWeight: weight.medium,
            background: step === i ? color.brand.base : step > i ? color.brand.tint : 'transparent',
            color: step === i ? color.surface.base : step > i ? color.brand.base : color.text.muted,
            borderRight: i < STEPS.length - 1 ? `1px solid ${color.border.base}` : 'none',
            transition: 'all 0.15s',
          }}>
            <span style={{ display: 'block', fontSize: size['3xs'], opacity: 0.7, marginBottom: 1 }}>Step {i + 1}</span>
            {s}
          </button>
        ))}
      </div>

      <div style={{ background: color.surface.base, border: `1px solid ${color.border.base}`, borderRadius: radius['5xl'], padding: '28px 32px' }}>
        {step === 0 && (
          <FormSection title="Basic Information" subtitle="Core details about the job listing">
            <FRow><FField label="Job Title *"><input value={form.title} onChange={e => up('title', e.target.value)} placeholder="e.g. Senior Software Engineer" style={IS} /></FField></FRow>
            <FRow cols={2}><FField label="Company Name *"><input value={form.company} onChange={e => up('company', e.target.value)} placeholder="e.g. Systems Limited" style={IS} /></FField>
            <FField label="Category *">
              <select value={form.category} onChange={e => up('category', e.target.value)} style={IS}>
                <option value="">Select category</option>
                {['IT & Technology', 'Design', 'Finance & Accounting', 'Marketing', 'Human Resources', 'Government', 'Data & Analytics', 'Content & Writing'].map(c => <option key={c}>{c}</option>)}
              </select>
            </FField></FRow>
            <FRow><FField label="Location *"><input value={form.location} onChange={e => up('location', e.target.value)} placeholder="e.g. Lahore, Pakistan or Remote" style={IS} /></FField></FRow>
          </FormSection>
        )}
        {step === 1 && (
          <FormSection title="Job Details" subtitle="Work arrangement and compensation">
            <FRow cols={2}>
              <FField label="Work Type"><select value={form.workType} onChange={e => up('workType', e.target.value)} style={IS}><option>On-site</option><option>Remote</option><option>Hybrid</option></select></FField>
              <FField label="Employment Type"><select value={form.employmentType} onChange={e => up('employmentType', e.target.value)} style={IS}><option>Full-time</option><option>Part-time</option><option>Contract</option><option>Internship</option></select></FField>
            </FRow>
            <FRow cols={2}>
              <FField label="Experience Level"><input value={form.experience} onChange={e => up('experience', e.target.value)} placeholder="e.g. 3–5 years" style={IS} /></FField>
              <FField label="Salary Range"><input value={form.salary} onChange={e => up('salary', e.target.value)} placeholder="e.g. PKR 150,000 – 250,000/mo" style={IS} /></FField>
            </FRow>
          </FormSection>
        )}
        {step === 2 && (
          <FormSection title="Content" subtitle="Job description and requirements">
            <FRow><FField label="Description *"><textarea value={form.description} onChange={e => up('description', e.target.value)} placeholder="Describe the role, team, and company…" rows={5} style={{ ...IS, resize: 'vertical' }} /></FField></FRow>
            <FRow cols={2}>
              <FField label="Requirements"><textarea value={form.requirements} onChange={e => up('requirements', e.target.value)} placeholder="One per line" rows={4} style={{ ...IS, resize: 'vertical' }} /></FField>
              <FField label="Responsibilities"><textarea value={form.responsibilities} onChange={e => up('responsibilities', e.target.value)} placeholder="One per line" rows={4} style={{ ...IS, resize: 'vertical' }} /></FField>
            </FRow>
            <FRow><FField label="Benefits"><input value={form.benefits} onChange={e => up('benefits', e.target.value)} placeholder="e.g. Medical insurance, Remote Fridays…" style={IS} /></FField></FRow>
          </FormSection>
        )}
        {step === 3 && (
          <FormSection title="Source & Publishing" subtitle="Where the job was found and how to publish">
            <FRow><FField label="Apply URL *"><input value={form.sourceUrl} onChange={e => up('sourceUrl', e.target.value)} placeholder="https://company.com/careers/job-id" type="url" style={IS} /></FField></FRow>
            <FRow><FField label="Expiry Date"><input value={form.expiry} onChange={e => up('expiry', e.target.value)} type="date" style={IS} /></FField></FRow>
            <FRow>
              <FField label="Publishing Mode">
                <div style={{ display: 'flex', gap: 10 }}>
                  {[{ k: 'publish', label: 'Publish Now' }, { k: 'draft', label: 'Save as Draft' }, { k: 'schedule', label: 'Schedule' }].map(m => (
                    <label key={m.k} style={{ display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer', flex: 1, padding: '10px 14px', border: `1px solid ${form.publishMode === m.k ? color.brand.base : color.border.base}`, borderRadius: radius.xl, background: form.publishMode === m.k ? color.brand.tint : color.surface.base }}>
                      <input type="radio" name="mode" checked={form.publishMode === m.k} onChange={() => up('publishMode', m.k)} style={{ accentColor: color.brand.base }} />
                      <span style={{ fontSize: size.sm, fontWeight: weight.medium, color: form.publishMode === m.k ? color.brand.base : color.text.strong }}>{m.label}</span>
                    </label>
                  ))}
                </div>
              </FField>
            </FRow>
          </FormSection>
        )}

        {/* Navigation */}
        <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 24, paddingTop: 20, borderTop: `1px solid ${color.surface.muted}` }}>
          <button onClick={() => setStep(s => Math.max(0, s - 1))} disabled={step === 0}
            style={{ padding: '10px 20px', border: `1px solid ${color.border.base}`, borderRadius: radius.xl, background: color.surface.base, fontSize: size.base, color: step === 0 ? color.text.disabled : color.text.strong, cursor: step === 0 ? 'not-allowed' : 'pointer', fontWeight: weight.medium }}>
            ← Previous
          </button>
          {step < 3 ? (
            <button onClick={() => setStep(s => s + 1)}
              style={{ padding: '10px 24px', border: 'none', borderRadius: radius.xl, background: color.brand.base, fontSize: size.base, color: color.surface.base, cursor: 'pointer', fontWeight: weight.medium }}>
              Next →
            </button>
          ) : (
            <button onClick={handleSubmit}
              style={{ padding: '10px 24px', border: 'none', borderRadius: radius.xl, background: color.brand.base, fontSize: size.base, color: color.surface.base, cursor: 'pointer', fontWeight: weight.semibold }}>
              {form.publishMode === 'draft' ? 'Save Draft' : form.publishMode === 'schedule' ? 'Schedule Job' : 'Publish Job'}
            </button>
          )}
        </div>
      </div>
    </div>
  )
}

