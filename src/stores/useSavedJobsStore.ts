import { create } from 'zustand'
import { persist, createJSONStorage } from 'zustand/middleware'
import { safeStorage, storageKey } from '@/lib/storage'

interface SavedJobsState {
  ids: string[]
  toggle: (id: string) => void
  clear: () => void
}

/**
 * Saved jobs, persisted to localStorage.
 *
 * Anonymous by design — the product promises browsing without an account, so
 * saves live on the device. Phase 8 adds an optional server-side sync for
 * users who do sign in, with this store as the offline fallback.
 */
export const useSavedJobsStore = create<SavedJobsState>()(
  persist(
    set => ({
      ids: [],
      toggle: id =>
        set(state => ({
          ids: state.ids.includes(id) ? state.ids.filter(x => x !== id) : [...state.ids, id],
        })),
      clear: () => set({ ids: [] }),
    }),
    {
      name: storageKey('saved'),
      version: 1,
      storage: createJSONStorage(() => safeStorage),
      partialize: state => ({ ids: state.ids }),
    },
  ),
)

/**
 * Selector hooks.
 *
 * Subscribing to a slice rather than the whole store is what keeps a bookmark
 * click from re-rendering every card in the grid — with Context this would
 * need hand-written memo boundaries at each consumer.
 */
export const useSavedIds = () => useSavedJobsStore(state => state.ids)
export const useSavedCount = () => useSavedJobsStore(state => state.ids.length)
export const useIsSaved = (id: string) => useSavedJobsStore(state => state.ids.includes(id))
export const useToggleSave = () => useSavedJobsStore(state => state.toggle)
