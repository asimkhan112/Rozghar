/**
 * Behavioural event tracking.
 *
 * The backend already knows how to count: `POST /analytics/events` takes a
 * batch, resolves attribution server-side, bumps the denormalised counters on
 * the job row and feeds the daily rollups. This module is the other half —
 * the part that decides *when* an event happened and gets the batch there.
 *
 * Three properties are non-negotiable, and they mirror the ingest endpoint's
 * own rules:
 *
 * **Measurement never breaks the product.** Every failure path here is a
 * swallowed promise. A dropped event costs a decimal place in a report; an
 * unhandled rejection in an apply handler costs the reader the job they were
 * about to apply for.
 *
 * **Events are batched, not chatty.** One request per interaction would put a
 * network round trip on the critical path of a bookmark click. The queue
 * flushes on a timer, when the page is hidden, and immediately for the two
 * events worth a request of their own.
 *
 * **The client reports what happened, never what it should be attributed to.**
 * No `source_id`, no device, no country — the endpoint is unauthenticated and
 * derives all of that itself. Sending it from here would be both forgeable and
 * ignored.
 */

import { API_BASE, api } from "@/lib/http"
import { getSessionId } from "@/lib/session"

/** Mirrors `EventType` in the backend enum. Values are the wire format. */
export type AnalyticsEventType =
  | "job_view"
  | "apply_click"
  | "search"
  | "share"
  | "report_created"
  | "source_click"
  | "job_saved"
  | "filter_used"

/**
 * One queued event.
 *
 * `occurred_at` is deliberately absent. The field exists on the API and the
 * server accepts a client timestamp within a tolerance, but a browser clock is
 * frequently wrong by more than that tolerance — and a skewed clock would get
 * every event from that device silently rejected rather than merely
 * mis-stamped. Letting the server stamp costs at most one flush interval of
 * accuracy, which no daily report can see.
 */
interface QueuedEvent {
  type: AnalyticsEventType
  job_id?: string
  query?: string
  filters?: Record<string, unknown>
  result_count?: number
}

/** Relative to the client's base URL, which is what `api.post` expects. */
const PATH = "/analytics/events"

/** The same endpoint, absolute — `sendBeacon` knows nothing about a base URL. */
const BEACON_URL = `${API_BASE}${PATH}`

/** The backend caps a batch at 50, so the queue is drained in chunks of 50. */
const MAX_BATCH = 50

/**
 * Beyond this the queue stops accepting. Only reachable if the API has been
 * unreachable for a long time on a very busy session — the cap is what stops
 * that becoming unbounded memory growth.
 */
const MAX_QUEUE = 500

/** Long enough to coalesce a burst of clicks, short enough that a visitor who
 *  closes the tab has usually already been counted by the timer. */
const FLUSH_INTERVAL_MS = 5_000

/**
 * A repeat `job_view` for the same listing inside this window is suppressed.
 *
 * This is not about deduplicating real visits — it exists because a view is
 * fired from an effect, and effects run more than once for reasons that have
 * nothing to do with the visitor: React's StrictMode double-invokes them in
 * development, and a query refetch can remount the page. Without this, every
 * development session would inflate production-shaped numbers and every
 * back-then-forward would count twice.
 */
const VIEW_DEDUPE_MS = 30_000

let queue: QueuedEvent[] = []
let timer: ReturnType<typeof setTimeout> | null = null
const recentViews = new Map<string, number>()

/** False during SSR and in the snapshot renderer, where there is no transport. */
const canSend = typeof window !== "undefined" && typeof navigator !== "undefined"

function scheduleFlush(): void {
  if (timer !== null) return
  timer = setTimeout(() => {
    timer = null
    void flush()
  }, FLUSH_INTERVAL_MS)
}

function enqueue(event: QueuedEvent): void {
  if (!canSend) return
  if (queue.length >= MAX_QUEUE) return
  queue.push(event)
  scheduleFlush()
}

/** Removes and returns everything currently queued, capped into batches. */
function drain(): QueuedEvent[][] {
  if (queue.length === 0) return []
  const pending = queue
  queue = []
  const batches: QueuedEvent[][] = []
  for (let i = 0; i < pending.length; i += MAX_BATCH) {
    batches.push(pending.slice(i, i + MAX_BATCH))
  }
  return batches
}

function payload(events: QueuedEvent[]): EventBatch {
  return { session_id: getSessionId(), events }
}

interface EventBatch {
  session_id: string
  events: QueuedEvent[]
}

/**
 * Send everything queued.
 *
 * `anonymous` skips the Authorization header and the 401-refresh path: the
 * ingest endpoint takes no credentials, and an admin who happens to be signed
 * in must not have a token attached to an anonymous beacon-shaped request.
 *
 * Failures are dropped rather than retried. Re-queueing a batch that failed
 * would mean an API outage turns into a request every five seconds for the
 * lifetime of the tab, and the events would be too stale to matter by the time
 * it recovered.
 */
export async function flush(): Promise<void> {
  if (!canSend) return
  if (timer !== null) {
    clearTimeout(timer)
    timer = null
  }
  for (const batch of drain()) {
    try {
      await api.post(PATH, payload(batch), { anonymous: true })
    } catch {
      // Intentionally silent. See the note above.
    }
  }
}

/**
 * Send everything queued without waiting for it.
 *
 * `sendBeacon` is the only transport a browser guarantees to complete after a
 * page starts unloading — a `fetch` issued from `pagehide` is routinely
 * cancelled, which is precisely when the last view of a session is sitting in
 * the queue. The Blob type matters: without it the request is sent as
 * `text/plain` and FastAPI will not parse the body.
 */
export function flushBeacon(): void {
  if (!canSend) return
  if (timer !== null) {
    clearTimeout(timer)
    timer = null
  }
  for (const batch of drain()) {
    const blob = new Blob([JSON.stringify(payload(batch))], {
      type: "application/json",
    })
    const sent = navigator.sendBeacon?.(BEACON_URL, blob) ?? false
    // No beacon support, or the browser refused to queue it. One best-effort
    // attempt over the normal transport, then give up.
    if (!sent) {
      void api.post(PATH, payload(batch), { anonymous: true }).catch(() => {})
    }
  }
}

/** A detail-page view. Safe to call from an effect — see `VIEW_DEDUPE_MS`. */
export function trackJobView(jobId: string | undefined): void {
  if (!jobId) return
  const now = Date.now()
  const last = recentViews.get(jobId)
  if (last !== undefined && now - last < VIEW_DEDUPE_MS) return
  // Entries outside the window can never suppress anything again, so they are
  // dropped here rather than accumulating for the lifetime of a long session.
  for (const [id, at] of recentViews) {
    if (now - at >= VIEW_DEDUPE_MS) recentViews.delete(id)
  }
  recentViews.set(jobId, now)
  enqueue({ type: "job_view", job_id: jobId })
}

/**
 * An Apply click, sent immediately.
 *
 * This is the conversion metric the whole dashboard is pointed at, and the
 * click is followed by a new tab and often by the original tab being
 * abandoned. Waiting up to five seconds for the timer would lose the ones that
 * matter most, so it goes out on a beacon now.
 */
export function trackApplyClick(jobId: string | undefined): void {
  if (!jobId) return
  enqueue({ type: "apply_click", job_id: jobId })
  flushBeacon()
}

/** A bookmark. Drives `jobs.save_count`; the un-save is not an event. */
export function trackJobSaved(jobId: string | undefined): void {
  if (!jobId) return
  enqueue({ type: "job_saved", job_id: jobId })
}

/** A share, once the visitor has picked a destination. */
export function trackShare(jobId: string | undefined): void {
  if (!jobId) return
  enqueue({ type: "share", job_id: jobId })
}

/** A click through to the original posting on the source site. */
export function trackSourceClick(jobId: string | undefined): void {
  if (!jobId) return
  enqueue({ type: "source_click", job_id: jobId })
}

/**
 * Wire the queue to the page lifecycle. Called once, from the entrypoint.
 *
 * `visibilitychange` is what actually fires on mobile — a tab switch or the
 * home button never produces `pagehide` on iOS, and `beforeunload` is not
 * fired at all there. `pagehide` is kept for the desktop close-the-tab case
 * and for browsers restoring from the back/forward cache.
 */
export function installAnalytics(): () => void {
  if (!canSend) return () => {}

  const onHidden = () => {
    if (document.visibilityState === "hidden") flushBeacon()
  }
  const onPageHide = () => flushBeacon()

  document.addEventListener("visibilitychange", onHidden)
  window.addEventListener("pagehide", onPageHide)

  return () => {
    document.removeEventListener("visibilitychange", onHidden)
    window.removeEventListener("pagehide", onPageHide)
  }
}
