/**
 * Renders every reachable page to static HTML using Vite's SSR pipeline, so
 * aliases/TSX/TS all resolve exactly as they do in the app.
 *
 * Inline style objects serialise into the `style` attribute, so a byte-diff of
 * the output catches any change to a colour, spacing value, font size, radius,
 * border, or shadow anywhere in the tree.
 *
 * Pages are mounted inside a MemoryRouter at a real path, which means this file
 * doubles as a route smoke test: a page that throws or fails to resolve its
 * params produces no snapshot.
 *
 * Usage: node render-snapshot.mjs <outputDir>
 */
import { createServer } from 'vite'
import { mkdirSync, writeFileSync } from 'node:fs'
import { join } from 'node:path'
import React from 'react'
import { MemoryRouter, Routes, Route } from 'react-router'
import { JSDOM } from 'jsdom'

// Render in a real DOM rather than to a string.
//
// Zustand reads through `useSyncExternalStore`, and static rendering uses the
// *server* snapshot — `getInitialState()` on the store's internal api object,
// which is not reachable from the bound hook. Store-driven UI therefore always
// renders as empty under renderToStaticMarkup. A DOM render uses the live
// snapshot, so saved-state styling is actually exercised.
const dom = new JSDOM('<!doctype html><html><body><div id="root"></div></body></html>', {
  url: 'http://localhost/',
  pretendToBeVisual: true,
})
globalThis.window = dom.window
globalThis.document = dom.window.document
Object.defineProperty(globalThis, 'navigator', { value: dom.window.navigator, configurable: true })
globalThis.HTMLElement = dom.window.HTMLElement
globalThis.Element = dom.window.Element
globalThis.Node = dom.window.Node
globalThis.getComputedStyle = dom.window.getComputedStyle
globalThis.requestAnimationFrame = cb => setTimeout(() => cb(Date.now()), 0)
globalThis.cancelAnimationFrame = clearTimeout
globalThis.IS_REACT_ACT_ENVIRONMENT = true

const { createRoot } = await import('react-dom/client')
const { act } = await import('react')

const ROOT = '/home/asim/Desktop/projects/Rozghar'
const outDir = process.argv[2]
if (!outDir) throw new Error('usage: node render-snapshot.mjs <outputDir>')
mkdirSync(outDir, { recursive: true })

const server = await createServer({
  root: ROOT,
  configFile: join(ROOT, 'vite.config.ts'),
  server: { middlewareMode: true },
  appType: 'custom',
  logLevel: 'error',
})

const load = p => server.ssrLoadModule(p)

const { JOBS } = await load('/src/data/jobs.mock.ts')

const HomePage = (await load('/src/pages/HomePage.tsx')).default
const JobsPage = (await load('/src/pages/JobsPage.tsx')).default
const JobDetailPage = (await load('/src/pages/JobDetailPage.tsx')).default
const SavedJobsPage = (await load('/src/pages/SavedJobsPage.tsx')).default
const AdminSignInPage = (await load('/src/pages/AdminSignInPage.tsx')).default
const CategoriesPage = (await load('/src/routes/CategoriesPage.tsx')).default
const AboutPage = (await load('/src/routes/AboutPage.tsx')).default
const ContactPage = (await load('/src/routes/ContactPage.tsx')).default
const NotFoundPage = (await load('/src/routes/NotFoundPage.tsx')).default
const JobCard = (await load('/src/components/JobCard.tsx')).default
const Navbar = (await load('/src/components/Navbar.tsx')).default

const AdminLayout = (await load('/src/routes/admin/AdminLayout.tsx')).default
const DashboardSection = (await load('/src/routes/admin/sections/DashboardSection.tsx')).default
const JobsSection = (await load('/src/routes/admin/sections/JobsSection.tsx')).default
const AddJobSection = (await load('/src/routes/admin/sections/AddJobSection.tsx')).default
const ReportsSection = (await load('/src/routes/admin/sections/ReportsSection.tsx')).default
const AnalyticsSection = (await load('/src/routes/admin/sections/AnalyticsSection.tsx')).default
const CategoriesSection = (await load('/src/routes/admin/sections/CategoriesSection.tsx')).default
const LocationsSection = (await load('/src/routes/admin/sections/LocationsSection.tsx')).default
const SourcesSection = (await load('/src/routes/admin/sections/SourcesSection.tsx')).default
const SettingsSection = (await load('/src/routes/admin/sections/SettingsSection.tsx')).default

// Seed the saved-jobs store so both saved and unsaved branches of every
// conditional style are exercised, matching the pre-routing snapshot props.
const { useSavedJobsStore } = await load('/src/stores/useSavedJobsStore.ts')

function seedSaved(ids) {
  useSavedJobsStore.setState({ ids })
}

/** Mounts into a detached container and returns the resulting markup. */
function renderToDom(element) {
  const container = dom.window.document.createElement('div')
  dom.window.document.body.appendChild(container)
  const root = createRoot(container)
  act(() => { root.render(element) })
  const html = container.innerHTML
  act(() => { root.unmount() })
  container.remove()
  return html
}

const h = React.createElement

/** Mounts an element at `path` inside a memory router. */
function at(path, element, routePattern = path) {
  return h(
    MemoryRouter,
    { initialEntries: [path] },
    h(Routes, null, h(Route, { path: routePattern, element })),
  )
}

const cases = [
  ['home', at('/', h(HomePage))],
  ['jobs', at('/jobs', h(JobsPage))],
  ['jobs-searched', at('/jobs?q=engineer&location=Lahore', h(JobsPage), '/jobs')],
  ['jobs-filtered', at('/jobs?category=Design&workType=Remote&sort=Salary%3A+High+to+Low', h(JobsPage), '/jobs')],
  ['saved', at('/saved-jobs', h(SavedJobsPage))],
  ['categories', at('/categories', h(CategoriesPage))],
  ['about', at('/about', h(AboutPage))],
  ['contact', at('/contact', h(ContactPage))],
  ['not-found', at('/nonsense', h(NotFoundPage), '*')],
  ['admin-signin', at('/admin/login', h(AdminSignInPage))],
  ['navbar-empty', at('/', h(Navbar)), []],
  ['navbar-saved', at('/jobs', h(Navbar)), ['job-01', 'job-03', 'job-07']],
]

// Admin sections, each mounted through the real layout so the sidebar active
// state and the outlet wiring are exercised.
const ADMIN_SECTIONS = [
  ['', DashboardSection, 'dashboard'],
  ['jobs', JobsSection, 'jobs'],
  ['add-job', AddJobSection, 'add-job'],
  ['reports', ReportsSection, 'reports'],
  ['analytics', AnalyticsSection, 'analytics'],
  ['categories', CategoriesSection, 'categories'],
  ['locations', LocationsSection, 'locations'],
  ['sources', SourcesSection, 'sources'],
  ['settings', SettingsSection, 'settings'],
]
for (const [segment, Section, name] of ADMIN_SECTIONS) {
  const path = segment ? `/admin/dashboard/${segment}` : '/admin/dashboard'
  cases.push([
    `admin-${name}`,
    h(
      MemoryRouter,
      { initialEntries: [path] },
      h(
        Routes,
        null,
        h(
          Route,
          { path: '/admin/dashboard', element: h(AdminLayout) },
          segment
            ? h(Route, { path: segment, element: h(Section) })
            : h(Route, { index: true, element: h(Section) }),
        ),
      ),
    ),
  ])
}

// One detail page per job: covers all four badge variants, all three work
// types, both currencies and every logo palette slot.
for (const job of JOBS) {
  cases.push([`detail-${job.id}`, at(`/jobs/${job.slug}`, h(JobDetailPage), '/jobs/:slug')])
}
// One card per job, in both densities.
for (const job of JOBS) {
  for (const compact of [false, true]) {
    cases.push([
      `card-${job.id}${compact ? '-compact' : ''}`,
      at('/jobs', h(JobCard, { job, compact })),
    ])
  }
}

let count = 0
const failures = []
const DEFAULT_SAVED = ['job-01', 'job-03', 'job-07']
for (const [name, element, savedOverride] of cases) {
  try {
    seedSaved(savedOverride ?? DEFAULT_SAVED)
    writeFileSync(join(outDir, `${name}.html`), renderToDom(element))
    count++
  } catch (err) {
    failures.push(`${name}: ${err.message}`)
  }
}

await server.close()
console.log(`wrote ${count}/${cases.length} snapshots to ${outDir}`)
if (failures.length) {
  console.log('\nRENDER FAILURES:\n' + failures.join('\n'))
  process.exit(1)
}
