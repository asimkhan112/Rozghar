import type { IconName } from "@/components/Icon"

/**
 * Types for the admin console.
 *
 * These describe the shapes the dashboard renders today from seeded data. Each
 * one is the response body of an endpoint listed in the Phase 8 API contract,
 * so the components consuming them will not change when the backend arrives.
 */

import type { ActivityTone } from '@/design-system'

export const ADMIN_SECTIONS = [
  'dashboard',
  'jobs',
  'add-job',
  'reports',
  'analytics',
  'categories',
  'locations',
  'sources',
  'settings',
] as const
export type AdminSection = (typeof ADMIN_SECTIONS)[number]

export interface AdminNavItem {
  key: AdminSection
  label: string
  /** A name from the icon set. Path data used to live here, which limited the
   *  sidebar to single-path glyphs — the gear, the map pin and the link were
   *  all rendering as fragments of themselves. */
  icon: IconName
}

export interface MetricCard {
  label: string
  value: string
  change: string
  trend: 'up' | 'down' | 'warn'
  icon: string
}

export interface TopJobRow {
  title: string
  company: string
  clicks: number
  views: number
  saved: number
  status: string
}

export const ACTIVITY_TYPES = ['add', 'click', 'warn', 'report'] as const
export type ActivityType = (typeof ACTIVITY_TYPES)[number]

export interface ActivityItem {
  type: ActivityType
  msg: string
  time: string
  /** Semantic tone for the timeline dot. Resolved to a colour by the design system. */
  tone: ActivityTone
}

export interface SearchKeyword {
  kw: string
  count: number
}

export const REPORT_REASONS = [
  'Broken Link',
  'Spam',
  'Expired',
  'Wrong Information',
  'Duplicate',
  'Other',
] as const
export type ReportReason = (typeof REPORT_REASONS)[number]

export interface JobReport {
  id: number
  job: string
  company: string
  reason: ReportReason
  comment: string
  date: string
  category: ReportReason
}

export interface CategoryStat {
  name: string
  count: number
  status: 'Active' | 'Archived'
  popularity: number
}

export interface LocationStat {
  name: string
  region: string
  type: 'City' | 'Remote'
  jobs: number
}

export interface SourceStat {
  name: string
  jobs: number
  clicks: number
  ctr: string
  status: 'Active' | 'Paused'
}

export interface ConversionStat {
  label: string
  rate: string
  count: string
  bar: number
}

export interface LocationShare {
  loc: string
  pct: number
}

/**
 * Row shape rendered by the admin jobs table. Projected from `Job` rather than
 * stored separately — the previous `JOBS_TABLE_DATA` array was a second source
 * of truth that had already drifted out of sync with the public listings.
 */
export interface AdminJobRow {
  id: string
  slug: string
  title: string
  company: string
  category: string
  location: string
  status: string
  published: string
  expiry: string
  clicks: number
  views: number
}
