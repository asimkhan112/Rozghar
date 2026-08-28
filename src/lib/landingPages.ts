/**
 * Keyword landing pages: the URLs built to be found.
 *
 * ## Why these exist rather than just filters
 *
 * `/jobs?work_type=remote` and `/remote-jobs` show the same listings, but only
 * one of them can rank. A query string says "the jobs page, narrowed"; a path
 * says "this is the remote jobs page". Search engines index the second and
 * consolidate the first, which is why every job board that competes for
 * "remote jobs" owns a path for it.
 *
 * The practical difference is what a page is allowed to *say*. A filtered view
 * of `/jobs` has to keep one generic title and one generic H1 — anything else
 * would be a page whose identity changes under it. A landing path has one
 * subject, so it gets its own title, its own H1 and its own opening paragraph,
 * which is the text a result is actually matched and ranked against.
 *
 * ## Why this module is framework-free
 *
 * `api/prerender.ts` imports it directly. That function runs on Vercel's edge
 * runtime with no React, no router and no `@/` alias, so nothing here may
 * import anything that assumes a browser. Keeping it to plain data and pure
 * functions is what lets one definition drive the route table, the rendered
 * copy and the server-side `<title>` without three of them drifting apart.
 *
 * ## The URL grammar
 *
 *   /remote-jobs              the work type
 *   /jobs-in-pakistan         a country   (checked first — the list is closed)
 *   /jobs-in-lahore           a city      (any location slug the taxonomy has)
 *   /it-technology-jobs       a category  (any category slug the taxonomy has)
 *
 * Countries are resolved before cities because their slugs are a fixed, known
 * set and a city cannot be added to the taxonomy that would shadow one.
 */

/** The job list's `work_type` values, repeated here to avoid a browser import. */
export type LandingWorkType = 'remote' | 'on_site' | 'hybrid'

export interface CountryLanding {
  /** URL segment after `jobs-in-`. */
  slug: string
  /** ISO 3166-1 alpha-2, which is what the API's `country` filter takes. */
  code: string
  /** How the place is named in a sentence: "jobs in Pakistan". */
  name: string
  /** The adjective a searcher actually types: "American jobs", "Pakistani jobs". */
  demonym: string
}

/**
 * Countries with their own landing page.
 *
 * A closed list, not every country the taxonomy mentions. A page for a country
 * with four listings is a thin page, and a hundred thin pages is a site-wide
 * quality signal rather than a hundred chances to rank. These are the markets
 * the board actually recruits for; add to it when the listing count justifies
 * the page, not in anticipation of it.
 */
export const COUNTRY_LANDINGS: readonly CountryLanding[] = [
  { slug: 'pakistan', code: 'PK', name: 'Pakistan', demonym: 'Pakistani' },
  { slug: 'usa', code: 'US', name: 'the United States', demonym: 'American' },
  { slug: 'uk', code: 'GB', name: 'the United Kingdom', demonym: 'British' },
  { slug: 'uae', code: 'AE', name: 'the United Arab Emirates', demonym: 'UAE' },
  { slug: 'saudi-arabia', code: 'SA', name: 'Saudi Arabia', demonym: 'Saudi' },
  { slug: 'canada', code: 'CA', name: 'Canada', demonym: 'Canadian' },
]

export type Landing =
  | { kind: 'work-type'; workType: LandingWorkType }
  | { kind: 'country'; country: CountryLanding }
  | { kind: 'location'; locationSlug: string }
  | { kind: 'category'; categorySlug: string }

/**
 * A single URL segment → the landing page it addresses, or null.
 *
 * Null means "not a landing URL", which the route turns into a real 404 rather
 * than an empty list. A page that answers every invented address with zero
 * results is a soft 404, and a site that emits them at scale gets its crawl
 * budget spent on URLs that were never real.
 *
 * Note this only *parses*. Whether the taxonomy actually holds the location or
 * category named here is settled by the page, which has the live lists.
 */
export function resolveLanding(segment: string): Landing | null {
  const slug = segment.trim().toLowerCase()
  if (!slug || !/^[a-z0-9-]+$/.test(slug)) return null

  if (slug === 'remote-jobs') return { kind: 'work-type', workType: 'remote' }

  if (slug.startsWith('jobs-in-')) {
    const place = slug.slice('jobs-in-'.length)
    if (!place) return null
    const country = COUNTRY_LANDINGS.find((c) => c.slug === place)
    if (country) return { kind: 'country', country }
    return { kind: 'location', locationSlug: place }
  }

  if (slug.endsWith('-jobs')) {
    const category = slug.slice(0, -'-jobs'.length)
    // Guards `/-jobs`, and stops `/remote-jobs` being reached by this branch
    // if the static case above is ever removed.
    if (!category) return null
    return { kind: 'category', categorySlug: category }
  }

  return null
}

/** The path for a landing page, so links and the sitemap agree by construction. */
export function landingPath(landing: Landing): string {
  switch (landing.kind) {
    case 'work-type':
      return landing.workType === 'remote' ? '/remote-jobs' : '/jobs'
    case 'country':
      return `/jobs-in-${landing.country.slug}`
    case 'location':
      return `/jobs-in-${landing.locationSlug}`
    case 'category':
      return `/${landing.categorySlug}-jobs`
  }
}

export interface LandingCopy {
  /** Unsuffixed page title — `formatTitle` adds the site name. */
  title: string
  /** The visible H1. Kept close to the title without being identical: the
   *  title is written for a result listing, the H1 for someone already here. */
  heading: string
  description: string
  /** Opening paragraph. The only substantial indexable prose on the page, and
   *  the thing that stops one landing page reading as a copy of the next. */
  intro: string
}

/**
 * The words a landing page is made of.
 *
 * `label` is the human name from the live taxonomy — "IT & Technology",
 * "Lahore, Pakistan" — because a slug is not a noun and "it-technology jobs" is
 * not a phrase anyone searches for.
 */
export function landingCopy(landing: Landing, label: string): LandingCopy {
  switch (landing.kind) {
    case 'work-type':
      return {
        title: 'Remote Jobs — Work From Anywhere',
        heading: 'Remote Jobs',
        description:
          'Browse remote jobs you can do from anywhere — full-time, contract and part-time roles from employers hiring worldwide. Every listing links straight to the employer. No account required.',
        intro:
          'Every role here is fully remote: no relocation, no commute, and no office attendance expected. Listings come from employers hiring across software, design, finance, customer support and more, and each one links directly to the employer’s own application page — Plenilo never sits between you and the company.',
      }

    case 'country': {
      const { name, demonym } = landing.country
      return {
        title: `Jobs in ${name} — ${demonym} Job Openings`,
        heading: `Jobs in ${name}`,
        description: `Find current job openings in ${name} — remote, hybrid and on-site roles across every field, updated daily. Apply directly with the employer. No account required.`,
        intro: `Live vacancies from employers hiring in ${name}, spanning technology, finance, healthcare, government and the trades. Filter by city, category, work type or salary to narrow the list, then apply on the employer’s own site — there is no registration, no CV upload and no fee.`,
      }
    }

    case 'location':
      return {
        title: `Jobs in ${label}`,
        heading: `Jobs in ${label}`,
        description: `Current job vacancies in ${label} — full-time, part-time, contract and remote-friendly roles, updated daily. Apply directly with the employer.`,
        intro: `Open positions with employers hiring in ${label}. Listings are refreshed daily and each one links straight through to the employer’s application page, so you can apply without creating an account here.`,
      }

    case 'category':
      return {
        title: `${label} Jobs`,
        heading: `${label} Jobs`,
        description: `Browse ${label.toLowerCase()} jobs — remote, hybrid and on-site openings from employers hiring now. Updated daily, apply directly, no account required.`,
        intro: `Current openings in ${label.toLowerCase()}, from entry level through senior roles. Every listing shows the salary where the employer disclosed one, and links directly to their own application page.`,
      }
  }
}
