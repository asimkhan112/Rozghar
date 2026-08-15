import type { Job } from '@/types/job'
import type { AdminJobRow } from '@/types/admin'
import { cityLabel, formatDate } from '@/lib/format'

/**
 * Projects a job listing into the row the admin table renders.
 *
 * Replaces the former `JOBS_TABLE_DATA` array, which was a second hand-written
 * copy of the same listings and had already drifted from the public site.
 */
export function toAdminRow(job: Job): AdminJobRow {
  return {
    id: job.id,
    slug: job.slug,
    title: job.title,
    company: job.company,
    category: job.category,
    location: cityLabel(job.location),
    status: job.status,
    published: formatDate(job.publishedAt),
    expiry: formatDate(job.expiresAt),
    clicks: job.metrics.clicks,
    views: job.metrics.views,
  }
}
