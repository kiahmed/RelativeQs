# Deployment Guide

How to stand up RelativeQs from scratch, and how to deploy it.

| Piece | Runs on | Public address |
|---|---|---|
| Frontend (Vite/React SPA) | Vercel | https://relativeqs.vercel.app |
| Backend (FastAPI + poll loop) | a local Docker container | https://edge-relativeq.facades.trade |
| Connector (cloudflared) | a local Docker container | — (outbound only) |
| Auth + Postgres | Supabase Cloud | — |
| Snapshot + bar history | Upstash Redis | — |

The backend is **not** hosted in the cloud. It runs on your machine and is
published on a permanent HTTPS hostname by a Cloudflare *named* tunnel. The
Vercel frontend talks to that hostname, so the browser never needs to know
where the backend physically is.

## Topology

```
   browser
      │
      ├──────────────▶ https://relativeqs.vercel.app        (static SPA, Vercel)
      │                        │
      │                        │ HTTPS + WSS
      │                        ▼
      │            https://edge-relativeq.facades.trade      (Cloudflare edge)
      │                        │
      │                        │  named tunnel 813121d1-…
      │                        ▼
      │            ┌───────────────────────┐
      │            │  relqs-cloudflared    │   connector, outbound only
      │            └───────────┬───────────┘
      │                        │ http://relativeq-backend:8000  (compose net)
      │                        ▼
      │            ┌───────────────────────┐
      │            │  relativeq-backend    │──▶ Upstash Redis (rediss://)
      │            │  FastAPI + poller     │──▶ Yahoo market data
      │            │  127.0.0.1:8001→8000  │──▶ Stripe / Resend (optional)
      │            └───────────┬───────────┘
      │                        │ JWT verify / REST
      └────────────────────────┴──────────▶ Supabase Cloud
```

### Why a *named* tunnel

A quick tunnel hands out a fresh `*.trycloudflare.com` address every restart.
The Vercel frontend bakes its backend URL in at **build time**, so a rotating
address would mean rebuilding the frontend on every backend restart. A named
tunnel keeps one hostname across restarts, rebuilds and host moves.

The tunnel's definition — name, ingress, DNS — lives in Cloudflare, not in the
container. The container holds only a connector token. That's why
`make tunnel-delete` genuinely destroys it, and `make tunnel-create` is
idempotent (re-running adopts the existing tunnel and re-applies ingress).

### The backend is a singleton

`_poll_and_broadcast` runs forever: it fetches market data, writes
`snapshot:latest` and `bars:<date>` into Redis, and pushes updates over
websockets. That intraday bar history accumulates through the trading day and
cannot be re-derived afterwards.

**Only one backend may run against a given Upstash database at a time.** Two
pollers writing the same `bars:<date>` clobber each other. If a Fly machine is
still running from the old topology, stop it first (`make fly-stop`).

## Prerequisites

- Docker (Docker Desktop on WSL2 is fine)
- Node.js 18+ and npm
- `vercel` CLI, logged in (`vercel login`)
- A Supabase project
- An Upstash Redis database
- A Cloudflare account holding the DNS zone you'll publish under, plus an API
  token (see [§4](#4-tunnel-env-deployenv))

`flyctl` is only needed if you still operate the legacy Fly backend.

## 1. Clone and configure

```bash
git clone <repo-url> RelativeQs
cd RelativeQs
cp .env.example .env                                       # frontend dev env
cp backend/.env.example backend/.env                       # backend runtime env
cp deploy/.env.example deploy/.env                         # tunnel/deploy env
cp deploy/.env.production.example deploy/.env.production   # frontend build env
```

All four copies are gitignored. They have distinct jobs:

| File | Read by | Holds |
|---|---|---|
| `.env` | Vite dev server | local backend URL, Supabase anon key |
| `backend/.env` | the backend container | Redis, Supabase, Stripe, Resend, providers |
| `deploy/.env` | `cf-tunnel.sh`, docker compose | Cloudflare token, tunnel name/host |
| `deploy/.env.production` | `vercel build` | the tunnel URL baked into the bundle |

`deploy/.env` is deploy-time only — the application never reads it.

## 2. Supabase

1. Create a project at https://supabase.com.
2. Apply the migrations in order via **SQL Editor**:
   - `supabase/migrations/0001_profiles.sql`
   - `supabase/migrations/0002_alerts.sql`
3. From **Settings → API**, copy:
   - **Project URL** → `SUPABASE_URL` (backend) and `VITE_SUPABASE_URL` (frontend)
   - **anon public key** → `VITE_SUPABASE_ANON_KEY` (frontend)
   - **service_role key** → `SUPABASE_SERVICE_KEY` (backend, secret)
4. Legacy HS256 projects also need **JWT Secret** → `SUPABASE_JWT_SECRET`.
   Projects using asymmetric keys are verified via JWKS automatically.

## 3. Upstash Redis

Redis holds the snapshot and the intraday bar history, so the dashboard keeps
showing data across a backend restart.

1. Create a database at https://upstash.com — region **us-east-1** keeps it
   close to US market data.
2. Copy the **TLS (`rediss://`) connection string** into `REDIS_URL` in
   `backend/.env`.

> With `REDIS_URL` empty the backend still boots, but every cache lookup misses
> and no bar history is retained. The dashboard will look perpetually
> "warming up". Set it before you rely on the data.

## 4. Tunnel env (`deploy/.env`)

```env
CF_API_TOKEN=...          # Account → Cloudflare Tunnel → Edit
CF_ACCOUNT_ID=...         # Zone → DNS → Edit  (on RELQS_CF_ZONE)
CF_TUNNEL_TOKEN=          # written by 'make tunnel-create' — don't hand-edit
RELQS_TUNNEL_ID=          # written by 'make tunnel-create' — don't hand-edit

RELQS_TUNNEL_NAME=relativeq-backend-tunnel
RELQS_API_HOST=edge-relativeq.facades.trade
RELQS_CF_ZONE=facades.trade
RELQS_ORIGIN_SERVICE=http://relativeq-backend:8000
```

The token needs **two** permissions on the account owning the zone:

- `Account → Cloudflare Tunnel → Edit` — create/inspect/delete the tunnel
- `Zone → DNS → Edit` on `RELQS_CF_ZONE` — create the CNAME

With only the first, `cf-tunnel.sh` still creates the tunnel and sets ingress,
then prints the CNAME for you to add by hand. See
[DNS by hand](#dns-by-hand) below.

`RELQS_ORIGIN_SERVICE` must match the backend container's network alias
(`relativeq-backend`) and its in-container port (`8000`), not the published
host port.

## 5. Create the tunnel

```bash
make tunnel-create
```

This creates (or adopts) the named tunnel, writes its ingress, creates the DNS
record, stores the connector token in `deploy/.env`, and points
`deploy/.env.production` at the tunnel hostname. It is safe to re-run — do so
after changing `RELQS_API_HOST` or `RELQS_ORIGIN_SERVICE`.

```bash
make tunnel-status    # tunnel state, ingress, DNS, connector, public health probe
make tunnel-delete    # destroy the tunnel and its DNS record (prompts)
```

### DNS by hand

If the token can't see the zone, `make tunnel-create` prints exactly what to
add. In **Cloudflare → your zone → DNS**:

| Type | Name | Target | Proxy |
|---|---|---|---|
| CNAME | `edge-relativeq` | `<RELQS_TUNNEL_ID>.cfargotunnel.com` | **Proxied** |

The record *must* be proxied (orange cloud) — a DNS-only record won't route
through the tunnel. Until it exists the hostname will not resolve and
`make tunnel-status` reports a non-200 health probe.

## 6. Backend env (`backend/.env`)

Required:

```env
DATA_PROVIDER=yahoo
REDIS_URL=rediss://default:...@...upstash.io:6379

SUPABASE_URL=https://YOUR-PROJECT-REF.supabase.co
SUPABASE_SERVICE_KEY=...

FRONTEND_URL=http://localhost:5173
CORS_ORIGINS=https://relativeqs.vercel.app
```

`CORS_ORIGINS` must list the deployed frontend's origin or the browser will be
blocked from calling the API. localhost dev origins are always allowed.

Optional: `STRIPE_*` (billing), `RESEND_API_KEY` / `ALERT_FROM_EMAIL` (alerts).
See `backend/.env.example` for the full annotated list, including poll cadence,
per-provider rate limits and the AI-capex basket.

## 7. Start the stack

```bash
make be-up      # builds and starts relativeq-backend + relqs-cloudflared
make be-logs    # tail the backend
```

Compose reads `--env-file deploy/.env` on every call so `CF_TUNNEL_TOKEN`
interpolates into the connector. Verify locally, then publicly:

```bash
curl http://127.0.0.1:8001/api/health              # published to loopback only
curl https://edge-relativeq.facades.trade/api/health
make tunnel-status
```

The backend port is bound to `127.0.0.1:8001` deliberately — the tunnel reaches
it over the compose network, so it never needs to listen on a public interface.

## 8. Frontend

Local development:

```env
# .env
VITE_RELQS_BACKEND_URL=http://localhost:8001
VITE_RELQS_WS_URL=ws://localhost:8001/ws/market
VITE_POLL_INTERVAL_MS=12000
VITE_SUPABASE_URL=https://YOUR-PROJECT-REF.supabase.co
VITE_SUPABASE_ANON_KEY=...
```

```bash
make fe-install
make fe-dev       # http://localhost:5173
```

Port 8001 is what compose publishes. Running uvicorn natively instead? Use 8000.

### Deploy to Vercel

`deploy/.env.production` holds the **tunnel** URL — `make tunnel-create` keeps
it in sync, so you shouldn't need to edit it by hand:

```env
VITE_RELQS_BACKEND_URL=https://edge-relativeq.facades.trade
VITE_RELQS_WS_URL=wss://edge-relativeq.facades.trade/ws/market
```

```bash
make deploy-fe
```

That copies `deploy/.env.production` to `./.env.production`, runs
`vercel build --prod` (Vite inlines the `VITE_*` values), then
`vercel deploy --prebuilt --prod`. Because the values are inlined at build
time, there is nothing to configure in the Vercel dashboard — but it also
means **changing the backend hostname requires a frontend rebuild**.

Only the **anon** Supabase key belongs here; it ships to the browser. Never the
`service_role` key.

`.vercelignore` hides `backend/`, `supabase/`, `deploy/` and friends so the CLI
doesn't detect the FastAPI app and try to make this a multi-service deploy.
`vercel.json` rewrites all paths to `/index.html` for client-side routing.

## 9. Day-to-day operations

```bash
make be-up        # (re)build and start the stack
make be-down      # stop it
make be-restart   # restart just the backend
make be-logs      # tail backend logs
make be-ps        # container status
make be-shell     # shell inside the backend

make tunnel-status   # is the tunnel healthy and does the hostname answer?
make tunnel-create   # re-apply ingress / DNS after a config change
make tunnel-delete   # tear the tunnel down

make deploy-fe    # rebuild + ship the frontend
make fe-test      # frontend tests
make clear-cache  # clear the Redis market-data cache (prompts)
make prune        # clean up this project's docker leftovers
make help         # list every target
```

A normal restart is `make be-down && make be-up`. The tunnel survives it —
the hostname and DNS live in Cloudflare, so nothing needs re-pointing and the
frontend needs no rebuild.

## 10. Legacy: the Fly backend

Fly used to host the backend, before the tunnel superseded it. The plumbing is
still present and usable: `deploy/fly.toml` (app name, region), `make deploy-be`,
`make secrets`, `make fly-*`. Everything reads the app name from `deploy/fly.toml`
(override for a one-off with `FLY_APP=... make deploy-be`).

If you ever run both, remember the singleton rule — `make fly-stop` before
`make be-up`, or `make takeover` to do both. `deploy_to_cloud.sh` will *not*
overwrite `deploy/.env.production` with the Fly URL while `RELQS_API_HOST` is
set in `deploy/.env`, so a stray backend deploy can't silently repoint the
frontend away from the tunnel.

## Troubleshooting

- **Hostname doesn't resolve** — the CNAME is missing. `make tunnel-status`
  shows the DNS section; add the proxied record from
  [DNS by hand](#dns-by-hand).
- **`502` / `1033` from the edge** — the tunnel is up but the connector can't
  reach the origin. Check `RELQS_ORIGIN_SERVICE` matches the backend's alias
  and in-container port (`http://relativeq-backend:8000`), and that
  `make be-ps` shows both containers Up.
- **Connector exits immediately** — `CF_TUNNEL_TOKEN` is empty in
  `deploy/.env`. Run `make tunnel-create`. (Compose deliberately uses `:-`
  rather than `:?` so a missing token doesn't break `down` / `logs` / `ps`.)
- **Connector can't hold a connection under WSL2** — QUIC over UDP degrades
  behind WSL2's NAT. Compose already forces `TUNNEL_TRANSPORT_PROTOCOL: http2`.
- **Dashboard perpetually "warming up"** — `REDIS_URL` is unset or wrong, so
  nothing persists between polls. It must be the `rediss://` Upstash string,
  **unquoted** — Compose's `env_file` passes values through literally (unlike
  a shell), so `REDIS_URL="rediss://..."` hands the app a literal leading `"`
  and `redis.from_url()` rejects it as schemeless. `redis://127.0.0.1` also
  fails: it points the container at itself.
- **Edited `backend/.env` or `deploy/.env` and nothing changed** —
  `make be-restart` / `docker compose restart` restarts the existing
  container's process; it does not re-read `env_file`. An edited value only
  takes effect after the container is recreated: `make be-up` (rebuilds too)
  or `docker compose --env-file deploy/.env -f backend/docker-compose.yml up -d`.
  Verify what a container actually has with
  `docker exec relativeq-backend printenv REDIS_URL`.
- **Bar history truncated or resetting** — two pollers on one Upstash database.
  Check for (and stop) a stray Fly machine with `make fly-stop`.
- **CORS error on the deployed site** — the Vercel origin isn't in
  `CORS_ORIGINS` in `backend/.env`. Add it and `make be-restart`.
- **Frontend still calls the old backend** — the URL is inlined at build time.
  Re-run `make deploy-fe` after changing the hostname.
- **`401 Invalid or expired session`** — `SUPABASE_URL` mismatch between
  frontend and backend, or the JWT signing scheme changed.
- **Stripe webhook signature failure** — forward to the published port:
  `stripe listen --forward-to http://localhost:8001/api/billing/webhook`.
  The `whsec_` rotates per CLI session.
