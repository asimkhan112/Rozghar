/**
 * Admin sidebar configuration.
 *
 * Labels and icon names — presentation, not data. This never came from an API
 * and never will, which is why it outlived `admin.mock.ts`: the rest of that
 * file was seeded numbers standing in for endpoints, and every one of those is
 * now a real query.
 */

import type { AdminNavItem } from "@/types/admin"

export const NAV_ITEMS: AdminNavItem[] = [
  { key: 'dashboard', label: 'Dashboard', icon: 'home' },
  { key: 'jobs', label: 'Jobs', icon: 'clipboard' },
  { key: 'add-job', label: 'Add Job', icon: 'plus' },
  { key: 'reports', label: 'Reports', icon: 'flag' },
  { key: 'analytics', label: 'Analytics', icon: 'barChart' },
  { key: 'categories', label: 'Categories', icon: 'list' },
  { key: 'locations', label: 'Locations', icon: 'mapPin' },
  { key: 'sources', label: 'Sources', icon: 'link' },
  { key: 'settings', label: 'Settings', icon: 'cog' },
]
