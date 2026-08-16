import type { JobCategory } from '@/types/job'

/**
 * Category taxonomy shown on the homepage and in filter lists.
 *
 * `count` is the platform-wide listing total, not the count within the seeded
 * jobs — it is served by `GET /api/v1/categories` in Phase 8.
 */
export const CATEGORIES: JobCategory[] = [
  { name: 'IT & Technology', count: 2840, icon: '💻' },
  { name: 'Design', count: 634, icon: '🎨' },
  { name: 'Finance & Accounting', count: 890, icon: '📊' },
  { name: 'Marketing', count: 712, icon: '📣' },
  { name: 'Human Resources', count: 456, icon: '👥' },
  { name: 'Government', count: 1200, icon: '🏛️' },
  { name: 'Data & Analytics', count: 398, icon: '📈' },
  { name: 'Content & Writing', count: 284, icon: '✍️' },
]

/** Category names as used by the jobs filter, with its "all" sentinel first. */
export const CATEGORY_NAMES = CATEGORIES.map(c => c.name)
