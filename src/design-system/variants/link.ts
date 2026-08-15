import type { CSSProperties } from 'react'

/**
 * Neutralises the browser's default anchor styling.
 *
 * Navigation targets became real `<a href>` elements during the routing
 * migration so that job listings are crawlable, shareable and middle-clickable.
 * Applying this reset means the computed appearance is unchanged from when the
 * same targets were `<button>` elements.
 */
export const linkReset: CSSProperties = {
  color: 'inherit',
  textDecoration: 'none',
}

/** Anchor that must also behave as a flex/inline layout box, as buttons did. */
export const linkResetBlock: CSSProperties = {
  ...linkReset,
  display: 'block',
}
