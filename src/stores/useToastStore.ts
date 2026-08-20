import { create } from 'zustand'

/**
 * How long a toast stays on screen.
 *
 * Long enough to read a full sentence without hurrying — some of these carry a
 * reason rather than a confirmation ("This location still has 1 published
 * listing(s).") — and short enough that it never becomes furniture.
 */
const TOAST_DURATION_MS = 4_000

interface ToastState {
  message: string
  /**
   * Bumped on every `show`. Two identical messages in a row are two separate
   * toasts, and without a changing value nothing downstream can tell them
   * apart — the second would silently inherit whatever was left of the first
   * one's time.
   */
  id: number
  show: (message: string) => void
  dismiss: () => void
}

/**
 * Module-scoped rather than stored in state: a pending timer is not something
 * a component should re-render over, and keeping exactly one means a rapid
 * second `show` replaces the first toast's countdown instead of racing it.
 */
let timer: ReturnType<typeof setTimeout> | null = null

function clearTimer(): void {
  if (timer !== null) {
    clearTimeout(timer)
    timer = null
  }
}

/**
 * Transient action feedback for the admin console.
 *
 * Deliberately not persisted — a toast that survives a reload would be lying
 * about something that already finished. The store exists so that sections
 * rendered through an `<Outlet />` can raise a toast without the layout
 * threading a callback down to each one.
 *
 * The dismissal timer lives here rather than in the component that renders the
 * toast. If it lived there, unmounting would cancel the timer while leaving
 * `message` set, so navigating away and back would resurrect a stale toast —
 * the same lie the store already refuses to tell across a reload.
 */
export const useToastStore = create<ToastState>()((set, get) => ({
  message: '',
  id: 0,
  show: message => {
    clearTimer()
    set(state => ({ message, id: state.id + 1 }))
    timer = setTimeout(() => {
      timer = null
      get().dismiss()
    }, TOAST_DURATION_MS)
  },
  dismiss: () => {
    clearTimer()
    set({ message: '' })
  },
}))

export const useToast = () => useToastStore(state => state.show)
export const useToastMessage = () => useToastStore(state => state.message)
/** Lets the reader close a toast early rather than waiting it out. */
export const useToastDismiss = () => useToastStore(state => state.dismiss)
/** Render key for the toast, so a replacement replays the entrance animation
 *  instead of silently swapping text inside the element already on screen. */
export const useToastId = () => useToastStore(state => state.id)
