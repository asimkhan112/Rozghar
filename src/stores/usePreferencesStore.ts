import { create } from 'zustand'
import { persist, createJSONStorage } from 'zustand/middleware'
import { safeStorage, storageKey } from '@/lib/storage'

interface PreferencesState {
  /** Admin sidebar expanded state. Defaults to the prototype's open sidebar. */
  adminSidebarOpen: boolean
  setAdminSidebarOpen: (open: boolean) => void
}

/**
 * Durable UI preferences.
 *
 * Deliberately small: only settings a user would be annoyed to re-apply belong
 * here. Transient view state stays in the component, and anything shareable
 * (search terms, filters, sort) lives in the URL instead — see `useJobFilters`.
 */
export const usePreferencesStore = create<PreferencesState>()(
  persist(
    set => ({
      adminSidebarOpen: true,
      setAdminSidebarOpen: open => set({ adminSidebarOpen: open }),
    }),
    {
      name: storageKey('prefs'),
      version: 1,
      storage: createJSONStorage(() => safeStorage),
    },
  ),
)

export const useAdminSidebarOpen = () => usePreferencesStore(state => state.adminSidebarOpen)
export const useSetAdminSidebarOpen = () => usePreferencesStore(state => state.setAdminSidebarOpen)
