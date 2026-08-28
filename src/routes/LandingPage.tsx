import { Link, useParams } from 'react-router'

import Navbar from '@/components/Navbar'
import SiteFooter from '@/components/SiteFooter'
import JobCard from '@/components/JobCard'
import { EmptyPanel, ErrorPanel, JobGridSkeleton } from '@/components/QueryState'
import NotFoundPage from '@/routes/NotFoundPage'
import { useJobs } from '@/hooks/queries/useJobs'
import { useCategories, useLocations } from '@/hooks/queries/useTaxonomy'
import { describeError } from '@/lib/http'
import { usePageMeta } from '@/lib/seo'
import { landingCopy, landingPath, resolveLanding, type Landing } from '@/lib/landingPages'
import type { JobQuery } from '@/lib/api'
import { color, container, radius, size, tracking, weight } from '@/design-system'

/**
 * Keyword landing pages — `/remote-jobs`, `/jobs-in-pakistan`, `/design-jobs`.
 *
 * ## Why this is not just `/jobs` with a filter preset
 *
 * It shows the same listings a filter would, and if ranking were about listings
 * this page would be redundant. It is not: it is about having one URL whose
 * subject never changes, so that URL can carry a title, a heading and a
 * paragraph written for one query instead of for all of them.
 *
 * `/jobs?work_type=remote` cannot do that. Its title has to stay true when the
 * filter is cleared, so it stays generic — and a generic title is what a search
 * engine matches against a specific query and finds wanting. The reasoning for
 * why the filtered URL is not indexable at all is in `canonicalUrl`.
 *
 * ## Why the list is read-only
 *
 * There are no filter controls here on purpose. Adding them would let the page
 * become a different page under the same address — the exact problem it exists
 * to avoid — and would put the reader back on a URL whose state is in a query
 * string. Anyone who wants to narrow further follows the link to `/jobs`, which
 * is the page built for that.
 *
 * The `<h1>` and the opening paragraph are the only substantial indexable prose
 * on the site outside a job description, and they come from `landingCopy` so
 * this component and `api/prerender.ts` cannot describe the page differently.
 */

/** How many listings a landing page shows before handing off to `/jobs`. */
const PAGE_SIZE = 24

/** The API query behind a landing page, once its subject is known to exist. */
function queryFor(landing: Landing, slug: string): JobQuery {
  switch (landing.kind) {
    case 'work-type':
      return { work_type: landing.workType, per_page: PAGE_SIZE }
    case 'country':
      return { country: landing.country.code, per_page: PAGE_SIZE }
    case 'location':
      return { location: slug, per_page: PAGE_SIZE }
    case 'category':
      return { category: slug, per_page: PAGE_SIZE }
  }
}

export default function LandingPage() {
  const { landingSlug = '' } = useParams()
  const landing = resolveLanding(landingSlug)

  // The taxonomy settles whether a location or category landing is real. Only
  // fetched for the kinds that need it — a country or work-type page is valid
  // on its own and must not wait on a list it will not read.
  const needsCategories = landing?.kind === 'category'
  const needsLocations = landing?.kind === 'location'
  const categories = useCategories()
  const locations = useLocations()
  const taxonomy = needsCategories ? categories : needsLocations ? locations : null

  let label = ''
  let known = true
  if (landing?.kind === 'category') {
    const match = categories.data?.find((c) => c.slug === landing.categorySlug)
    label = match?.name ?? ''
    known = Boolean(match)
  } else if (landing?.kind === 'location') {
    const match = locations.data?.find((l) => l.slug === landing.locationSlug)
    label = match?.label ?? ''
    known = Boolean(match)
  } else if (landing?.kind === 'country') {
    label = landing.country.name
  } else if (landing?.kind === 'work-type') {
    label = 'Remote'
  }

  const copy = landing ? landingCopy(landing, label) : null

  const slug =
    landing?.kind === 'category'
      ? landing.categorySlug
      : landing?.kind === 'location'
        ? landing.locationSlug
        : ''

  const jobs = useJobs(landing ? queryFor(landing, slug) : {}, {
    // A category page must not query until the taxonomy has confirmed the
    // category exists: an unknown slug returns an empty list, and rendering
    // that as "no jobs yet" would present a 404 as an ordinary empty page.
    enabled: Boolean(landing) && (taxonomy ? taxonomy.isSuccess && known : true),
  })

  // Set before any early return: hooks may not be skipped, and passing `null`
  // is how this page defers to the 404 surface it is about to render.
  usePageMeta(
    copy && (!taxonomy || taxonomy.isPending || known)
      ? { title: copy.title, description: copy.description, canonical: landingPath(landing!) }
      : null,
  )

  // Not a landing URL at all, or one naming a category or city the taxonomy
  // does not have. Either way there is nothing here and never was.
  if (!landing || !copy) return <NotFoundPage />
  if (taxonomy?.isSuccess && !known) return <NotFoundPage />

  const results = jobs.data?.items ?? []
  const total = jobs.data?.total ?? 0
  const waitingOnTaxonomy = Boolean(taxonomy?.isPending)

  return (
    <div style={{ minHeight: '100vh', background: color.surface.canvas, display: 'flex', flexDirection: 'column' }}>
      <Navbar />

      <main style={{ flex: 1, width: '100%', maxWidth: container.wide, margin: '0 auto', padding: '40px 24px 64px' }}>
        <header style={{ maxWidth: 760, marginBottom: 32 }}>
          <h1
            style={{
              fontSize: size['5xl'],
              fontWeight: weight.bold,
              color: color.text.primary,
              letterSpacing: tracking.tight,
              margin: '0 0 12px',
            }}
          >
            {copy.heading}
          </h1>
          <p style={{ fontSize: size.base, lineHeight: 1.65, color: color.text.secondary, margin: '0 0 16px' }}>
            {copy.intro}
          </p>
          {total > 0 && (
            <p style={{ fontSize: size.sm, color: color.text.muted, margin: 0 }}>
              {total.toLocaleString()} open {total === 1 ? 'position' : 'positions'}
            </p>
          )}
        </header>

        {jobs.isError && !waitingOnTaxonomy ? (
          <ErrorPanel message={describeError(jobs.error)} onRetry={() => void jobs.refetch()} />
        ) : jobs.isPending || waitingOnTaxonomy ? (
          <JobGridSkeleton count={6} />
        ) : results.length === 0 ? (
          <EmptyPanel
            icon="briefcase"
            title="No openings right now"
            message="Nothing matches this search today. New listings are added every 24 hours, so it is worth checking back."
          />
        ) : (
          <div style={{ display: 'grid', gap: 16 }}>
            {results.map((job) => (
              <JobCard key={job.id} job={job} />
            ))}
          </div>
        )}

        {/* The one route out. A landing page deliberately has no filter
            controls of its own; `/jobs` is where narrowing happens. */}
        <div style={{ marginTop: 32 }}>
          <Link
            to="/jobs"
            style={{
              display: 'inline-block',
              padding: '12px 20px',
              borderRadius: radius.pill,
              border: `1px solid ${color.border.base}`,
              background: color.surface.base,
              color: color.text.primary,
              fontSize: size.sm,
              fontWeight: weight.medium,
              textDecoration: 'none',
            }}
          >
            {total > PAGE_SIZE ? `See all ${total.toLocaleString()} jobs` : 'Search all jobs'} →
          </Link>
        </div>
      </main>

      <SiteFooter />
    </div>
  )
}
