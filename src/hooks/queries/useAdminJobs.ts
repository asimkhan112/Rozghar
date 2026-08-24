/**
 * Admin job queries and mutations.
 *
 * Two rules run through every mutation here.
 *
 * **Invalidate broadly, not precisely.** Publishing a listing changes the admin
 * table, the public list, the category counters and the analytics rollups. A
 * mutation that surgically patches one cache entry and leaves the others stale
 * produces a UI that disagrees with itself, so these invalidate whole prefixes
 * and let React Query refetch what is actually mounted.
 *
 * **Optimistic only where a rollback is honest.** Toggling `featured` is safe:
 * the state is a boolean, the server is authoritative, and reverting on failure
 * restores exactly what was there. Creating and deleting are not — an
 * optimistically inserted row has no server id, and a "deleted" row that comes
 * back looks like a ghost.
 */

import { useMutation, useQuery, useQueryClient, type QueryClient } from '@tanstack/react-query'
import {
  createJob,
  deleteJob,
  expireJob,
  featureJob,
  fetchAdminJob,
  fetchAdminJobs,
  importUsajobs,
  publishJob,
  updateJob,
  verifyJob,
  type AdminJob,
  type AdminJobPage,
  type AdminJobQuery,
} from '@/lib/api/admin'
import type { JobWriteDto } from '@/lib/api/admin-types'
import { queryKeys } from './keys'

export function useAdminJobs(query: AdminJobQuery) {
  return useQuery({
    queryKey: queryKeys.admin.jobs.list(query),
    queryFn: ({ signal }) => fetchAdminJobs(query, signal),
  })
}

export function useAdminJob(id: string | undefined) {
  return useQuery({
    queryKey: queryKeys.admin.jobs.detail(id ?? ''),
    queryFn: ({ signal }) => fetchAdminJob(id!, signal),
    enabled: Boolean(id),
  })
}

/**
 * Everything a job write touches.
 *
 * The public lists are included deliberately: an admin who publishes a listing
 * and then opens the site in the next tab must see it there. Job counts on
 * categories move too, which is why the taxonomy goes as well.
 */
function invalidateJobWrites(client: QueryClient): Promise<unknown> {
  return Promise.all([
    client.invalidateQueries({ queryKey: queryKeys.admin.jobs.all }),
    client.invalidateQueries({ queryKey: queryKeys.jobs.all }),
    client.invalidateQueries({ queryKey: queryKeys.taxonomy.all }),
    client.invalidateQueries({ queryKey: queryKeys.admin.analytics.all }),
    client.invalidateQueries({ queryKey: queryKeys.admin.audit.all }),
  ])
}

export function useCreateJob() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (body: JobWriteDto) => createJob(body),
    // Not optimistic: the row has no id until the server assigns one, and a
    // placeholder that cannot be linked to is worse than a moment's wait.
    onSuccess: () => invalidateJobWrites(client),
  })
}

export function useUpdateJob() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: ({
      id,
      changes,
      version,
    }: {
      id: string
      changes: Partial<JobWriteDto>
      version?: number
    }) => updateJob(id, changes, version),
    onSuccess: updated => {
      client.setQueryData(queryKeys.admin.jobs.detail(updated.id), updated)
      return invalidateJobWrites(client)
    },
  })
}

export function useDeleteJob() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => deleteJob(id),
    onSuccess: () => invalidateJobWrites(client),
  })
}

/**
 * The lifecycle actions, optimistically applied.
 *
 * All four are safe to apply early: each flips a small, well-known part of a
 * row the server will confirm or correct within a moment. The cancel-snapshot-
 * rollback dance is the standard one — cancelling in-flight refetches first
 * matters, because a response that arrives mid-mutation would otherwise
 * overwrite the optimistic state and make the button appear to bounce back.
 */
function useJobAction<TArgs>(
  action: (args: TArgs) => Promise<AdminJob>,
  optimistic: (job: AdminJob, args: TArgs) => AdminJob,
  idOf: (args: TArgs) => string,
) {
  const client = useQueryClient()

  return useMutation({
    mutationFn: action,
    async onMutate(args: TArgs) {
      await client.cancelQueries({ queryKey: queryKeys.admin.jobs.all })
      const snapshot = client.getQueriesData<AdminJobPage>({
        queryKey: queryKeys.admin.jobs.lists(),
      })
      const id = idOf(args)

      client.setQueriesData<AdminJobPage>({ queryKey: queryKeys.admin.jobs.lists() }, page =>
        page
          ? { ...page, items: page.items.map(job => (job.id === id ? optimistic(job, args) : job)) }
          : page,
      )
      return { snapshot }
    },
    onError(_error, _args, context) {
      // Put back exactly what was there. Re-deriving the previous state from
      // the failed action would guess, and guessing wrong here means the table
      // shows a status the server never had.
      for (const [key, data] of context?.snapshot ?? []) {
        client.setQueryData(key, data)
      }
    },
    onSettled: () => invalidateJobWrites(client),
  })
}

/**
 * Imports from USAJOBS.
 *
 * Invalidates every job query rather than patching the cache: a run creates an
 * unknown number of rows across pages the client has never loaded, so there is
 * nothing meaningful to splice in.
 */
export function useImportUsajobs() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: importUsajobs,
    onSettled: () => invalidateJobWrites(client),
  })
}

export function usePublishJob() {
  return useJobAction<{ id: string; scheduledAt?: string }>(
    ({ id, scheduledAt }) => publishJob(id, scheduledAt),
    job => ({ ...job, status: 'published' }),
    ({ id }) => id,
  )
}

export function useExpireJob() {
  return useJobAction<{ id: string; reason?: string }>(
    ({ id, reason }) => expireJob(id, reason),
    job => ({ ...job, status: 'expired' }),
    ({ id }) => id,
  )
}

export function useVerifyJob() {
  return useJobAction<{ id: string; verified: boolean }>(
    ({ id, verified }) => verifyJob(id, verified),
    (job, { verified }) => ({ ...job, verified, badge: verified ? 'verified' : job.badge }),
    ({ id }) => id,
  )
}

export function useFeatureJob() {
  return useJobAction<{ id: string; featured: boolean; until?: string | null }>(
    ({ id, featured, until }) => featureJob(id, featured, until),
    (job, { featured }) => ({ ...job, featured, badge: featured ? 'featured' : job.badge }),
    ({ id }) => id,
  )
}
