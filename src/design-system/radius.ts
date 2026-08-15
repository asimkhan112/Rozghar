/**
 * Corner radius tokens.
 *
 * These are the values already present in the components, named rather than
 * renumbered. Twelve steps is more than a system needs, but consolidating them
 * would change rendered output — that is a design decision, not a refactor, so
 * they are recorded here as-is for that decision to be made against one file.
 */
export const radius = {
  /** 2 — progress bars and micro indicators. */
  xxs: 2,
  /** 3 — inline swatches. */
  xs: 3,
  /** 4 — checkboxes, small chips. */
  sm: 4,
  /** 5 — compact inputs. */
  smd: 5,
  /** 6 — tags, filter pills, icon buttons. */
  md: 6,
  /** 7 — small toolbar buttons. */
  lg: 7,
  /** 8 — the default control radius: buttons, inputs, selects. */
  xl: 8,
  /** 10 — avatars and monogram tiles. */
  '2xl': 10,
  /** 12 — cards and panels. */
  '3xl': 12,
  /** 14 — large logo tiles. */
  '4xl': 14,
  /** 16 — feature panels. */
  '5xl': 16,
  /** 20 — fully rounded pills. */
  pill: 20,
  /** Circles. */
  full: '50%',
} as const
