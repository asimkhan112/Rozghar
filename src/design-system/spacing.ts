/**
 * Spacing tokens.
 *
 * The scale is the set of values already present in the components. The product
 * is broadly on a 4px grid with 6/10/14 as deliberate half-steps, so the scale
 * is named by step rather than forced onto a strict multiplier.
 *
 * Radii live in `radius.ts`.
 */

export const space = {
  none: 0,
  hairline: 1,
  '2': 2,
  '3': 3,
  '4': 4,
  '5': 5,
  '6': 6,
  '8': 8,
  '10': 10,
  '12': 12,
  '14': 14,
  '16': 16,
  '20': 20,
  '24': 24,
  '28': 28,
  '32': 32,
  '48': 48,
} as const


/** Layout container widths already in use across the pages. */
export const container = {
  wide: 1200,
  detail: 1100,
  narrow: 900,
  hero: 720,
  form: 400,
} as const
