/**
 * The single HTTP client, built on Axios.
 *
 * Everything the app fetches goes through this instance. That is what makes
 * the cross-cutting concerns — error shape, timeouts, auth headers, token
 * refresh — exist in one place instead of being reimplemented slightly
 * differently at forty call sites.
 *
 * Requests are same-origin by design. In production a reverse proxy serves the
 * app and the API from one host; in development the Vite proxy does the same.
 * The base URL is therefore a path, never an origin — which also means the
 * refresh cookie (`SameSite=Strict`) is sent without any CORS involvement.
 *
 * The exported surface (`api`, `ApiError`, `describeError`, `installAuthHooks`)
 * is unchanged from the fetch implementation it replaces, so the auth store and
 * auth service continue to work untouched. The 401-refresh path in particular
 * is ported rather than rewritten: rotating a refresh token twice looks like
 * theft to the backend, which revokes every session in the family.
 */

import axios, {
  AxiosError,
  type AxiosInstance,
  type AxiosRequestConfig,
  type InternalAxiosRequestConfig,
} from "axios"

export const API_BASE = "/api/v1"

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
    this.name = "ApiError"
    this.status = problem.status
    this.problem = problem
    this.fieldErrors = problem.errors ?? {}
  }

  /** The error code, e.g. `permission_denied` — stable across message edits. */
  get code(): string {
    const match = /\/errors\/([a-z_]+)$/.exec(this.problem.type)
    return match?.[1] ?? "unknown"
  }

  /** True when retrying later might work; false when the request itself is wrong. */
  get isTransient(): boolean {
    return this.status === 429 || this.status >= 500
  }
}

/** Raised when the network never answered — distinct from the server saying no. */
export class NetworkError extends Error {
  readonly cause?: unknown
  constructor(message: string, cause?: unknown) {
    super(message)
    this.name = "NetworkError"
    this.cause = cause
  }
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

/** Per-request options this client understands beyond Axios' own. */
export interface RequestConfig
  extends AxiosRequestConfig {
  /** Skips the access token and the 401-refresh path. Used by auth itself. */
  anonymous?: boolean
}

interface RetryableConfig
  extends InternalAxiosRequestConfig {
  /** Set once a request has already been retried after a refresh. */
  anonymous?: boolean
  _retried?: boolean
}

export const client: AxiosInstance = axios.create({
  baseURL: API_BASE,
  timeout: DEFAULT_TIMEOUT_MS,
  // Same-origin, so cookies ride along without `withCredentials` and without
  // this becoming a CORS request.
  headers: { Accept: "application/json" },
  // Repeated keys rather than bracket notation: FastAPI reads `?ids=a&ids=b`
  // as a list, and `?ids[]=a` as a parameter literally named `ids[]`.
  paramsSerializer: { indexes: null },
})

client.interceptors.request.use((config: RetryableConfig) => {
  if (!config.anonymous) {
    const token = hooks?.getAccessToken() ?? null
    if (token) config.headers.set("Authorization", `Bearer ${token}`)
  }
  return config
})

function toProblem(error: AxiosError): Problem {
  const body = error.response?.data
  if (body && typeof body === "object" && "title" in body)
    return body as Problem

  // Not our API answering: a proxy error page, a gateway timeout, an HTML
  // body. `statusText` is always empty over HTTP/2, so relying on it left
  // every one of these reading "Request failed" with the one useful fact —
  // the status — discarded.
  const status = error.response?.status ?? 0
  return {
    type: "about:blank",
    title: error.response?.statusText || `Request failed (${status || "no response"})`,
    status,
    detail: typeof body === "string" && body.trim() ? body.slice(0, 300) : undefined,
  }
}

client.interceptors.response.use(
  (response) => response,
  async (error: AxiosError) => {
    const config = error.config as RetryableConfig | undefined

    // The server never answered: a timeout, a dropped connection, an offline
    // device. Distinct from the server answering "no", which is an ApiError.
    if (!error.response) {
      if (axios.isCancel(error)) throw error
      const timedOut =
        error.code === "ECONNABORTED" || error.code === "ETIMEDOUT"
      throw new NetworkError(
        timedOut ? "The request timed out." : "Could not reach the server.",
        error,
      )
    }

    // One retry, and only after a successful refresh. `refresh()` is
    // single-flight in the auth layer: concurrent 401s wait on one rotation
    // rather than each starting their own.
    if (
      error.response.status === 401 &&
      config &&
      !config.anonymous &&
      !config._retried &&
      hooks
    ) {
      config._retried = true
      const token = await hooks.refresh()
      if (token) {
        config.headers.set("Authorization", `Bearer ${token}`)
        return client.request(config)
      }
      hooks.onAuthFailure()
    }

    throw new ApiError(toProblem(error))
  },
)

async function unwrap<T>(
  promise: Promise<{ data: T; status: number }>,
): Promise<T> {
  const response = await promise
  // 204 carries no body; Axios gives an empty string, which is not the absence
  // of a value the caller is typed to expect.
  if (response.status === 204) return undefined as T
  return response.data
}

export const api = {
  get: <T>(path: string, config?: RequestConfig) =>
    unwrap<T>(client.get<T>(path, config)),
  post: <T>(path: string, body?: unknown, config?: RequestConfig) =>
    unwrap<T>(client.post<T>(path, body, config)),
  patch: <T>(path: string, body?: unknown, config?: RequestConfig) =>
    unwrap<T>(client.patch<T>(path, body, config)),
  delete: <T>(path: string, config?: RequestConfig) =>
    unwrap<T>(client.delete<T>(path, config)),
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
    // A rejected field is the whole point of a 422, and "One or more fields
    // are invalid" names none of them. The form highlights them too, but the
    // fields it cannot show — an immutable one, an unknown one — would
    // otherwise leave the reader with nothing to act on.
    const fields = Object.entries(error.fieldErrors)
    if (error.status === 422 && fields.length > 0) {
      const named = fields
        .slice(0, 3)
        .map(([field, messages]) => `${field}: ${messages[0] ?? "invalid"}`)
        .join("; ")
      const rest = fields.length > 3 ? ` (and ${fields.length - 3} more)` : ""
      return `${named}${rest}`
    }
    if (error.status === 401)
      return error.problem.detail ?? "Your session has expired. Sign in again."
    if (error.status === 429)
      return error.problem.detail ?? "Too many requests. Please slow down."
    // 503 is the one 5xx the server raises deliberately, and it always says
    // *why* — a feature that is switched off rather than broken. Replacing
    // that with "try again" sends the reader into a loop retrying a
    // configuration problem.
    if (error.status === 503 && error.problem.detail) return error.problem.detail
    if (error.status >= 500)
      return "Something went wrong on our side. Please try again."
    return error.problem.detail ?? error.problem.title
  }
  if (error instanceof NetworkError)
    return "Could not reach the server. Check your connection."
  return "Something went wrong."
}
