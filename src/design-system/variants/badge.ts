import type { CSSProperties } from 'react'
import { badgeTone, color, workTypeTone } from '../colors'
import { radius } from '../radius'
import { size, weight } from '../typography'
import type { JobBadge, WorkType } from '@/types/job'

/**
 * Badge variants.
 *
 * The two densities correspond to the two places a badge appears today: the
 * job card (`sm`) and the job detail header (`md`). They were previously two
 * copied style objects with two copied colour maps — including a label map that
 * had already drifted ("Fresh" on the card, "Fresh Listing" on the detail page).
 *
 * That drift is preserved deliberately: the labels live in `badgeLabel` below,
 * keyed by surface, so the extraction changes no rendered text.
 */

export type BadgeDensity = 'sm' | 'md'

const density: Record<BadgeDensity, Pick<CSSProperties, 'fontSize' | 'padding'>> = {
  sm: { fontSize: size['2xs'], padding: '3px 8px' },
  md: { fontSize: size.xs, padding: '4px 10px' },
}

/** Status badge as rendered on job cards and the detail header. */
export function badgeStyle(badge: JobBadge, d: BadgeDensity): CSSProperties {
  return {
    ...density[d],
    borderRadius: radius.md,
    fontWeight: weight.semibold,
    background: badgeTone[badge].bg,
    color: badgeTone[badge].color,
  }
}

/**
 * Badge copy, per surface. The card and the detail page have always used
 * different wording for the same badge; keeping both preserves the UI exactly.
 */
export const badgeLabel = {
  card: {
    fresh: 'Fresh',
    verified: 'Verified',
    featured: 'Featured',
    expiring: 'Expiring Soon',
  },
  detail: {
    fresh: 'Fresh Listing',
    verified: 'Verified',
    featured: 'Featured',
    expiring: 'Expiring Soon',
  },
} as const satisfies Record<'card' | 'detail', Record<JobBadge, string>>

/** Work-type chip (Remote / Hybrid / On-site). */
export function workTypeChip(workType: WorkType): CSSProperties {
  return {
    fontSize: size.xs,
    padding: '3px 8px',
    borderRadius: radius.md,
    fontWeight: weight.medium,
    background: workTypeTone[workType].bg,
    color: workTypeTone[workType].color,
  }
}

/** Neutral outlined chip — employment type, experience, generic metadata. */
export const neutralChip: CSSProperties = {
  fontSize: size.xs,
  padding: '3px 8px',
  borderRadius: radius.md,
  fontWeight: weight.medium,
  background: color.surface.subtle,
  color: color.text.strong,
  border: `1px solid ${color.border.base}`,
}

/** Small brand-filled counter, e.g. the saved-jobs count in the navbar. */
export const countPill: CSSProperties = {
  background: color.brand.base,
  color: color.text.inverse,
  borderRadius: radius['2xl'],
  padding: '1px 6px',
  fontSize: size['2xs'],
  fontWeight: weight.semibold,
}
