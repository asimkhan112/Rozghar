import { useCallback, useEffect, useId, useMemo, useRef, useState } from 'react'
import { color, radius, shadow, size, tracking, weight } from '@/design-system'
import type { AdminSuggestions, SuggestionItem } from '@/lib/api'
import Icon, { type IconName } from '@/components/Icon'

/** A row the reader can move to, flattened out of the grouped response. */
export interface SuggestChoice {
  group: GroupKey
  item: SuggestionItem
}

type GroupKey = keyof AdminSuggestions

/**
 * Display order and labelling. Jobs first because a job is what the reader
 * came for; sources last because only an editor ever sees them.
 */
const GROUPS: { key: GroupKey; label: string; icon: IconName; badge: string }[] = [
  { key: 'jobs', label: 'Jobs', icon: 'briefcase', badge: 'Job' },
  { key: 'companies', label: 'Companies', icon: 'building', badge: 'Company' },
  { key: 'skills', label: 'Skills', icon: 'sparkles', badge: 'Skill' },
  { key: 'locations', label: 'Locations', icon: 'mapPin', badge: 'Location' },
  { key: 'categories', label: 'Categories', icon: 'layers', badge: 'Category' },
  { key: 'sources', label: 'Sources', icon: 'link', badge: 'Source' },
]

/**
 * Splits `text` on the first case-insensitive occurrence of `query`.
 *
 * Matching, not marking, is the server's job — it returns plain text so a
 * payload that changes on every keystroke never has to be trusted as HTML.
 * The client already knows what was typed, so the highlight is computed here.
 */
function highlight(text: string, query: string): [string, string, string] {
  const at = text.toLowerCase().indexOf(query.toLowerCase())
  if (at < 0 || !query) return [text, '', '']
  return [text.slice(0, at), text.slice(at, at + query.length), text.slice(at + query.length)]
}

/**
 * Keyboard navigation over the flattened suggestion list.
 *
 * State lives in the caller rather than in the dropdown because the input owns
 * the keystrokes: the field never loses focus, so arrow keys have to be handled
 * by the element the reader is typing into, not by the list.
 */
export function useSuggestNavigation(
  groups: AdminSuggestions,
  { open, onChoose, onDismiss }: {
    open: boolean
    onChoose: (choice: SuggestChoice) => void
    onDismiss: () => void
  },
) {
  const choices = useMemo<SuggestChoice[]>(
    () => GROUPS.flatMap(g => (groups[g.key] ?? []).map(item => ({ group: g.key, item }))),
    [groups],
  )
  const [active, setActive] = useState(0)

  // A new result set invalidates the old position: index 3 of the previous
  // list is a different row, or no row at all.
  useEffect(() => setActive(0), [choices])

  const onKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (e.key === 'Escape') {
        e.preventDefault()
        onDismiss()
        return
      }
      if (!open || choices.length === 0) return
      if (e.key === 'ArrowDown') {
        e.preventDefault()
        setActive(i => (i + 1) % choices.length)
      } else if (e.key === 'ArrowUp') {
        e.preventDefault()
        setActive(i => (i - 1 + choices.length) % choices.length)
      } else if (e.key === 'Enter') {
        const choice = choices[active]
        if (choice) {
          e.preventDefault()
          onChoose(choice)
        }
      }
    },
    [open, choices, active, onChoose, onDismiss],
  )

  return { choices, active, setActive, onKeyDown }
}

export default function SearchSuggest({
  query,
  groups,
  choices,
  active,
  onActiveChange,
  open,
  loading = false,
  onChoose,
  onDismiss,
  showBadges = false,
  anchorWidth,
}: {
  /** What has been typed. Used for the highlight, so it is the live value
   *  rather than the debounced one the request used. */
  query: string
  groups: AdminSuggestions
  /** The flattened list and cursor, from `useSuggestNavigation`. */
  choices: SuggestChoice[]
  active: number
  onActiveChange: (index: number) => void
  open: boolean
  loading?: boolean
  onChoose: (choice: SuggestChoice) => void
  onDismiss: () => void
  /** Admin search labels every row with its type. */
  showBadges?: boolean
  anchorWidth?: number | string
}) {
  const listId = useId()
  const boxRef = useRef<HTMLDivElement | null>(null)

  // Outside click. Pointerdown rather than click so the dropdown closes before
  // a click on the page behind it resolves, and touch behaves like mouse.
  useEffect(() => {
    if (!open) return
    const onPointerDown = (e: PointerEvent) => {
      if (!boxRef.current?.parentElement?.contains(e.target as Node)) onDismiss()
    }
    document.addEventListener('pointerdown', onPointerDown)
    return () => document.removeEventListener('pointerdown', onPointerDown)
  }, [open, onDismiss])

  if (!open) return null

  const empty = choices.length === 0

  return (
    <div
      ref={boxRef}
      id={listId}
      role="listbox"
      aria-label="Search suggestions"
      style={{
        position: 'absolute',
        top: 'calc(100% + 6px)',
        left: 0,
        width: anchorWidth ?? '100%',
        // Never taller than roughly half a phone screen; the list scrolls
        // inside itself rather than pushing the page around.
        maxHeight: 'min(60vh, 420px)',
        overflowY: 'auto',
        WebkitOverflowScrolling: 'touch',
        background: color.surface.base,
        border: `1px solid ${color.border.base}`,
        borderRadius: radius['3xl'],
        boxShadow: shadow.menu,
        zIndex: 60,
        padding: empty ? 0 : '6px 0',
        // The hero centres its text; a suggestion list must not inherit that.
        textAlign: 'left',
      }}
    >
      {empty ? (
        <div style={{ padding: '18px 16px', fontSize: size.sm, color: color.text.muted, textAlign: 'center' }}>
          {loading ? 'Searching…' : `Nothing matches “${query}”`}
        </div>
      ) : (
        GROUPS.map(group => {
          const items = groups[group.key] ?? []
          if (items.length === 0) return null
          return (
            <div key={group.key} role="group" aria-label={group.label}>
              <div
                style={{
                  padding: '7px 14px 4px',
                  fontSize: size['2xs'],
                  fontWeight: weight.semibold,
                  color: color.text.muted,
                  textTransform: 'uppercase',
                  letterSpacing: tracking.wide,
                }}
              >
                {group.label}
              </div>
              {items.map(item => {
                const index = choices.findIndex(c => c.group === group.key && c.item === item)
                const isActive = index === active
                const [before, hit, after] = highlight(item.text, query.trim())
                return (
                  <div
                    key={`${group.key}:${item.text}`}
                    role="option"
                    aria-selected={isActive}
                    // Mousedown, not click: a click fires after the input has
                    // already blurred and closed the dropdown.
                    onMouseDown={e => {
                      e.preventDefault()
                      onChoose({ group: group.key, item })
                    }}
                    onMouseEnter={() => onActiveChange(index)}
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      gap: 10,
                      // Comfortably past the 44px touch target minimum.
                      minHeight: 44,
                      padding: '8px 14px',
                      cursor: 'pointer',
                      background: isActive ? color.brand.tint : 'transparent',
                    }}
                  >
                    <Icon
                      name={group.icon}
                      size={15}
                      style={{ color: isActive ? color.brand.deep : color.text.muted }}
                    />
                    <span style={{ flex: 1, minWidth: 0, fontSize: size.sm, color: color.text.primary, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                      {before}
                      <mark style={{ background: 'none', color: color.brand.deep, fontWeight: weight.bold }}>{hit}</mark>
                      {after}
                    </span>
                    {showBadges && (
                      <span
                        style={{
                          fontSize: size['2xs'],
                          fontWeight: weight.semibold,
                          padding: '2px 7px',
                          borderRadius: radius.sm,
                          background: color.surface.muted,
                          color: color.text.secondary,
                          flexShrink: 0,
                        }}
                      >
                        {group.badge}
                      </span>
                    )}
                    {item.count > 0 && (
                      <span style={{ fontSize: size['2xs'], color: color.text.muted, flexShrink: 0 }}>
                        {item.count.toLocaleString()}
                      </span>
                    )}
                  </div>
                )
              })}
            </div>
          )
        })
      )}
    </div>
  )
}

export { GROUPS as SUGGEST_GROUPS, highlight }
