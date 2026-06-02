# Deployment Guide

This guide covers running the Price Flow Tracker stack in a development
environment on a fresh machine.

## Topology

```
  ┌─────────────────────┐         ┌─────────────────────┐
  │  React frontend     │         │   Supabase Cloud    │
  │  npm run dev        │ ──auth─▶│   (Postgres + Auth) │
  │  http://localhost:  │         └─────────────────────┘
  │  5173 (native)      │                  ▲
  └──────────┬──────────┘                  │ REST + JWT verify
             │                             │
             │ HTTP + WS                   │
             ▼                             │
  ┌─────────────────────┐                  │
  │  FastAPI backend    │──────────────────┘
  │  docker container   │
  │  :8000              │──▶ postiz-redis:6379 (DB 1, shared)
  └─────────────────────┘──▶ Stripe / Resend (optional, cloud)
```

- **Frontend** runs natively (`npm run dev`).
- **Backend** runs in a Docker container via `backend/docker-compose.yml`.
- **Supabase** stays on the cloud — nothing to install locally.
- **Redis** is shared with the existing `postiz-redis` container on
  `soljet-postiz_postiz-network`. We use DB index `1` to avoid colliding
  with postiz (which uses DB `0`).

## Prerequisites

- Docker (Docker Desktop on WSL2 is fine)
- Node.js 18+ and npm
- A Supabase project (free tier is enough)
- Optional: Stripe account + CLI (for billing), Resend account (for alerts)
- The `postiz-redis` container must be running on
  `soljet-postiz_postiz-network`. Check with:
  ```bash
  docker ps --filter name=postiz-redis
  ```

## 1. Clone and configure

```bash
git clone <repo-url> RelativeQs
cd RelativeQs
cp .env.example .env                   # frontend env
cp backend/.env.example backend/.env   # backend env
```

## 2. Supabase (cloud)

1. Create a project at https://supabase.com (or reuse an existing one).
2. Apply the SQL migrations in order: Supabase dashboard → **SQL Editor**
   → paste each file → **Run**:
   - `supabase/migrations/0001_profiles.sql`
   - `supabase/migrations/0002_alerts.sql`
3. From **Settings → API**, copy:
   - **Project URL** → `SUPABASE_URL` (backend) and `VITE_SUPABASE_URL`
     (frontend)
   - **anon public key** → `VITE_SUPABASE_ANON_KEY` (frontend)
   - **service_role key** (secret) → `SUPABASE_SERVICE_KEY` (backend)
4. If the project uses legacy HS256 JWTs, also copy **JWT Secret** →
   `SUPABASE_JWT_SECRET`. New projects with asymmetric keys don't need this
   — the backend reads JWKS automatically.

## 3. Backend env (`backend/.env`)

Required:

```env
DATA_PROVIDER=yahoo

SUPABASE_URL=https://YOUR-PROJECT-REF.supabase.co
SUPABASE_SERVICE_KEY=...
# SUPABASE_JWT_SECRET=...  # only for legacy HS256 projects

FRONTEND_URL=http://localhost:5173
```

`REDIS_URL` is set by docker-compose itself (`redis://postiz-redis:6379/1`)
— no need to set it in `.env`. If you do set it, compose will override it.

Optional (only if you want billing / alerts in dev):

```env
STRIPE_SECRET_KEY=sk_test_...
STRIPE_WEBHOOK_SECRET=whsec_...
STRIPE_PRICE_ID=price_...
RESEND_API_KEY=re_...
ALERT_FROM_EMAIL=Price Flow Tracker <onboarding@resend.dev>
```

## 4. Frontend env (`.env`)

```env
VITE_BACKEND_URL=http://localhost:8001
VITE_WS_URL=ws://localhost:8001/ws/market
VITE_POLL_INTERVAL_MS=12000
VITE_SUPABASE_URL=https://YOUR-PROJECT-REF.supabase.co
VITE_SUPABASE_ANON_KEY=...
```

Vite inlines these at build time. Restart `npm run dev` after editing.

## 5. Start the backend

```bash
cd backend
docker compose up --build -d
docker compose logs -f web
```

Verify:

- API docs: http://localhost:8001/docs
- Health: `curl http://localhost:8001/api/health`

The container joins both its own default network and the external
`soljet-postiz_postiz-network`, so it resolves `postiz-redis` by name.

## 6. Start the frontend

```bash
# from repo root
npm install
npm run dev
```

Open http://localhost:5173.

## 7. Verify the whole flow

1. Register a new account on the frontend.
2. Confirm the email (Supabase will send a confirmation if email
   confirmations are enabled in your project).
3. Log in. The dashboard should populate with snapshot data from the
   backend.
4. Check that the backend log shows snapshot polling and that the
   websocket connects.

## Stripe (optional, for billing)

1. Create a recurring **Product / Price** in Stripe; copy the price ID
   into `STRIPE_PRICE_ID`.
2. Use a `sk_test_` secret key in dev.
3. Forward webhooks locally:
   ```bash
   stripe listen --forward-to http://localhost:8001/api/billing/webhook
   ```
   Copy the printed `whsec_...` into `STRIPE_WEBHOOK_SECRET`, then restart
   the backend container.

## Resend (optional, for regime alerts)

Set `RESEND_API_KEY` and `ALERT_FROM_EMAIL`. With no key set, alerts are
logged but not sent. For a non-personal `from` address you must verify
the sending domain in Resend.

## Common operations

```bash
# Tail backend logs
docker compose -f backend/docker-compose.yml logs -f web

# Rebuild after backend code change
docker compose -f backend/docker-compose.yml up --build -d

# Stop the backend
docker compose -f backend/docker-compose.yml down

# Inspect the shared Redis from the backend container
docker compose -f backend/docker-compose.yml exec web \
  python -c "import redis; r=redis.from_url('redis://postiz-redis:6379/1'); print(r.ping())"
```

## Troubleshooting

- **`could not resolve postiz-redis`** — the postiz stack isn't running.
  Start it first: `docker start postiz-redis`. The network
  `soljet-postiz_postiz-network` must exist before `docker compose up`.
- **`401 Invalid or expired session`** — `SUPABASE_URL` mismatch between
  frontend and backend, or the JWT signing scheme switched. Re-copy both
  values from Settings → API.
- **Stripe webhook 400 / signature failure** — `STRIPE_WEBHOOK_SECRET`
  doesn't match the `whsec_` printed by `stripe listen`. They rotate per
  CLI session.
- **Frontend can't reach the backend** — check `VITE_BACKEND_URL` and
  that `docker compose ps` shows `web` Up on `0.0.0.0:8000`.
- **Redis key collision worries** — postiz uses DB 0, we use DB 1. To
  flush only our data: `redis-cli -h postiz-redis -n 1 FLUSHDB` (run from
  inside the backend container).
