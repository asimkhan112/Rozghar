/**
 * AI drafting.
 *
 * Both calls return a *proposal*. Nothing is saved server-side — the editor
 * reviews the draft against what they had and decides whether to apply it, and
 * the ordinary create/update path is still what writes to the database.
 */

import { api } from '@/lib/http'

export interface AIDraft {
  description: string
  responsibilities: string[]
  requirements: string[]
  benefits: string[]
  apply_note: string
}

export interface GenerateInput {
  title: string
  company: string
  location?: string
  employment_type?: string
  experience_level?: string
  salary?: string | null
  skills?: string[]
}

export function rewriteDescription(description: string): Promise<AIDraft> {
  // Longer than the default: drafting runs a model call, and 15s is a normal
  // duration rather than a fault.
  return api.post<AIDraft>('/admin/ai/rewrite', { description }, { timeout: 90_000 })
}

export function generateDescription(input: GenerateInput): Promise<AIDraft> {
  return api.post<AIDraft>('/admin/ai/generate', input, { timeout: 90_000 })
}
