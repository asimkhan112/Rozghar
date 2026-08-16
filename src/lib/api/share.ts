/**
 * Share assets for a listing.
 *
 * Captions are generated server-side, not here. Wording that lives in the
 * browser would have to be reimplemented for anything else that ever posts a
 * job — a digest email, a scheduled repost — and the two copies would drift.
 */

import { api } from '@/lib/http'

export interface ShareUrls {
  linkedin: string
  facebook: string
  twitter: string
  whatsapp: string
}

export interface ShareAssets {
  job_id: string
  job_url: string
  job_title: string
  image_url: string
  image_urls: Record<string, string>
  linkedin_caption: string
  whatsapp_message: string
  facebook_caption: string
  twitter_caption: string
  hashtags: string[]
  share_urls: ShareUrls
}

export function fetchShareAssets(jobId: string, signal?: AbortSignal): Promise<ShareAssets> {
  return api.get<ShareAssets>(`/admin/jobs/${jobId}/share-assets`, { signal })
}
