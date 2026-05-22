import { createClient } from '@supabase/supabase-js'
import { SUPABASE_URL, SUPABASE_ANON_KEY } from '../config'

if (!SUPABASE_URL || !SUPABASE_ANON_KEY) {
  // The app still renders (landing/pricing/etc.), but auth will fail until
  // VITE_SUPABASE_URL and VITE_SUPABASE_ANON_KEY are set in the root .env.
  console.error(
    '[supabase] VITE_SUPABASE_URL / VITE_SUPABASE_ANON_KEY are not configured — ' +
      'sign up / log in will not work until they are set in .env.',
  )
}

/**
 * Shared Supabase client. Handles auth (signup/login/sessions), persists the
 * session in localStorage, and refreshes access tokens automatically.
 */
export const supabase = createClient(
  SUPABASE_URL || 'https://not-configured.supabase.co',
  SUPABASE_ANON_KEY || 'not-configured',
)
