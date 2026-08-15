import type { CSSProperties } from 'react'
import { color } from '../colors'
import { radius } from '../radius'
import { fontFamily, size, tracking, weight } from '../typography'

/**
 * Input, select and field-label variants.
 *
 * The product has three genuinely different field densities and two different
 * label treatments. They are recorded separately rather than merged, because
 * merging them would change what renders:
 *
 *   admin  10px 12px / 13px   — admin console forms
 *   form    9px 12px / 14px   — public contact form
 *   auth   10px 14px / 14px   — sign-in, with a focus ring
 *
 * Consolidating these is a design decision. This file makes it a one-line
 * change when someone decides to make it.
 */

/** Admin console field. Was `IS`, copied into every admin form section. */
export const adminInput: CSSProperties = {
  width: '100%',
  padding: '10px 12px',
  border: `1px solid ${color.border.base}`,
  borderRadius: radius.xl,
  fontSize: size.sm,
  color: color.text.primary,
  background: color.surface.base,
  outline: 'none',
  boxSizing: 'border-box',
  fontFamily: fontFamily.sans,
}

/** Public form field, as used by the contact form. */
export const formInput: CSSProperties = {
  width: '100%',
  padding: '9px 12px',
  border: `1px solid ${color.border.base}`,
  borderRadius: radius.xl,
  fontSize: size.base,
  color: color.text.primary,
  background: color.surface.base,
  outline: 'none',
}

/** Select built on the public form field, with the pointer affordance. */
export const formSelect: CSSProperties = {
  ...formInput,
  cursor: 'pointer',
}

/** Multi-line variant of the public form field. */
export const formTextarea: CSSProperties = {
  ...formInput,
  resize: 'vertical',
  fontFamily: 'inherit',
  lineHeight: 1.6,
}

/**
 * Sign-in field. Wider horizontal padding than the other two, and its border
 * reflects a validation error.
 */
export function authInput(hasError: boolean, extra?: CSSProperties): CSSProperties {
  return {
    width: '100%',
    padding: '10px 14px',
    borderRadius: radius.xl,
    fontSize: size.base,
    border: `1px solid ${hasError ? color.danger.border : color.border.base}`,
    outline: 'none',
    color: color.text.primary,
    background: color.surface.base,
    boxSizing: 'border-box',
    transition: 'border-color 0.15s',
    ...extra,
  }
}

/**
 * Borderless field that sits inside its own bordered container — the hero
 * search box, the jobs toolbar, and the admin jobs search all use this shape.
 * The container owns the border; the input must not draw a second one.
 */
export function bareInput(fontSize: number, extra?: CSSProperties): CSSProperties {
  return {
    border: 'none',
    outline: 'none',
    fontSize,
    color: color.text.primary,
    background: 'transparent',
    ...extra,
  }
}

/** Standalone select in a toolbar, e.g. the jobs location and sort controls. */
export const toolbarSelect: CSSProperties = {
  border: `1px solid ${color.border.base}`,
  borderRadius: radius.xl,
  padding: '9px 12px',
  fontSize: size.base,
  color: color.text.primary,
  background: color.surface.base,
  cursor: 'pointer',
  outline: 'none',
}

/** Field label above an admin form input. */
export const adminFieldLabel: CSSProperties = {
  display: 'block',
  fontSize: size.xs,
  fontWeight: weight.semibold,
  color: color.text.strong,
  marginBottom: 6,
  textTransform: 'uppercase',
  letterSpacing: tracking.wider,
}

/** Field label above a public form input. Lighter and smaller than the admin one. */
export const formFieldLabel: CSSProperties = {
  display: 'block',
  fontSize: size['2xs'],
  fontWeight: weight.semibold,
  color: color.text.muted,
  textTransform: 'uppercase',
  letterSpacing: tracking.wide,
  marginBottom: 6,
}
