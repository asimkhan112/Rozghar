/**
 * Content-bearing HTML for the shell's empty `<div id="root">`.
 *
 * ## Why this exists
 *
 * `html.ts` gives every URL a truthful head — its own title, description and
 * JSON-LD. The body stayed as Vite built it: `<div id="root"></div>`. So a
 * fetch of a job listing returned a document that *described* a job in its
 * metadata and contained no job, and the only readers that ever saw the listing
 * itself were the ones that ran the bundle.
 *
 * Google does run it, on a render pass that can trail the first crawl by days.
 * Nothing else does. Bing, the social unfurlers, and the automated checks that
 * decide whether a site carries real content all read the markup as delivered —
 * and a body holding one empty `div` is, to every one of them, a blank page
 * wearing a good description.
 *
 * This module fills that body in from data the prerenderer has already fetched
 * for the metadata, so the page costs no extra round trip to become readable.
 *
 * ## The same document for everyone
 *
 * As in `prerender.ts`, there is no crawler detection. What is written here is
 * what a person receives too, and on a slow connection they read it while the
 * 180 KB bundle arrives — this is the first paint, not a decoy. React replaces
 * it wholesale at mount (`createRoot` clears its container), which is why the
 * markup carries its own inline styling and depends on nothing in the app.
 *
 * That equivalence is the whole safety argument. Content assembled for crawlers
 * and withheld from readers is cloaking however it is motivated, so every
 * branch below renders a plain, legible version of what React renders richly —
 * never more, never different.
 *
 * ## Why the markup is styled inline
 *
 * The stylesheet is Tailwind's, and the classes the app composes are not
 * knowable here. Unstyled markup would flash as full-bleed serif text against
 * the browser default, which reads as a broken page for the moment it is up.
 * A dozen inline declarations keep it looking deliberate, and they cost nothing
 * once React has taken the container.
 */

/** Escapes text for HTML body content. */
function text(value: string): string {
  return value
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
}

/** Escapes a value for a double-quoted attribute. */
function attr(value: string): string {
  return text(value).replace(/"/g, '&quot;')
}

export interface LinkItem {
  label: string
  href: string
  /** A line under the label — a company and city beneath a job title. */
  note?: string
}

/** Free text with blank-line paragraph breaks, as job descriptions arrive. */
export interface ProseBlock {
  kind: 'prose'
  heading?: string
  body: string
}

/** A bulleted list of plain strings. */
export interface ListBlock {
  kind: 'list'
  heading?: string
  items: string[]
}

/** Labelled links — the listings on a browse page, or site navigation. */
export interface LinksBlock {
  kind: 'links'
  heading?: string
  items: LinkItem[]
}

/** Term/value pairs: where a job is, what it pays, how it is worked. */
export interface FactsBlock {
  kind: 'facts'
  items: readonly { label: string; value: string }[]
}

/** The one thing the page wants the reader to do. */
export interface ActionBlock {
  kind: 'action'
  label: string
  href: string
}

/**
 * A block of page content.
 *
 * A closed set rather than free-form HTML strings: every caller below builds
 * values the renderer escapes, so no branch can put unescaped API text — a job
 * title carrying an ampersand, a company name with an angle bracket — into the
 * document.
 */
export type Block = ProseBlock | ListBlock | LinksBlock | FactsBlock | ActionBlock

export interface BodyPlan {
  /** The page's `<h1>`. Every page gets exactly one. */
  heading: string
  /** The line under the heading. */
  intro?: string
  /** Trail from the site root, rendered as a nav above the heading. */
  breadcrumbs?: readonly LinkItem[]
  blocks?: readonly Block[]
}

const ink = '#1b2733'
const muted = '#5b6b7a'
const rule = '#e3e8ed'
const brand = '#33A4BB'

const FONT =
  "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif"

function style(declarations: Record<string, string>): string {
  const css = Object.entries(declarations)
    .map(([property, value]) => `${property}:${value}`)
    .join(';')
  return ` style="${attr(css)}"`
}

function link(item: LinkItem, weight = '500'): string {
  const anchor = `<a href="${attr(item.href)}"${
    style({ color: brand, 'text-decoration': 'none', 'font-weight': weight })
  }>${text(item.label)}</a>`
  if (!item.note) return anchor
  return `${anchor}<div${
    style({ color: muted, 'font-size': '14px', 'margin-top': '2px' })
  }>${text(item.note)}</div>`
}

function blockHeading(heading?: string): string {
  if (!heading) return ''
  return `<h2${
    style({ 'font-size': '18px', 'font-weight': '600', color: ink, margin: '28px 0 10px' })
  }>${text(heading)}</h2>`
}

/**
 * Splits free text into paragraphs on blank lines.
 *
 * Descriptions arrive as plain text carrying its own line breaks — the same
 * shape `RichText` parses for the React page. Rendering it as one block would
 * run every section together into a wall; splitting on blank lines recovers the
 * paragraphing the employer wrote without interpreting anything else.
 */
function paragraphs(body: string): string {
  return body
    .split(/\n\s*\n/)
    .map((part) => part.trim())
    .filter(Boolean)
    .map(
      (part) =>
        `<p${style({ margin: '0 0 12px', 'line-height': '1.65' })}>${
          text(part).replace(/\n/g, '<br>')
        }</p>`,
    )
    .join('')
}

function renderBlock(block: Block): string {
  switch (block.kind) {
    case 'prose':
      return blockHeading(block.heading) + paragraphs(block.body)

    case 'list': {
      const items = block.items
        .map(
          (item) =>
            `<li${style({ 'margin-bottom': '6px', 'line-height': '1.6' })}>${text(item)}</li>`,
        )
        .join('')
      if (!items) return ''
      return `${blockHeading(block.heading)}<ul${
        style({ margin: '0 0 12px', 'padding-left': '20px' })
      }>${items}</ul>`
    }

    case 'links': {
      const items = block.items
        .map(
          (item) =>
            `<li${style({ padding: '10px 0', 'border-bottom': `1px solid ${rule}` })}>${
              link(item)
            }</li>`,
        )
        .join('')
      if (!items) return ''
      return `${blockHeading(block.heading)}<ul${
        style({ margin: '0 0 12px', padding: '0', 'list-style': 'none' })
      }>${items}</ul>`
    }

    case 'facts': {
      const items = block.items
        .map(
          ({ label, value }) =>
            `<div${style({ padding: '6px 0' })}><span${style({ color: muted })}>${
              text(label)
            }: </span><span${style({ color: ink, 'font-weight': '500' })}>${
              text(value)
            }</span></div>`,
        )
        .join('')
      if (!items) return ''
      return `<div${style({ margin: '0 0 20px' })}>${items}</div>`
    }

    case 'action':
      return `<p${style({ margin: '24px 0' })}><a href="${attr(block.href)}"${
        style({
          display: 'inline-block',
          padding: '10px 22px',
          background: brand,
          color: '#ffffff',
          'border-radius': '10px',
          'text-decoration': 'none',
          'font-weight': '500',
        })
      }>${text(block.label)}</a></p>`
  }
}

function renderBreadcrumbs(items: readonly LinkItem[]): string {
  const trail = items
    .map((item) => link(item, '400'))
    .join(`<span${style({ color: muted, margin: '0 6px' })}>/</span>`)
  return `<nav aria-label="Breadcrumb"${
    style({ 'font-size': '14px', 'margin-bottom': '14px' })
  }>${trail}</nav>`
}

/**
 * The links every page carries, whether or not its own content resolved.
 *
 * A crawler that reads one page of this site should be able to reach the rest
 * of it, and should find the policy pages from wherever it landed rather than
 * only from a footer that lives inside the bundle. These are the same
 * destinations `SiteFooter` renders.
 */
const SITE_LINKS: readonly LinkItem[] = [
  { label: 'Home', href: '/' },
  { label: 'Browse Jobs', href: '/jobs' },
  { label: 'Categories', href: '/categories' },
  { label: 'Remote Jobs', href: '/remote-jobs' },
  { label: 'About', href: '/about' },
  { label: 'Contact', href: '/contact' },
  { label: 'Privacy Policy', href: '/privacy' },
  { label: 'Terms of Service', href: '/terms' },
]

function renderFooter(): string {
  const links = SITE_LINKS.map(
    (item) =>
      `<a href="${attr(item.href)}"${
        style({
          color: muted,
          'text-decoration': 'none',
          'margin-right': '16px',
          'line-height': '2',
        })
      }>${text(item.label)}</a>`,
  ).join('')
  return `<footer${
    style({
      'margin-top': '40px',
      'padding-top': '20px',
      'border-top': `1px solid ${rule}`,
      'font-size': '14px',
    })
  }>${links}</footer>`
}

/**
 * The plan as markup, ready to be placed inside `#root`.
 *
 * Never throws and never returns nothing: a plan with no blocks still yields a
 * heading, the site links and a reachable page.
 */
export function renderBody(plan: BodyPlan): string {
  const parts: string[] = [
    `<header${
      style({
        'padding-bottom': '18px',
        'border-bottom': `1px solid ${rule}`,
        'margin-bottom': '22px',
      })
    }><a href="/"${
      style({ color: ink, 'text-decoration': 'none', 'font-size': '20px', 'font-weight': '700' })
    }>Plenilo.com</a></header>`,
  ]

  if (plan.breadcrumbs?.length) parts.push(renderBreadcrumbs(plan.breadcrumbs))

  parts.push(
    `<h1${
      style({
        'font-size': '30px',
        'font-weight': '700',
        color: ink,
        margin: '0 0 10px',
        'line-height': '1.25',
      })
    }>${text(plan.heading)}</h1>`,
  )

  if (plan.intro) {
    parts.push(
      `<p${
        style({ color: muted, 'font-size': '17px', 'line-height': '1.6', margin: '0 0 24px' })
      }>${text(plan.intro)}</p>`,
    )
  }

  for (const block of plan.blocks ?? []) parts.push(renderBlock(block))

  parts.push(renderFooter())

  return `<main${
    style({
      'max-width': '760px',
      margin: '0 auto',
      padding: '32px 24px 64px',
      font: `16px/1.6 ${FONT}`,
      color: ink,
    })
  }>${parts.join('')}</main>`
}
