# Deployment Guide

How to run RelativeQs locally, and how to ship it to the cloud.

Two things get deployed:

| Piece | Where | URL |
|---|---|---|
| Frontend (Vite/React SPA) | Vercel | https://relativeqs.vercel.app |
| Backend (FastAPI + poll loop) | Fly.io, **or** a local container | https://relativeqs-api.fly.dev |

Both talk to the same two managed services: **Supabase** (Postgres + Auth)
and **Upstash Redis** (snapshot + intraday bar history).

## Topology

```
  ┌─────────────────────┐         ┌─────────────────────┐
  │  React frontend     │ ──auth─▶│   Supabase Cloud    │
  │  Vercel (prod)      │         │   (Postgres + Auth) │
  │  Vite :5173 (dev)   │         └─────────────────────┘
  └──────────┬──────────┘                  ▲
             │                             │ REST + JWT verify
             │ HTTPS + WSS                 │
             ▼                             │
  ┌─────────────────────┐                  │
  │  FastAPI backend    │──────────────────┘
  │  Fly machine, OR    │
  │  local container    │──▶ Upstash Redis (managed, rediss://)
  │  :8001 -> :8000     │──▶ Yahoo market data
  └─────────────────────┘──▶ Stripe / Resend (optional)
```

### The backend is a singleton

The backend is not a plain request/response API. `_poll_and_broadcast` runs
forever: it fetches market data, writes `snapshot:latest` and `bars:<date>`
into Redis, and pushes updates over websockets. That intraday bar history
accumulates over the trading day and cannot be re-derived after the fact.

**Exactly one backend may run at a time.** The Fly machine and a local
container both write the same Upstash keys — running both clobbers the bar
history. Before starting a local backend, stop Fly (see
[Switching between Fly and local](#switching-between-fly-and-local)).

## Prerequisites

- Docker (Docker Desktop on WSL2 is fine)
- Node.js 18+ and npm
- A Supabase project (free tier is enough)
- An Upstash Redis database (free tier is enough)
- For cloud deploys: `flyctl` and `vercel` CLIs, both logged in
- Optional: Stripe account + CLI (billing), Resend account (alert emails)

## 1. Clone and configure

```bash
git clone <repo-url> RelativeQs
cd RelativeQs
cp .env.example .env                                       # frontend env
cp backend/.env.example backend/.env                       # backend env
cp deploy/.env.production.example deploy/.env.production   # frontend prod env
```

All three copies are gitignored. `backend/.env` holds real secrets — it is
also the source `deploy_to_cloud.sh --sync-secrets` reads when pushing Fly
secrets, so keep it complete.

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

## 3. Upstash Redis (cloud)

Redis is where the snapshot and the intraday bar history live, so the
frontend keeps showing data across a backend restart.

1. Create a database at https://upstash.com — region **us-east-1** to sit
   close to the Fly `iad` machine and to US market data.
2. Copy the **TLS (rediss://) connection string** into `REDIS_URL` in
   `backend/.env`.

Use the *same* `REDIS_URL` for the Fly machine and for local runs — that's
what lets a local container pick up the keys the cloud deploy accumulated.

> Do **not** point `REDIS_URL` at `redis://127.0.0.1:6379` when running via
> Docker Compose: `127.0.0.1` resolves to the container itself, which has no
> Redis. Either use the Upstash URL or run the backend natively.

## 4. Backend env (`backend/.env`)

Required:

```env
DATA_PROVIDER=yahoo
REDIS_URL=rediss://default:...@...upstash.io:6379

SUPABASE_URL=https://YOUR-PROJECT-REF.supabase.co
SUPABASE_SERVICE_KEY=...
# SUPABASE_JWT_SECRET=...  # only for legacy HS256 projects

FRONTEND_URL=http://localhost:5173
```

Optional (billing / alerts / the deployed frontend's origin):

```env
STRIPE_SECRET_KEY=sk_test_...
STRIPE_WEBHOOK_SECRET=whsec_...
STRIPE_PRICE_ID=price_...
RESEND_API_KEY=re_...
ALERT_FROM_EMAIL=RelativeQs <onboarding@resend.dev>
CORS_ORIGINS=https://relativeqs.vercel.app
```

See `backend/.env.example` for the full annotated list (poll cadence,
per-provider rate limits, the AI-capex basket).

## 5. Frontend env (`.env`)

```env
VITE_RELQS_BACKEND_URL=http://localhost:8001
VITE_RELQS_WS_URL=ws://localhost:8001/ws/market
VITE_POLL_INTERVAL_MS=12000
VITE_SUPABASE_URL=https://YOUR-PROJECT-REF.supabase.co
VITE_SUPABASE_ANON_KEY=...
```

Port **8001** is the Compose-published port (the container listens on 8000;
`docker-compose.yml` maps `8001:8000`). If you instead run uvicorn natively
on port 8000, use 8000 in both URLs.

Vite inlines these at build time. Restart `npm run dev` after editing.

## 6. Start the backend

```bash
make be-up        # docker compose up --build -d
make be-logs      # tail the logs
```

Verify:

- API docs: http://localhost:8001/docs
- Health: `curl http://localhost:8001/api/health`

## 7. Start the frontend

```bash
make fe-install   # npm install
make fe-dev       # npm run dev
```

Open http://localhost:5173. `make dev` does both (backend container, then
the Vite dev server).

## 8. Verify the whole flow

1. Register a new account on the frontend.
2. Confirm the email (Supabase sends a confirmation if email confirmations
   are enabled in your project).
3. Log in. The dashboard should populate with snapshot data from the backend.
4. Check that the backend log shows snapshot polling and that the websocket
   connects.

---

# Cloud deploy

`deploy_to_cloud.sh` drives both halves; the Makefile wraps it. Run
`./deploy_to_cloud.sh --help` for the full flag list.

```bash
make deploy-dry   # print every command, run nothing — always start here
make deploy       # backend (Fly) + frontend (Vercel)
make deploy-be    # backend only
make deploy-fe    # frontend only
```

Check you're authenticated first:

```bash
make fly-check
make vercel-check
```

## Backend → Fly.io

`make deploy-be` runs `flyctl deploy` with the build context set to
`backend/`, `deploy/fly.toml` as config, and `--ha=false`.

`deploy/fly.toml` deliberately sets `auto_stop_machines = false`,
`auto_start_machines = false` and `min_machines_running = 1`: this is an
outbound-only always-on poller with no inbound traffic of its own, so any
autostop idle-timer would kill the loop. `min_machines_running` alone is not
enough — autostop must be fully disabled. The VM is 512MB because
pandas + numpy + scipy + scikit-learn OOM on import at 256MB.

After a successful backend deploy the script rewrites the two URL lines in
`deploy/.env.production` to point at `https://$FLY_APP.fly.dev`, so the next
frontend deploy bakes in the right host.

### Secrets

Non-secret defaults (`DATA_PROVIDER`, `POLL_INTERVAL_SECONDS`, `LOG_LEVEL`,
…) live in `[env]` in `deploy/fly.toml`. Everything secret — `REDIS_URL`,
`SUPABASE_*`, `STRIPE_*`, `RESEND_*`, `CORS_ORIGINS` — is pushed from
`backend/.env` to Fly secrets:

```bash
make secrets             # sync only
make deploy-be-secrets   # sync, then deploy
```

The sync skips comments, blanks, and unfilled placeholders (`your-*`,
`sk_test_your*`, …), and strips one layer of surrounding quotes.

## Frontend → Vercel

Vercel hosts the **frontend only**. `.vercelignore` hides `backend/`,
`supabase/`, `deploy/` and friends so the CLI doesn't auto-detect the
FastAPI app and turn this into a multi-service deploy.

`make deploy-fe` copies `deploy/.env.production` to `./.env.production`,
runs `vercel build --prod` (Vite auto-loads `.env.production` in production
mode and inlines the `VITE_*` values), then `vercel deploy --prebuilt --prod`.
Because the values are inlined at build time, there is nothing to configure
in the Vercel dashboard.

`vercel.json` rewrites all paths to `/index.html` for client-side routing.

Only the **anon** Supabase key belongs in `deploy/.env.production` — it ends
up in the browser bundle. Never the `service_role` key.

## After deploying the frontend

Add the Vercel origin to `CORS_ORIGINS` in `backend/.env` and re-sync
secrets, or the browser will be blocked from calling the API:

```env
CORS_ORIGINS=https://relativeqs.vercel.app
```

```bash
make deploy-be-secrets
```

## Switching between Fly and local

Only one poller may run at a time (see [above](#the-backend-is-a-singleton)).

```bash
make takeover     # stop Fly, then start the local backend on the same Upstash
make fly-start    # hand the role back to Fly (stop the local one first: make be-down)
make fly-retire   # scale Fly to 0 for good; 'make deploy-be' brings it back
```

`FLY_APP` is overridable in both the Makefile and `deploy_to_cloud.sh`:
`make takeover FLY_APP=my-app`.

## Common operations

```bash
make be-logs                 # tail backend logs
make be-up                   # rebuild + restart after a backend code change
make be-down                 # stop the backend
make be-shell                # shell inside the container
make clear-cache             # clear the Redis market-data cache (prompts)
make quotes ARGS="QQQ SMH"   # fetch live quotes
make prune                   # clean up this project's docker leftovers
make help                    # list every target
```

## Troubleshooting

- **Dashboard is empty / snapshot never arrives** — the backend can't reach
  Redis. Check `REDIS_URL` in `backend/.env` is the `rediss://` Upstash
  string, not `redis://127.0.0.1` (unreachable from inside the container).
- **Bar history looks truncated or keeps resetting** — two pollers are
  writing the same Upstash keys. Confirm the Fly machine is stopped:
  `flyctl machine list --app relativeqs-api`. Use `make takeover`.
- **`401 Invalid or expired session`** — `SUPABASE_URL` mismatch between
  frontend and backend, or the JWT signing scheme switched. Re-copy both
  values from Settings → API.
- **CORS error in the browser on the deployed site** — the Vercel origin
  isn't in `CORS_ORIGINS`. Add it to `backend/.env` and `make secrets`.
  localhost dev origins are always allowed.
- **Frontend can't reach the backend locally** — check
  `VITE_RELQS_BACKEND_URL` uses port **8001**, and that `make be-ps` shows
  `relqs-web-service` Up on `0.0.0.0:8001->8000`.
- **Stripe webhook 400 / signature failure** — `STRIPE_WEBHOOK_SECRET`
  doesn't match the `whsec_` printed by `stripe listen`. They rotate per CLI
  session. Forward to the published port:
  `stripe listen --forward-to http://localhost:8001/api/billing/webhook`.
- **Fly machine keeps stopping** — something re-enabled autostop. Both
  `auto_stop_machines = false` and `min_machines_running = 1` must be set in
  `deploy/fly.toml`.
- **Fly deploy OOMs on import** — the VM is below 512MB. See `[[vm]]` in
  `deploy/fly.toml`.
- **Vercel tries to build the backend** — something was removed from
  `.vercelignore`. It must keep hiding `backend/`.
