/**
 * Elevation tokens.
 *
 * Transcribed verbatim from the box-shadow literals already in the components.
 * Two of the five are tinted with the brand hue rather than neutral black,
 * which is deliberate in the original design and preserved here.
 */
export const shadow = {
  /** Job card lift on hover. */
  card: '0 4px 20px rgba(0,0,0,0.08)',
  /** Dropdown and popover elevation. */
  menu: '0 8px 24px rgba(0,0,0,0.1)',
  /** Toast elevation. */
  toast: '0 8px 24px rgba(0,0,0,0.2)',
  /** Hero search field, tinted with the brand hue. */
  search: '0 8px 32px rgba(51,164,187,0.12)',
  /** Category tile lift on hover, tinted with the brand hue. */
  tile: '0 2px 12px rgba(51,164,187,0.08)',
} as const

/** Focus ring applied to inputs on the sign-in form. */
export const focusRing = (tint: string) => `0 0 0 3px ${tint}`
