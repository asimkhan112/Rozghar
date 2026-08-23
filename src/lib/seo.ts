/**
 * Document metadata — the browser tab, and what a link to this page unfurls as.
 *
 * A single-page app never reloads the document, so the `<title>` baked into
 * `index.html` is the title of every route unless something changes it. That is
 * how a tab reading "Plenilo.com — Find Jobs Worldwide" ends up sitting on a
 * job listing: the tab strip, the history menu and a bookmark all describe the
 * homepage no matter where the reader actually is.
 *
 * Every route therefore declares its own title through `usePageMeta`, in the
 * shape the rest of the web uses — "<what this page is> | <site>" — with the
 * specific part first, because a tab is truncated from the right and a row of
 * tabs that all begin with the site name is a row of identical tabs.
 *
 * The same call keeps the description, the Open Graph tags and the canonical
 * link in step, so a URL pasted into WhatsApp or LinkedIn previews as the page
 * it points at rather than as the homepage.
 */

import { useEffect } from "react"
import { useLocation } from "react-router"

export const SITE_NAME = "Plenilo.com"
export const SITE_TAGLINE = "Find Jobs Worldwide"

/** The homepage title, and the fallback for anything that declares none. */
export const DEFAULT_TITLE = `${SITE_NAME} — ${SITE_TAGLINE}`

/** Mirrors `description` in `.figma/make/site.json`, which seeds the shell. */
export const DEFAULT_DESCRIPTION =
  "Discover and apply for jobs anywhere in the world — remote, hybrid and on-site — on a platform built for real job seekers. No account required."

export interface PageMeta {
  /** The page-specific part, unsuffixed: "Saved Jobs", not "Saved Jobs | …". */
  title?: string
  description?: string
}

/**
 * "Saved Jobs" -> "Saved Jobs | Plenilo.com".
 *
 * An empty title falls back to the site title rather than rendering a bare
 * separator, and a title that already carries the site name is left alone.
 */
export function formatTitle(title?: string | null): string {
  const page = title?.trim().replace(/\s+/g, " ")
  if (!page) return DEFAULT_TITLE
  if (page === SITE_NAME || page.startsWith(`${SITE_NAME} `) || page.endsWith(`| ${SITE_NAME}`)) return page
  return `${page} | ${SITE_NAME}`
}

/** A tab is only so wide, and a truncated title still has to identify the page. */
function truncate(value: string, max: number): string {
  const clean = value.trim().replace(/\s+/g, " ")
  return clean.length <= max ? clean : `${clean.slice(0, max - 1).trimEnd()}…`
}

/**
 * Finds the existing tag before creating one, so a route change updates the
 * tag the HTML shell already shipped instead of appending a duplicate that
 * crawlers would have to guess between.
 */
function upsertMeta(attribute: "name" | "property", key: string, content: string): void {
  const selector = `meta[${attribute}="${key}"]`
  let tag = document.head.querySelector<HTMLMetaElement>(selector)
  if (!tag) {
    tag = document.createElement("meta")
    tag.setAttribute(attribute, key)
    document.head.appendChild(tag)
  }
  tag.setAttribute("content", content)
}

function upsertCanonical(href: string): void {
  let link = document.head.querySelector<HTMLLinkElement>('link[rel="canonical"]')
  if (!link) {
    link = document.createElement("link")
    link.setAttribute("rel", "canonical")
    document.head.appendChild(link)
  }
  link.setAttribute("href", href)
}

/**
 * Declares what this route is called.
 *
 * Pass `null` to opt out — the page is deferring to something it renders. The
 * job detail page does this when the listing has been removed: the 404 surface
 * it falls back to has already set the honest title, and React runs a child's
 * effects before its parent's, so a parent that still wrote its own would
 * overwrite it.
 *
 * The query string is deliberately left out of the canonical URL: every
 * filtered view of the jobs list is the same page seen through a different
 * lens, and pointing them all at the unfiltered path is what stops the same
 * listings being indexed under a dozen addresses.
 */
export function usePageMeta(meta: PageMeta | null): void {
  const { pathname } = useLocation()
  const owns = meta !== null
  const title = meta?.title
  const description = meta?.description

  useEffect(() => {
    if (!owns) return

    const fullTitle = truncate(formatTitle(title), 70)
    const pageDescription = truncate(description || DEFAULT_DESCRIPTION, 300)
    const canonical = `${window.location.origin}${pathname}`

    document.title = fullTitle
    upsertMeta("name", "description", pageDescription)
    upsertMeta("property", "og:site_name", SITE_NAME)
    upsertMeta("property", "og:type", "website")
    upsertMeta("property", "og:title", fullTitle)
    upsertMeta("property", "og:description", pageDescription)
    upsertMeta("property", "og:url", canonical)
    upsertMeta("name", "twitter:title", fullTitle)
    upsertMeta("name", "twitter:description", pageDescription)
    upsertCanonical(canonical)
  }, [owns, title, description, pathname])
}
