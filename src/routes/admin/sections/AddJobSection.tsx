import { useState } from 'react'
import { useNavigate } from 'react-router'
import { color, radius, size, weight } from '@/design-system'
import { FField, FormSection, FRow, IS } from '@/components/ui/AdminForm'
import { useToast } from '@/stores/useToastStore'
import { useCategories, useCreateJob, useLocations, usePublishJob } from '@/hooks/queries'
import { ApiError, describeError } from '@/lib/http'
import type { JobWriteDto } from '@/lib/api/admin-types'

const WORK_TYPE = { 'On-site': 'on_site', Remote: 'remote', Hybrid: 'hybrid' } as const
const EMPLOYMENT_TYPE = {
  'Full-time': 'full_time',
  'Part-time': 'part_time',
  Contract: 'contract',
  Internship: 'internship',
} as const

/** The API's seniority levels, with the wording an editor reads. */
const EXPERIENCE_LEVELS = [
  ['intern', 'Internship'],
  ['entry', 'Entry level'],
  ['mid', 'Mid level'],
  ['senior', 'Senior level'],
  ['lead', 'Lead'],
  ['executive', 'Executive'],
] as const

const EMPTY = {
  title: '', company: '', categoryId: '', locationId: '',
  workType: 'On-site', employmentType: 'Full-time', experienceLevel: 'mid',
  salaryMin: '', salaryMax: '', description: '', requirements: '',
  responsibilities: '', benefits: '', sourceUrl: '', publishMode: 'publish', expiry: '',
}

/** Which step holds each field the API can reject. */
const STEP_FOR_FIELD: Record<string, number> = {
  title: 0, company_name: 0, category_id: 0, location_id: 0,
  work_type: 1, employment_type: 1, experience_level: 1,
  salary_min: 1, salary_max: 1,
  description: 2, requirements: 2, responsibilities: 2, benefits: 2,
  apply_url: 3, expiry_date: 3, status: 3,
}

/** Textareas collect one item per line; the API takes arrays. */
function toList(value: string): string[] {
  return value.split('\n').map(line => line.trim()).filter(Boolean)
}

export default function AddJobSection() {
  const showToast = useToast()
  const navigate = useNavigate()
  const categories = useCategories()
  const locations = useLocations()
  const createJob = useCreateJob()
  const publishJob = usePublishJob()

  const [form, setForm] = useState({ ...EMPTY })
  const [step, setStep] = useState(0)
  /** Field-level messages from a 422, keyed by the API's field names. */
  const [fieldErrors, setFieldErrors] = useState<Record<string, string[]>>({})
  const up = (k: string, v: string) => setForm(p => ({ ...p, [k]: v }))
  const STEPS = ['Basic Info', 'Job Details', 'Content', 'Source & Publish']

  const submitting = createJob.isPending || publishJob.isPending

  /** The first message for a field, if the server rejected it. */
  const errorFor = (field: string) => fieldErrors[field]?.[0]

  const handleSubmit = async () => {
    setFieldErrors({})

    const body: JobWriteDto = {
      title: form.title.trim(),
      company_name: form.company.trim(),
      category_id: form.categoryId,
      location_id: form.locationId,
      work_type: WORK_TYPE[form.workType as keyof typeof WORK_TYPE],
      employment_type: EMPLOYMENT_TYPE[form.employmentType as keyof typeof EMPLOYMENT_TYPE],
      experience_level: form.experienceLevel as JobWriteDto['experience_level'],
      salary_min: form.salaryMin ? Number(form.salaryMin) : null,
      salary_max: form.salaryMax ? Number(form.salaryMax) : null,
      // A listing with no figure is marked undisclosed rather than sent as a
      // zero — the API distinguishes the two and the public site says so.
      salary_is_disclosed: Boolean(form.salaryMin || form.salaryMax),
      description: form.description.trim(),
      requirements: toList(form.requirements),
      responsibilities: toList(form.responsibilities),
      benefits: toList(form.benefits),
      apply_url: form.sourceUrl.trim(),
      expiry_date: form.expiry || null,
      // "Schedule" creates a draft and then publishes it with a future
      // timestamp, because publishing is a separate audited action.
      status: form.publishMode === 'publish' ? 'published' : 'draft',
    }

    try {
      const created = await createJob.mutateAsync(body)

      if (form.publishMode === 'schedule' && form.expiry) {
        await publishJob.mutateAsync({ id: created.id, scheduledAt: form.expiry })
      }

      showToast(
        form.publishMode === 'draft'
          ? `Saved “${created.title}” as a draft`
          : form.publishMode === 'schedule'
            ? `Scheduled “${created.title}”`
            : `Published “${created.title}”`,
      )
      setForm({ ...EMPTY })
      setStep(0)
      navigate('/admin/dashboard/jobs')
    } catch (err) {
      if (err instanceof ApiError && Object.keys(err.fieldErrors).length > 0) {
        setFieldErrors(err.fieldErrors)
        // Send the editor to the step that actually holds the rejected field,
        // rather than showing an error next to a form they cannot see.
        const first = Object.keys(err.fieldErrors)[0] ?? ''
        setStep(STEP_FOR_FIELD[first] ?? step)
      }
      showToast(describeError(err))
    }
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
              {/* Ids, not names: the API needs a category that exists, and a
                  free-text field can only produce one that might not. */}
              <select value={form.categoryId} onChange={e => up('categoryId', e.target.value)} style={IS}>
                <option value="">{categories.isPending ? 'Loading…' : 'Select category'}</option>
                {(categories.data ?? []).map(c => <option key={c.slug} value={c.id}>{c.name}</option>)}
              </select>
              <FieldError message={errorFor('category_id')} />
            </FField></FRow>
            <FRow><FField label="Location *">
              <select value={form.locationId} onChange={e => up('locationId', e.target.value)} style={IS}>
                <option value="">{locations.isPending ? 'Loading…' : 'Select location'}</option>
                {(locations.data ?? []).map(l => <option key={l.slug} value={l.id}>{l.label}</option>)}
              </select>
              <FieldError message={errorFor('location_id')} />
            </FField></FRow>
          </FormSection>
        )}
        {step === 1 && (
          <FormSection title="Job Details" subtitle="Work arrangement and compensation">
            <FRow cols={2}>
              <FField label="Work Type"><select value={form.workType} onChange={e => up('workType', e.target.value)} style={IS}><option>On-site</option><option>Remote</option><option>Hybrid</option></select></FField>
              <FField label="Employment Type"><select value={form.employmentType} onChange={e => up('employmentType', e.target.value)} style={IS}><option>Full-time</option><option>Part-time</option><option>Contract</option><option>Internship</option></select></FField>
            </FRow>
            <FRow cols={2}>
              <FField label="Experience Level">
                <select value={form.experienceLevel} onChange={e => up('experienceLevel', e.target.value)} style={IS}>
                  {EXPERIENCE_LEVELS.map(([value, label]) => (
                    <option key={value} value={value}>{label}</option>
                  ))}
                </select>
              </FField>
              {/* Two numbers rather than one free-text range. The site sorts
                  and filters on salary, which a formatted string cannot do —
                  and the old single field was discarded entirely. */}
              <FField label="Salary (PKR / month)">
                <div style={{ display: 'flex', gap: 8 }}>
                  <input value={form.salaryMin} onChange={e => up('salaryMin', e.target.value)} placeholder="Minimum" type="number" min="0" style={IS} />
                  <input value={form.salaryMax} onChange={e => up('salaryMax', e.target.value)} placeholder="Maximum" type="number" min="0" style={IS} />
                </div>
                <FieldError message={errorFor('salary_max') ?? errorFor('salary_min')} />
              </FField>
            </FRow>
          </FormSection>
        )}
        {step === 2 && (
          <FormSection title="Content" subtitle="Job description and requirements">
            <FRow><FField label="Description *"><textarea value={form.description} onChange={e => up('description', e.target.value)} placeholder="Describe the role, team, and company… (at least 50 characters)" rows={5} style={{ ...IS, resize: 'vertical' }} />
              <FieldError message={errorFor('description')} />
            </FField></FRow>
            <FRow cols={2}>
              <FField label="Requirements"><textarea value={form.requirements} onChange={e => up('requirements', e.target.value)} placeholder="One per line" rows={4} style={{ ...IS, resize: 'vertical' }} /></FField>
              <FField label="Responsibilities"><textarea value={form.responsibilities} onChange={e => up('responsibilities', e.target.value)} placeholder="One per line" rows={4} style={{ ...IS, resize: 'vertical' }} /></FField>
            </FRow>
            <FRow><FField label="Benefits"><input value={form.benefits} onChange={e => up('benefits', e.target.value)} placeholder="e.g. Medical insurance, Remote Fridays…" style={IS} /></FField></FRow>
          </FormSection>
        )}
        {step === 3 && (
          <FormSection title="Source & Publishing" subtitle="Where the job was found and how to publish">
            <FRow><FField label="Apply URL *"><input value={form.sourceUrl} onChange={e => up('sourceUrl', e.target.value)} placeholder="https://company.com/careers/job-id" type="url" style={IS} />
              <FieldError message={errorFor('apply_url')} />
            </FField></FRow>
            <FRow><FField label="Expiry Date"><input value={form.expiry} onChange={e => up('expiry', e.target.value)} type="date" style={IS} />
              <FieldError message={errorFor('expiry_date')} />
            </FField></FRow>
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
            <button onClick={() => void handleSubmit()} disabled={submitting}
              style={{ padding: '10px 24px', border: 'none', borderRadius: radius.xl, background: color.brand.base, fontSize: size.base, color: color.surface.base, cursor: submitting ? 'wait' : 'pointer', fontWeight: weight.semibold, opacity: submitting ? 0.7 : 1 }}>
              {submitting
                ? 'Saving…'
                : form.publishMode === 'draft' ? 'Save Draft' : form.publishMode === 'schedule' ? 'Schedule Job' : 'Publish Job'}
            </button>
          )}
        </div>
      </div>
    </div>
  )
}


/**
 * A rejected field's message, shown under the control that caused it.
 *
 * The API validates far more than the form does — description length, URL
 * shorteners, salary ordering, expiry in the future. Rather than duplicating
 * those rules client-side and letting the two drift, the server's own message
 * is rendered where the editor is looking.
 */
function FieldError({ message }: { message?: string }) {
  if (!message) return null
  return (
    <div style={{ fontSize: size.xs, color: color.danger.base, marginTop: 4 }}>{message}</div>
  )
}
