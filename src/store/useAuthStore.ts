import { create } from 'zustand'
import { persist } from 'zustand/middleware'

type User = {
  fullName: string
  email: string
}

type AuthState = {
  user: User | null
  login: (email: string, fullName?: string) => void
  register: (fullName: string, email: string) => void
  logout: () => void
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      user: null,
      login: (email, fullName = '') => set({ user: { email, fullName } }),
      register: (fullName, email) => set({ user: { fullName, email } }),
      logout: () => set({ user: null }),
    }),
    { name: 'price-flow-auth' },
  ),
)
