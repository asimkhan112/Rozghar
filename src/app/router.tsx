import { createBrowserRouter } from 'react-router'

import HomePage from '@/pages/HomePage'
import JobsPage from '@/pages/JobsPage'
import JobDetailPage from '@/pages/JobDetailPage'
import SavedJobsPage from '@/pages/SavedJobsPage'
import AdminSignInPage from '@/pages/AdminSignInPage'

import CategoriesPage from '@/routes/CategoriesPage'
import AboutPage from '@/routes/AboutPage'
import ContactPage from '@/routes/ContactPage'
import NotFoundPage from '@/routes/NotFoundPage'
import RouteErrorBoundary from '@/routes/RouteErrorBoundary'

import RequireAuth from '@/routes/admin/RequireAuth'
import AdminLayout from '@/routes/admin/AdminLayout'
import DashboardSection from '@/routes/admin/sections/DashboardSection'
import JobsSection from '@/routes/admin/sections/JobsSection'
import AddJobSection from '@/routes/admin/sections/AddJobSection'
import ReportsSection from '@/routes/admin/sections/ReportsSection'
import AnalyticsSection from '@/routes/admin/sections/AnalyticsSection'
import CategoriesSection from '@/routes/admin/sections/CategoriesSection'
import LocationsSection from '@/routes/admin/sections/LocationsSection'
import SourcesSection from '@/routes/admin/sections/SourcesSection'
import SettingsSection from '@/routes/admin/sections/SettingsSection'

/**
 * Router basename.
 *
 * `BASE_URL` comes from Vite's `base`, which this project derives from
 * `FIGMA_PUBLIC_URL`. That can be an absolute URL, which is not a valid
 * basename, so it is reduced to a pathname before use.
 */
function resolveBasename(): string {
  const base = import.meta.env.BASE_URL || '/'
  if (base.startsWith('/')) return base
  try {
    return new URL(base).pathname
  } catch {
    return '/'
  }
}

export const router = createBrowserRouter(
  [
    {
      errorElement: <RouteErrorBoundary />,
      children: [
        { path: '/', element: <HomePage /> },
        { path: '/jobs', element: <JobsPage /> },
        { path: '/jobs/:slug', element: <JobDetailPage /> },
        { path: '/saved-jobs', element: <SavedJobsPage /> },
        { path: '/categories', element: <CategoriesPage /> },
        { path: '/about', element: <AboutPage /> },
        { path: '/contact', element: <ContactPage /> },

        { path: '/admin/login', element: <AdminSignInPage /> },
        {
          path: '/admin/dashboard',
          element: (
            <RequireAuth>
              <AdminLayout />
            </RequireAuth>
          ),
          children: [
            { index: true, element: <DashboardSection /> },
            { path: 'jobs', element: <JobsSection /> },
            { path: 'add-job', element: <AddJobSection /> },
            { path: 'reports', element: <ReportsSection /> },
            { path: 'analytics', element: <AnalyticsSection /> },
            { path: 'categories', element: <CategoriesSection /> },
            { path: 'locations', element: <LocationsSection /> },
            { path: 'sources', element: <SourcesSection /> },
            { path: 'settings', element: <SettingsSection /> },
          ],
        },

        { path: '*', element: <NotFoundPage /> },
      ],
    },
  ],
  { basename: resolveBasename() },
)
