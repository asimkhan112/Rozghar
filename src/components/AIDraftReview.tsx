/**
 * Side-by-side review of an AI draft.
 *
 * The editor sees what they had beside what is proposed, field by field, and
 * nothing is applied until they say so. That is a deliberate constraint: the
 * failure mode of a drafting tool is not a bad sentence, it is a plausible
 * sentence that quietly changes a requirement or invents a benefit — and the
 * only reliable defence is a human reading both columns.
 *
 * Fields are accepted individually. A rewrite is usually right about the prose
 * and occasionally wrong about one list; all-or-nothing would force the editor
 * to discard the good part with the bad.
 */

import { useState } from 'react'
import { color, radius, shadow, size, weight } from '@/design-system'
import type { AIDraft } from '@/lib/api/ai'

/** The form's own shape, in the form's own vocabulary. */
export interface DraftFields {
  description: string
  requirements: string
  responsibilities: string
  benefits: string
}

type FieldKey = keyof DraftFields

const FIELDS: { key: FieldKey; label: string }[] = [
  { key: 'description', label: 'Description' },
  { key: 'responsibilities', label: 'Responsibilities' },
  { key: 'requirements', label: 'Requirements' },
  { key: 'benefits', label: 'Benefits' },
]

/** The API returns arrays; the form's textareas are one item per line. */
export function draftToFields(draft: AIDraft): DraftFields {
  return {
    description: draft.description,
    responsibilities: draft.responsibilities.join('\n'),
    requirements: draft.requirements.join('\n'),
    benefits: draft.benefits.join('\n'),
  }
}

/**
 * Word-level diff.
 *
 * A longest-common-subsequence over words rather than characters: character
 * diffs of prose shatter into unreadable fragments mid-word, and what a
 * reviewer needs to see is which *words* changed. Words are the unit a person
 * checks a requirement against.
 *
 * Whitespace is folded into the preceding token so the reassembled text spaces
 * correctly without tracking separators.
 */
export function diffWords(before: string, after: string): { text: string; changed: boolean }[][] {
  const a = before.match(/\S+\s*/g) ?? []
  const b = after.match(/\S+\s*/g) ?? []

  // Standard LCS table. These are single fields — a job description, not a
  // repository — so the quadratic table is a few thousand cells at worst.
  const lcs: number[][] = Array.from({ length: a.length + 1 }, () =>
    new Array<number>(b.length + 1).fill(0),
  )
  for (let i = a.length - 1; i >= 0; i--) {
    for (let j = b.length - 1; j >= 0; j--) {
      lcs[i]![j] =
        a[i]!.trim() === b[j]!.trim()
          ? lcs[i + 1]![j + 1]! + 1
          : Math.max(lcs[i + 1]![j]!, lcs[i]![j + 1]!)
    }
  }

  const left: { text: string; changed: boolean }[] = []
  const right: { text: string; changed: boolean }[] = []
  let i = 0
  let j = 0
  while (i < a.length && j < b.length) {
    if (a[i]!.trim() === b[j]!.trim()) {
      left.push({ text: a[i]!, changed: false })
      right.push({ text: b[j]!, changed: false })
      i++
      j++
    } else if (lcs[i + 1]![j]! >= lcs[i]![j + 1]!) {
      left.push({ text: a[i]!, changed: true })
      i++
    } else {
      right.push({ text: b[j]!, changed: true })
      j++
    }
  }
  while (i < a.length) left.push({ text: a[i++]!, changed: true })
  while (j < b.length) right.push({ text: b[j++]!, changed: true })

  return [left, right]
}

function Column({
  title,
  body,
  tone,
  parts,
}: {
  title: string
  body: string
  tone: 'current' | 'proposed'
  parts?: { text: string; changed: boolean }[]
}) {
  const empty = !body.trim()
  return (
    <div style={{ flex: 1, minWidth: 0 }}>
      <div
        style={{
          fontSize: size['2xs'],
          fontWeight: weight.semibold,
          textTransform: 'uppercase',
          letterSpacing: '0.06em',
          color: tone === 'proposed' ? color.brand.base : color.text.muted,
          marginBottom: 6,
        }}
      >
        {title}
      </div>
      <div
        style={{
          border: `1px solid ${tone === 'proposed' ? color.brand.alpha40 : color.border.base}`,
          background: tone === 'proposed' ? color.brand.tint : color.surface.canvas,
          borderRadius: radius['2xl'],
          padding: '12px 14px',
          fontSize: size.sm,
          lineHeight: 1.6,
          color: empty ? color.text.muted : color.text.primary,
          whiteSpace: 'pre-wrap',
          minHeight: 72,
          fontStyle: empty ? 'italic' : 'normal',
        }}
      >
        {empty ? (
          '(empty)'
        ) : parts ? (
          parts.map((part, i) =>
            part.changed ? (
              <mark
                key={i}
                style={{
                  // Removed on the left, added on the right — the colours say
                  // which without a legend.
                  background: tone === 'proposed' ? '#DCFCE7' : '#FEE2E2',
                  color: tone === 'proposed' ? '#166534' : '#991B1B',
                  borderRadius: 3,
                  padding: '1px 0',
                }}
              >
                {part.text}
              </mark>
            ) : (
              <span key={i}>{part.text}</span>
            ),
          )
        ) : (
          body
        )}
      </div>
    </div>
  )
}

export default function AIDraftReview({
  open,
  current,
  draft,
  applyNote,
  onApply,
  onClose,
}: {
  open: boolean
  current: DraftFields
  draft: DraftFields | null
  applyNote?: string
  onApply: (accepted: Partial<DraftFields>) => void
  onClose: () => void
}) {
  // Everything starts accepted: the editor asked for the draft, so the default
  // is to take it. Opting out per field is the exception.
  const [accepted, setAccepted] = useState<Record<FieldKey, boolean>>({
    description: true,
    responsibilities: true,
    requirements: true,
    benefits: true,
  })

  if (!open || !draft) return null

  // A field the draft left identical is not a decision to make.
  const changed = FIELDS.filter(f => draft[f.key].trim() !== current[f.key].trim())
  const acceptedCount = changed.filter(f => accepted[f.key]).length

  const handleApply = () => {
    const patch: Partial<DraftFields> = {}
    for (const field of changed) {
      if (accepted[field.key]) patch[field.key] = draft[field.key]
    }
    onApply(patch)
  }

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label="Review the suggested description"
      onClick={onClose}
      style={{
        position: 'fixed',
        inset: 0,
        background: 'rgba(17, 24, 39, 0.55)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        padding: 24,
        zIndex: 1100,
      }}
    >
      <div
        onClick={e => e.stopPropagation()}
        style={{
          background: color.surface.base,
          borderRadius: radius['4xl'],
          boxShadow: shadow.menu,
          width: '100%',
          maxWidth: 1040,
          maxHeight: '90vh',
          overflow: 'auto',
        }}
      >
        <div
          style={{
            padding: '22px 26px 0',
            display: 'flex',
            justifyContent: 'space-between',
            gap: 16,
          }}
        >
          <div>
            <div
              style={{ fontSize: size['2xl'], fontWeight: weight.bold, color: color.text.primary }}
            >
              Review the suggested wording
            </div>
            <div style={{ fontSize: size.sm, color: color.text.muted, marginTop: 4 }}>
              Nothing is saved until you apply. Check that no requirement, figure or condition
              changed meaning.
            </div>
          </div>
          <button
            onClick={onClose}
            aria-label="Close"
            style={{
              border: 'none',
              background: 'none',
              cursor: 'pointer',
              fontSize: size['3xl'],
              color: color.text.muted,
              lineHeight: 1,
              padding: 0,
            }}
          >
            ×
          </button>
        </div>

        <div style={{ padding: '20px 26px 26px', display: 'flex', flexDirection: 'column', gap: 20 }}>
          {changed.length === 0 ? (
            <div
              style={{
                padding: '40px 20px',
                textAlign: 'center',
                fontSize: size.sm,
                color: color.text.muted,
              }}
            >
              The suggestion matches what you already have — nothing to apply.
            </div>
          ) : (
            changed.map(field => (
              <div key={field.key}>
                <label
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: 8,
                    marginBottom: 8,
                    cursor: 'pointer',
                  }}
                >
                  <input
                    type="checkbox"
                    checked={accepted[field.key]}
                    onChange={e =>
                      setAccepted(prev => ({ ...prev, [field.key]: e.target.checked }))
                    }
                    style={{ accentColor: color.brand.base }}
                  />
                  <span
                    style={{
                      fontSize: size.base,
                      fontWeight: weight.semibold,
                      color: color.text.primary,
                    }}
                  >
                    {field.label}
                  </span>
                </label>
                {(() => {
                  const [before, after] = diffWords(current[field.key], draft[field.key])
                  return (
                    <div style={{ display: 'flex', gap: 14 }}>
                      <Column
                        title="Current"
                        body={current[field.key]}
                        tone="current"
                        parts={before}
                      />
                      <Column
                        title="Suggested"
                        body={draft[field.key]}
                        tone="proposed"
                        parts={after}
                      />
                    </div>
                  )
                })()}
              </div>
            ))
          )}

          {applyNote ? (
            <div
              style={{
                fontSize: size.xs,
                color: color.text.muted,
                borderTop: `1px solid ${color.surface.muted}`,
                paddingTop: 12,
              }}
            >
              <strong style={{ color: color.text.secondary }}>Suggested apply note:</strong>{' '}
              {applyNote}
              {/* Shown for reference only. The listing has no field for it, and
                  inventing one to hold model output would be the wrong order. */}
            </div>
          ) : null}

          <div style={{ display: 'flex', gap: 10, justifyContent: 'flex-end' }}>
            <button
              onClick={onClose}
              style={{
                padding: '10px 20px',
                border: `1px solid ${color.border.base}`,
                borderRadius: radius.xl,
                background: color.surface.base,
                color: color.text.strong,
                fontSize: size.base,
                fontWeight: weight.medium,
                cursor: 'pointer',
              }}
            >
              Discard
            </button>
            <button
              onClick={handleApply}
              disabled={acceptedCount === 0}
              style={{
                padding: '10px 24px',
                border: 'none',
                borderRadius: radius.xl,
                background: acceptedCount === 0 ? color.text.disabled : color.brand.base,
                color: color.surface.base,
                fontSize: size.base,
                fontWeight: weight.semibold,
                cursor: acceptedCount === 0 ? 'not-allowed' : 'pointer',
              }}
            >
              Apply {acceptedCount} change{acceptedCount === 1 ? '' : 's'}
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
