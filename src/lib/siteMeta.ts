/**
 * Site identity and title formatting — the parts with no browser in them.
 *
 * Split out of `seo.ts` so `api/prerender.ts` can import them. That function
 * runs on Vercel's edge runtime and formats the very same titles into the HTML
 * before the bundle loads; if it carried its own copy of the suffix rule, a
 * page's server-rendered title and its client-rendered title would be free to
 * disagree, and the one search engines index is the one nobody is looking at.
 *
 * `seo.ts` re-exports everything here, so existing imports are unaffected.
 */

export const SITE_NAME = 'Plenilo.com'
export const SITE_TAGLINE = 'Find Jobs Worldwide'

/** The homepage title, and the fallback for anything that declares none. */
export const DEFAULT_TITLE = `${SITE_NAME} — ${SITE_TAGLINE}`

/** Mirrors `description` in `.figma/make/site.json`, which seeds the shell. */
export const DEFAULT_DESCRIPTION =
  'Discover and apply for jobs anywhere in the world — remote, hybrid and on-site — on a platform built for real job seekers. No account required.'

/**
 * "Saved Jobs" -> "Saved Jobs | Plenilo.com".
 *
 * An empty title falls back to the site title rather than rendering a bare
 * separator, and a title that already carries the site name is left alone.
 */
export function formatTitle(title?: string | null): string {
  const page = title?.trim().replace(/\s+/g, ' ')
  if (!page) return DEFAULT_TITLE
  if (page === SITE_NAME || page.startsWith(`${SITE_NAME} `) || page.endsWith(`| ${SITE_NAME}`)) {
    return page
  }
  return `${page} | ${SITE_NAME}`
}

/** A tab is only so wide, and a truncated title still has to identify the page. */
export function truncate(value: string, max: number): string {
  const clean = value.trim().replace(/\s+/g, ' ')
  return clean.length <= max ? clean : `${clean.slice(0, max - 1).trimEnd()}…`
}

/**
 * Search results cut a title at roughly this width, and a description at the
 * second. Both are budgets rather than limits — nothing breaks past them, the
 * tail is simply never read.
 */
export const TITLE_BUDGET = 70
export const DESCRIPTION_BUDGET = 300

/**
 * A page title, suffixed and cut to fit.
 *
 * The order matters, and getting it wrong is easy: truncating *after* adding
 * the site name eats the site name, so a long job title renders as
 * "… at Smithsonian Institution | Plenil…" — the one part of the title that
 * was supposed to be constant is the part that gets destroyed, and every
 * over-long result loses its brand at a different point.
 *
 * So the page-specific part is cut first, to whatever the suffix leaves it,
 * and the suffix is added to a string already known to fit. A title that
 * already carries the site name is passed straight to `formatTitle`, which
 * leaves it alone.
 */
export function pageTitle(title?: string | null): string {
  const full = formatTitle(title)
  if (full.length <= TITLE_BUDGET) return full

  const suffix = ` | ${SITE_NAME}`
  if (!full.endsWith(suffix)) return truncate(full, TITLE_BUDGET)

  const page = full.slice(0, -suffix.length)
  return `${truncate(page, TITLE_BUDGET - suffix.length)}${suffix}`
}

/**
 * The canonical URL for a path.
 *
 * The query string is deliberately dropped, and that single rule is the whole
 * duplicate-content policy for this site. It works because of how the URL space
 * is arranged rather than in spite of it:
 *
 *   * `/jobs?category=design&sort=salary_desc&page=3` is one catalogue seen
 *     through a lens. Letting each combination be its own indexable address
 *     would offer a few hundred listings under a few thousand URLs, and a
 *     crawler would spend its entire budget on this site discovering that they
 *     are the same listings in a different order. All of them canonicalise to
 *     `/jobs`.
 *
 *   * The facets that *are* worth ranking for — a category, a place, remote
 *     work — do not live in the query string at all. They have real paths
 *     (`/design-creative-jobs`, `/jobs-in-lahore`, `/remote-jobs`, see
 *     `landingPages.ts`), each with its own title, heading and copy, and each
 *     canonicalising to itself because a path has no query to drop.
 *
 * So nothing indexable is lost by dropping the query string, and the sitemap
 * must list the landing paths rather than the filtered URLs — a sitemap that
 * submits a URL which then canonicalises elsewhere is asking to be ignored.
 */
export function canonicalUrl(origin: string, pathname: string): string {
  return `${origin.replace(/\/$/, '')}${pathname}`
}

/**
 * The generated share card for a listing, sized for a link preview.
 *
 * `landscape` rather than `square`: 1200x627 is what LinkedIn and Facebook
 * render as a full-width card, and the square variant is letterboxed into a
 * thumbnail there. The endpoint renders on first request and is cacheable, so
 * naming it here costs nothing until something actually unfurls the link.
 */
export function socialCardUrl(origin: string, slug: string): string {
  return `${origin.replace(/\/$/, '')}/api/v1/jobs/${encodeURIComponent(slug)}/social/landscape.png`
}

/** The site-wide preview image, for every page that is not one listing. */
export function defaultSocialImage(origin: string): string {
  return `${origin.replace(/\/$/, '')}/icon-512.png`
}
