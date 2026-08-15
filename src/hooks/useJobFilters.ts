import { useMemo } from 'react'
import { useSearchParams } from 'react-router'
import type { Job } from '@/types/job'

/**
 * Job list filter state, backed by the URL.
 *
 * Filters live in search params rather than component state so a result set is
 * shareable, bookmarkable, and survives the back button. It also closes the
 * bug where the location typed on the homepage was passed to this page and
 * then never read.
 */

export const ALL_LOCATIONS = 'All Locations'
export const ALL_CATEGORIES = 'All Categories'
export const ALL_TYPES = 'All Types'
export const ALL_EMPLOYMENT = 'All Employment'
export const ANY_EXPERIENCE = 'Any Experience'
export const ANY_TIME = 'Any time'
export const SORT_RECENT = 'Most Recent'

export const LOCATIONS = [ALL_LOCATIONS, 'Lahore', 'Karachi', 'Islamabad', 'Remote']
export const CATEGORIES_LIST = [ALL_CATEGORIES, 'IT & Technology', 'Design', 'Finance & Accounting', 'Marketing', 'Human Resources', 'Government', 'Data & Analytics', 'Content & Writing']
export const WORK_TYPES = [ALL_TYPES, 'Remote', 'Hybrid', 'On-site']
export const EMPLOYMENT_TYPES_LIST = [ALL_EMPLOYMENT, 'Full-time', 'Part-time', 'Contract', 'Internship']
export const EXP_LEVELS = [ANY_EXPERIENCE, 'Fresh / Intern', '1–3 years', '3–5 years', '5+ years']
export const DATE_FILTERS = [ANY_TIME, 'Today', 'This week', 'This month']
export const SORT_OPTIONS = [SORT_RECENT, 'Most Relevant', 'Salary: High to Low', 'Salary: Low to High']

/** Upper bound in days for each "date posted" option. */
const DATE_WINDOW_DAYS: Record<string, number> = {
  Today: 1,
  'This week': 7,
  'This month': 31,
}

/** Inclusive year ranges for each experience option. */
const EXPERIENCE_RANGE: Record<string, [number, number]> = {
  '1–3 years': [1, 3],
  '3–5 years': [3, 5],
  '5+ years': [5, Infinity],
}

/** Reference date for relative filtering — the seed data's "today". */
const TODAY = new Date('2026-08-13T00:00:00Z')

export interface JobFilters {
  q: string
  location: string
  category: string
  workType: string
  employmentType: string
  experience: string
  datePosted: string
  sort: string
}

export function useJobFilters() {
  const [params, setParams] = useSearchParams()

  const filters: JobFilters = {
    q: params.get('q') ?? '',
    location: params.get('location') ?? ALL_LOCATIONS,
    category: params.get('category') ?? ALL_CATEGORIES,
    workType: params.get('workType') ?? ALL_TYPES,
    employmentType: params.get('employmentType') ?? ALL_EMPLOYMENT,
    experience: params.get('experience') ?? ANY_EXPERIENCE,
    datePosted: params.get('datePosted') ?? ANY_TIME,
    sort: params.get('sort') ?? SORT_RECENT,
  }

  const page = Math.max(1, Number(params.get('page') ?? '1') || 1)

  const defaults: Record<keyof JobFilters, string> = {
    q: '',
    location: ALL_LOCATIONS,
    category: ALL_CATEGORIES,
    workType: ALL_TYPES,
    employmentType: ALL_EMPLOYMENT,
    experience: ANY_EXPERIENCE,
    datePosted: ANY_TIME,
    sort: SORT_RECENT,
  }

  /** Writes one filter and resets pagination, dropping default values. */
  function setFilter(key: keyof JobFilters, value: string) {
    setParams(
      prev => {
        const next = new URLSearchParams(prev)
        if (!value || value === defaults[key]) next.delete(key)
        else next.set(key, value)
        next.delete('page')
        return next
      },
      { replace: true },
    )
  }

  function setPage(next: number) {
    setParams(
      prev => {
        const p = new URLSearchParams(prev)
        if (next <= 1) p.delete('page')
        else p.set('page', String(next))
        return p
      },
      { replace: true },
    )
  }

  function reset(keys?: (keyof JobFilters)[]) {
    setParams(
      prev => {
        const next = new URLSearchParams(prev)
        for (const key of keys ?? (Object.keys(defaults) as (keyof JobFilters)[])) next.delete(key)
        next.delete('page')
        return next
      },
      { replace: true },
    )
  }

  const hasAdvancedFilters =
    filters.workType !== ALL_TYPES ||
    filters.employmentType !== ALL_EMPLOYMENT ||
    filters.category !== ALL_CATEGORIES ||
    filters.experience !== ANY_EXPERIENCE ||
    filters.datePosted !== ANY_TIME

  return { filters, page, setFilter, setPage, reset, hasAdvancedFilters }
}

/** Applies every active filter, then sorts. Pure — safe to memoise. */
export function applyJobFilters(jobs: Job[], filters: JobFilters): Job[] {
  let result = [...jobs]

  if (filters.q) {
    const q = filters.q.toLowerCase()
    result = result.filter(
      j =>
        j.title.toLowerCase().includes(q) ||
        j.company.toLowerCase().includes(q) ||
        j.category.toLowerCase().includes(q),
    )
  }

  if (filters.location !== ALL_LOCATIONS) {
    const loc = filters.location.toLowerCase()
    result = result.filter(
      j => j.location.toLowerCase().includes(loc) || (loc === 'remote' && j.workType === 'Remote'),
    )
  }

  if (filters.category !== ALL_CATEGORIES) {
    result = result.filter(j => j.category === filters.category)
  }

  if (filters.workType !== ALL_TYPES) {
    result = result.filter(j => j.workType === filters.workType)
  }

  if (filters.employmentType !== ALL_EMPLOYMENT) {
    result = result.filter(j => j.employmentType === filters.employmentType)
  }

  if (filters.experience === 'Fresh / Intern') {
    result = result.filter(j => j.experience.includes('Fresh') || j.employmentType === 'Internship')
  } else if (filters.experience in EXPERIENCE_RANGE) {
    const [min, max] = EXPERIENCE_RANGE[filters.experience]
    result = result.filter(j => j.experienceMax >= min && j.experienceMin <= max)
  }

  if (filters.datePosted in DATE_WINDOW_DAYS) {
    const windowMs = DATE_WINDOW_DAYS[filters.datePosted] * 24 * 60 * 60 * 1000
    result = result.filter(j => {
      if (!j.publishedAt) return false
      const age = TODAY.getTime() - new Date(j.publishedAt).getTime()
      return age >= 0 && age < windowMs
    })
  }

  switch (filters.sort) {
    case 'Salary: High to Low':
      result.sort((a, b) => salaryFloor(b) - salaryFloor(a))
      break
    case 'Salary: Low to High':
      result.sort((a, b) => salaryFloor(a) - salaryFloor(b))
      break
    case 'Most Relevant':
      result.sort((a, b) => b.metrics.views - a.metrics.views)
      break
    default:
      result.sort((a, b) => (b.publishedAt ?? '').localeCompare(a.publishedAt ?? ''))
  }

  return result
}

/** Normalises to PKR so mixed-currency listings sort against each other. */
const USD_TO_PKR = 280

function salaryFloor(job: Job): number {
  return job.salaryCurrency === 'USD' ? job.salaryMin * USD_TO_PKR : job.salaryMin
}

export function useFilteredJobs(jobs: Job[], filters: JobFilters): Job[] {
  return useMemo(() => applyJobFilters(jobs, filters), [jobs, filters])
}
