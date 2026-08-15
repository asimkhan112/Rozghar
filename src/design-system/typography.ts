/**
 * Typography tokens.
 *
 * The scale is the set of sizes already in use, named rather than renumbered.
 * No value has been changed; `size.base` is 14 because 14 is what the product
 * actually uses as its body size.
 */

export const fontFamily = {
  sans: "'Geist', system-ui, sans-serif",
} as const

export const size = {
  '3xs': 10,
  '2xs': 11,
  xs: 12,
  sm: 13,
  base: 14,
  md: 15,
  lg: 16,
  xl: 17,
  '2xl': 18,
  '3xl': 20,
  '4xl': 22,
  '5xl': 24,
  '6xl': 26,
  '7xl': 36,
  '8xl': 48,
} as const

export const weight = {
  regular: 400,
  medium: 500,
  semibold: 600,
  bold: 700,
  extrabold: 800,
} as const

export const tracking = {
  /** Uppercase micro-labels. */
  wide: '0.05em',
  wider: '0.04em',
  /** Headings: optical tightening. */
  tight: '-0.3px',
  tighter: '-0.5px',
} as const

/** Fluid hero headline, preserved exactly as authored. */
export const fluidDisplay = 'clamp(28px, 5vw, 48px)'
