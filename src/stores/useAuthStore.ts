import { create } from 'zustand'
import { persist, createJSONStorage } from 'zustand/middleware'
import { safeStorage, storageKey } from '@/lib/storage'
import type { Session } from '@/types/auth'

interface AuthState {
  session: Session | null
  signIn: (session: Session) => void
  signOut: () => void
}

export const useAuthStore = create<AuthState>()(
  persist(
    set => ({
      session: null,
      signIn: session => set({ session }),
      signOut: () => set({ session: null }),
    }),
    {
      name: storageKey('auth'),
      version: 1,
      storage: createJSONStorage(() => safeStorage),
      partialize: state => ({ session: state.session }),
      /** A session restored past its expiry is discarded on load. */
      onRehydrateStorage: () => state => {
        if (state?.session && state.session.expiresAt <= Date.now()) {
          state.signOut()
        }
      },
    },
  ),
)

/** True only for a present, unexpired session. */
export function isSessionValid(session: Session | null): session is Session {
  return session !== null && session.expiresAt > Date.now()
}

export const useSession = () => useAuthStore(state => state.session)
export const useIsAuthenticated = () => useAuthStore(state => isSessionValid(state.session))
export const useSignIn = () => useAuthStore(state => state.signIn)
export const useSignOut = () => useAuthStore(state => state.signOut)

/**
 * Non-hook accessor for use outside React — route guards and the HTTP layer.
 * This is the capability Context could not provide and the reason this project
 * uses a store rather than a provider.
 */
export const getAuthToken = (): string | null => {
  const { session } = useAuthStore.getState()
  return isSessionValid(session) ? session.token : null
}
