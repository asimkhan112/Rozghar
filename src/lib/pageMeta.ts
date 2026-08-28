/**
 * Titles and descriptions for the pages whose copy never changes.
 *
 * These used to live inline in each route's `usePageMeta` call, which was fine
 * while the browser was the only thing that read them. It stopped being fine
 * when `api/prerender.ts` started writing the same tags into the HTML before
 * the bundle loads: two copies of every description, one of which is what
 * search engines actually index, and no mechanism to notice when they diverge.
 *
 * So the strings live here once, and both readers import them. The prerenderer
 * runs on Vercel's edge runtime, so — as with `landingPages.ts` — nothing in
 * this module may import React, the router, or anything reached by the `@/`
 * alias.
 *
 * Pages whose meta depends on data they fetch (a job listing, a landing page, a
 * saved-jobs count) are not here; they compose their own and are handled
 * individually by the prerenderer.
 */

export interface StaticMeta {
  /** Unsuffixed — `formatTitle` in `seo.ts` appends the site name. */
  title: string
  description: string
}

/** Keyed by pathname, exactly as the router registers it. */
export const STATIC_PAGE_META: Readonly<Record<string, StaticMeta>> = {
  '/jobs': {
    title: 'Browse Jobs',
    description:
      'Search live job openings by keyword, category, location, work type and experience level. Every listing links straight to the employer — no account needed.',
  },
  '/categories': {
    title: 'Job Categories',
    description:
      'Every field hiring on Plenilo.com — technology, design, finance, marketing, government and more — with a live count of open roles in each.',
  },
  '/saved-jobs': {
    title: 'Saved Jobs',
    description:
      'The jobs you bookmarked on Plenilo.com, kept in this browser. No account, no sync, nothing stored on our servers.',
  },
  '/about': {
    title: 'About Us',
    description:
      'Why Plenilo.com exists: one honest search across company career pages, job boards and government portals, with expired listings taken down rather than left up.',
  },
  '/contact': {
    title: 'Contact Us',
    description:
      'Report a listing, ask about posting a job, or send feedback to the Plenilo.com team.',
  },
  '/privacy': {
    title: 'Privacy Policy',
    description: 'What Plenilo.com records when you use the site, and what it does not.',
  },
  '/terms': {
    title: 'Terms of Service',
    description: 'The rules for using Plenilo.com, and the limits of what we promise.',
  },
}

/** The 404 surface. Not in the map above: it answers no fixed path. */
export const NOT_FOUND_META: StaticMeta = {
  title: 'Page Not Found',
  description: 'This page may have moved, or the job listing has expired and been removed.',
}

/**
 * Paths that must never be indexed, matched by prefix.
 *
 * The admin console would otherwise produce a wall of soft 404s — every route
 * under it redirects an unauthenticated visitor to the login page, so a crawler
 * sees one page repeated under a dozen addresses. `robots.txt` already asks
 * crawlers not to fetch these, but a URL that is merely disallowed can still be
 * indexed from an inbound link; only `noindex` on the response settles it.
 */
export const NOINDEX_PREFIXES: readonly string[] = ['/admin']

export function isNoindexPath(pathname: string): boolean {
  return NOINDEX_PREFIXES.some(
    (prefix) => pathname === prefix || pathname.startsWith(`${prefix}/`),
  )
}
