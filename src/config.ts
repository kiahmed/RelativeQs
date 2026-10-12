/**
 * Frontend runtime configuration.
 *
 * Values come from Vite environment variables (`.env` at the project root,
 * variables must be prefixed with `VITE_`). Each has a safe fallback so the
 * app still runs if the `.env` file is missing.
 *
 * NOTE: Vite inlines these at build time — after editing `.env` you must
 * restart `npm run dev` or rebuild for changes to take effect.
 */

const env = import.meta.env

/** Base URL of the backend HTTP API. */
export const BACKEND_URL: string = env.VITE_RELQS_BACKEND_URL || 'http://localhost:8000'

/** Websocket URL for the realtime market feed. Derived from BACKEND_URL if unset. */
export const WS_URL: string =
  env.VITE_RELQS_WS_URL || `${BACKEND_URL.replace(/^http/, 'ws')}/ws/market`

/** How often the dashboard re-fetches data over HTTP, in milliseconds. */
export const POLL_INTERVAL_MS: number = Number(env.VITE_POLL_INTERVAL_MS) || 12000

/** Supabase project URL — from the Supabase dashboard (Settings → API). */
export const SUPABASE_URL: string = env.VITE_SUPABASE_URL || ''

/** Supabase anon/public API key — safe to expose to the browser. */
export const SUPABASE_ANON_KEY: string = env.VITE_SUPABASE_ANON_KEY || ''
