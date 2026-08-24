/**
 * Job body text, parsed into blocks.
 *
 * A description is stored as one plain-text field, and it arrives from two very
 * different places: an editor typing into a textarea, and an editor pasting a
 * listing copied off another job site. Both produce line structure — headings,
 * bullets, paragraph breaks — and HTML throws all of it away, because a run of
 * newlines inside a `<p>` collapses to a single space. That is why a pasted
 * listing renders as one unbroken wall of text.
 *
 * So the text is parsed here rather than trusted to the browser: lines are
 * classified into headings, list items and paragraphs, and the renderer emits
 * real `<h3>`, `<ul>` and `<p>` elements. Pure functions, no React — the same
 * classification is what the admin-side tidier reasons about.
 */

export type RichBlock =
  | { kind: 'heading'; text: string }
  | { kind: 'paragraph'; text: string }
  | { kind: 'list'; ordered: boolean; items: string[] }

/** `- `, `* `, `• `, an en dash — every bullet glyph a paste can carry. */
const BULLET_LINE = /^[ \t]*[-–—*•·▪◦‣]+[ \t]+(.*)$/
/** `1. `, `2) `, `(3) ` — numbered steps, kept numbered. */
const NUMBERED_LINE = /^[ \t]*\(?(\d{1,2})[.)][ \t]+(.*)$/

/**
 * Whitespace and invisible characters, normalised.
 *
 * Pasted text is full of non-breaking spaces and zero-width joiners that look
 * like nothing and break every `\s`-based test downstream. Blank runs collapse
 * to a single blank line so a source with six of them does not render six
 * paragraph gaps.
 */
export function normalizeText(raw: string): string {
  return raw
    .replace(/\r\n?/g, '\n')
    .replace(/[\u00A0\u2007\u202F]/g, ' ')
    .replace(/[\u200B-\u200D\uFEFF]/g, '')
    .replace(/[ \t]+/g, ' ')
    .replace(/ *\n */g, '\n')
    .replace(/\n{3,}/g, '\n\n')
    .trim()
}

/** Inline markdown emphasis, dropped. The page has its own type scale. */
function plain(text: string): string {
  return text
    .replace(/\*\*(.+?)\*\*/g, '$1')
    .replace(/__(.+?)__/g, '$1')
    .trim()
}

/**
 * Is this line a section label?
 *
 * Three forms, in the order a paste produces them: a markdown heading, a bold
 * line, and — by far the most common — a short line ending in a colon, which
 * is how every job site writes "Requirements:". The word limit is what keeps a
 * full sentence that happens to end in a colon from being promoted.
 */
function headingText(line: string): string | null {
  const trimmed = plain(line)
  if (!trimmed) return null

  const markdown = /^#{1,6}\s+(.*)$/.exec(trimmed)
  if (markdown) return markdown[1]!.replace(/:$/, '').trim() || null

  if (trimmed.length <= 80 && trimmed.endsWith(':') && trimmed.split(/\s+/).length <= 9)
    return trimmed.slice(0, -1).trim() || null

  // ALL CAPS, short, unpunctuated — a heading in every listing that uses them.
  if (
    trimmed.length <= 60 &&
    /[A-Z]/.test(trimmed) &&
    trimmed === trimmed.toUpperCase() &&
    !/[.!?]$/.test(trimmed)
  )
    return trimmed

  return null
}

/**
 * Rejoins hard wraps.
 *
 * Text copied from a plain-text source is often wrapped at a fixed width, and
 * honouring those newlines would ladder the paragraph down the page. A line
 * that reached full width without closing punctuation is a wrap; anything
 * shorter was a break the writer meant.
 */
function joinWrapped(lines: string[]): string {
  const out: string[] = []
  for (const line of lines) {
    const previous = out[out.length - 1]
    if (previous !== undefined && previous.length >= 60 && !/[.!?:;]$/.test(previous)) {
      out[out.length - 1] = `${previous} ${line}`
    } else {
      out.push(line)
    }
  }
  return out.join('\n')
}

/** Splits body text into the blocks the renderer draws. */
export function parseRichText(raw: string): RichBlock[] {
  const text = normalizeText(raw)
  if (!text) return []

  const blocks: RichBlock[] = []
  let paragraph: string[] = []
  let list: { ordered: boolean; items: string[] } | null = null

  const flushParagraph = () => {
    if (!paragraph.length) return
    blocks.push({ kind: 'paragraph', text: joinWrapped(paragraph) })
    paragraph = []
  }
  const flushList = () => {
    if (!list) return
    blocks.push({ kind: 'list', ordered: list.ordered, items: list.items })
    list = null
  }

  for (const line of text.split('\n')) {
    if (!line.trim()) {
      flushList()
      flushParagraph()
      continue
    }

    const bullet = BULLET_LINE.exec(line)
    const numbered = bullet ? null : NUMBERED_LINE.exec(line)
    if (bullet || numbered) {
      flushParagraph()
      const item = plain(bullet?.[1] ?? numbered?.[2] ?? '')
      if (!item) continue
      const ordered = Boolean(numbered)
      // A change of marker starts a new list rather than mixing dots and
      // numbers under one.
      if (!list || list.ordered !== ordered) {
        flushList()
        list = { ordered, items: [] }
      }
      list.items.push(item)
      continue
    }

    flushList()
    const heading = headingText(line)
    if (heading) {
      flushParagraph()
      blocks.push({ kind: 'heading', text: heading })
      continue
    }
    paragraph.push(plain(line))
  }

  flushList()
  flushParagraph()
  return blocks
}

// --- admin-side tidying ---------------------------------------------------

/**
 * Section labels a copied listing runs together with its body.
 *
 * Pasting from a job site frequently loses every newline, leaving
 * `…adventure Responsibilities: Close deals…` as one sentence. These are the
 * labels worth breaking on; each may be followed by a few words of its own
 * ("Key Reasons to Join Agicap:") before the colon.
 */
/**
 * Labels safe to break on wherever they appear. Each is a heading in practice
 * and almost never a phrase inside a sentence.
 */
const STRONG_LABELS = [
  'about the role',
  'about the company',
  'about the team',
  'about us',
  'responsibilities',
  'key responsibilities',
  'your responsibilities',
  'what you will do',
  "what you'll do",
  'requirements',
  'key requirements',
  'qualifications',
  'preferred qualifications',
  'required qualifications',
  'who you are',
  'what we are looking for',
  "what we're looking for",
  'skills required',
  'nice to have',
  'benefits',
  'benefits and perks',
  'what we offer',
  'why join us',
  'key reasons to join',
  'how to apply',
  'application process',
]

/**
 * Labels that are also ordinary words. "Attractive compensation:" is a
 * sentence, not a section, so these break only after a full stop or a line
 * end — where a heading actually starts.
 */
const WEAK_LABELS = [
  'the role',
  'skills',
  'experience',
  'perks',
  'compensation',
  'deadline',
]


function escapeRegExp(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
}

/** Up to three trailing words — a company or team name before the colon. */
const LABEL_TAIL = String.raw`((?:\s+[\w&'\u2019/-]+){0,3})\s*:\s*`

const STRONG_PATTERN = new RegExp(
  String.raw`(^|[\s.,;:!?)\]])(` + STRONG_LABELS.map(escapeRegExp).join('|') + String.raw`)` + LABEL_TAIL,
  'gi',
)

/** Only at a real break: start of text, a newline, or the end of a sentence. */
const WEAK_PATTERN = new RegExp(
  String.raw`(^|\n|[.!?;]\s)\s*(` + WEAK_LABELS.map(escapeRegExp).join('|') + String.raw`)` + LABEL_TAIL,
  'gi',
)

/**
 * Restores line structure to pasted text.
 *
 * Only ever inserts breaks and normalises whitespace — no word is added,
 * removed or reordered, which is what makes it safe to run on paste without
 * asking. It cannot invent the bullets a run-on paragraph never had; splitting
 * `targets Conduct discovery calls` into two items needs to understand the
 * sentences, and that is what "Rewrite with AI" is for.
 */
export function tidyPastedText(raw: string): string {
  let text = normalizeText(raw)
  if (!text) return ''

  // Bullet glyphs used inline as separators become real list lines.
  text = text.replace(/\s*[\u2022\u00B7\u25AA\u25E6\u2023]\s*/g, '\n- ')
  // A dash before a capitalised phrase is a bullet the source flattened. The
  // narrowness is deliberate: a dash inside a range (`300,000 - 450,000`) or
  // used as prose punctuation ("great team - we ship weekly") must survive,
  // so an em dash never counts and a lower-case continuation never counts.
  text = text.replace(/([a-z),.])\s+[-\u2013]\s+(?=[A-Z])/g, '$1\n- ')

  const breakOnLabel = (_match: string, before: string, label: string, tail: string) => {
    // Sentence punctuation is kept; a separator comma is not — it only ever
    // joined two things the source should have split, and it would otherwise
    // be left dangling at the end of the section above.
    const lead = before.trim().replace(/^[,;]+$/, '')
    return `${lead}\n\n${label}${tail}:\n`
  }
  text = text.replace(STRONG_PATTERN, breakOnLabel).replace(WEAK_PATTERN, breakOnLabel)

  return text
    .replace(/\n{3,}/g, '\n\n')
    .replace(/[ \t]+\n/g, '\n')
    // A separator left stranded at the end of a line — matched one newline at
    // a time so the blank line between sections survives.
    .replace(/[ \t]*[,;]+[ \t]*(\n|$)/g, '$1')
    .trim()
}

/**
 * True when a paste is a wall of text worth tidying — long, and with almost no
 * breaks of its own. Text that already has structure is left exactly as typed.
 */
export function looksUnformatted(raw: string): boolean {
  const text = raw.trim()
  if (text.length < 400) return false
  const breaks = (text.match(/\n/g) ?? []).length
  return breaks < text.length / 400
}
