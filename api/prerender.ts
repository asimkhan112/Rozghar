/**
 * Server-side metadata for the single-page app.
 *
 * ## What this is for
 *
 * `dist/index.html` is one file with one `<title>`, one description and an
 * empty `<div id="root">`. Every URL on the site serves it byte-for-byte, so
 * before this function existed, fetching a job listing as a crawler returned a
 * document that described the homepage and contained no listing.
 *
 * Google renders JavaScript and would eventually have seen the real page, but
 * on a second pass that can lag the first crawl by days — and these listings
 * carry an `expiry_date` measured in weeks. Bing, LinkedIn, Facebook and
 * WhatsApp do not render JavaScript at all, which is why a job link shared into
 * a WhatsApp group unfurled as the generic homepage no matter which job it was.
 *
 * This function sits in front of the shell, resolves what the URL is *about*,
 * asks the API, and writes the answer into the head as metadata and JSON-LD.
 *
 * ## The same HTML for everyone
 *
 * There is no crawler detection here on purpose. Serving assembled HTML to
 * Googlebot and a bare shell to people is cloaking, it is against Google's
 * guidelines whatever the intent, and the penalty for being judged to have done
 * it is severe. Everyone gets the same document; the difference is that a
 * browser then boots React over it and a crawler does not.
 *
 * ## Why it may never throw
 *
 * `vercel.ts` routes every page request here, so an unhandled error is not a
 * degraded listing — it is the whole site down. Every branch that can fail
 * falls back to the unmodified shell, which is exactly what shipped before this
 * existed. The only response that is not HTML is a 503 when the shell itself
 * cannot be read, and that is deliberate: 503 tells a crawler to come back,
 * where an empty 200 tells it the page is genuinely blank and to drop it.
 */

import { applyHead, type HeadPlan } from './_seo/html'
import {
  breadcrumbSchema,
  itemListSchema,
  jobPostingSchema,
  serializeJsonLd,
  siteSchema,
} from './_seo/schema'
import type { WireJobDetail, WireJobList, WireLocation, WireCategory } from './_seo/types'
import {
  DEFAULT_DESCRIPTION,
  DEFAULT_TITLE,
  DESCRIPTION_BUDGET,
  canonicalUrl,
  defaultSocialImage,
  pageTitle,
  socialCardUrl,
  truncate,
} from '../src/lib/siteMeta'
import { NOT_FOUND_META, STATIC_PAGE_META, isNoindexPath } from '../src/lib/pageMeta'
import { landingCopy, landingPath, resolveLanding, type Landing } from '../src/lib/landingPages'

export const config = { runtime: 'edge' }

/**
 * How long the API gets before the page ships without its metadata.
 *
 * Set from measurement, not from taste: the jobs endpoint currently answers a
 * detail request in about four seconds, so the 2.5s this started at expired
 * before almost every real listing and would have published a 404 for each one.
 *
 * A visitor waiting four seconds for the document is genuinely bad, and the
 * only reason it is tolerable is the edge cache below — `s-maxage` plus
 * `stale-while-revalidate` means one visitor per URL per hour pays this, and
 * everyone after them is served from the edge while the refresh happens behind
 * them. That is a mitigation, not a fix. The fix is for the API to answer
 * faster, and until it does this number cannot come down.
 */
const API_TIMEOUT_MS = 5000

/** The shell is a static file on the same deployment; it should be immediate. */
const SHELL_TIMEOUT_MS = 4000

/** How many listings a browse page names in its `ItemList`. */
const LIST_SCHEMA_SIZE = 20

/**
 * The built shell, remembered between invocations.
 *
 * Module scope persists for the life of a warm instance, so the extra fetch is
 * paid once per instance rather than once per request. It is safe to cache for
 * that long precisely because it cannot go stale: a new deployment is new
 * instances, and the shell only changes when there is one.
 */
let cachedShell: string | null = null

/**
 * Fetches `/index.html` from this deployment.
 *
 * Vercel resolves the filesystem before rewrites — the same rule `vercel.ts`
 * relies on when it deletes `dist/robots.txt` so the backend's copy can win —
 * so this reads the real static file and does not re-enter this function.
 */
async function loadShell(origin: string): Promise<string | null> {
  if (cachedShell) return cachedShell
  try {
    const response = await fetch(`${origin}/index.html`, {
      signal: AbortSignal.timeout(SHELL_TIMEOUT_MS),
    })
    if (!response.ok) return null
    const html = await response.text()
    // A body with no head is not the shell — most likely an error page from
    // somewhere upstream. Caching it would poison every request this instance
    // serves for as long as it lives.
    if (!/<\/head>/i.test(html)) return null
    cachedShell = html
    return html
  } catch {
    return null
  }
}

/**
 * The three answers a fetch can give, kept apart.
 *
 * Collapsing `absent` and `unavailable` into one "no data" is the mistake this
 * type exists to prevent. They call for opposite responses: a listing the API
 * says is gone must return 404 so the dead URL stops being crawled, while a
 * listing the API merely failed to hand over in time must *not* — publishing a
 * 404 for a live job because the database was slow tells Google to drop a page
 * that is perfectly fine, and it will be believed.
 */
type Fetched<T> = { kind: 'ok'; data: T } | { kind: 'absent' } | { kind: 'unavailable' }

/** Fetches JSON, classifying the outcome. Never throws. */
async function fetchJson<T>(url: string): Promise<Fetched<T>> {
  try {
    const response = await fetch(url, {
      signal: AbortSignal.timeout(API_TIMEOUT_MS),
      headers: { accept: 'application/json' },
    })
    // 404 is "no listing at this address"; 410 is "there was one and it is
    // gone". Both are the API stating a fact about the URL.
    if (response.status === 404 || response.status === 410) return { kind: 'absent' }
    if (!response.ok) return { kind: 'unavailable' }
    return { kind: 'ok', data: (await response.json()) as T }
  } catch {
    // Timeout, DNS, connection reset — the API said nothing at all.
    return { kind: 'unavailable' }
  }
}

/**
 * Where the API lives.
 *
 * `API_ORIGIN` is the backend directly, which is one hop rather than two —
 * going through this deployment's own `/api` rewrite would mean Vercel proxying
 * a request that originated inside Vercel. It falls back to the public path so
 * a deployment that forgot the variable degrades to slower rather than broken.
 */
function apiBase(origin: string): string {
  const configured = process.env.API_ORIGIN?.replace(/\/$/, '')
  return configured ? `${configured}/api/v1` : `${origin}/api/v1`
}

/** The public origin, preferring the proxy's view of the request. */
function resolveOrigin(request: Request): string {
  const url = new URL(request.url)
  const host = request.headers.get('x-forwarded-host') ?? request.headers.get('host') ?? url.host
  const proto = request.headers.get('x-forwarded-proto') ?? url.protocol.replace(':', '')
  return `${proto}://${host}`
}

interface Resolved {
  plan: HeadPlan
  status: number
}

/** The shell's own metadata, used for anything with nothing better to say. */
function baseline(origin: string, pathname: string, noindex = false): HeadPlan {
  return {
    title: DEFAULT_TITLE,
    description: DEFAULT_DESCRIPTION,
    canonical: canonicalUrl(origin, pathname),
    image: defaultSocialImage(origin),
    ogType: 'website',
    jsonLd: [],
    noindex,
  }
}

function finish(plan: Omit<HeadPlan, 'title' | 'description'> & {
  title: string
  description: string
}): HeadPlan {
  return {
    ...plan,
    title: pageTitle(plan.title),
    description: truncate(plan.description, DESCRIPTION_BUDGET),
  }
}

/** The 404 surface: honest status, honest title, and never indexed. */
function notFound(origin: string, pathname: string): Resolved {
  return {
    status: 404,
    plan: finish({
      ...baseline(origin, pathname, true),
      title: NOT_FOUND_META.title,
      description: NOT_FOUND_META.description,
      image: undefined,
    }),
  }
}

/**
 * The API could not be reached. The page still ships, with the shell's own
 * metadata and a 200.
 *
 * Not a 404, and not a 503. The page is real and React will render it from the
 * browser, so the only thing missing is the metadata — and a crawler that
 * renders JavaScript will still see the client-side tags `usePageMeta` writes.
 * Answering 404 here would retract a live listing over a slow query; answering
 * 503 would deny a working page to a reader who could have had it.
 */
function unavailable(origin: string, pathname: string): Resolved {
  return { status: 200, plan: baseline(origin, pathname) }
}

/** One listing: the `JobPosting` that makes it eligible for Google's job box. */
async function resolveJob(
  origin: string,
  pathname: string,
  slug: string,
): Promise<Resolved> {
  const fetched = await fetchJson<WireJobDetail>(
    `${apiBase(origin)}/jobs/${encodeURIComponent(slug)}`,
  )

  // A listing the API says is gone. Returning 200 with a "not found" screen —
  // which is what the SPA alone did — is a soft 404, and a board that
  // accumulates them spends its crawl budget rediscovering dead URLs forever.
  if (fetched.kind === 'absent') return notFound(origin, pathname)
  if (fetched.kind === 'unavailable') return unavailable(origin, pathname)
  const job = fetched.data

  const canonical = canonicalUrl(origin, pathname)
  const pay = job.salary.disclosed && (job.salary.min || job.salary.max)
  const where = job.location.display_name

  return {
    status: 200,
    plan: finish({
      title: `${job.title} at ${job.company_name}`,
      description:
        `${job.title} at ${job.company_name} — ${where}. ` +
        `${job.employment_type.replace('_', '-')}, ${job.work_type.replace('_', '-')}` +
        `${pay ? `, ${job.salary.currency} ${job.salary.min ?? ''}–${job.salary.max ?? ''} per ${job.salary.period}` : ''}. ` +
        'Apply directly on Plenilo.com.',
      canonical,
      image: socialCardUrl(origin, job.slug),
      ogType: 'article',
      jsonLd: [
        serializeJsonLd(jobPostingSchema(job, canonical)),
        serializeJsonLd(
          breadcrumbSchema([
            { name: 'Home', url: `${origin}/` },
            { name: 'Jobs', url: `${origin}/jobs` },
            { name: job.category.name, url: `${origin}/${job.category.slug}-jobs` },
            { name: job.title, url: canonical },
          ]),
        ),
      ],
    }),
  }
}

/**
 * Turns a landing page into the API query behind it.
 *
 * Returns null for a landing whose subject the taxonomy does not actually hold
 * — an invented category or a city with no page. The caller renders that as a
 * 404 rather than as an empty result set, because a site that answers every
 * guessable address with a valid-looking empty page teaches a crawler that its
 * URL space is infinite.
 */
type LandingSubject =
  | { kind: 'ok'; query: string; label: string }
  /** The taxonomy answered and does not contain this category or city. */
  | { kind: 'absent' }
  | { kind: 'unavailable' }

async function landingQuery(origin: string, landing: Landing): Promise<LandingSubject> {
  switch (landing.kind) {
    case 'work-type':
      return { kind: 'ok', query: `work_type=${landing.workType}`, label: 'Remote' }

    case 'country':
      return {
        kind: 'ok',
        query: `country=${landing.country.code}`,
        label: landing.country.name,
      }

    case 'location': {
      const fetched = await fetchJson<WireLocation[]>(`${apiBase(origin)}/locations`)
      if (fetched.kind !== 'ok') return { kind: 'unavailable' }
      const match = fetched.data.find((l) => l.slug === landing.locationSlug)
      return match
        ? { kind: 'ok', query: `location=${match.slug}`, label: match.display_name }
        : { kind: 'absent' }
    }

    case 'category': {
      const fetched = await fetchJson<WireCategory[]>(`${apiBase(origin)}/categories`)
      if (fetched.kind !== 'ok') return { kind: 'unavailable' }
      const match = fetched.data.find((c) => c.slug === landing.categorySlug)
      return match
        ? { kind: 'ok', query: `category=${match.slug}`, label: match.name }
        : { kind: 'absent' }
    }
  }
}

/**
 * The listings a landing page shows, addressed by the slug in the URL.
 *
 * Deliberately independent of `landingQuery`, which is what lets the two run at
 * once. The taxonomy lookup exists to find a *label* and to confirm the subject
 * is real; the filter itself only ever needed the slug that was already in the
 * path. Chaining them would have made a category page two four-second round
 * trips deep for no reason.
 */
function listingQuery(landing: Landing): string {
  switch (landing.kind) {
    case 'work-type':
      return `work_type=${landing.workType}`
    case 'country':
      return `country=${landing.country.code}`
    case 'location':
      return `location=${encodeURIComponent(landing.locationSlug)}`
    case 'category':
      return `category=${encodeURIComponent(landing.categorySlug)}`
  }
}

async function resolveLandingPage(
  origin: string,
  pathname: string,
  landing: Landing,
): Promise<Resolved> {
  // Both round trips at once. Sequentially this page cost two API timeouts.
  const [subject, list] = await Promise.all([
    landingQuery(origin, landing),
    fetchJson<WireJobList>(
      `${apiBase(origin)}/jobs?${listingQuery(landing)}&per_page=${LIST_SCHEMA_SIZE}`,
    ),
  ])

  // The taxonomy answered and has no such category or city: this URL names
  // nothing, and guessable addresses must not all resolve to an empty page.
  if (subject.kind === 'absent') return notFound(origin, pathname)
  // The taxonomy did not answer. The page is probably fine, so it ships —
  // but with generic metadata rather than a heading built from a label that
  // was never retrieved.
  if (subject.kind === 'unavailable') return unavailable(origin, pathname)

  const copy = landingCopy(landing, subject.label)
  const items = list.kind === 'ok' ? list.data.items : []

  return {
    status: 200,
    plan: finish({
      title: copy.title,
      description: copy.description,
      // The *resolved* path, not the requested one. `resolveLanding` is
      // case-insensitive, so `/JOBS-IN-PAKISTAN` reaches this page too — and
      // if each spelling canonicalised to itself, every landing page would be
      // indexable under as many addresses as there are ways to capitalise it.
      canonical: canonicalUrl(origin, landingPath(landing)),
      image: defaultSocialImage(origin),
      ogType: 'website',
      // An empty landing page still gets its metadata, but no ItemList — an
      // ItemList of nothing states that the collection is empty, which is a
      // worse thing to say than saying nothing.
      jsonLd: items.length ? [serializeJsonLd(itemListSchema(items, origin))] : [],
    }),
  }
}

async function resolve(origin: string, pathname: string): Promise<Resolved> {
  if (isNoindexPath(pathname)) {
    return { status: 200, plan: baseline(origin, pathname, true) }
  }

  if (pathname === '/') {
    return {
      status: 200,
      plan: finish({
        ...baseline(origin, pathname),
        title: DEFAULT_TITLE,
        description: DEFAULT_DESCRIPTION,
        jsonLd: siteSchema(origin, DEFAULT_DESCRIPTION).map(serializeJsonLd),
      }),
    }
  }

  const jobMatch = /^\/jobs\/([^/]+)\/?$/.exec(pathname)
  if (jobMatch) return resolveJob(origin, pathname, decodeURIComponent(jobMatch[1]))

  if (pathname === '/jobs') {
    const list = await fetchJson<WireJobList>(
      `${apiBase(origin)}/jobs?per_page=${LIST_SCHEMA_SIZE}`,
    )
    // The browse page is real whether or not the list came back, so an
    // unreachable API costs it its `ItemList` and nothing else.
    const items = list.kind === 'ok' ? list.data.items : []
    const meta = STATIC_PAGE_META['/jobs']
    return {
      status: 200,
      plan: finish({
        ...baseline(origin, pathname),
        title: meta.title,
        description: meta.description,
        jsonLd: items.length ? [serializeJsonLd(itemListSchema(items, origin))] : [],
      }),
    }
  }

  const staticMeta = STATIC_PAGE_META[pathname]
  if (staticMeta) {
    return {
      status: 200,
      plan: finish({
        ...baseline(origin, pathname),
        title: staticMeta.title,
        description: staticMeta.description,
      }),
    }
  }

  // Landing pages are single-segment by construction: `/remote-jobs`,
  // `/jobs-in-lahore`, `/design-creative-jobs`.
  const segments = pathname.split('/').filter(Boolean)
  if (segments.length === 1) {
    const landing = resolveLanding(segments[0])
    if (landing) return resolveLandingPage(origin, pathname, landing)
  }

  // Nothing claims this URL. The SPA will render its 404 screen; this makes the
  // status line agree with it.
  return {
    status: 404,
    plan: finish({
      ...baseline(origin, pathname, true),
      title: NOT_FOUND_META.title,
      description: NOT_FOUND_META.description,
      image: undefined,
    }),
  }
}

/**
 * The page that was actually requested.
 *
 * `vercel.ts` forwards it as `?path=` because a rewrite does not reliably leave
 * the original path in `req.url` — without this the function would resolve its
 * own address, `/api/prerender`, for every request on the site. The fallback to
 * `pathname` covers a direct hit on the function, which should only happen
 * while someone is debugging it.
 *
 * The value arrives from the URL, so it is treated as untrusted: anything that
 * is not a plain absolute path is replaced with `/` rather than being allowed
 * to reach the API as a path fragment.
 */
function requestedPath(request: Request): string {
  const url = new URL(request.url)
  const forwarded = url.searchParams.get('path')
  if (!forwarded) return url.pathname

  // Must be absolute and single-segment-safe: no scheme, no `//host` form that
  // some URL parsers read as protocol-relative, no `..` traversal.
  if (!forwarded.startsWith('/') || forwarded.startsWith('//')) return '/'
  if (forwarded.includes('..') || forwarded.includes('\\')) return '/'
  return forwarded
}

export default async function handler(request: Request): Promise<Response> {
  const origin = resolveOrigin(request)
  const pathname = requestedPath(request)

  const shell = await loadShell(origin)
  if (!shell) {
    // Tell the crawler to come back rather than showing it a blank page it
    // would be entitled to treat as the truth about this URL.
    return new Response('Temporarily unavailable', {
      status: 503,
      headers: { 'content-type': 'text/plain; charset=utf-8', 'retry-after': '60' },
    })
  }

  let resolved: Resolved
  try {
    resolved = await resolve(origin, pathname)
  } catch {
    // Metadata is an enhancement. Losing it must not lose the page.
    resolved = { status: 200, plan: baseline(origin, pathname) }
  }

  return new Response(applyHead(shell, resolved.plan), {
    status: resolved.status,
    headers: {
      'content-type': 'text/html; charset=utf-8',
      // Served from the edge cache while a stale copy is refreshed behind it,
      // so the API round trip above is paid by one visitor an hour per URL
      // rather than by every visitor. `must-revalidate` is deliberately absent:
      // a stale title for a minute is a far better outcome than a slow page.
      'cache-control': 'public, max-age=0, s-maxage=3600, stale-while-revalidate=86400',
    },
  })
}
