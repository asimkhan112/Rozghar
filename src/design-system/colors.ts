/**
 * Colour tokens.
 *
 * Every value is transcribed verbatim from the literals already in the
 * components — nothing has been rounded, merged, or adjusted. Two tokens with
 * the same hex are intentional: they record that one value is doing two
 * different jobs, which is information a later consolidation pass needs.
 *
 * `as const` keeps the values as literal types, so a typo produces a compile
 * error rather than a silently wrong colour.
 */
export const color = {
  brand: {
    /** Primary teal. Buttons, links, active states, focus accents. */
    base: '#33A4BB',
    /** Hover state for solid brand buttons. */
    hover: '#2B8FA3',
    /** Deep teal, used as foreground on the tinted logo chip. */
    deep: '#0E7490',
    /** Light teal, used for the sparkline/secondary chart series. */
    light: '#7EC9D6',
    /** Pale teal wash behind active pills, saved states and highlight rows. */
    tint: '#F0FAFC',
    /** Brand at 25% alpha — hover borders. */
    alpha40: '#33A4BB40',
    /** Brand at 19% alpha — resting borders on tinted surfaces. */
    alpha30: '#33A4BB30',
    /** Brand at 13% alpha. */
    alpha20: '#33A4BB20',
    /** Brand at 9% alpha — chart gridlines and faint dividers. */
    alpha18: '#33A4BB18',
  },

  text: {
    /** Headings and primary body copy. */
    primary: '#111827',
    /** Emphasised secondary copy, e.g. salary figures. */
    strong: '#374151',
    /** Supporting copy, labels, inactive nav items. */
    secondary: '#6B7280',
    /** Metadata, timestamps, uppercase field labels. */
    muted: '#9CA3AF',
    /** Unselected checkbox and unsaved bookmark glyphs. */
    disabled: '#D1D5DB',
    /** Copy on brand and dark surfaces. */
    inverse: '#fff',
  },

  surface: {
    /** Cards, panels, bars. */
    base: '#fff',
    /** Page background. */
    canvas: '#F8FAFB',
    /** Table headers, inset chips, secondary fills. */
    subtle: '#F9FAFB',
    /** Muted fills and disabled pills. */
    muted: '#F3F4F6',
    /** Table row hover. */
    hover: '#FAFBFD',
  },

  border: {
    /** The default hairline used across the entire product. */
    base: '#E5EAF0',
    /** Heavier border on unchecked controls. Same value as `text.disabled`. */
    strong: '#D1D5DB',
    /** Faint internal divider, e.g. the job card footer rule. */
    faint: '#F3F4F6',
  },

  success: {
    base: '#22C55E',
    text: '#059669',
    deep: '#065F46',
    tint: '#ECFDF5',
    tintAlt: '#F0FDF4',
    border: '#BBF7D0',
  },

  warning: {
    base: '#F59E0B',
    text: '#C2410C',
    deep: '#9A3412',
    amber: '#D97706',
    ochre: '#854D0E',
    tint: '#FFF7ED',
    tintAlt: '#FFFBEB',
    tintSoft: '#FEF3C7',
    tintYellow: '#FEF9C3',
  },

  danger: {
    base: '#EF4444',
    text: '#DC2626',
    deep: '#BE123C',
    tint: '#FEF2F2',
    tintAlt: '#FFF1F2',
    border: '#FECACA',
  },

  info: {
    base: '#3B82F6',
    text: '#2563EB',
    deep: '#4338CA',
    tint: '#EFF6FF',
    tintAlt: '#EEF2FF',
  },

  accent: {
    violet: '#7C3AED',
    purple: '#9333EA',
    magenta: '#A21CAF',
    tintViolet: '#F5F3FF',
    tintMagenta: '#FDF4FF',
  },

  /** Third-party brand colours, fixed by the platforms themselves. */
  external: {
    whatsapp: '#25D366',
    linkedin: '#0A66C2',
  },
} as const

/**
 * Company monogram palette. Selected by `Job.logoPalette`, never derived from
 * an identifier — see the note on that field.
 */
export const logoPalette = [
  { bg: color.info.tintAlt, text: color.info.deep },
  { bg: color.accent.tintMagenta, text: color.accent.magenta },
  { bg: color.success.tint, text: color.success.deep },
  { bg: color.warning.tint, text: color.warning.deep },
  { bg: color.brand.tint, text: color.brand.deep },
  { bg: color.warning.tintYellow, text: color.warning.ochre },
] as const

/** Tone pairs for the public-facing job badge. */
export const badgeTone = {
  fresh: { bg: color.success.tint, color: color.success.text },
  verified: { bg: color.info.tint, color: color.info.text },
  featured: { bg: color.warning.tint, color: color.warning.text },
  expiring: { bg: color.danger.tint, color: color.danger.text },
} as const

/** Tone pairs for the work-type chip. */
export const workTypeTone = {
  Remote: { bg: color.brand.tint, color: color.brand.base },
  Hybrid: { bg: color.accent.tintViolet, color: color.accent.violet },
  'On-site': { bg: color.surface.subtle, color: color.text.strong },
} as const

/** Tone pairs for the admin lifecycle pill. Superset of the public badges. */
export const adminStatusTone: Record<string, { bg: string; color: string }> = {
  featured: { bg: color.warning.tint, color: color.warning.text },
  verified: { bg: color.info.tint, color: color.info.text },
  published: { bg: color.success.tint, color: color.success.text },
  draft: { bg: color.surface.subtle, color: color.text.secondary },
  expiring: { bg: color.danger.tint, color: color.danger.text },
  expired: { bg: color.surface.muted, color: color.text.muted },
  reported: { bg: color.danger.tintAlt, color: color.danger.deep },
  archived: { bg: color.surface.muted, color: color.text.muted },
}


/**
 * Dot colours for the admin activity feed.
 *
 * Keyed by tone rather than by event type: the feed deliberately uses a
 * different accent for the weekly-report entry than for other additions, so
 * tone and type are not the same axis.
 */
export const activityTone = {
  success: color.success.base,
  brand: color.brand.base,
  warning: color.warning.base,
  danger: color.danger.base,
  accent: color.accent.violet,
} as const

export type ActivityTone = keyof typeof activityTone
