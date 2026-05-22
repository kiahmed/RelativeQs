-- ============================================================================
-- Migration 0002 — regime alert preferences
-- ----------------------------------------------------------------------------
-- Adds a per-user toggle for regime-change email alerts. Pro users with this
-- enabled are emailed when QQQ flips between risk-on and risk-off.
--
-- HOW TO APPLY:
--   Supabase dashboard -> SQL Editor -> New query -> paste this file -> Run.
--   Idempotent: safe to run more than once.
-- ============================================================================

alter table public.profiles
    add column if not exists alerts_enabled boolean not null default true;

comment on column public.profiles.alerts_enabled is
    'Whether the user receives regime-change email alerts (Pro feature).';
