# Price Flow Tracker

A full-stack **market-regime analytics dashboard** for the Nasdaq-100. It
watches the sector ETFs behind QQQ and distils them into one clear read — the
market's **trend regime** (risk-on / risk-off), plus the sector leadership,
breadth, and fragility behind it.

It is a complete SaaS application: authentication, a freemium subscription
model, feature gating, email alerts, and a backtesting suite.

> **Not investment advice.** Price Flow Tracker is a market-internals
> analytics and education tool. Past performance does not guarantee future
> results.

---

## Contents

- [Overview](#overview)
- [Features](#features)
- [Architecture](#architecture)
- [Tech stack](#tech-stack)
- [Project structure](#project-structure)
- [Getting started](#getting-started)
- [Environment variables](#environment-variables)
- [Backtesting suite](#backtesting-suite)
- [API reference](#api-reference)
- [Notes & limitations](#notes--limitations)

---

## Overview

Looking at QQQ's price alone tells you little about whether a move is healthy.
The answer lives in the *internals*: which sectors lead, whether breadth
confirms, and where price sits relative to its long-term trend.

The core signal is a **200-day trend regime** — whether QQQ is trading above
or below its 200-day simple moving average. The dashboard surrounds that with
sector relative-strength, rolling correlations, a fragility meter, and an
ETF-level signal scan.

The app runs a **freemium** model:

| Plan | What you get |
| --- | --- |
| **Free** | Live trend-regime banner, health KPIs |
| **Pro** | Sector analytics, ETF signal grid, CSV export, regime-change email alerts |

---

## Features

- **Trend-regime engine** — risk-on / risk-off based on QQQ vs its 200-day SMA.
- **Sector analytics** — relative strength, divergence, rolling correlations,
  lead/lag detection across XLK, SMH, XLY, XLF, XLI, XLE, IWM.
- **Real-time updates** — a backend poll loop broadcasts snapshots over a
  WebSocket; the frontend also polls as a fallback.
- **Authentication** — email/password accounts via Supabase Auth (password
  reset and email verification included).
- **Subscriptions** — Stripe Checkout, a customer billing portal, and a
  signature-verified webhook that drives plan changes.
- **Feature gating** — Pro-only endpoints (`require_pro`) and a frontend
  `ProGate` that blurs locked sections.
- **Regime-change alerts** — when the regime flips, Pro subscribers are
  emailed via Resend.
- **CSV export** — Pro users can download recent history.
- **Backtesting suite** — replay the signal engine over historical data and
  measure whether it had any edge (see [Backtesting suite](#backtesting-suite)).

---

## Architecture

```
                ┌──────────────────┐
                │  React frontend  │  Vite · Tailwind · Zustand
                │  (this repo /src)│
                └────────┬─────────┘
            REST + WS    │      Supabase Auth (browser SDK)
                         ▼
                ┌──────────────────┐        ┌──────────────┐
                │  FastAPI backend │───────▶│   Supabase   │  Postgres + Auth
                │  (backend/)      │        └──────────────┘
                │                  │        ┌──────────────┐
                │  • poll loop     │───────▶│    Stripe    │  subscriptions
                │  • REST + WS     │        └──────────────┘
                │  • JWT verify    │        ┌──────────────┐
                │  • alerts        │───────▶│    Resend    │  alert emails
                └────────┬─────────┘        └──────────────┘
                         │
                         ▼
                 Market data (Yahoo Finance via yfinance;
                 optional keyed providers)
```

- Signup/login happen **directly between the browser and Supabase**. The
  backend only *verifies* the resulting JWT (ES256 via JWKS, or legacy HS256).
- The Stripe **webhook** is the single source of truth for a user's plan — it
  writes `profiles.plan` using the Supabase service-role key.

---

## Tech stack

**Frontend** — React 18, TypeScript, Vite, Tailwind CSS, Recharts, Zustand,
React Router, `@supabase/supabase-js`.

**Backend** — FastAPI, Python 3.14, pandas / numpy / scipy, aiohttp, PyJWT +
cryptography, the Stripe SDK.

**Services** — Supabase (Postgres + Auth), Stripe (billing), Resend (email).

**Market data** — Yahoo Finance via `yfinance` by default; adapters also exist
for TwelveData, Polygon, Finnhub, Alpaca, and AlphaVantage.

---

## Project structure

```
price-flow-tracker/
├── src/                       # React frontend
│   ├── components/            # Layout, ProtectedRoute, ProGate, AlertToggle
│   ├── pages/                 # Landing, Login, Register, Dashboard, Account,
│   │                          #   Pricing, About, Contact, BillingSuccess
│   ├── services/              # marketApi, backendClient, billing, supabase
│   ├── store/                 # useAuthStore, useMarketStore (Zustand)
│   ├── config.ts              # reads VITE_* env vars
│   └── App.tsx
├── backend/
│   ├── app/
│   │   ├── api.py             # REST routes
│   │   ├── billing.py         # Stripe checkout / portal / webhook
│   │   ├── auth.py            # Supabase JWT verification + require_pro
│   │   ├── alerts.py          # regime-change email alerts (Resend)
│   │   ├── supabase_admin.py  # service-role writes to Supabase
│   │   ├── config.py          # settings loaded from .env
│   │   ├── core/              # qqq_score (trend engine), score_engine
│   │   └── services/          # market_data, adapters/, cache, rate_limiter
│   ├── backend/main.py        # FastAPI app, WebSocket, background poll loop
│   ├── backtest.py            # signal backtest harness
│   ├── trend_experiment.py    # 200-SMA trend-filter experiment
│   ├── letf_backtest.py       # leveraged-ETF drawdown backtest
│   └── requirements.txt
├── supabase/migrations/       # SQL migrations (apply via Supabase SQL Editor)
├── .env                       # frontend (Vite) env — VITE_* vars
└── package.json
```

---

## Getting started

### Prerequisites

- **Node.js 18+** and **Python 3.13+**
- A free **Supabase** project (for auth + database)
- Optional for billing: a **Stripe** account + the Stripe CLI
- Optional for alerts: a **Resend** account

### 1. Backend

```bash
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1        # Windows PowerShell
pip install -r requirements.txt

cp .env.example .env                # then fill in the values
uvicorn backend.main:app --reload --port 8000
```

API docs: <http://localhost:8000/docs>

### 2. Frontend

```bash
npm install
cp .env.example .env                # then fill in the values
npm run dev                         # http://localhost:5173
```

`npm run build` produces a production bundle; `npm run preview` serves it on
port 4173.

### 3. Supabase (database)

Apply the SQL migrations in order — Supabase dashboard → **SQL Editor** →
paste each file → **Run**:

1. `supabase/migrations/0001_profiles.sql` — the `profiles` table, signup
   trigger, and row-level security.
2. `supabase/migrations/0002_alerts.sql` — the `alerts_enabled` column.

### 4. Stripe (optional — for subscriptions)

1. Create a **Product** with a recurring **Price**; copy the price ID.
2. Copy your **secret key** into `STRIPE_SECRET_KEY`.
3. For local webhooks, run the Stripe CLI and copy the printed `whsec_…`:
   ```bash
   stripe listen --forward-to localhost:8000/api/billing/webhook
   ```

---

## Environment variables

Two `.env` files — the backend and the frontend are separate processes. See
`backend/.env.example` and `.env.example` for the full annotated lists.

**`backend/.env`** (key entries)

| Variable | Purpose |
| --- | --- |
| `DATA_PROVIDER` | `yahoo` (recommended), `mock`, or a keyed provider |
| `SUPABASE_URL` / `SUPABASE_JWT_SECRET` / `SUPABASE_SERVICE_KEY` | Supabase auth + admin writes |
| `STRIPE_SECRET_KEY` / `STRIPE_WEBHOOK_SECRET` / `STRIPE_PRICE_ID` | billing |
| `RESEND_API_KEY` / `ALERT_FROM_EMAIL` | alert emails |
| `POLL_INTERVAL_SECONDS` / `CACHE_TTL_SECONDS` | refresh rates |
| `FRONTEND_URL` | base URL for Stripe redirects |

**`.env`** (frontend / Vite)

| Variable | Purpose |
| --- | --- |
| `VITE_BACKEND_URL` | backend HTTP base URL |
| `VITE_SUPABASE_URL` / `VITE_SUPABASE_ANON_KEY` | Supabase client |
| `VITE_POLL_INTERVAL_MS` | dashboard refresh rate |

> Vite inlines `VITE_*` variables at build time — restart the dev server or
> rebuild after changing them.

---

## Backtesting suite

The `backend/` directory ships three research scripts. They replay the *real*
signal logic over historical data with no lookahead — run them to check
whether a signal actually had predictive value before relying on it.

```bash
cd backend
python backtest.py --years 12          # replay the QQQ signal engine
python trend_experiment.py             # 200-SMA trend filter vs buy & hold
python letf_backtest.py --etf TQQQ     # leveraged-ETF drawdown analysis
```

Each prints a report covering correlation with forward returns, quintile
analysis, hit rates, and a strategy comparison (Sharpe, max drawdown). The
backtest design — measuring edge before shipping a signal — is a core part of
the project.

---

## API reference

All routes are prefixed with `/api`.

| Method | Route | Auth | Description |
| --- | --- | --- | --- |
| `GET` | `/health` | — | health check |
| `GET` | `/snapshot` | — | latest market snapshot |
| `GET` | `/qqq-score` | — | QQQ trend-regime score |
| `GET` | `/auth/me` | user | verify token, return the user |
| `GET` | `/export/history.csv` | Pro | CSV export of recent history |
| `GET`/`POST` | `/alerts/preferences` | Pro | read / set alert preference |
| `POST` | `/alerts/test` | Pro | send a test alert email |
| `POST` | `/billing/create-checkout-session` | user | start Stripe Checkout |
| `POST` | `/billing/portal` | user | open the Stripe billing portal |
| `POST` | `/billing/webhook` | Stripe sig | subscription lifecycle events |
| `WS` | `/ws/market` | — | live snapshot stream |

---

## Notes & limitations

- **Not investment advice.** This is an analytics and education tool. The
  trend-regime signal is based on a 200-day moving average — a well-known,
  public method, not proprietary alpha.
- **Market-data licensing.** `yfinance` pulls from Yahoo Finance, which is
  fine for personal and research use. **Commercial use requires a properly
  licensed market-data feed** — budget for a paid provider before charging
  users.
- **Production hardening.** For a real deployment you would still want
  login rate-limiting, HTTPS, a publicly hosted Stripe webhook endpoint, and
  monitoring.
