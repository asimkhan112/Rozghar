import type { CSSProperties } from 'react'
import { color } from '../colors'
import { radius } from '../radius'
import { size, weight } from '../typography'

/**
 * Button tones.
 *
 * Only the parts that are genuinely identical across call sites are captured
 * here — the colour triplet and border. Padding and font size vary by context
 * (a toolbar button is not a hero CTA) and stay at the call site, so nothing
 * renders differently than it did before extraction.
 */

export type ButtonTone = 'solid' | 'outline' | 'ghost' | 'subtle'

interface ToneStyle {
  background: string
  border: string
  color: string
  /** Applied by the hover handlers; becomes a `:hover` rule in Phase 7. */
  hoverBackground?: string
  hoverBorderColor?: string
  hoverColor?: string
}

export const buttonTone: Record<ButtonTone, ToneStyle> = {
  /** Primary call to action. */
  solid: {
    background: color.brand.base,
    border: 'none',
    color: color.text.inverse,
    hoverBackground: color.brand.hover,
  },
  /** Secondary action on a white surface. */
  outline: {
    background: color.surface.base,
    border: `1px solid ${color.border.base}`,
    color: color.text.primary,
    hoverBackground: color.brand.tint,
    hoverBorderColor: color.brand.alpha40,
  },
  /** Bare text button — breadcrumbs, icon-only controls. */
  ghost: {
    background: 'none',
    border: 'none',
    color: color.text.secondary,
    hoverColor: color.brand.base,
  },
  /** Bordered but low-emphasis, e.g. the "View Site" control in the admin bar. */
  subtle: {
    background: 'none',
    border: `1px solid ${color.border.base}`,
    color: color.text.secondary,
    hoverBorderColor: color.brand.alpha40,
    hoverColor: color.brand.base,
  },
}

/**
 * Selectable filter pill.
 *
 * The same three-colour pattern appears in the jobs filter groups, the homepage
 * quick filters, the admin status filters and the admin sidebar. Radius,
 * padding and font size still differ per site and are passed by the caller.
 */
export function pillTone(active: boolean): Pick<CSSProperties, 'border' | 'background' | 'color'> {
  return {
    border: `1px solid ${active ? color.brand.base : color.border.base}`,
    background: active ? color.brand.tint : color.surface.base,
    color: active ? color.brand.base : color.text.secondary,
  }
}

/** Destructive/bulk-action button tinted from a semantic hue. */
export function actionTone(hue: string): CSSProperties {
  return {
    border: `1px solid ${hue}30`,
    background: `${hue}0A`,
    color: hue,
  }
}

/** The primary CTA as used at full size — hero search, form submit, reset. */
export const primaryButton: CSSProperties = {
  background: color.brand.base,
  border: 'none',
  borderRadius: radius.xl,
  color: color.text.inverse,
  fontSize: size.base,
  fontWeight: weight.medium,
  cursor: 'pointer',
}
