/**
 * Rewriting the built `index.html` head.
 *
 * The shell that Vite emits already carries a `<title>`, a description and two
 * Open Graph tags, all describing the homepage — they are baked in from
 * `.figma/make/site.json` at build time and are identical on every URL. This
 * module replaces them per-request rather than appending alongside, because a
 * document containing two `<title>` elements or two `og:title` tags leaves the
 * crawler to pick one, and which one it picks is not something we get to know.
 *
 * String surgery rather than an HTML parser on purpose: the input is one file
 * this repository builds itself, the tags being replaced are written by a
 * plugin in `vite.config.ts`, and pulling a parser into an edge function to
 * rewrite four known tags would cost more cold-start time than the whole
 * request budget.
 */

export interface MetaTag {
  attribute: 'name' | 'property'
  key: string
  content: string
}

export interface HeadPlan {
  /** Full document title, site suffix already applied. */
  title: string
  description: string
  canonical: string
  /** Absolute URL. Omitted when the page has no image worth unfurling. */
  image?: string
  /** `website` for browse surfaces, `article` for a single listing. */
  ogType: string
  /** Pre-serialised JSON-LD bodies, one `<script>` each. */
  jsonLd: string[]
  /** Adds `noindex, nofollow`. Set for admin, 404s and anything unresolved. */
  noindex?: boolean
}

/** Escapes a value for use inside a double-quoted HTML attribute. */
function attr(value: string): string {
  return value
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
}

/** Escapes text content — only `&` and `<` can end a `<title>` early. */
function text(value: string): string {
  return value.replace(/&/g, '&amp;').replace(/</g, '&lt;')
}

/**
 * Removes the shell's build-time tags so the per-request ones are unopposed.
 *
 * Scoped to the four tags `figmaSiteConfiguration` injects. Anything else in
 * the head — the icons, the manifest, the theme colour, the module script — is
 * per-deployment rather than per-page and is left exactly as built.
 */
function stripBuiltInMeta(html: string): string {
  return html
    .replace(/<title>[\s\S]*?<\/title>/i, '')
    .replace(/<meta\s+name="description"[^>]*>/gi, '')
    .replace(/<meta\s+property="og:(?:title|description|image|url|type|site_name)"[^>]*>/gi, '')
    .replace(/<meta\s+name="twitter:[^"]*"[^>]*>/gi, '')
    .replace(/<link\s+rel="canonical"[^>]*>/gi, '')
}

function metaTag({ attribute, key, content }: MetaTag): string {
  return `<meta ${attribute}="${key}" content="${attr(content)}">`
}

/**
 * The head this page should have, as markup.
 *
 * Open Graph and Twitter tags are both emitted because they are read by
 * different consumers: WhatsApp, LinkedIn and Facebook read `og:`, X reads
 * `twitter:` and falls back to `og:` only for some properties. A job link
 * shared into a WhatsApp group is a meaningful share channel for this audience,
 * and it unfurls from these tags alone — it never runs the page's JavaScript.
 */
function renderHead(plan: HeadPlan): string {
  const tags: string[] = [
    `<title>${text(plan.title)}</title>`,
    `<link rel="canonical" href="${attr(plan.canonical)}">`,
    metaTag({ attribute: 'name', key: 'description', content: plan.description }),
    metaTag({ attribute: 'property', key: 'og:type', content: plan.ogType }),
    metaTag({ attribute: 'property', key: 'og:site_name', content: 'Plenilo.com' }),
    metaTag({ attribute: 'property', key: 'og:title', content: plan.title }),
    metaTag({ attribute: 'property', key: 'og:description', content: plan.description }),
    metaTag({ attribute: 'property', key: 'og:url', content: plan.canonical }),
    metaTag({ attribute: 'name', key: 'twitter:title', content: plan.title }),
    metaTag({ attribute: 'name', key: 'twitter:description', content: plan.description }),
  ]

  if (plan.image) {
    tags.push(
      metaTag({ attribute: 'property', key: 'og:image', content: plan.image }),
      // Without an explicit size some consumers refuse to render a large card
      // and fall back to a thumbnail beside the text.
      metaTag({ attribute: 'property', key: 'og:image:width', content: '1200' }),
      metaTag({ attribute: 'property', key: 'og:image:height', content: '627' }),
      metaTag({ attribute: 'name', key: 'twitter:card', content: 'summary_large_image' }),
      metaTag({ attribute: 'name', key: 'twitter:image', content: plan.image }),
    )
  } else {
    tags.push(metaTag({ attribute: 'name', key: 'twitter:card', content: 'summary' }))
  }

  if (plan.noindex) {
    tags.push(metaTag({ attribute: 'name', key: 'robots', content: 'noindex, nofollow' }))
  }

  for (const block of plan.jsonLd) {
    tags.push(`<script type="application/ld+json">${block}</script>`)
  }

  return tags.join('\n    ')
}

/**
 * Applies a head plan to the built shell.
 *
 * If `</head>` is somehow absent the shell is returned untouched. A page with
 * stale metadata still works; a page assembled from a failed string replacement
 * may not, and this function must never be the reason the site stops rendering.
 */
export function applyHead(shell: string, plan: HeadPlan): string {
  if (!/<\/head>/i.test(shell)) return shell
  return stripBuiltInMeta(shell).replace(
    /<\/head>/i,
    `    ${renderHead(plan)}\n  </head>`,
  )
}
