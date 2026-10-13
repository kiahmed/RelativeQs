-- ============================================================================
-- Migration 0003 — daily picture: overnight movers + daily highlights
-- ----------------------------------------------------------------------------
-- Two tables the backend fills once a trading day, joined on `trade_date`
-- (the US/Eastern calendar date of the session):
--
--   overnight_movers_stats  one row PER MOVER, captured ~09:28 ET (pre-open)
--   daily_highlights        one row PER DAY, captured ~10:05 ET
--   daily_picture (view)    highlights + that day's movers, joined on trade_date
--
-- Written only by the backend with the service_role key (it bypasses RLS).
-- RLS is enabled with NO policies, so the anon / authenticated keys can read
-- nothing; add a select policy later if the dashboard should show history.
--
-- HOW TO APPLY:
--   Supabase dashboard -> SQL Editor -> New query -> paste this file -> Run.
--   Idempotent: safe to run more than once.
-- ============================================================================

-- ---------------------------------------------------------------------------
-- overnight_movers_stats
-- ---------------------------------------------------------------------------
create table if not exists public.overnight_movers_stats (
    trade_date        date             not null,
    symbol            text             not null,
    captured_at       timestamptz      not null,   -- when the board was read
    rank              smallint         not null,   -- 1 = biggest mover
    gap               double precision,            -- signed overnight fraction (-0.06 = -6%)
    since_open        double precision,
    dir               text,                        -- up | down
    sector            text,
    weight            double precision,            -- QQQ weight, percent
    vs_tape           text,                        -- with_tape | counter_tape
    crowd             text,                        -- sector_wide | lone | mixed | with_market | against_market
    sustain           text,                        -- holding | fading
    -- board-level context, repeated on every row of the day so one row is self-contained
    board_phase       text,
    open_lean_dir     text,                        -- up | down | flat
    open_lean_basis   text,                        -- asia | futures | none
    tape_nq           double precision,
    tape_es           double precision,
    tape_asia         double precision,
    tape_europe       double precision,
    breadth_up        double precision,
    cap_breadth_up    double precision,
    created_at        timestamptz      not null default now(),
    primary key (trade_date, symbol)
);

create index if not exists overnight_movers_stats_symbol_idx
    on public.overnight_movers_stats (symbol, trade_date desc);

-- ---------------------------------------------------------------------------
-- daily_highlights
-- ---------------------------------------------------------------------------
create table if not exists public.daily_highlights (
    trade_date             date        primary key,
    captured_at            timestamptz not null,
    -- headline read
    qqq_price              double precision,
    direction              text,                   -- bullish | neutral | bearish | warming up
    probability_up         double precision,
    verdict                text,                   -- continue | stall | fragile | warming_up
    -- internal health (0-100) and fragility
    health_score           smallint,
    health_regime          text,
    fragility              double precision,       -- 0-1
    fragility_level        text,                   -- Low | Elevated | High | Unknown
    confirmation_state     text,                   -- confirmed | unconfirmed | fragile
    correlation_regime     text,                   -- coupled | transitional | fragmented
    leader_symbol          text,
    -- strongest sector (30m momentum)
    strongest_sector       text,
    strongest_sector_name  text,
    strongest_sector_mom   double precision,
    -- breadth
    breadth_state          text,                   -- broad | mixed | narrow
    breadth_equal_pct      double precision,
    breadth_cap_pct        double precision,
    breadth_divergence     double precision,
    advancers              integer,
    decliners              integer,
    -- AI build-out dependency
    ai_dependency          double precision,
    ai_dependency_change   double precision,
    ai_dependency_2w       jsonb,                  -- [{date, value}] last ~2 weeks
    -- rotation flow (per window: regime, summary, top rows)
    rotation               jsonb,
    -- the full structured highlights, for anything not promoted to a column
    detail                 jsonb,
    created_at             timestamptz not null default now()
);

-- ---------------------------------------------------------------------------
-- daily_picture — highlights joined to that morning's movers on trade_date
-- ---------------------------------------------------------------------------
create or replace view public.daily_picture as
select
    h.*,
    coalesce(m.movers, '[]'::jsonb) as overnight_movers,
    m.movers_captured_at
from public.daily_highlights h
left join lateral (
    select
        jsonb_agg(
            jsonb_build_object(
                'symbol', o.symbol, 'rank', o.rank, 'gap', o.gap, 'dir', o.dir,
                'sector', o.sector, 'vs_tape', o.vs_tape, 'crowd', o.crowd,
                'sustain', o.sustain
            ) order by o.rank
        ) as movers,
        max(o.captured_at) as movers_captured_at
    from public.overnight_movers_stats o
    where o.trade_date = h.trade_date
) m on true;

-- ---------------------------------------------------------------------------
-- Row-level security: locked to service_role (which bypasses RLS)
-- ---------------------------------------------------------------------------
alter table public.overnight_movers_stats enable row level security;
alter table public.daily_highlights       enable row level security;

-- the view runs with the caller's rights, so it exposes nothing to anon/authenticated
alter view public.daily_picture set (security_invoker = true);

comment on table public.overnight_movers_stats is
    'One row per overnight mover, captured ~09:28 ET. Join to daily_highlights on trade_date.';
comment on table public.daily_highlights is
    'One row per trading day, captured ~10:05 ET: breadth, rotation, AI dependency (2w), health, fragility, strongest sector.';
