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

import { applyBody, applyHead, type HeadPlan } from './_seo/html'
import { renderBody, type BodyPlan, type LinkItem } from './_seo/body'
import {
  breadcrumbSchema,
  itemListSchema,
  jobPostingSchema,
  serializeJsonLd,
  siteSchema,
} from './_seo/schema'
import type {
  WireCategory,
  WireJobDetail,
  WireJobList,
  WireJobSummary,
  WireLocation,
} from './_seo/types'
import {
  DEFAULT_DESCRIPTION,
  DEFAULT_TITLE,
  DESCRIPTION_BUDGET,
  SITE_TAGLINE,
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
 * Where the built shell is fetched from, in order of preference.
 *
 * `app.html` first because that is what `vercel.ts` renames it to at build
 * time. The rename exists so that nothing on the filesystem answers `/`: Vercel
 * resolves files before rewrites, so while the shell sat at `index.html` the
 * home page was served straight from disk and this function never ran for it —
 * the site's most-read URL was its only one with no metadata and no content.
 *
 * `index.html` stays in the list as the fallback. A deployment built without
 * that command — a preview built by hand, a rolled-back configuration — then
 * still renders every other route correctly instead of answering 503 across
 * the whole site.
 */
const SHELL_PATHS = ['/app.html', '/index.html'] as const

/**
 * Fetches the built shell from this deployment.
 *
 * Vercel resolves the filesystem before rewrites — the same rule `vercel.ts`
 * relies on when it deletes `dist/robots.txt` so the backend's copy can win —
 * so this reads the real static file and does not re-enter this function.
 */
async function loadShell(origin: string): Promise<string | null> {
  if (cachedShell) return cachedShell
  for (const path of SHELL_PATHS) {
    try {
      const response = await fetch(`${origin}${path}`, {
        signal: AbortSignal.timeout(SHELL_TIMEOUT_MS),
      })
      if (!response.ok) continue
      const html = await response.text()
      // A body with no head is not the shell — most likely an error page from
      // somewhere upstream, or the catch-all rewrite answering for a path that
      // no longer exists. Caching it would poison every request this instance
      // serves for as long as it lives.
      if (!/<\/head>/i.test(html)) continue
      cachedShell = html
      return html
    } catch {
      // Timed out or refused. Try the next candidate before giving up.
    }
  }
  return null
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
  /**
   * What to write into `#root`. Optional because a page may resolve its
   * metadata and still have nothing to say in the body — the API was slow, the
   * URL names nothing — and an absent plan leaves the shell's empty mount
   * exactly as it was.
   */
  body?: BodyPlan
}

/** `full_time` -> `Full-time`, `on_site` -> `On-site`. */
function humanise(value: string): string {
  const spaced = value.replace(/_/g, '-')
  return spaced.charAt(0).toUpperCase() + spaced.slice(1)
}

/**
 * A salary as a person reads it, or null when there is nothing to state.
 *
 * Undisclosed pay renders as no row at all rather than as "Not specified": the
 * fact is already absent from the page, and inventing a label for its absence
 * fills a listing with rows that say nothing.
 */
function formatSalary(salary: WireJobSummary['salary']): string | null {
  if (!salary.disclosed) return null
  const amount = (value: string | null) => {
    if (!value) return null
    const parsed = Number(value)
    // Decimals arrive as strings and are not always numeric; anything that does
    // not parse is printed as it came rather than rendered as `NaN`.
    return Number.isFinite(parsed)
      ? parsed.toLocaleString('en-US', { maximumFractionDigits: 0 })
      : value
  }
  const min = amount(salary.min)
  const max = amount(salary.max)
  const range = min && max ? `${min}–${max}` : (min ?? max)
  if (!range) return null
  return `${salary.currency} ${range} per ${salary.period}`
}

/** A listing as one row of a browse page: title, then who and where. */
function jobLink(job: WireJobSummary): LinkItem {
  return {
    label: job.title,
    href: `/jobs/${job.slug}`,
    note: `${job.company_name} — ${job.location.display_name}`,
  }
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
    body: { heading: NOT_FOUND_META.title, intro: NOT_FOUND_META.description },
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
  return {
    status: 200,
    plan: baseline(origin, pathname),
    // No data means no listing to write out, but the reader still gets a page
    // that names the site and links into it rather than an empty container.
    body: { heading: SITE_TAGLINE, intro: DEFAULT_DESCRIPTION },
  }
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

  const salary = formatSalary(job.salary)

  return {
    status: 200,
    body: {
      breadcrumbs: [
        { label: 'Home', href: '/' },
        { label: 'Jobs', href: '/jobs' },
        { label: job.category.name, href: `/${job.category.slug}-jobs` },
      ],
      heading: job.title,
      intro: `${job.company_name} — ${where}`,
      blocks: [
        {
          kind: 'facts',
          items: [
            { label: 'Company', value: job.company_name },
            { label: 'Location', value: where },
            { label: 'Employment type', value: humanise(job.employment_type) },
            { label: 'Work type', value: humanise(job.work_type) },
            { label: 'Category', value: job.category.name },
            ...(salary ? [{ label: 'Salary', value: salary }] : []),
          ],
        },
        { kind: 'prose', heading: 'Job description', body: job.description },
        { kind: 'list', heading: 'Responsibilities', items: job.responsibilities ?? [] },
        { kind: 'list', heading: 'Requirements', items: job.requirements ?? [] },
        { kind: 'list', heading: 'Benefits', items: job.benefits ?? [] },
        // The employer's own page, which is where every application goes.
        { kind: 'action', label: 'Apply for this job', href: job.apply_url },
      ],
    },
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
    body: {
      heading: copy.heading,
      intro: copy.intro,
      blocks: [{ kind: 'links', heading: 'Open positions', items: items.map(jobLink) }],
    },
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
    // The homepage used to resolve without touching the API, because its title
    // and description are constants. It fetches now for the body: the front
    // page of a job board that lists no jobs is the emptiest page on the site,
    // and it is the one anything auditing the site reads first.
    const list = await fetchJson<WireJobList>(
      `${apiBase(origin)}/jobs?per_page=${LIST_SCHEMA_SIZE}`,
    )
    const items = list.kind === 'ok' ? list.data.items : []
    return {
      status: 200,
      body: {
        heading: SITE_TAGLINE,
        intro: DEFAULT_DESCRIPTION,
        blocks: [{ kind: 'links', heading: 'Latest jobs', items: items.map(jobLink) }],
      },
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
      body: {
        heading: meta.title,
        intro: meta.description,
        blocks: [{ kind: 'links', heading: 'Open positions', items: items.map(jobLink) }],
      },
      plan: finish({
        ...baseline(origin, pathname),
        title: meta.title,
        description: meta.description,
        jsonLd: items.length ? [serializeJsonLd(itemListSchema(items, origin))] : [],
      }),
    }
  }

  if (pathname === '/categories') {
    const fetched = await fetchJson<WireCategory[]>(`${apiBase(origin)}/categories`)
    const meta = STATIC_PAGE_META['/categories']
    const categories = fetched.kind === 'ok' ? fetched.data : []
    return {
      status: 200,
      body: {
        heading: meta.title,
        intro: meta.description,
        blocks: [
          {
            kind: 'links',
            heading: 'Browse by field',
            items: categories.map((category) => ({
              label: category.name,
              href: `/${category.slug}-jobs`,
              note:
                category.job_count === undefined
                  ? undefined
                  : `${category.job_count} open ${category.job_count === 1 ? 'role' : 'roles'}`,
            })),
          },
        ],
      },
      plan: finish({
        ...baseline(origin, pathname),
        title: meta.title,
        description: meta.description,
      }),
    }
  }

  const staticMeta = STATIC_PAGE_META[pathname]
  if (staticMeta) {
    return {
      status: 200,
      // Heading and lead only. The prose on these pages lives in JSX, and
      // restating it here would be a second copy free to drift from the one
      // readers see — the exact failure `pageMeta.ts` exists to prevent. Both
      // strings below come from that shared module, so this page's server body
      // and its rendered body cannot disagree about what it is.
      body: { heading: staticMeta.title, intro: staticMeta.description },
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
    body: { heading: NOT_FOUND_META.title, intro: NOT_FOUND_META.description },
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

  // Head first, then the body it describes. Both are best-effort by
  // construction: each returns the document unchanged if its anchor is missing,
  // so a shell that changes shape costs metadata or content, never the page.
  const document = applyBody(
    applyHead(shell, resolved.plan),
    resolved.body ? renderBody(resolved.body) : '',
  )

  return new Response(document, {
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
