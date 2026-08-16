/**
 * Admin sidebar configuration.
 *
 * Labels and icon paths — presentation, not data. This never came from an API
 * and never will, which is why it outlived `admin.mock.ts`: the rest of that
 * file was seeded numbers standing in for endpoints, and every one of those is
 * now a real query.
 */

import type { AdminNavItem } from "@/types/admin"

export const NAV_ITEMS: AdminNavItem[] = [
  { key: 'dashboard', label: 'Dashboard', icon: 'M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z' },
  { key: 'jobs', label: 'Jobs', icon: 'M9 5H7a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V7a2 2 0 0 0-2-2h-2M9 5a2 2 0 0 0 2 2h2a2 2 0 0 0 2-2M9 5a2 2 0 0 1 2-2h2a2 2 0 0 1 2 2' },
  { key: 'add-job', label: 'Add Job', icon: 'M12 5v14M5 12h14' },
  { key: 'reports', label: 'Reports', icon: 'M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z' },
  { key: 'analytics', label: 'Analytics', icon: 'M18 20V10M12 20V4M6 20v-6' },
  { key: 'categories', label: 'Categories', icon: 'M4 6h16M4 12h16M4 18h7' },
  { key: 'locations', label: 'Locations', icon: 'M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z' },
  { key: 'sources', label: 'Sources', icon: 'M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71' },
  { key: 'settings', label: 'Settings', icon: 'M12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6z' },
]
