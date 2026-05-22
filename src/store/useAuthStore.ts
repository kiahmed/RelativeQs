import { create } from 'zustand'
import type { Session } from '@supabase/supabase-js'
import { supabase } from '../services/supabase'

export type User = {
  id: string
  email: string
  fullName: string
  plan: string
}

/**
 * Result of a login/register attempt.
 * - `ok: false` carries an `error` message to display.
 * - `ok: true` with a `message` means success-but-no-session — e.g. Supabase
 *   is waiting for email confirmation before the account can log in.
 */
export type AuthResult = { ok: boolean; error?: string; message?: string }

/** Map a Supabase session to the app's User shape (plan filled in separately). */
function toUser(session: Session | null): User | null {
  const u = session?.user
  if (!u) return null
  return {
    id: u.id,
    email: u.email ?? '',
    fullName: (u.user_metadata?.full_name as string) ?? '',
    // The plan is NOT in the JWT — it lives in the profiles table and is
    // loaded by refreshPlan(). Start at 'free' until that resolves.
    plan: 'free',
  }
}

type AuthState = {
  user: User | null
  /** Supabase access token — attach as `Bearer` on protected backend calls. */
  token: string | null
  /** false until the persisted Supabase session has been checked on app start */
  ready: boolean
  login: (email: string, password: string) => Promise<AuthResult>
  register: (fullName: string, email: string, password: string) => Promise<AuthResult>
  logout: () => Promise<void>
  loadSession: () => Promise<void>
  /** Re-read the authoritative subscription plan from the profiles table. */
  refreshPlan: () => Promise<void>
}

export const useAuthStore = create<AuthState>((set, get) => ({
  user: null,
  token: null,
  ready: false,

  login: async (email, password) => {
    const { data, error } = await supabase.auth.signInWithPassword({ email, password })
    if (error) return { ok: false, error: error.message }
    set({ user: toUser(data.session), token: data.session?.access_token ?? null })
    return { ok: true }
  },

  register: async (fullName, email, password) => {
    const { data, error } = await supabase.auth.signUp({
      email,
      password,
      options: { data: { full_name: fullName } },
    })
    if (error) return { ok: false, error: error.message }
    // When email confirmation is enabled, signUp returns no session — the
    // user must confirm via the emailed link before they can log in.
    if (!data.session) {
      return {
        ok: true,
        message: 'Account created. Check your email to confirm it, then log in.',
      }
    }
    set({ user: toUser(data.session), token: data.session.access_token })
    return { ok: true }
  },

  logout: async () => {
    await supabase.auth.signOut()
    set({ user: null, token: null })
  },

  // Restore any persisted Supabase session on app start.
  loadSession: async () => {
    const { data } = await supabase.auth.getSession()
    set({
      user: toUser(data.session),
      token: data.session?.access_token ?? null,
      ready: true,
    })
  },

  // The plan is not in the JWT — read it from public.profiles (RLS lets a
  // user see their own row). Called after sign-in and after Stripe checkout.
  refreshPlan: async () => {
    const current = get().user
    if (!current) return
    const { data, error } = await supabase
      .from('profiles')
      .select('plan')
      .eq('id', current.id)
      .maybeSingle()
    if (error) {
      console.error('[auth] could not read plan:', error.message)
      return
    }
    const plan = (data?.plan as string) ?? 'free'
    const u = get().user
    if (u && u.plan !== plan) set({ user: { ...u, plan } })
  },
}))

// Keep the store in sync with Supabase auth events — token refreshes, sign-out
// in another tab, email-confirmation completing, etc. Whenever a session is
// present, (re)load the plan from the profiles table.
supabase.auth.onAuthStateChange((_event, session) => {
  const next = toUser(session)
  const prev = useAuthStore.getState().user
  // preserve an already-known plan across token refreshes to avoid a flicker
  if (next && prev && prev.id === next.id) next.plan = prev.plan
  useAuthStore.setState({ user: next, token: session?.access_token ?? null })
  if (session) {
    void useAuthStore.getState().refreshPlan()
  }
})
