# Supabase migrations

Versioned SQL migrations for the Supabase Postgres database. Keeping them in
the repo means the schema is reproducible — not just clicked into existence.

## Applying a migration

This project applies migrations manually through the dashboard:

1. Open the Supabase project → **SQL Editor** → **New query**.
2. Paste the contents of the next un-applied `NNNN_*.sql` file.
3. Click **Run**.

Apply files in numeric order. Each file is written to be idempotent — safe to
re-run if you're unsure whether it was applied.

## Files

| File | What it does |
|------|--------------|
| `0001_profiles.sql` | `public.profiles` table (1:1 with `auth.users`), `updated_at` trigger, auto-create-on-signup trigger, row-level security, and a backfill for existing users. |
