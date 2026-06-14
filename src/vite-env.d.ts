/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_RELQS_BACKEND_URL?: string
  readonly VITE_RELQS_WS_URL?: string
  readonly VITE_POLL_INTERVAL_MS?: string
  readonly VITE_SUPABASE_URL?: string
  readonly VITE_SUPABASE_ANON_KEY?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
