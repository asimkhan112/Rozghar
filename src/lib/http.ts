/**
 * The single HTTP client.
 *
 * Everything the app fetches goes through `request`. That is what makes the
 * cross-cutting concerns — error shape, timeouts, auth headers, token refresh —
 * exist in one place instead of being reimplemented slightly differently at
 * forty call sites.
 *
 * Requests are same-origin by design. In production a reverse proxy serves the
 * app and the API from one host; in development the Vite proxy does the same.
 * The base URL is therefore a path, never an origin — which also means the
 * refresh cookie (`SameSite=Strict`) is sent without any CORS involvement.
 */

export const API_BASE = '/api/v1'

/** Long enough for a cold search, short enough that a hung request surfaces. */
const DEFAULT_TIMEOUT_MS = 15_000

/**
 * RFC 7807 problem response. The backend returns this shape for every failure,
 * so the client has exactly one error contract to handle.
 */
export interface Problem {
  type: string
  title: string
  status: number
  detail?: string
  instance?: string
  errors?: Record<string, string[]>
}

export class ApiError extends Error {
  readonly status: number
  readonly problem: Problem
  /** Field-level validation messages, when the failure was a 422. */
  readonly fieldErrors: Record<string, string[]>

  constructor(problem: Problem) {
    super(problem.detail || problem.title)
    this.name = 'ApiError'
    this.status = problem.status
    this.problem = problem
    this.fieldErrors = problem.errors ?? {}
  }

  /** The error code, e.g. `permission_denied` — stable across message edits. */
  get code(): string {
    const match = /\/errors\/([a-z_]+)$/.exec(this.problem.type)
    return match?.[1] ?? 'unknown'
  }

  /** True when retrying later might work; false when the request itself is wrong. */
  get isTransient(): boolean {
    return this.status === 429 || this.status >= 500
  }
}

/** Raised when the network never answered — distinct from the server saying no. */
export class NetworkError extends Error {
  constructor(message: string, readonly cause?: unknown) {
    super(message)
    this.name = 'NetworkError'
  }
}

export interface RequestOptions extends Omit<RequestInit, 'body'> {
  /** Serialised as JSON unless it is already a `FormData` or a string. */
  body?: unknown
  /** Appended as a query string; `undefined` and `null` values are dropped. */
  query?: Record<string, string | number | boolean | undefined | null>
  timeoutMs?: number
  /** Skips the access token and the 401-refresh path. Used by auth itself. */
  anonymous?: boolean
  signal?: AbortSignal
}

/**
 * Hooks the auth layer installs. Kept as injection rather than an import so
 * this module does not depend on the auth store — the store depends on it, and
 * a cycle between the two is how "cannot access before initialisation" bugs
 * appear at module load.
 */
interface AuthHooks {
  getAccessToken: () => string | null
  /** Attempts a silent refresh. Returns the new token, or null to give up. */
  refresh: () => Promise<string | null>
  onAuthFailure: () => void
}

let hooks: AuthHooks | null = null

export function installAuthHooks(next: AuthHooks): void {
  hooks = next
}

function buildUrl(path: string, query: RequestOptions['query']): string {
  const url = `${API_BASE}${path}`
  if (!query) return url
  const params = new URLSearchParams()
  for (const [key, value] of Object.entries(query)) {
    if (value === undefined || value === null || value === '') continue
    params.set(key, String(value))
  }
  const serialised = params.toString()
  return serialised ? `${url}?${serialised}` : url
}

async function toProblem(response: Response): Promise<Problem> {
  try {
    const body = await response.json()
    if (body && typeof body === 'object' && 'title' in body) return body as Problem
  } catch {
    // A non-JSON error body — a proxy 502, an HTML error page. Fall through.
  }
  return {
    type: 'about:blank',
    title: response.statusText || 'Request failed',
    status: response.status,
  }
}

async function send(path: string, options: RequestOptions, token: string | null): Promise<Response> {
  const { body, query, timeoutMs = DEFAULT_TIMEOUT_MS, anonymous, headers, ...rest } = options

  const finalHeaders = new Headers(headers)
  if (!anonymous && token) finalHeaders.set('Authorization', `Bearer ${token}`)

  let payload: BodyInit | undefined
  if (body instanceof FormData || typeof body === 'string') {
    payload = body
  } else if (body !== undefined) {
    payload = JSON.stringify(body)
    finalHeaders.set('Content-Type', 'application/json')
  }

  // A caller-supplied signal and the timeout both have to be able to abort.
  const timeout = new AbortController()
  const timer = setTimeout(() => timeout.abort(), timeoutMs)
  const signal = options.signal
    ? AbortSignal.any([options.signal, timeout.signal])
    : timeout.signal

  try {
    return await fetch(buildUrl(path, query), {
      ...rest,
      headers: finalHeaders,
      body: payload,
      signal,
      // Sends the refresh cookie. Same-origin, so this is not a CORS request.
      credentials: 'same-origin',
    })
  } finally {
    clearTimeout(timer)
  }
}

export async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  let response: Response
  try {
    response = await send(path, options, hooks?.getAccessToken() ?? null)
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') {
      // A caller-cancelled request is not a failure worth surfacing; a
      // timed-out one is. They are distinguished by whose signal fired.
      if (options.signal?.aborted) throw error
      throw new NetworkError('The request timed out.', error)
    }
    throw new NetworkError('Could not reach the server.', error)
  }

  // One retry, and only after a successful refresh. `refresh()` is
  // single-flight in the auth layer: concurrent 401s wait on one rotation
  // rather than each starting their own. Rotating a refresh token twice looks
  // like theft to the backend, which revokes every session in the family.
  if (response.status === 401 && !options.anonymous && hooks) {
    const token = await hooks.refresh()
    if (token) {
      response = await send(path, options, token)
    } else {
      hooks.onAuthFailure()
    }
  }

  if (!response.ok) throw new ApiError(await toProblem(response))
  if (response.status === 204) return undefined as T

  const contentType = response.headers.get('content-type') ?? ''
  if (!contentType.includes('application/json')) return (await response.text()) as T
  return (await response.json()) as T
}

export const api = {
  get: <T>(path: string, options?: RequestOptions) => request<T>(path, { ...options, method: 'GET' }),
  post: <T>(path: string, body?: unknown, options?: RequestOptions) =>
    request<T>(path, { ...options, method: 'POST', body }),
  patch: <T>(path: string, body?: unknown, options?: RequestOptions) =>
    request<T>(path, { ...options, method: 'PATCH', body }),
  delete: <T>(path: string, options?: RequestOptions) =>
    request<T>(path, { ...options, method: 'DELETE' }),
}

/**
 * A message worth showing a person.
 *
 * The backend's `detail` is already written for humans, so it is preferred.
 * The fallbacks exist for the cases where it is not reachable — a proxy error,
 * a dropped connection.
 */
export function describeError(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.status === 429) return error.problem.detail ?? 'Too many requests. Please slow down.'
    if (error.status >= 500) return 'Something went wrong on our side. Please try again.'
    return error.problem.detail ?? error.problem.title
  }
  if (error instanceof NetworkError) return 'Could not reach the server. Check your connection.'
  return 'Something went wrong.'
}
