/**
 * Document metadata — the browser tab, and what a link to this page unfurls as.
 *
 * A single-page app never reloads the document, so the `<title>` baked into
 * `index.html` is the title of every route unless something changes it. That is
 * how a tab reading "Plenilo.com - Find Jobs Worldwide" ends up sitting on a
 * job listing: the tab strip, the history menu and a bookmark all describe the
 * homepage no matter where the reader actually is.
 *
 * Every route therefore declares its own title through `usePageMeta`, in the
 * shape the rest of the web uses — "<what this page is> | <site>" — with the
 * specific part first, because a tab is truncated from the right and a row of
 * tabs that all begin with the site name is a row of identical tabs.
 *
 * ## What this hook is, and is not, responsible for
 *
 * It is responsible for what a *person* sees while navigating: the tab, the
 * history entry, the bookmark. It is no longer what search engines and link
 * unfurlers read. `api/prerender.ts` writes the same title, description,
 * canonical, Open Graph tags and JSON-LD into the HTML before it is served,
 * because a crawler that does not run JavaScript — Bing, LinkedIn, Facebook,
 * WhatsApp — never reaches the code below, and one that does reaches it days
 * later on a second pass.
 *
 * So this hook and the prerenderer describe the same pages, and they agree
 * because the strings and the formatting rules live in one place
 * (`siteMeta.ts`, `pageMeta.ts`, `landingPages.ts`) that both import. Changing
 * a title here without changing it there is not possible; there is only one
 * copy of it.
 */

import { useEffect } from "react"
import { useLocation } from "react-router"

import {
  DEFAULT_DESCRIPTION,
  DESCRIPTION_BUDGET,
  canonicalUrl,
  defaultSocialImage,
  pageTitle,
  truncate,
} from "./siteMeta"

// Re-exported so the many modules that already import these from `seo.ts` are
// unaffected by the split. `siteMeta.ts` holds the ones the edge runtime needs.
export {
  DEFAULT_DESCRIPTION,
  DEFAULT_TITLE,
  SITE_NAME,
  SITE_TAGLINE,
  canonicalUrl,
  formatTitle,
  socialCardUrl,
} from "./siteMeta"

export interface PageMeta {
  /** The page-specific part, unsuffixed: "Saved Jobs", not "Saved Jobs | …". */
  title?: string
  description?: string
  /**
   * Absolute URL of the preview image for this page.
   *
   * Only worth setting where the page has an image of its own — a job listing
   * has a generated share card. Everything else inherits the site image, and
   * passing nothing is how a page says so.
   */
  image?: string
  /**
   * Overrides the canonical URL, which otherwise follows the current path.
   *
   * Only for a route that answers to more than one address and has to name the
   * one that counts — the landing pages resolve case-insensitively, so
   * `/JOBS-IN-PAKISTAN` renders the same page as `/jobs-in-pakistan` and must
   * not claim to be a second copy of it.
   */
  canonical?: string
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
 * The canonical URL drops the query string. That rule and the reasoning behind
 * it live in `canonicalUrl`; the short version is that filtered views of
 * `/jobs` are one page seen through a lens, while the facets actually worth
 * ranking for have paths of their own.
 */
export function usePageMeta(meta: PageMeta | null): void {
  const { pathname } = useLocation()
  const owns = meta !== null
  const title = meta?.title
  const description = meta?.description
  const image = meta?.image
  const canonicalOverride = meta?.canonical

  useEffect(() => {
    if (!owns) return

    const fullTitle = pageTitle(title)
    const pageDescription = truncate(
      description || DEFAULT_DESCRIPTION,
      DESCRIPTION_BUDGET,
    )
    const origin = window.location.origin
    const canonical = canonicalOverride
      ? canonicalUrl(origin, canonicalOverride)
      : canonicalUrl(origin, pathname)
    // Always written, never left to a previous route: client-side navigation
    // from one listing to another would otherwise leave the first listing's
    // share card attached to the second.
    const preview = image || defaultSocialImage(origin)

    document.title = fullTitle
    upsertMeta("name", "description", pageDescription)
    upsertMeta("property", "og:site_name", "Plenilo.com")
    upsertMeta("property", "og:type", "website")
    upsertMeta("property", "og:title", fullTitle)
    upsertMeta("property", "og:description", pageDescription)
    upsertMeta("property", "og:url", canonical)
    upsertMeta("property", "og:image", preview)
    upsertMeta("name", "twitter:card", "summary_large_image")
    upsertMeta("name", "twitter:title", fullTitle)
    upsertMeta("name", "twitter:description", pageDescription)
    upsertMeta("name", "twitter:image", preview)
    upsertCanonical(canonical)
  }, [owns, title, description, image, canonicalOverride, pathname])
}
