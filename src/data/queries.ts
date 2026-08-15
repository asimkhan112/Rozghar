import { JOBS } from './jobs.mock'
import type { Job } from '@/types/job'

/**
 * Query helpers over the seeded listings.
 *
 * Routes call these rather than importing the array, so Phase 8 replaces the
 * bodies with repository calls without touching a single component.
 */

export function getAllJobs(): Job[] {
  return JOBS
}

export function getJobBySlug(slug: string | undefined): Job | null {
  if (!slug) return null
  return JOBS.find(job => job.slug === slug) ?? null
}

/** Same rule the detail page used inline: same category or same work type. */
export function getRelatedJobs(job: Job, limit = 3): Job[] {
  return JOBS.filter(
    other => other.id !== job.id && (other.category === job.category || other.workType === job.workType),
  ).slice(0, limit)
}

export function getJobsByIds(ids: string[]): Job[] {
  return JOBS.filter(job => ids.includes(job.id))
}
