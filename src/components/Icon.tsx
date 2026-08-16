import type { CSSProperties, ReactNode } from 'react'
import { color, radius } from '@/design-system'

/**
 * The product's icon set.
 *
 * Every glyph is a stroked outline on a 24x24 grid drawn with `currentColor`,
 * which is the style the hand-written SVGs in the navigation and the job card
 * already used. Emoji were doing this job in a lot of places, and they cannot
 * be made to match: their colour, weight and metrics belong to whichever font
 * the operating system picked, so the same screen rendered differently on every
 * machine and never matched the line icons sitting next to it.
 *
 * Drawing them here rather than adding an icon dependency keeps the set to the
 * glyphs actually used, and keeps the stroke weight consistent with the SVGs
 * already in the tree.
 */
const PATHS: Record<string, ReactNode> = {
  // --- navigation and actions ------------------------------------------
  search: <><circle cx="11" cy="11" r="7" /><path d="M20 20l-3.6-3.6" /></>,
  bookmark: <path d="M19 21l-7-5-7 5V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2z" />,
  check: <path d="M20 6L9 17l-5-5" />,
  checkCircle: <><path d="M22 11.1V12a10 10 0 1 1-5.9-9.1" /><path d="M22 4L12 14l-3-3" /></>,
  close: <><line x1="18" y1="6" x2="6" y2="18" /><line x1="6" y1="6" x2="18" y2="18" /></>,
  upload: <><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" /><polyline points="7 8 12 3 17 8" /><line x1="12" y1="3" x2="12" y2="15" /></>,
  download: <><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" /><polyline points="7 10 12 15 17 10" /><line x1="12" y1="15" x2="12" y2="3" /></>,
  arrowUp: <><line x1="12" y1="19" x2="12" y2="5" /><polyline points="5 12 12 5 19 12" /></>,
  copy: <><rect x="9" y="9" width="12" height="12" rx="2" /><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1" /></>,
  external: <><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6" /><polyline points="15 3 21 3 21 9" /><line x1="10" y1="14" x2="21" y2="3" /></>,
  compass: <><circle cx="12" cy="12" r="10" /><polygon points="16.24 7.76 14.12 14.12 7.76 16.24 9.88 9.88 16.24 7.76" /></>,
  home: <><path d="M3 9.5L12 3l9 6.5V20a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z" /><path d="M9 22v-7h6v7" /></>,
  plus: <><line x1="12" y1="5" x2="12" y2="19" /><line x1="5" y1="12" x2="19" y2="12" /></>,
  list: <><line x1="8" y1="6" x2="21" y2="6" /><line x1="8" y1="12" x2="21" y2="12" /><line x1="8" y1="18" x2="21" y2="18" /><line x1="3.5" y1="6" x2="3.51" y2="6" /><line x1="3.5" y1="12" x2="3.51" y2="12" /><line x1="3.5" y1="18" x2="3.51" y2="18" /></>,

  // --- job attributes ---------------------------------------------------
  mapPin: <><path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z" /><circle cx="12" cy="10" r="3" /></>,
  briefcase: <><rect x="2" y="7" width="20" height="14" rx="2" /><path d="M16 21V5a2 2 0 0 0-2-2h-4a2 2 0 0 0-2 2v16" /></>,
  currency: <><line x1="12" y1="1" x2="12" y2="23" /><path d="M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6" /></>,
  trendingUp: <><polyline points="23 6 13.5 15.5 8.5 10.5 1 18" /><polyline points="17 6 23 6 23 12" /></>,
  tag: <><path d="M20.6 13.4l-7.2 7.2a2 2 0 0 1-2.8 0L2 12V2h10l8.6 8.6a2 2 0 0 1 0 2.8z" /><line x1="7" y1="7" x2="7.01" y2="7" /></>,
  clock: <><circle cx="12" cy="12" r="10" /><polyline points="12 6 12 12 16 14" /></>,
  star: <polygon points="12 2 15.1 8.3 22 9.3 17 14.1 18.2 21 12 17.8 5.8 21 7 14.1 2 9.3 8.9 8.3 12 2" />,
  zap: <polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2" />,
  lock: <><rect x="3" y="11" width="18" height="11" rx="2" /><path d="M7 11V7a5 5 0 0 1 10 0v4" /></>,
  shield: <><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" /><path d="M9 12l2 2 4-4" /></>,

  // --- states -----------------------------------------------------------
  alert: <><path d="M10.3 3.9L1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z" /><line x1="12" y1="9" x2="12" y2="13" /><line x1="12" y1="17" x2="12.01" y2="17" /></>,
  flag: <><path d="M4 15s1-1 4-1 5 2 8 2 4-1 4-1V3s-1 1-4 1-5-2-8-2-4 1-4 1z" /><line x1="4" y1="22" x2="4" y2="15" /></>,
  inbox: <><polyline points="22 12 16 12 14 15 10 15 8 12 2 12" /><path d="M5.5 5.1L2 12v6a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2v-6l-3.5-6.9A2 2 0 0 0 16.7 4H7.3a2 2 0 0 0-1.8 1.1z" /></>,
  sparkles: <><path d="M12 3l1.9 5.1L19 10l-5.1 1.9L12 17l-1.9-5.1L5 10l5.1-1.9L12 3z" /><path d="M18.5 15l.8 2.2 2.2.8-2.2.8-.8 2.2-.8-2.2-2.2-.8 2.2-.8.8-2.2z" /></>,

  // --- analytics --------------------------------------------------------
  clipboard: <><path d="M16 4h2a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h2" /><rect x="8" y="2" width="8" height="4" rx="1" /></>,
  eye: <><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z" /><circle cx="12" cy="12" r="3" /></>,
  pointer: <path d="M5 3l14.5 8.4-6.4 1.4-2.6 6.2z" />,
  barChart: <><line x1="6" y1="20" x2="6" y2="13" /><line x1="12" y1="20" x2="12" y2="4" /><line x1="18" y1="20" x2="18" y2="9" /></>,

  // --- share ------------------------------------------------------------
  chat: <path d="M21 11.5a8.4 8.4 0 0 1-.9 3.8 8.5 8.5 0 0 1-7.6 4.7 8.4 8.4 0 0 1-3.8-.9L3 21l1.9-5.7a8.4 8.4 0 0 1-.9-3.8 8.5 8.5 0 0 1 4.7-7.6 8.4 8.4 0 0 1 3.8-.9h.5a8.5 8.5 0 0 1 8 8z" />,
  linkedin: <><path d="M16 8a6 6 0 0 1 6 6v7h-4v-7a2 2 0 0 0-4 0v7h-4V8h4v1.5A6 6 0 0 1 16 8z" /><rect x="2" y="9" width="4" height="12" /><circle cx="4" cy="4" r="2" /></>,
  link: <><path d="M10 13a5 5 0 0 0 7.5.5l3-3a5 5 0 0 0-7-7l-1.7 1.7" /><path d="M14 11a5 5 0 0 0-7.5-.5l-3 3a5 5 0 0 0 7 7l1.7-1.7" /></>,

  // --- job categories ---------------------------------------------------
  code: <><polyline points="16 18 22 12 16 6" /><polyline points="8 6 2 12 8 18" /></>,
  cog: <><circle cx="12" cy="12" r="3.2" /><path d="M12 2v3M12 19v3M4.2 4.2l2.1 2.1M17.7 17.7l2.1 2.1M2 12h3M19 12h3M4.2 19.8l2.1-2.1M17.7 6.3l2.1-2.1" /></>,
  palette: <><path d="M12 22a10 10 0 1 1 10-10c0 2.2-1.8 3.5-3.5 3.5H16a2 2 0 0 0-1.4 3.4A2 2 0 0 1 13 22z" /><circle cx="7.5" cy="11.5" r="1" /><circle cx="12" cy="7.5" r="1" /><circle cx="16.5" cy="10" r="1" /></>,
  target: <><circle cx="12" cy="12" r="9" /><circle cx="12" cy="12" r="5" /><circle cx="12" cy="12" r="1.5" /></>,
  megaphone: <><path d="M3 11v2a1 1 0 0 0 1 1h2l5 4V6L6 10H4a1 1 0 0 0-1 1z" /><path d="M15.5 8.5a5 5 0 0 1 0 7" /><path d="M18.5 5.5a9 9 0 0 1 0 13" /></>,
  users: <><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2" /><circle cx="9" cy="7" r="4" /><path d="M23 21v-2a4 4 0 0 0-3-3.9" /><path d="M16 3.1a4 4 0 0 1 0 7.8" /></>,
  headset: <><path d="M4 14v-2a8 8 0 0 1 16 0v2" /><path d="M4 14h2a1 1 0 0 1 1 1v4a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1z" /><path d="M20 14h-2a1 1 0 0 0-1 1v4a1 1 0 0 0 1 1h1a1 1 0 0 0 1-1z" /></>,
  package: <><path d="M21 16V8a2 2 0 0 0-1-1.7l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.7l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z" /><polyline points="3.3 7 12 12 20.7 7" /><line x1="12" y1="22" x2="12" y2="12" /></>,
  stethoscope: <><path d="M5 3v7a5 5 0 0 0 10 0V3" /><path d="M3.5 3h3M13.5 3h3" /><path d="M10 15v1a5 5 0 0 0 10 0v-2" /><circle cx="20" cy="12" r="2" /></>,
  graduation: <><path d="M22 10L12 5 2 10l10 5 10-5z" /><path d="M6 12.5V17c0 1.7 2.7 3 6 3s6-1.3 6-3v-4.5" /></>,
  landmark: <><line x1="3" y1="21" x2="21" y2="21" /><line x1="6" y1="21" x2="6" y2="10" /><line x1="10" y1="21" x2="10" y2="10" /><line x1="14" y1="21" x2="14" y2="10" /><line x1="18" y1="21" x2="18" y2="10" /><polygon points="12 3 21 8 3 8 12 3" /></>,
  scale: <><path d="M12 3v18" /><path d="M7 21h10" /><path d="M4 7h16" /><path d="M4 7l-2.5 5a2.5 2.5 0 0 0 5 0z" /><path d="M20 7l2.5 5a2.5 2.5 0 0 1-5 0z" /></>,
  pen: <path d="M17 3a2.8 2.8 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5z" />,
  plane: <path d="M17.8 19.2L16 11l3.5-3.5a2.1 2.1 0 0 0-3-3L13 8 4.8 6.2a1 1 0 0 0-.9 1.7l5.6 3.4-2.4 2.4-2.6-.5a.8.8 0 0 0-.7 1.3l4.6 4.6a.8.8 0 0 0 1.3-.7l-.5-2.6 2.4-2.4 3.4 5.6a1 1 0 0 0 1.7-.9z" />,
  building: <><line x1="2" y1="21" x2="22" y2="21" /><path d="M5 21V7l8-4v18" /><path d="M13 10h6v11" /><line x1="9" y1="8" x2="9" y2="8.01" /><line x1="9" y1="12" x2="9" y2="12.01" /><line x1="9" y1="16" x2="9" y2="16.01" /></>,
  factory: <><path d="M2 21h20" /><path d="M4 21V10l6 4V10l6 4V5h4v16" /><line x1="7" y1="17" x2="7" y2="17.01" /><line x1="13" y1="17" x2="13" y2="17.01" /></>,
  truck: <><rect x="1" y="6" width="13" height="10" rx="1" /><path d="M14 9h4l3 3v4h-7z" /><circle cx="5.5" cy="18.5" r="1.8" /><circle cx="17.5" cy="18.5" r="1.8" /></>,
  sprout: <><path d="M12 21V11" /><path d="M12 11C12 7.2 9.2 5 5 5c0 3.8 2.8 6 7 6z" /><path d="M12 13.5c0-3 2.3-5 5.5-5 0 3-2.3 5-5.5 5z" /></>,
  folder: <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z" />,
  layers: <><polygon points="12 2 2 7 12 12 22 7 12 2" /><polyline points="2 17 12 22 22 17" /><polyline points="2 12 12 17 22 12" /></>,
}

export type IconName = keyof typeof PATHS

/** Every name in the set, so a caller can assert coverage. */
export const iconNames = Object.keys(PATHS) as IconName[]

export default function Icon({
  name,
  size = 16,
  strokeWidth = 2,
  style,
}: {
  name: IconName
  size?: number
  /** Thinner strokes read better at large sizes; 2 is right at 16-20px. */
  strokeWidth?: number
  style?: CSSProperties
}) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={strokeWidth}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
      style={{ flexShrink: 0, display: 'block', ...style }}
    >
      {PATHS[name]}
    </svg>
  )
}

/** Background and foreground for a badge, keyed by meaning rather than colour. */
const TONES = {
  brand: { bg: color.brand.alpha20, fg: color.brand.deep, ring: color.brand.alpha30 },
  success: { bg: color.success.tint, fg: color.success.text, ring: color.success.border },
  warning: { bg: color.warning.tintAlt, fg: color.warning.amber, ring: color.warning.tintSoft },
  danger: { bg: color.danger.tint, fg: color.danger.text, ring: color.danger.border },
  neutral: { bg: color.surface.muted, fg: color.text.secondary, ring: color.border.base },
} as const

export type IconTone = keyof typeof TONES

/**
 * Badge geometry. The icon is deliberately a little under half the box: an
 * icon that fills its container reads as cramped at every size.
 */
const SIZES = {
  xs: { box: 28, glyph: 14, radius: radius.xl, stroke: 2 },
  sm: { box: 34, glyph: 17, radius: radius['2xl'], stroke: 2 },
  md: { box: 42, glyph: 20, radius: radius['3xl'], stroke: 1.9 },
  lg: { box: 56, glyph: 26, radius: radius['4xl'], stroke: 1.8 },
  xl: { box: 76, glyph: 34, radius: radius['5xl'], stroke: 1.6 },
} as const

export type IconBadgeSize = keyof typeof SIZES

/**
 * An icon on a tinted plate.
 *
 * Rounded square by default: the product's surfaces are cards and panels, and
 * a squircle sits inside that language where a circle reads as an avatar. The
 * circle is kept for the cases that genuinely are avatar-shaped.
 */
export function IconBadge({
  name,
  size = 'md',
  tone = 'brand',
  shape = 'square',
  style,
}: {
  name: IconName
  size?: IconBadgeSize
  tone?: IconTone
  shape?: 'square' | 'circle'
  style?: CSSProperties
}) {
  const s = SIZES[size]
  const t = TONES[tone]
  return (
    <span
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        justifyContent: 'center',
        width: s.box,
        height: s.box,
        flexShrink: 0,
        borderRadius: shape === 'circle' ? radius.full : s.radius,
        background: t.bg,
        // A hairline of the same hue keeps the plate from dissolving into a
        // white card at the palest tones.
        border: `1px solid ${t.ring}`,
        color: t.fg,
        ...style,
      }}
    >
      <Icon name={name} size={s.glyph} strokeWidth={s.stroke} />
    </span>
  )
}

/**
 * Category icons.
 *
 * The taxonomy table stores an emoji per category, seeded by
 * `backend/app/db/seed_taxonomy.py`. Mapping it here rather than migrating the
 * column keeps the API contract unchanged and means a category added through
 * the admin console with any emoji still renders — as a folder, not as tofu.
 */
const CATEGORY_ICONS: Record<string, IconName> = {
  '💻': 'code',
  '⚙️': 'cog',
  '⚙': 'cog',
  '📈': 'trendingUp',
  '🎨': 'palette',
  '🤝': 'target',
  '📣': 'megaphone',
  '📊': 'barChart',
  '👥': 'users',
  '🎧': 'headset',
  '📦': 'package',
  '🩺': 'stethoscope',
  '🎓': 'graduation',
  '🏛️': 'landmark',
  '🏛': 'landmark',
  '⚖️': 'scale',
  '⚖': 'scale',
  '✍️': 'pen',
  '✍': 'pen',
  '✈️': 'plane',
  '✈': 'plane',
  '🏗️': 'building',
  '🏗': 'building',
  '🏭': 'factory',
  '🚚': 'truck',
  '🌱': 'sprout',
}

/** Slug fallbacks, for a category whose stored icon is absent or unrecognised. */
const CATEGORY_SLUG_ICONS: [RegExp, IconName][] = [
  [/tech|software|it\b/, 'code'],
  [/engineer/, 'cog'],
  [/data|analytic/, 'trendingUp'],
  [/design|creative/, 'palette'],
  [/sales|business/, 'target'],
  [/market|pr\b/, 'megaphone'],
  [/financ|account/, 'barChart'],
  [/human-resource|hr\b/, 'users'],
  [/support|customer/, 'headset'],
  [/operation|supply/, 'package'],
  [/health|medical/, 'stethoscope'],
  [/education|training/, 'graduation'],
  [/government|public/, 'landmark'],
  [/legal/, 'scale'],
  [/media|content/, 'pen'],
  [/hospitality|travel/, 'plane'],
  [/construction|real-estate/, 'building'],
  [/manufactur/, 'factory'],
  [/logistic|transport/, 'truck'],
  [/intern|trainee|fresh/, 'sprout'],
]

export function categoryIcon(stored: string | null | undefined, slug = ''): IconName {
  if (stored && CATEGORY_ICONS[stored]) return CATEGORY_ICONS[stored]
  for (const [pattern, name] of CATEGORY_SLUG_ICONS) {
    if (pattern.test(slug)) return name
  }
  return 'folder'
}
