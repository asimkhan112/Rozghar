import { useRef, useState } from 'react'
import { adminInput, color, radius, size, weight } from '@/design-system'

/**
 * A list of short items, entered one at a time.
 *
 * Requirements, responsibilities and benefits are arrays in the database and
 * render as separate chips and bullets on the listing page. The form used to
 * collect them as text — a textarea split on newlines, and for benefits a
 * single-line input that was split the same way, so "Medical insurance,
 * Remote Fridays" arrived as *one* benefit containing a comma. This makes the
 * input match the shape of the data: what you see as a chip here is exactly
 * one item on the job page.
 *
 * Committing is deliberately forgiving, because the muscle memory differs by
 * editor: Enter, a comma, or moving focus away all turn the pending text into
 * a chip, and pasting a list from a job ad splits it on commas, semicolons and
 * newlines at once. Backspace on an empty box removes the last chip, which is
 * the one gesture people try without being told.
 */
export default function TagInput({
  value,
  onChange,
  placeholder,
  max = 30,
  maxLength = 300,
}: {
  value: string[]
  onChange: (next: string[]) => void
  placeholder?: string
  /** Mirrors the API's cap on the array. */
  max?: number
  /** Mirrors `ShortText` on the API — 300 characters per item. */
  maxLength?: number
}) {
  const [pending, setPending] = useState('')
  const [focused, setFocused] = useState(false)
  const inputRef = useRef<HTMLInputElement>(null)

  const full = value.length >= max

  /** Typed or pasted text → the items it describes. */
  const parse = (raw: string): string[] =>
    raw
      .split(/[,;\n]/)
      .map(part => part.trim().slice(0, maxLength))
      .filter(Boolean)

  /** Appends to `base`, dropping blanks, repeats and anything over the cap. */
  const merge = (base: string[], parts: string[]): string[] => {
    const next = [...base]
    for (const part of parts) {
      // Case-insensitive: "Remote work" and "remote work" are one benefit, and
      // a duplicate chip reads as a mistake on the published listing.
      if (next.some(item => item.toLowerCase() === part.toLowerCase())) continue
      if (next.length >= max) break
      next.push(part)
    }
    return next
  }

  const commit = (raw: string) => {
    const parts = parse(raw)
    if (parts.length === 0) return
    const next = merge(value, parts)
    if (next.length !== value.length) onChange(next)
    setPending('')
  }

  const removeAt = (index: number) => onChange(value.filter((_, i) => i !== index))

  /**
   * Clicking a chip puts it back in the box to be retyped.
   *
   * A chip has no cursor in it, so without this the only way to fix a typo is
   * to delete and rewrite the whole item. It is also how a listing entered
   * before this control existed gets tidied: an old benefit reading "Medical
   * insurance, Remote Fridays" arrives as one chip, and clicking it and typing
   * a comma splits it into the two it was always meant to be.
   */
  const editAt = (index: number) => {
    // One `onChange` for both halves of the swap. Committing the pending text
    // and removing the chip as two calls would compute both from the same
    // props, and React would batch them into whichever landed last.
    onChange(merge(value.filter((_, i) => i !== index), parse(pending)))
    setPending(value[index] ?? '')
    inputRef.current?.focus()
  }

  return (
    <div>
      <div
        onClick={() => inputRef.current?.focus()}
        style={{
          ...adminInput,
          display: 'flex',
          flexWrap: 'wrap',
          alignItems: 'center',
          gap: 6,
          minHeight: 42,
          padding: '7px 8px',
          cursor: 'text',
          borderColor: focused ? color.brand.base : color.border.base,
        }}
      >
        {value.map((item, index) => (
          <span
            key={`${item}-${index}`}
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: 6,
              padding: '4px 6px 4px 10px',
              borderRadius: radius.xl,
              background: color.brand.tint,
              border: `1px solid ${color.brand.alpha30}`,
              color: color.brand.deep,
              fontSize: size.sm,
              fontWeight: weight.medium,
              maxWidth: '100%',
            }}
          >
            <button
              type="button"
              title="Click to edit"
              onClick={event => {
                event.stopPropagation()
                editAt(index)
              }}
              style={{
                maxWidth: 260,
                overflow: 'hidden',
                textOverflow: 'ellipsis',
                whiteSpace: 'nowrap',
                border: 'none',
                background: 'transparent',
                padding: 0,
                font: 'inherit',
                color: 'inherit',
                cursor: 'text',
              }}
            >
              {item}
            </button>
            <button
              type="button"
              aria-label={`Remove ${item}`}
              onClick={event => {
                event.stopPropagation()
                removeAt(index)
              }}
              style={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                width: 16,
                height: 16,
                padding: 0,
                border: 'none',
                borderRadius: radius.full,
                background: 'transparent',
                color: color.brand.base,
                cursor: 'pointer',
                lineHeight: 1,
              }}
            >
              <svg width="10" height="10" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="3" fill="none">
                <path d="M18 6L6 18M6 6l12 12" />
              </svg>
            </button>
          </span>
        ))}

        <input
          ref={inputRef}
          value={pending}
          disabled={full}
          maxLength={maxLength}
          placeholder={full ? `Maximum ${max} reached` : value.length === 0 ? placeholder : 'Add another…'}
          onChange={event => {
            // A typed comma commits rather than being stored: an editor
            // writing "Medical insurance, " expects two chips, not one.
            if (event.target.value.includes(',')) {
              commit(event.target.value)
              return
            }
            setPending(event.target.value)
          }}
          onKeyDown={event => {
            if (event.key === 'Enter') {
              // Inside a form this would otherwise submit the step.
              event.preventDefault()
              commit(pending)
              return
            }
            if (event.key === 'Backspace' && pending === '' && value.length > 0) {
              event.preventDefault()
              removeAt(value.length - 1)
            }
          }}
          onPaste={event => {
            const text = event.clipboardData.getData('text')
            if (!/[,;\n]/.test(text)) return
            event.preventDefault()
            commit(`${pending}${text}`)
          }}
          onFocus={() => setFocused(true)}
          onBlur={() => {
            setFocused(false)
            // Half-typed text is a real item the editor forgot to enter, not
            // something to discard on the way to the next field.
            commit(pending)
          }}
          style={{
            flex: '1 1 120px',
            minWidth: 120,
            border: 'none',
            outline: 'none',
            background: 'transparent',
            fontSize: size.sm,
            fontFamily: 'inherit',
            color: color.text.primary,
            padding: '3px 2px',
          }}
        />
      </div>

      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          gap: 12,
          marginTop: 5,
          fontSize: size['2xs'],
          color: color.text.muted,
        }}
      >
        <span>Press Enter or comma to add each item separately. Click one to edit it.</span>
        <span style={{ flexShrink: 0 }}>
          {value.length}/{max}
        </span>
      </div>
    </div>
  )
}
