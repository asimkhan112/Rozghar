import { useEffect, useRef, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router'
import { color, radius, size, weight } from '@/design-system'
import { FField, FormSection, FRow, IS } from '@/components/ui/AdminForm'
import { useToast } from '@/stores/useToastStore'
import {
  useCategories,
  useCreateJob,
  useCreateLocation,
  useGenerateDescription,
  useLocations,
  usePublishJob,
  useRewriteDescription,
  useUpdateJob,
  useAdminJob,
} from '@/hooks/queries'
import { ApiError, describeError } from '@/lib/http'
import { ErrorPanel } from '@/components/QueryState'
import type { JobWriteDto } from '@/lib/api/admin-types'
import ShareJobModal from '@/components/ShareJobModal'
import AIDraftReview, { draftToFields, type DraftFields } from '@/components/AIDraftReview'
import Icon from '@/components/Icon'

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

  const createLocation = useCreateLocation()
  const rewrite = useRewriteDescription()
  const generate = useGenerateDescription()

  // The proposed draft, held for review. Never written into the form until the
  // editor accepts it field by field.
  const [draft, setDraft] = useState<DraftFields | null>(null)
  const [applyNote, setApplyNote] = useState<string | undefined>()
  const drafting = rewrite.isPending || generate.isPending
  // Set once a listing goes live, which opens the share modal.
  const [publishedJobId, setPublishedJobId] = useState<string | null>(null)
  const [addingLocation, setAddingLocation] = useState(false)
  const [newCity, setNewCity] = useState('')
  const [newRegion, setNewRegion] = useState('')

  // `?edit=<id>` turns this into the edit form. One component rather than two
  // near-identical ones: the fields, the validation and the AI tools are the
  // same, and only the submit target differs.
  const [params] = useSearchParams()
  const editId = params.get('edit')
  const existing = useAdminJob(editId ?? undefined)
  const updateJob = useUpdateJob()

  const [form, setForm] = useState({ ...EMPTY })
  //: Guards the prefill. Without it, a refetch (window focus, cache
  //: invalidation after a sibling mutation) would overwrite whatever the
  //: editor had typed since the form loaded.
  const prefilled = useRef<string | null>(null)

  useEffect(() => {
    const job = existing.data
    if (!job || prefilled.current === job.id) return
    prefilled.current = job.id
    setForm({
      title: job.title,
      company: job.company,
      categoryId: job.categoryId,
      locationId: job.locationId,
      workType: job.workType,
      employmentType: job.employmentType,
      experienceLevel:
        EXPERIENCE_LEVELS.find(([, label]) => label === job.experience)?.[0] ?? 'mid',
      salaryMin: job.salaryMin ? String(job.salaryMin) : '',
      salaryMax: job.salaryMax ? String(job.salaryMax) : '',
      description: job.description,
      requirements: job.requirements.join('\n'),
      responsibilities: job.responsibilities.join('\n'),
      benefits: job.benefits.join('\n'),
      sourceUrl: job.applyUrl,
      publishMode: job.status === 'published' ? 'publish' : 'draft',
      expiry: job.expiresAt ?? '',
    })
  }, [existing.data])
  const [step, setStep] = useState(0)
  /** Field-level messages from a 422, keyed by the API's field names. */
  const [fieldErrors, setFieldErrors] = useState<Record<string, string[]>>({})
  const up = (k: string, v: string) => setForm(p => ({ ...p, [k]: v }))

  useEffect(() => {
    // Leaving edit mode does not unmount this component — the admin console
    // swaps sections in place — so the edited listing's content would survive
    // into "Add Job" and be submitted as a new one. Reset only on the way out
    // of an edit: an editor who is part-way through a fresh listing must keep
    // what they typed.
    if (editId || prefilled.current === null) return
    prefilled.current = null
    setForm({ ...EMPTY })
    setStep(0)
    setFieldErrors({})
    setDraft(null)
    setApplyNote(undefined)
  }, [editId])

  const STEPS = ['Basic Info', 'Job Details', 'Content', 'Source & Publish']

  const submitting = createJob.isPending || publishJob.isPending || updateJob.isPending

  /** The first message for a field, if the server rejected it. */
  const errorFor = (field: string) => fieldErrors[field]?.[0]

  /**
   * Adds a location the list does not have, then selects it.
   *
   * Anyone who can create a listing can create the place it is in — requiring
   * a second person for "we opened an office in Sahiwal" would just push
   * editors to pick the nearest city that already exists.
   */
  const handleAddLocation = async () => {
    const city = newCity.trim()
    if (!city) return
    try {
      const created = await createLocation.mutateAsync({
        city,
        region: newRegion.trim() || undefined,
        country: 'PK',
      })
      up('locationId', created.id)
      setAddingLocation(false)
      setNewCity('')
      setNewRegion('')
      showToast(`Added ${created.display_name}`)
    } catch (err) {
      showToast(describeError(err))
    }
  }

  /** The form's current content, in the shape the review modal compares. */
  const currentFields = (): DraftFields => ({
    description: form.description,
    responsibilities: form.responsibilities,
    requirements: form.requirements,
    benefits: form.benefits,
  })

  /**
   * A configuration problem, not a transient failure.
   *
   * A 503 means the server has no API key — retrying will fail identically
   * every time, so it is held in place next to the buttons rather than shown
   * as a toast that vanishes and invites another click.
   */
  const [aiUnavailable, setAiUnavailable] = useState<string | null>(null)

  const handleAIError = (err: unknown) => {
    if (err instanceof ApiError && err.status === 503) {
      setAiUnavailable(describeError(err))
      return
    }
    showToast(describeError(err))
  }

  const handleRewrite = async () => {
    try {
      const result = await rewrite.mutateAsync(form.description)
      setDraft(draftToFields(result))
      setApplyNote(result.apply_note)
      setAiUnavailable(null)
    } catch (err) {
      handleAIError(err)
    }
  }

  const handleGenerate = async () => {
    const category = (categories.data ?? []).find(c => c.id === form.categoryId)
    const location = (locations.data ?? []).find(l => l.id === form.locationId)
    try {
      const result = await generate.mutateAsync({
        title: form.title.trim(),
        company: form.company.trim(),
        location: location?.label ?? '',
        employment_type: form.employmentType,
        experience_level:
          EXPERIENCE_LEVELS.find(([value]) => value === form.experienceLevel)?.[1] ?? 'Mid level',
        // Only sent when the editor entered one — the assistant is told
        // explicitly that an absent salary is undisclosed, not unknown.
        salary:
          form.salaryMin || form.salaryMax
            ? `PKR ${form.salaryMin || '?'} – ${form.salaryMax || '?'} per month`
            : null,
        // Category doubles as a domain hint; requirements are the skill list.
        skills: [
          ...(category ? [category.name] : []),
          ...toList(form.requirements),
        ].slice(0, 20),
      })
      setDraft(draftToFields(result))
      setApplyNote(result.apply_note)
      setAiUnavailable(null)
    } catch (err) {
      handleAIError(err)
    }
  }

  /** Applies only the fields the editor ticked. */
  const applyDraft = (accepted: Partial<DraftFields>) => {
    setForm(prev => ({ ...prev, ...accepted }))
    setDraft(null)
    const count = Object.keys(accepted).length
    showToast(count ? `Applied ${count} suggested change${count === 1 ? '' : 's'}` : 'Nothing applied')
    setStep(2)
  }

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
      if (editId) {
        // `If-Match` carries the version last read, so a concurrent edit is
        // rejected rather than silently overwritten.
        const updated = await updateJob.mutateAsync({
          id: editId,
          changes: body,
          version: existing.data?.version,
        })
        showToast(`Saved changes to \u201c${updated.title}\u201d`)
        navigate('/admin/dashboard/jobs')
        return
      }

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

      // A draft has nothing to share yet, so only a live listing opens the
      // modal. Navigation waits until it is dismissed — routing away would
      // unmount the modal the editor is looking at.
      if (form.publishMode === 'publish') {
        setPublishedJobId(created.id)
      } else {
        navigate('/admin/dashboard/jobs')
      }
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

  if (editId && existing.isPending) {
    return (
      <div style={{ padding: '60px 24px', textAlign: 'center', fontSize: size.sm, color: color.text.muted }}>
        Loading the listing…
      </div>
    )
  }

  if (editId && existing.isError) {
    return (
      <ErrorPanel
        message={describeError(existing.error)}
        onRetry={() => void existing.refetch()}
      />
    )
  }

  return (
    <div style={{ maxWidth: 720 }}>
      {editId ? (
        <div
          style={{
            marginBottom: 16,
            padding: '10px 16px',
            borderRadius: radius.xl,
            background: color.warning.tintAlt,
            border: `1px solid ${color.warning.tintSoft}`,
            fontSize: size.sm,
            color: color.warning.deep,
          }}
        >
          Editing <strong>{existing.data?.title}</strong> — changes are saved only when you
          press “Save changes”.
        </div>
      ) : null}
      <AIDraftReview
        open={draft !== null}
        current={currentFields()}
        draft={draft}
        applyNote={applyNote}
        onApply={applyDraft}
        onClose={() => setDraft(null)}
      />
      <ShareJobModal
        jobId={publishedJobId}
        onClose={() => {
          setPublishedJobId(null)
          navigate('/admin/dashboard/jobs')
        }}
      />
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
              {addingLocation ? (
                <div style={{ display: 'flex', gap: 8, alignItems: 'flex-start' }}>
                  <input value={newCity} onChange={e => setNewCity(e.target.value)} placeholder="City, e.g. Sahiwal" style={IS} autoFocus />
                  <input value={newRegion} onChange={e => setNewRegion(e.target.value)} placeholder="Province (optional)" style={IS} />
                  <button
                    type="button"
                    onClick={() => void handleAddLocation()}
                    disabled={!newCity.trim() || createLocation.isPending}
                    style={{ padding: '9px 16px', border: 'none', borderRadius: radius.xl, background: color.brand.base, color: color.surface.base, fontSize: size.sm, fontWeight: weight.medium, cursor: 'pointer', whiteSpace: 'nowrap' }}
                  >
                    {createLocation.isPending ? 'Adding…' : 'Add'}
                  </button>
                  <button
                    type="button"
                    onClick={() => setAddingLocation(false)}
                    style={{ padding: '9px 14px', border: `1px solid ${color.border.base}`, borderRadius: radius.xl, background: color.surface.base, color: color.text.secondary, fontSize: size.sm, cursor: 'pointer' }}
                  >
                    Cancel
                  </button>
                </div>
              ) : (
                <div style={{ display: 'flex', gap: 8 }}>
                  <select value={form.locationId} onChange={e => up('locationId', e.target.value)} style={IS}>
                    <option value="">{locations.isPending ? 'Loading…' : 'Select location'}</option>
                    {(locations.data ?? []).map(l => <option key={l.slug} value={l.id}>{l.label}</option>)}
                  </select>
                  <button
                    type="button"
                    onClick={() => setAddingLocation(true)}
                    title="Add a location that is not listed"
                    style={{ padding: '9px 16px', border: `1px solid ${color.border.base}`, borderRadius: radius.xl, background: color.surface.base, color: color.brand.base, fontSize: size.sm, fontWeight: weight.medium, cursor: 'pointer', whiteSpace: 'nowrap' }}
                  >
                    + New
                  </button>
                </div>
              )}
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
            {/* Drafting tools. Both open a side-by-side review; neither writes
                to the form directly. */}
            <div style={{ display: 'flex', gap: 8, marginBottom: 14, flexWrap: 'wrap' }}>
              <button
                type="button"
                onClick={() => void handleRewrite()}
                disabled={drafting || form.description.trim().length < 40}
                title={
                  form.description.trim().length < 40
                    ? 'Write a rough draft first — a few sentences is enough'
                    : 'Improve grammar and readability without changing meaning'
                }
                style={aiButton(drafting)}
              >
                <Icon name="sparkles" size={15} />
                {rewrite.isPending ? 'Rewriting…' : 'Rewrite with AI'}
              </button>
              <button
                type="button"
                onClick={() => void handleGenerate()}
                disabled={drafting || !form.title.trim() || !form.company.trim()}
                title={
                  !form.title.trim() || !form.company.trim()
                    ? 'Enter a job title and company first'
                    : 'Draft a description from the details you have entered'
                }
                style={aiButton(drafting)}
              >
                <Icon name="sparkles" size={15} />
                {generate.isPending ? 'Writing…' : 'Generate from job details'}
              </button>
              <span style={{ fontSize: size.xs, color: color.text.muted, alignSelf: 'center' }}>
                You review every change before it is applied.
              </span>
            </div>

            {aiUnavailable ? (
              <div
                style={{
                  marginBottom: 14,
                  padding: '10px 14px',
                  borderRadius: radius.xl,
                  background: color.warning.tintAlt,
                  border: `1px solid ${color.warning.tintSoft}`,
                  fontSize: size.sm,
                  color: color.warning.deep,
                }}
              >
                {aiUnavailable} Writing the description by hand works exactly as before.
              </div>
            ) : null}
            <FRow><FField label="Description *"><textarea value={form.description} onChange={e => up('description', e.target.value)} placeholder="Describe the role, team, and company…" rows={5} style={{ ...IS, resize: 'vertical' }} />
              <CharacterCount value={form.description} min={50} max={20000} />
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
                : editId
                  ? 'Save changes'
                  : form.publishMode === 'draft' ? 'Save Draft' : form.publishMode === 'schedule' ? 'Schedule Job' : 'Publish Job'}
            </button>
          )}
        </div>
      </div>
    </div>
  )
}


/**
 * Live length, against the limits the API actually enforces.
 *
 * Shown because the two constraints that reject a description are invisible
 * while typing: fewer than 50 characters is rejected outright, and the rewrite
 * tool needs something to work from. Turning red only once the field is
 * non-empty keeps a blank form from looking like it is already wrong.
 */
function CharacterCount({ value, min, max }: { value: string; min: number; max: number }) {
  const length = value.trim().length
  const tooShort = length > 0 && length < min
  const tooLong = length > max
  const tone = tooShort || tooLong ? color.danger.base : color.text.muted

  return (
    <div
      style={{
        display: 'flex',
        justifyContent: 'space-between',
        gap: 12,
        marginTop: 4,
        fontSize: size.xs,
        color: tone,
      }}
    >
      <span>
        {tooShort
          ? `${min - length} more character${min - length === 1 ? '' : 's'} needed`
          : tooLong
            ? `${(length - max).toLocaleString()} over the limit`
            : ''}
      </span>
      <span style={{ fontVariantNumeric: 'tabular-nums' }}>
        {length.toLocaleString()} / {max.toLocaleString()}
      </span>
    </div>
  )
}

/** Shared style for the two drafting buttons. */
function aiButton(busy: boolean) {
  return {
    padding: '8px 14px',
    border: `1px solid ${color.brand.alpha40}`,
    borderRadius: radius.xl,
    background: color.brand.tint,
    color: color.brand.deep,
    fontSize: size.sm,
    fontWeight: weight.medium,
    cursor: busy ? 'wait' : 'pointer',
    opacity: busy ? 0.6 : 1,
  } as const
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
