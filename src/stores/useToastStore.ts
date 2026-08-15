import { create } from 'zustand'

interface ToastState {
  message: string
  show: (message: string) => void
  dismiss: () => void
}

/**
 * Transient action feedback for the admin console.
 *
 * Deliberately not persisted — a toast that survives a reload would be lying
 * about something that already finished. The store exists so that sections
 * rendered through an `<Outlet />` can raise a toast without the layout
 * threading a callback down to each one.
 */
export const useToastStore = create<ToastState>()(set => ({
  message: '',
  show: message => set({ message }),
  dismiss: () => set({ message: '' }),
}))

export const useToast = () => useToastStore(state => state.show)
export const useToastMessage = () => useToastStore(state => state.message)
