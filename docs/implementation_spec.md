# RelativeQs — Implementation Spec

How the RelativeQs engine is designed and built, what it exposes to other
tools, and what is planned. Written from the code on `cloud-deploy`
(2026-10-12). Where this spec and the code disagree, the code wins — fix the
spec.

> RelativeQs is Nasdaq-100 internals analytics and education — not investment
> advice. Everything below is descriptive or probabilistic context.

**Contents**

1. [Purpose and scope](#1-purpose-and-scope)
2. [Functional requirements](#2-functional-requirements)
3. [Architecture](#3-architecture)
4. [Engines](#4-engines)
5. [API reference](#5-api-reference)
6. [Access control](#6-access-control)
7. [Integrations](#7-integrations)
8. [Future features](#8-future-features)

---

## 1. Purpose and scope

RelativeQs answers one question for QQQ (the Nasdaq-100 ETF): *what is happening
underneath it right now, and how much should I trust the move?* It does that by
measuring, from live market data:

- which tracked ETFs **lead or lag** QQQ, and how persistently;
- how **broad** participation is across the ~100 constituents;
- where money appears to be **rotating** (inferred, not observed);
- how **dependent** QQQ has become on the AI build-out complex (daily, structural);
- what the **overnight tape and biggest pre-market movers** look like before the open.

**Design rules that shape the code**

- *Nothing fabricated.* Roles, weights and scores are measured from data. When
  history is too short the engine reports `warming_up`/`limited_history`, never a
  made-up number.
- *Descriptive metrics are walled off from the prediction.* The AI-dependency
  index and the pre-market board never feed the intraday score or projection.
- *Honest about what can't be seen.* Rotation is an inference from relative
  return and dollar-volume (real fund flows settle end-of-day), and says
  "unaccounted" when nothing in the universe explains a move.
- *Singleton poller.* One backend instance owns the Redis keys (see §3.3).

**Out of scope:** order execution, personalised advice, anything that needs
account data, a hosted multi-tenant backend (the backend runs on one local
machine behind a Cloudflare tunnel; see `DEPLOYMENT.md`).

---

## 2. Functional requirements

| ID | Requirement | Where it lives | Status |
|---|---|---|---|
| FR-1 | Poll market data every `POLL_INTERVAL_SECONDS` (default 30 s) and publish the freshest payloads to a cache | `backend/backend/main.py` `_poll_and_broadcast` | Implemented |
| FR-2 | Stream each cycle's `snapshot`, `qqq_score`, `prediction`, `rotation` to websocket clients | `backend/app/ws_manager.py`, `/ws/market` | Implemented |
| FR-3 | Measure lead/lag of every tracked ETF vs QQQ from 1-minute bars (cross-correlation, up to `LEAD_LAG_MAX_LAG` = 15 min), streak-confirmed, multi-timeframe, with a decoupling watch | `core/lead_lag.py` | Implemented |
| FR-4 | Composite intraday score + probability-up, and a short-horizon projection (default 15 min) | `core/intraday_score.py`, `core/projection.py` | Implemented |
| FR-5 | Confirmation gate: do enough non-leader names agree with the leader's direction | `core/confirmation.py` | Implemented |
| FR-6 | Driver attribution: which tracked engines are carrying QQQ's move | `core/attribution.py` | Implemented |
| FR-7 | Cross-day stability / tradeability verdict for the current leader | `core/stability.py` | Implemented |
| FR-8 | Leader hit-rate: when the leader moves, how often QQQ follows over 5/15/30 min | `core/hit_rate.py` | Implemented |
| FR-9 | Correlation regime: coupled vs fragmenting over a short trailing window | `core/correlation_regime.py` | Implemented |
| FR-10 | Nasdaq-100 breadth, equal-weight and cap-weight, with divergence | `core/breadth.py`, `services/holdings.py` | Implemented |
| FR-11 | Breadth-shift email alerts to Pro users (Resend) on a broad/mixed/narrow state flip | `app/alerts.py` | Implemented |
| FR-12 | Rotation flow: where money appears to move relative to QQQ over 15/30/60 min, plus a settled after-close daily backtest | `core/rotation.py`, `services/rotation_store.py` | Implemented |
| FR-13 | AI-capex dependency index (daily bars, theme-balanced composite, trend over all history) | `core/ai_dependency.py` | Implemented |
| FR-14 | Overnight / pre-market board: futures, Asia, Europe tape; top Nasdaq-100 movers with `vs_tape`, `crowd`, `sustain`; faint validated pre-open lean | `core/premarket.py` | Implemented |
| FR-15 | Long-horizon QQQ score from daily bars (`/qqq-score`) | `core/qqq_score.py` | Implemented |
| FR-16 | Accounts, sessions, Pro plan: Supabase Auth, Stripe checkout + webhook | `app/auth.py`, `app/billing.py` | Implemented |
| FR-17 | Pro CSV export of history, alert preferences | `app/api.py` | Implemented |
| FR-18 | Whole-backend access control (service token or Supabase JWT) | `app/auth.py` | Implemented 2026-10-12 |
| FR-19 | Tokens never appear in logs | `app/logging_config.py` | Implemented 2026-10-12 |
| FR-21 | Persist the overnight movers once a day at 09:28 ET (one row per mover) to `overnight_movers_stats` | `app/daily_capture.py` | Implemented 2026-10-13 — needs migration 0003 applied |
| FR-22 | Persist a daily highlights row at 10:05 ET (breadth, rotation, AI dependency last ~2 weeks, internal health, strongest sector, fragility) to `daily_highlights`, joined to the movers on `trade_date` | `app/daily_capture.py` | Implemented 2026-10-13 — needs migration 0003 applied |
| FR-20 | Per-caller inbound rate limiting | — | **Not implemented** (see §5.3, §8) |

Frontend (Vite/React SPA, `src/`): Landing, Login/Register, Pricing, About,
Contact, `/dashboard` and `/account` (login-gated), `/billing/success`.

---

## 3. Architecture

### 3.1 Topology

```
 browser ──▶ <frontend>.vercel.app  (static SPA)
                  │  HTTPS + WSS, Supabase bearer
                  ▼
        https://<api-host>   (Cloudflare edge, named tunnel)
                  │
        relqs-cloudflared  ──▶  relativeq-backend (FastAPI + poll loop)
                                   │  127.0.0.1:8001 -> 8000 (debug only)
                                   ├──▶ Upstash Redis   (latest payloads, bar history)
                                   ├──▶ Yahoo Finance   (market data; other providers pluggable)
                                   ├──▶ Supabase        (JWT verify, profiles/plan)
                                   └──▶ Stripe / Resend (optional)
```

Deployment details, tunnel creation and the singleton rule are in
`DEPLOYMENT.md`; day-two operations are in `docs/operating_manual.md` §15.

### 3.2 The poll loop

`_poll_and_broadcast` runs forever inside the backend process. Each cycle it:

1. fetches a fresh **snapshot** (`signals`, `flow_series`),
2. computes the **QQQ score** and overrides its price with the freshest
   intraday price,
3. runs the **prediction** pipeline over the accumulated 1-minute bars
   (lead/lag → score → projection → confirmation → attribution → stability →
   hit-rate → correlation regime → breadth → AI dependency),
4. computes **rotation** (live session),
5. kicks off a de-duplicated background **pre-market board** refresh,
6. writes the four payloads to Redis and **broadcasts** them to websocket clients,
7. after 16:00 ET on weekdays, settles that day's **rotation backtest** once,
8. checks for a **breadth-shift alert**.

One failed cycle is logged and skipped; it does not stop the loop.

### 3.3 State and caching

| Store | Holds | Lifetime |
|---|---|---|
| Redis `snapshot:latest`, `qqq_score:latest`, `prediction:latest`, `rotation:latest` | Latest payload per endpoint | TTL = `max(3 × POLL_INTERVAL, 60 s)` (90 s by default) |
| Redis `bars:<date>` (`IntradayHistoryStore`) | The day's accumulated 1-minute bars | Grows through the session; **cannot be re-derived afterwards** |
| In-process pre-market cache | Overnight board | `PREMARKET_REFRESH_SECONDS` (900 s) |
| In-process AI-dependency cache | Daily-bar index | `AI_DEPENDENCY_REFRESH_SECONDS` (3600 s) |
| SQLite `rotation.db` | One settled rotation backtest per date | Persistent |
| Supabase `overnight_movers_stats`, `daily_highlights` (view `daily_picture`) | The morning's movers and the day's key takeaways, keyed by `trade_date` (§3.5) | Permanent history |

**Singleton rule:** two backends writing the same Upstash database clobber
`bars:<date>`. Run exactly one.

API handlers read the Redis cache; only on a **cache miss** do they compute on
demand (slow — 20–30 s cold after a restart for `/snapshot` and `/premarket`).

### 3.4 Data providers

Selected by `DATA_PROVIDER` (`mock`, `yahoo`, `alphavantage`, `twelvedata`,
`polygon`, `alpaca`; `finnhub` has an adapter). Yahoo (via `yfinance`) is what
production uses; the others are adapters under `services/adapters/` guarded by a
sliding-window outbound limiter (`services/rate_limiter.py`, per-provider calls
per 60 s: Twelve Data 8, Alpha Vantage 5, Polygon 5, Finnhub 30, Alpaca 5).
Extended-hours bars are fetched outside the regular session
(`FETCH_PRE_POST_MARKET`).

Default tracked universe (`ETF_UNIVERSE`): `QQQ, XLK, SMH, MAGS, IGV, XLY, XLF,
XLI, IWM, XLE, XLP, TLT`. Constituents come from a committed snapshot
(`app/data/qqq_holdings.json`), refreshed with
`dev-utils/refresh-qqq-holdings.py` when the index reconstitutes.

### 3.5 Daily persistence

Two captures run inside the poll loop (`DailyCapture.tick`, once per cycle),
weekdays only, in US/Eastern time. Tables live in Supabase Postgres
(`supabase/migrations/0003_daily_picture.sql`, applied by hand in the SQL
editor like the earlier migrations) and are written with the service-role key.
Nothing is stored on the container, which has no volumes.

| | `overnight_movers_stats` | `daily_highlights` |
|---|---|---|
| When | **09:28 ET** (before the 09:30 open; window closes 09:43) | **10:05 ET** (window closes 10:35) |
| Grain | one row per mover — key `(trade_date, symbol)` | one row per day — key `trade_date` |
| Source | a forced-fresh `fetch_premarket_board` | the prediction, rotation and QQQ-score payloads the loop already holds |
| Holds | `rank`, `gap`, `since_open`, `dir`, `sector`, `weight`, `vs_tape`, `crowd`, `sustain`, plus the board context on every row (`board_phase`, open lean, tape NQ/ES/Asia/Europe, breadth up) and `captured_at` | direction + `probability_up`, `verdict`, internal **health** score/regime, **fragility** value/level, confirmation state, correlation regime, leader, **strongest sector** (30 m momentum), **breadth** (state, equal/cap %, divergence, advancers/decliners), **AI-capex dependency** now/change and the last ~10 trading days as `ai_dependency_2w`, **rotation** per window (regime, summary, top 3 rows), and a `detail` JSON for the rest |

The join key is **`trade_date`**, the Eastern calendar date. The view
`daily_picture` returns each highlights row with that morning's movers attached
as a JSON list (`overnight_movers`), so "what was the picture on 2026-10-13" is
`select * from daily_picture where trade_date = '2026-10-13'`. A day with no
movers still has its highlights row.

Behaviour worth knowing:

- Health, fragility level and strongest sector use the same formulas as the
  dashboard (`deriveQQQHealth`, the fragility thresholds 0.25 / 0.5, top 30 m
  momentum excluding QQQ), computed server-side so history matches what users saw.
- **Idempotent:** both writes are upserts on the primary key, so a restart inside
  the window rewrites the same rows. `captured_at` shows when the read really
  happened.
- **Retries:** a failed write is retried every 60 s until the window closes, then
  logged as an error and abandoned for the day.
- **Holidays / stale data:** the movers capture is skipped if the board's `asof`
  date is not today; the highlights capture waits for a ready prediction, which a
  market holiday never produces. No weekday calendar is hard-coded.
- **Warming up:** if the engines aren't ready, columns are `null` (and
  `direction = 'warming up'`) — never filled with made-up numbers.
- Configuration: `DAILY_CAPTURE_ENABLED`, `OVERNIGHT_CAPTURE_TIME`,
  `HIGHLIGHTS_CAPTURE_TIME` (see `backend/.env.example`). Needs `SUPABASE_URL` and
  `SUPABASE_SERVICE_KEY`; without them the captures are disabled with one warning.
- RLS is on with no policies: only the backend (service role) can read or write.
  Add a read policy before letting the dashboard query history.

---

## 4. Engines

All live under `backend/app/core/`. They are pure compute over DataFrames of
bars — no I/O — which is why the backend suite (150 tests) runs offline against
synthetic sessions.

| Engine | Input | Output (key fields) |
|---|---|---|
| `LeadLagEngine` | 1 m bars, all universe symbols | per-symbol role (leader / confirmer / diverging / weak), lag minutes, correlation; `status` (`ok`/`warming_up`); streak + multi-timeframe views; decoupling flag |
| `IntradayScoreEngine` | bars + lead/lag | `score`, `probability_up`, `verdict` (`continue` / `stall` / `fragile` / `warming_up`) |
| `ProjectionEngine` | bars + lead/lag + score | `horizon_minutes`, `expected_return`, `projected_price`, `band_low` / `band_high`, `confidence`, `direction`, `basis` |
| `ConfirmationGate` | bars + lead/lag | `state` (`confirmed` / `unconfirmed` / `fragile`), participating count, message |
| `DriverAttributionEngine` | bars | contributors with share and trend, headline |
| `StabilityEngine` | stored session frames | persistence of the leader across days, `verdict` (e.g. `tradeable` / `unstable`) and a `tradeable` flag |
| `HitRateEngine` | bars + current leader | hit rate and sample size per horizon |
| `CorrelationRegimeEngine` | bars | `regime` (`coupled` / `transitional` / `fragmented`), dispersion |
| `breadth` | per-stock open + last price | `equal_weight_pct`, `cap_weight_pct`, divergence, `state` (`broad` / `mixed` / `narrow`) |
| `rotation` | 1 m bars (and daily for backtest) | direction (`qqq_out` / `qqq_in` / `broad` / `flat`), `into` / `from`, `unaccounted`, text; windows 15/30/60 |
| `ai_dependency` | daily bars | `dependency_now`, `change`, per-theme correlation, history, headline |
| `PremarketBoard` | pre-market quotes, tape, constituents | `tape`, `open_lean`, `movers[]`, `phase` |
| `QQQScoreEngine` | daily bars | `direction`, `probability`, `fragility`, momentum groups |
| `ScoreEngine` | caller-supplied signals | weighted `raw_score`, `probability`, `fragility` (`POST /api/score`) |

Engines return a `status` rather than raising when data is thin. Consumers must
check it (§7.3).

---

## 5. API reference

Base URL: `https://<api-host>` (production, via the tunnel) or
`http://127.0.0.1:8001` (the host machine only). All paths are under `/api`
unless noted. Responses are JSON.

### 5.1 Endpoints

| Method + path | Returns | Source / freshness | Access |
|---|---|---|---|
| `GET /api/health` | `{"status":"ok"}` | live | **Open** |
| `GET /api/snapshot` | `timestamp`, `signals{}`, `flow_series[]` | Redis, ≤ one poll old | Token |
| `GET /api/qqq-score?interval=1d&period=2y` | long-horizon score: `direction`, `probability`, `fragility`, momentum groups, `lead_lag`, `recent_qqq` | Redis for the default params; computed on demand otherwise | Token |
| `GET /api/prediction` | full intraday payload: `status`, `bars_used`, `universe`, `target`, `lead_lag`, `lead_lag_tf`, `score`, `projection`, `attribution`, `confirmation`, `correlation_regime`, `stability`, `hit_rate`, `breadth`, `ai_dependency` | Redis, ≤ one poll old | Token |
| `GET /api/rotation` | rotation flow payload (`session`, `windows`, `asof`, per-window verdicts) | Redis, ≤ one poll old | Token |
| `GET /api/rotation/history?limit=30` | `{"history":[…]}` settled daily backtests | SQLite | Token |
| `GET /api/premarket` | `status`, `asof`, `phase`, `minutes_to_open`, `tape{nq,es,asia,europe,breadth_up,cap_breadth_up}`, `open_lean{dir,hist_hit,basis}`, `movers[]` | in-process cache, ≤ 15 min | Token |
| `GET /api/ai-dependency` | `status`, `dependency_now`, `change`, `change_lookback_days`, `themes[]`, `headline`, history | cached prediction or daily cache | Token |
| `POST /api/score` | body `{"signals":{…}}` → `raw_score`, `probability`, `fragility` | computed per call | Token |
| `GET /api/auth/me` | the verified user | — | Supabase JWT |
| `GET /api/export/history.csv` | CSV of history | computed | Supabase JWT + Pro |
| `GET/POST /api/alerts/preferences`, `POST /api/alerts/test` | alert settings | Supabase | Supabase JWT + Pro |
| `POST /api/billing/create-checkout-session`, `/billing/portal` | Stripe URLs | Stripe | Supabase JWT |
| `POST /api/billing/webhook` | — | Stripe | Stripe signature only |
| `WS /ws/market?token=<token>` | stream of `{type, payload}` where `type` ∈ `snapshot`, `qqq_score`, `prediction`, `rotation` | pushed each poll | Token |

`movers[]` item (premarket): `symbol`, `gap` (signed fraction, `-0.06` = −6%),
`since_open`, `dir` (`up`/`down`), `sector`, `weight`, `vs_tape`
(`with_tape`/`counter_tape`), `crowd` (`sector_wide`/`lone`/`mixed`, or
`with_market`/`against_market`/`mixed` when the sector is unknown), `sustain`
(`holding`/`fading`).

Unauthenticated calls get `401`; a websocket without a valid token is closed
with code `1008` (HTTP `403` on upgrade).

### 5.2 Payload stability

Payloads are consumed by the dashboard and by sibling tools, and are additive by
convention: new fields may appear, existing fields are not repurposed. Treat
unknown fields as ignorable and every field as possibly `null`.

### 5.3 Rate limits (read this before integrating)

**There is no inbound rate limiting today** (FR-20). The only limiter in the
code (`SimpleRateLimiter`) throttles *outbound* calls to market-data providers.
What actually bounds a caller is data freshness and the single-machine origin:

| Endpoint | Data changes | Poll no faster than |
|---|---|---|
| `/snapshot`, `/prediction`, `/rotation`, `/qqq-score` | every poll (30 s) | **1 per 30 s** each |
| `/premarket` | every 15 min | **1 per 15 min**; one call shortly before the open is typical |
| `/ai-dependency` | hourly (daily-bar metric) | **1 per hour** |
| `/rotation/history` | once per day after the close | **1 per day** |
| `/ws/market` | pushed every poll | one connection, no polling |

Guidance for integrators:

- Prefer the **websocket** for continuous consumption; one connection receives
  every cycle. Reconnect with a delay (≥ 1 s, with backoff), not in a tight loop.
- Do not call `POST /score` in a loop; it computes per call.
- After a backend restart, the first `/snapshot` or `/premarket` can take
  20–30 s (cold cache). Use a timeout of ≥ 60 s for the first call and retry
  on failure rather than hammering.
- Cloudflare sits in front of the tunnel, but the origin is one local container;
  a burst can starve the poll loop. Expect the operator to block abusive callers
  by revoking their token (§6) until a real limiter exists.

---

## 6. Access control

Every `/api` route except `/api/health` and the Stripe webhook, and the
websocket, require **one of**:

1. **A Supabase session token** (`Authorization: Bearer <JWT>`) — what the SPA
   sends after login. Verified as HS256 (`SUPABASE_JWT_SECRET`) or ES256/RS256
   (project JWKS). Any logged-in user passes the gate.
2. **The service token** `RELQ_API_TOKEN` — a static shared secret for
   server-to-server callers. Compared in constant time. Unset means service
   access is disabled (JWT only).

Pro-only routes (`export/history.csv`, `alerts/*`) additionally check the user's
`plan` in the Supabase `profiles` table. The prediction payload itself is served
in full to any authenticated caller; the dashboard hides Pro panels in the UI,
not on the server (see §8 item F-9).

Websocket: browsers cannot set headers on a WebSocket, so the token travels as
`?token=`. The backend redacts `token=` from its own logs
(`RedactTokenFilter`); callers must not log the URL themselves.

Rules for the service token: it lives only in `backend/.env` and in the calling
tool's server-side secret store. **Never** put it in a `VITE_*` variable or any
browser-delivered code. Rotate it by editing `backend/.env` and running
`make be-up` (the container must be recreated to re-read `env_file`).

---

## 7. Integrations

### 7.1 Today: EdgeLane / Simmer

EdgeLane is the sibling repo (`../EdgeLane`, Simmer options tool). It is the
only external consumer of RelativeQs.

| | |
|---|---|
| Data it reads | `GET /api/premarket` → `movers[]`: `symbol`, `gap`, `dir`, `sector`, `crowd`, `vs_tape`, `sustain` |
| Why | Import the overnight's biggest Nasdaq-100 movers into each opted-in user's watchlist before the open, then decide *sell this credit side / wait / skip* per name. EdgeLane reuses RelativeQs's `crowd` tag as its peer-confirmation signal instead of recomputing peers. |
| Schedule | One fetch at **09:25 ET** on trading days (fixed in EdgeLane's code) |
| Client | `EdgeLane/market/backend/app/simmer_relativeqs.py` — 10 s timeout, ≤ 100 movers, symbols must match `^[A-Z]{1,6}$`, finite `gap`, 1 MB body cap; any failure logs and returns an empty list (no import that session) |
| Config | Base URL in EdgeLane's `app_config` row `relativeqs_api_base`; optional bearer; kill-switch `relativeqs_overnight_enabled` |
| Contract doc | `EdgeLane/docs/simmer.md` → "Overnight movers — RelativeQs import + premium-decision analyzer" |
| Status | **Planned on the EdgeLane side** (brief approved 2026-10-11, not built when this was written) |

What RelativeQs has done for it: `/api/premarket` is now token-gated
(2026-10-12). **Action needed on the EdgeLane side:** its docs still describe
the endpoint as unauthenticated and its bearer as "optional". It must now send
`Authorization: Bearer <RELQ_API_TOKEN>`, and the same value must be in
RelativeQs's `backend/.env`. Without it EdgeLane receives `401` and imports
nothing (it fails safe).

Fit with the rate limits in §5.3: one call at 09:25 ET is well inside the
15-minute cache; the board is warm by then because the poll loop pre-warms it.

### 7.2 How another tool integrates

1. **Get access.** Ask the RelativeQs operator for the service token (or, for an
   end-user-facing tool, use the user's own Supabase session token). Store it
   server-side only.
2. **Pick the endpoint for the data you need:**

   | You want | Use | Cadence |
   |---|---|---|
   | Is QQQ's move trustworthy, and who's leading it | `/api/prediction` (`lead_lag`, `score`, `projection`, `confirmation`) | ≤ 1/30 s, or websocket |
   | How broad the participation is | `/api/prediction` → `breadth` | same |
   | Where money is rotating | `/api/rotation` | ≤ 1/30 s |
   | Pre-open movers and overnight tape | `/api/premarket` | ≤ 1/15 min |
   | AI-capex dependency (structural) | `/api/ai-dependency` | ≤ 1/hour |
   | Long-horizon QQQ posture | `/api/qqq-score` | ≤ 1/30 s |
   | Live stream of all of the above | `WS /ws/market?token=…` | persistent |

3. **Send** `Authorization: Bearer <token>` on HTTP calls, `?token=` on the
   websocket.
4. **Call from a server**, not a browser (CORS only allows the configured
   origins in `CORS_ORIGINS`).
5. **Respect §5.3**, set a ≥ 60 s timeout for the first call after a restart, and
   fail safe (skip the cycle) on `401`, `5xx` or timeout.

### 7.3 Consumer checklist

- Check `status` before trusting a payload; `warming_up` and
  `limited_history` mean "not enough data yet", not "flat".
- Treat every numeric field as nullable; guard against `NaN`/non-finite values
  and cap list lengths (EdgeLane's client is a good reference).
- Validate symbols and ranges yourself — do not assume the board is clean.
- The pre-market `open_lean` is a faint, labelled lean (~60% historically), not
  a call; do not present it as a signal to trade.
- Everything here is descriptive context. Do not wire it straight to order
  placement.

---

## 8. Future features

Convention: every item has an ID, a source (this repo, or the other repo/tool
that asked for it, with a reference), and a status. **When an item ships it is
struck through with `~~…~~` and the done date is added in the Status column.**
New asks from other tools go in the "Requested by other tools" table with a
link back to their request.

### 8.1 From this repo

| ID | Feature | Source / reference | Status |
|---|---|---|---|
| F-1 | ~~Run the backend locally against the shared Upstash, behind a Cloudflare named tunnel; retire Fly~~ | This repo — `DEPLOYMENT.md` | Done 2026-09-02 (tunnel hardening 2026-09-03) |
| F-2 | ~~Overnight / pre-market board~~ | This repo — commit `2856910`, `docs/operating_manual.md` §1a | Done 2026-06-13 |
| F-3 | ~~Drop the backend's host bind mount (fixes `docker restart` on WSL2)~~ | This repo — commit `1fffb51` | Done 2026-09-05 (on `cloud-deploy` 2026-10-12) |
| F-4 | ~~Authentication for the backend~~ (token gate: `RELQ_API_TOKEN` or Supabase JWT) | `backend/README.md` ("Add authentication and rate-limiting for production") | Done 2026-10-12 |
| F-5 | ~~Keep websocket tokens out of logs~~ | Security review, 2026-10-12 | Done 2026-10-12 |
| F-16 | ~~Persist the 09:28 ET overnight movers and a 10:05 ET daily highlights row to Supabase, joined on `trade_date`~~ | Owner request, 2026-10-13 — §3.5, `supabase/migrations/0003_daily_picture.sql` | Done 2026-10-13 (apply migration 0003, then `make be-up`) |
| F-6 | **Inbound rate limiting** per token / per IP (the other half of the `backend/README.md` item) | `backend/README.md`; needed by §5.3 | Open |
| F-7 | **Per-caller service tokens** (one per tool, individually revocable) instead of one shared `RELQ_API_TOKEN` | This spec §6 | Open — proposed |
| F-8 | **Fix the `/rotation` fetch path.** The frontend calls `${BACKEND_URL}/rotation`; the route is `/api/rotation`, so the rotation panel gets 404 | `src/services/marketApi.ts` (`fetchRotation`) | Open — bug |
| F-9 | **Server-side Pro filtering** of `/api/prediction` (today Pro panels are hidden in the UI only) | This spec §6 | Open — needs a product decision |
| F-10 | **Public teaser decision.** With the whole backend gated, the Landing page's AI-dependency teaser is blank for logged-out visitors. Either exempt `/api/ai-dependency` or serve a static/cached copy | `src/pages/Landing.tsx`, `main.py` router gate | Open — needs a product decision |
| F-11 | **Redeploy the frontend with the correct tunnel host.** `deploy/.env.production` had a stale hostname, so the deployed site cannot reach the backend until `make deploy-fe` is rerun from the corrected file | `DEPLOYMENT.md`, `deploy/.env.production` | Open — operational |
| F-12 | **Retire the remaining Fly tooling** (`deploy_to_cloud.sh` backend path, `fly-*` Make targets, `deploy/fly.toml`, `DEPLOYMENT.md` §10) | `Makefile`, `deploy_to_cloud.sh` | Open — proposed |
| F-13 | **Scrub old history.** Early commits still contain real hostnames, a personal email address and session links; removing them needs a history rewrite + force-push, which requires the owner's explicit approval | Security review, 2026-10-12 | Open — needs approval |
| F-17 | **Read access to history**: a read-only API endpoint and/or RLS policy so the dashboard (or sibling tools) can query `daily_picture` | Follow-on to F-16 | Open — proposed |
| F-18 | **Persist the SQLite rotation backtest in Supabase too** — `rotation.db` lives inside the container (no volume), so it is lost on every rebuild | `services/rotation_store.py`; observed 2026-10-13 | Open — proposed |
| F-14 | **Real social handles** in the footer | `src/components/Footer.tsx:5` (TODO) | Open |
| F-15 | **Make `/api/premarket` and other cached endpoints cold-start faster** (20–30 s after a restart) — e.g. warm the caches before accepting traffic | Observed 2026-10-12 | Open — proposed |

### 8.2 Requested by other tools / repos

| ID | Feature | Requested by | Reference | Status |
|---|---|---|---|---|
| X-1 | ~~Lock down `GET /api/premarket` with a token or allow-listed service caller before EdgeLane uses it in production~~ | EdgeLane / Simmer | `EdgeLane/docs/simmer.md` → "Overnight movers — RelativeQs import…" (RelativeQs-repo checklist) | Done 2026-10-12 (whole backend gated; see F-4) |
| X-2 | **EdgeLane to send the bearer** (`RELQ_API_TOKEN`) and update its docs, which still say the endpoint is open | EdgeLane / Simmer | same section; client `simmer_relativeqs.py` | Open — EdgeLane side |
| X-3 | **Overnight movers import** (09:25 ET fetch, per-user watchlist import, premium-decision analyzer) | EdgeLane / Simmer | `EdgeLane/docs/simmer.md`; brief approved 2026-10-11 | Planned — EdgeLane side; RelativeQs only serves the data |

*Adding a request:* append a row with the next `X-n`, name the tool, link its
doc or issue, and say what RelativeQs must provide. Strike it through and add the
date when it ships.

### 8.3 Maintenance of this spec

- Update §2 (requirements) and §5 (endpoints) in the same change that alters
  them.
- Keep real hostnames, tokens and keys out of this file — use `<api-host>`,
  `<frontend>`, and describe secrets by variable name only.
