/**
 * schema.org JSON-LD, built from the API's wire shape.
 *
 * ## Why this exists at all
 *
 * Google's job experience — the boxed listings that sit above the ordinary
 * results — is populated *only* from `JobPosting` structured data. It is not
 * inferred from page text, and there is no other route in. A job board without
 * this markup is not ranking badly for job queries; it is ineligible for the
 * surface where nearly all job queries are answered.
 *
 * ## Why it runs on the server
 *
 * Structured data emitted by React after the bundle boots is only seen by
 * crawlers that execute JavaScript, on a second pass that can lag the first by
 * days. Listings here carry an `expiry_date` measured in weeks, so a listing
 * indexed late is a listing indexed after it stopped being true. Emitting the
 * markup into the HTML makes indexing single-pass.
 *
 * ## The rule every builder here follows
 *
 * A field is omitted rather than guessed. Structured data that disagrees with
 * the page is a manual-action risk, and Google treats an absent recommended
 * property far more kindly than a present wrong one — so an undisclosed salary
 * produces no `baseSalary` at all rather than a zero, and an unknown country
 * produces no `applicantLocationRequirements` rather than a plausible default.
 */

import type {
  EmploymentType,
  SalaryPeriod,
  WireJobDetail,
  WireJobSummary,
  WireLocation,
  WorkType,
} from './types'

/** schema.org spells these out; the API uses its own enum. */
const EMPLOYMENT_TYPE: Record<EmploymentType, string> = {
  full_time: 'FULL_TIME',
  part_time: 'PART_TIME',
  // Not "CONTRACT". schema.org names the person, not the paper.
  contract: 'CONTRACTOR',
  internship: 'INTERN',
}

/** `unitText` on a QuantitativeValue. Google rejects lowercase. */
const SALARY_UNIT: Record<SalaryPeriod, string> = {
  hour: 'HOUR',
  month: 'MONTH',
  year: 'YEAR',
}

type Json = Record<string, unknown>

/** Drops keys whose value is null/undefined/empty so no half-filled node ships. */
function compact(node: Json): Json {
  const out: Json = {}
  for (const [key, value] of Object.entries(node)) {
    if (value === null || value === undefined) continue
    if (typeof value === 'string' && !value.trim()) continue
    if (Array.isArray(value) && value.length === 0) continue
    out[key] = value
  }
  return out
}

/** A decimal that arrived as a string, as a number — or null if it is neither. */
function amount(value: string | null): number | null {
  if (value === null) return null
  const parsed = Number(value)
  return Number.isFinite(parsed) ? parsed : null
}

/**
 * `datePosted` and `validThrough` must be ISO 8601.
 *
 * `published_at` already is. `expiry_date` is a bare date, which Google accepts,
 * but it is widened to end-of-day UTC so a listing does not read as expired for
 * the whole of its final day in every timezone west of the server.
 */
function asDateTime(value: string | null, { endOfDay = false } = {}): string | null {
  if (!value) return null
  if (!endOfDay) return value
  return /^\d{4}-\d{2}-\d{2}$/.test(value) ? `${value}T23:59:59Z` : value
}

function escapeHtml(value: string): string {
  return value
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
}

/**
 * The listing body as the HTML fragment `JobPosting.description` expects.
 *
 * Google explicitly wants formatting here — a wall of unbroken text is
 * documented as a quality problem — and the bullet arrays are the parts a
 * reader actually scans. The source strings are plain text from the editor, so
 * they are escaped before being wrapped: a job description containing "R&D" or
 * "C++ < C#" must not be able to close the tag it sits in.
 */
function descriptionHtml(job: WireJobDetail): string {
  const parts: string[] = []

  const body = job.description.trim()
  if (body) {
    const paragraphs = body
      .split(/\n{2,}/)
      .map((p) => p.trim())
      .filter(Boolean)
      .map((p) => `<p>${escapeHtml(p).replace(/\n/g, '<br>')}</p>`)
    parts.push(paragraphs.join(''))
  }

  const section = (heading: string, items: string[]) => {
    const clean = items.map((i) => i.trim()).filter(Boolean)
    if (!clean.length) return
    const list = clean.map((i) => `<li>${escapeHtml(i)}</li>`).join('')
    parts.push(`<h3>${heading}</h3><ul>${list}</ul>`)
  }

  section('Responsibilities', job.responsibilities)
  section('Requirements', job.requirements)
  section('Benefits', job.benefits)

  return parts.join('')
}

/** `jobLocation`, as a schema.org Place wrapping a PostalAddress. */
function placeFor(location: WireLocation): Json | null {
  const address = compact({
    '@type': 'PostalAddress',
    addressLocality: location.city,
    addressRegion: location.region,
    addressCountry: location.country,
  })
  // "@type" alone means every field was blank — a Place asserting nothing.
  if (Object.keys(address).length <= 1) return null
  return { '@type': 'Place', address }
}

/**
 * Where the work happens.
 *
 * Google models remote work as `jobLocationType: "TELECOMMUTE"` *plus*
 * `applicantLocationRequirements` naming the country a candidate must be in,
 * and reports TELECOMMUTE without that requirement as an error. So the
 * telecommute pair is only emitted when the country is actually known;
 * otherwise the listing falls back to describing its physical location, which
 * is incomplete but true.
 *
 * Hybrid roles are deliberately *not* telecommute: they require attendance, and
 * surfacing them to someone filtering for remote work is the kind of mismatch
 * that gets a site's markup distrusted.
 */
function locationFields(workType: WorkType, location: WireLocation): Json {
  const remote = workType === 'remote' || location.is_remote
  const place = placeFor(location)

  if (remote && location.country) {
    return {
      jobLocationType: 'TELECOMMUTE',
      applicantLocationRequirements: {
        '@type': 'Country',
        name: location.country,
      },
      // Kept alongside when known: a remote role advertised from a real office
      // still answers "remote jobs in Lahore".
      ...(place ? { jobLocation: place } : {}),
    }
  }

  return place ? { jobLocation: place } : {}
}

/** `baseSalary`, or nothing at all when the employer did not disclose one. */
function baseSalary(job: WireJobSummary): Json | null {
  const { salary } = job
  if (!salary.disclosed) return null

  const min = amount(salary.min)
  const max = amount(salary.max)
  if (min === null && max === null) return null
  // A published range of 0 is a placeholder, not an offer of nothing.
  if ((min ?? 0) <= 0 && (max ?? 0) <= 0) return null

  return {
    '@type': 'MonetaryAmount',
    currency: salary.currency,
    value: compact({
      '@type': 'QuantitativeValue',
      minValue: min && min > 0 ? min : null,
      maxValue: max && max > 0 ? max : null,
      unitText: SALARY_UNIT[salary.period],
    }),
  }
}

/**
 * The `JobPosting` for one listing.
 *
 * `directApply` is false on purpose. Applying happens on the employer's own
 * site — `apply_url` leaves Plenilo — and Google uses this flag to distinguish
 * boards that complete an application from boards that hand off. Claiming
 * otherwise is the single most common way a job board loses the rich result.
 */
export function jobPostingSchema(job: WireJobDetail, canonical: string): Json {
  return compact({
    '@context': 'https://schema.org/',
    '@type': 'JobPosting',
    title: job.title,
    description: descriptionHtml(job),
    identifier: {
      '@type': 'PropertyValue',
      name: 'Plenilo.com',
      value: job.id,
    },
    datePosted: asDateTime(job.published_at),
    validThrough: asDateTime(job.expiry_date, { endOfDay: true }),
    employmentType: EMPLOYMENT_TYPE[job.employment_type],
    hiringOrganization: compact({
      '@type': 'Organization',
      name: job.company_name,
      sameAs: job.company_website,
      logo: job.company_logo,
    }),
    ...locationFields(job.work_type, job.location),
    baseSalary: baseSalary(job),
    occupationalCategory: job.category.name,
    directApply: false,
    url: canonical,
  })
}

/** Trail above a listing, so the result renders as a path rather than a URL. */
export function breadcrumbSchema(
  trail: { name: string; url: string }[],
): Json {
  return {
    '@context': 'https://schema.org/',
    '@type': 'BreadcrumbList',
    itemListElement: trail.map((crumb, index) => ({
      '@type': 'ListItem',
      position: index + 1,
      name: crumb.name,
      item: crumb.url,
    })),
  }
}

/**
 * The listings on a browse page, in the order they are shown.
 *
 * `ItemList` does not itself win a rich result. It states that the page is a
 * collection and which URLs it collects, which is what stops a filtered browse
 * page being read as a near-duplicate of every other filtered browse page —
 * the failure mode that keeps landing pages out of the index.
 */
export function itemListSchema(jobs: WireJobSummary[], origin: string): Json {
  return {
    '@context': 'https://schema.org/',
    '@type': 'ItemList',
    itemListElement: jobs.map((job, index) => ({
      '@type': 'ListItem',
      position: index + 1,
      url: `${origin}/jobs/${job.slug}`,
      name: `${job.title} at ${job.company_name}`,
    })),
  }
}

/**
 * Site-level identity, emitted on the homepage.
 *
 * `WebSite` with a `SearchAction` is what lets Google show a search box inside
 * the site's own result. `Organization` is what a knowledge panel is built
 * from, and is how "Plenilo" as a brand name starts resolving to this site
 * rather than to the nearest similarly-spelled word.
 */
export function siteSchema(origin: string, description: string): Json[] {
  return [
    {
      '@context': 'https://schema.org/',
      '@type': 'WebSite',
      name: 'Plenilo.com',
      url: `${origin}/`,
      description,
      potentialAction: {
        '@type': 'SearchAction',
        target: {
          '@type': 'EntryPoint',
          urlTemplate: `${origin}/jobs?q={search_term_string}`,
        },
        'query-input': 'required name=search_term_string',
      },
    },
    {
      '@context': 'https://schema.org/',
      '@type': 'Organization',
      name: 'Plenilo.com',
      url: `${origin}/`,
      logo: `${origin}/icon-512.png`,
      description,
    },
  ]
}

/**
 * Serialises a node for a `<script type="application/ld+json">` block.
 *
 * `<` is escaped because a description containing `</script>` would otherwise
 * end the block early and spill JSON into the document as markup — the classic
 * JSON-in-HTML injection, and entirely reachable here since job descriptions
 * are attacker-influenced text from imported feeds.
 */
export function serializeJsonLd(node: Json | Json[]): string {
  return JSON.stringify(node).replace(/</g, '\\u003c')
}
