"""Phase-2 acceptance / simulation test (design doc section 10).

Feeds a multi-session synthetic history through a fakeredis-backed
IntradayHistoryStore and runs ALL Phase-2 engines, asserting the full
acceptance contract on a single coherent scenario:

  - a "broad rally" where SMH is the planted leader (lead = 3m) and the whole
    sector universe co-moves with it (coupled regime, broad participation);
  - same planted leader on every session so cross-day stability is tradeable.

Assertions (one per feature):
  #1 Driver attribution : top contributor == planted driver (SMH), high
                          explained_share.
  #3 Confirmation gate  : state == "confirmed" on the broad aligned rally.
  #5 Correlation regime : regime == "coupled", signals_reliable True.
  #2 Stability          : verdict == "tradeable" once >= STABILITY_MIN_SESSIONS.
  #4 Hit-rate           : status "ok", hit_rate > baseline, edge > 0, and the
                          AUTO horizon == the planted lead.

Everything is offline: synthetic data + fakeredis only. NO network, NO real
Redis. Run with output:

    python3 -m pytest tests/test_simulation_phase2.py -q -s
"""
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import pytest

import fakeredis.aioredis

from app.config import settings
from app.services.cache import RedisCache
from app.services.history_store import IntradayHistoryStore
from app.core.lead_lag import LeadLagEngine
from app.core.intraday_score import IntradayScoreEngine
from app.core.attribution import DriverAttributionEngine
from app.core.confirmation import ConfirmationGate
from app.core.correlation_regime import CorrelationRegimeEngine
from app.core.stability import StabilityEngine
from app.core.hit_rate import HitRateEngine


# ---- planted scenario --------------------------------------------------- #
PLANTED_LEADER = "SMH"
PLANTED_LAG = 3
N_BARS = 240
CHUNK = 30
# Per-day RNG seeds. Each individually produces SMH-leader / coupled / confirmed
# / SMH-attribution (validated offline). >= STABILITY_MIN_SESSIONS days planted.
DAY_SEEDS = [1, 2, 4, 5]

UNIVERSE = ["QQQ", "XLK", "SMH", "MAGS", "IGV",
            "XLY", "XLF", "XLI", "IWM", "XLE", "XLP", "TLT"]


def make_broad_rally_session(n_bars: int = N_BARS, seed: int = 0,
                             drift: float = 0.0006,
                             start: str = "2026-06-02 09:30") -> pd.DataFrame:
    """A broad-rally 1m close DataFrame with a planted SMH -> QQQ lead.

    SMH is BOTH the market leader (the whole universe keys off it -> coupled
    regime, broad participation) AND the planted lead driver: QQQ's return is
    dominated by SMH's return LAGGED by ``PLANTED_LAG`` minutes (so the lead/lag
    engine detects SMH at that lag), with a smaller contemporaneous SMH loading
    so SMH is also the top contributor in the contemporaneous attribution
    regression. IGV/MAGS load on SMH more weakly (so they don't out-score SMH
    in attribution) but still strongly enough to keep the regime coupled.
    """
    rng = np.random.default_rng(seed)
    idx = pd.date_range(start=start, periods=n_bars, freq="1min")

    smh = drift + rng.normal(0.0, 0.0013, n_bars)
    shifted = np.zeros(n_bars)
    shifted[PLANTED_LAG:] = smh[:-PLANTED_LAG]
    # lagged SMH dominant (lead detection) + contemporaneous SMH (attribution)
    target_ret = 0.65 * shifted + 0.6 * smh + rng.normal(0.0, 0.00010, n_bars)

    rets = {}
    for s in UNIVERSE:
        if s == PLANTED_LEADER:
            rets[s] = smh
        elif s == "QQQ":
            rets[s] = target_ret
        elif s in ("IGV", "MAGS"):
            rets[s] = 0.7 * smh + rng.normal(0.0, 0.0007, n_bars)
        else:
            rets[s] = rng.uniform(0.9, 1.1) * smh + rng.normal(0.0, 0.0005, n_bars)

    data = {}
    for s in UNIVERSE:
        base = 100.0 + rng.uniform(-3.0, 3.0)
        data[s] = base * np.exp(np.cumsum(rets[s]))
    df = pd.DataFrame(data, index=idx)
    df.index.name = None
    return df


@pytest.fixture
def store():
    cache = RedisCache()
    cache._client = fakeredis.aioredis.FakeRedis()
    # retention long enough to cover the planted calendar span
    return IntradayHistoryStore(cache=cache, retention_days=10), cache


def _et_date(offset_back: int) -> str:
    today = datetime.now(ZoneInfo("America/New_York")).date()
    return (today - timedelta(days=offset_back)).strftime("%Y-%m-%d")


@pytest.mark.asyncio
async def test_phase2_acceptance(store):
    history, cache = store
    n_days = len(DAY_SEEDS)
    assert n_days >= settings.STABILITY_MIN_SESSIONS

    # ---- seed prior sessions directly (older days) --------------------- #
    # Dates are real-today-relative so get_recent_sessions() (which walks back
    # from ET today) finds them. The MOST RECENT day is "today" and is fed in
    # chunks below to exercise the live poll-loop path (append_bars).
    session_dates = [_et_date(n_days - 1 - i) for i in range(n_days)]
    today_date = session_dates[-1]

    for ds, seed in zip(session_dates[:-1], DAY_SEEDS[:-1]):
        frame = make_broad_rally_session(seed=seed, start=ds + " 09:30")
        payload = IntradayHistoryStore._frame_to_payload(frame)
        await cache.set("bars:" + ds, payload, expire=10 * 86400)

    # ---- feed TODAY in chunks through the store (poll cycles) ---------- #
    today_session = make_broad_rally_session(
        seed=DAY_SEEDS[-1], start=today_date + " 09:30")

    ll_engine = LeadLagEngine()
    score_engine = IntradayScoreEngine()
    attr_engine = DriverAttributionEngine()
    conf_engine = ConfirmationGate()
    corr_engine = CorrelationRegimeEngine()
    stab_engine = StabilityEngine()
    hr_engine = HitRateEngine()

    final = None
    for start in range(0, N_BARS, CHUNK):
        chunk = today_session.iloc[start:start + CHUNK]
        await history.append_bars(chunk)
        bars = await history.get_session_bars()
        assert bars is not None

        lead_lag = ll_engine.compute(bars)
        score = score_engine.compute(bars, lead_lag)
        attribution = attr_engine.compute(bars)
        confirmation = conf_engine.compute(bars, lead_lag, score)
        correlation = corr_engine.compute(bars)

        sessions = await history.get_recent_sessions()
        stability = stab_engine.compute(sessions, lead_lag)
        recent = await history.get_recent_bars()
        hit_rate = hr_engine.compute(recent, lead_lag)

        final = {
            "lead_lag": lead_lag, "score": score, "attribution": attribution,
            "confirmation": confirmation, "correlation": correlation,
            "stability": stability, "hit_rate": hit_rate,
            "sessions": [d for d, _ in sessions],
        }

    f = final
    ll, attribution = f["lead_lag"], f["attribution"]
    confirmation, correlation = f["confirmation"], f["correlation"]
    stability, hit_rate = f["stability"], f["hit_rate"]

    # ---- visible report (shows in -s mode) ---------------------------- #
    print()
    print("=== Phase-2 acceptance ===")
    print(f"sessions stored : {f['sessions']}")
    print(f"leader          : {ll['leader']['symbol']} @ "
          f"{ll['leader']['lag_minutes']}m (planted {PLANTED_LEADER}/{PLANTED_LAG})")
    top = attribution["contributors"][0]
    print(f"#1 attribution  : top={top['symbol']} share={top['share']:.2f} "
          f"explained={attribution['explained_share']:.2f} :: {attribution['headline']}")
    print(f"#3 confirmation : {confirmation['state']} "
          f"({confirmation['participating_count']}/{confirmation['universe_count']}, "
          f"agree={confirmation['leaders_agree']}) :: {confirmation['message']}")
    print(f"#5 correlation  : {correlation['regime']} "
          f"avg_corr={correlation['avg_pairwise_corr']:.2f} "
          f"reliable={correlation['signals_reliable']}")
    print(f"#2 stability    : {stability['verdict']} "
          f"sessions={stability['sessions_analyzed']} "
          f"persistence={stability['lead_persistence']:.2f} "
          f"median_lag={stability['median_lag']}")
    print(f"#4 hit_rate     : {hit_rate['status']} hit={hit_rate['hit_rate']:.3f} "
          f"base={hit_rate['baseline']:.3f} edge={hit_rate['edge']:+.3f} "
          f"n={hit_rate['sample_size']} sessions={hit_rate['sessions']} "
          f"H={hit_rate['horizon_minutes']}m ({hit_rate['horizon_mode']})")
    auto_matches = hit_rate["horizon_minutes"] == ll["leader"]["lag_minutes"]
    print(f"auto horizon == planted lead : {auto_matches}")

    # ---- planted leader detected -------------------------------------- #
    assert ll["status"] == "ok"
    assert ll["leader"] is not None
    assert ll["leader"]["symbol"] == PLANTED_LEADER
    assert ll["leader"]["lag_minutes"] == PLANTED_LAG

    # ---- #1 driver attribution ---------------------------------------- #
    assert attribution["status"] == "ok"
    assert attribution["contributors"], "no attribution contributors"
    assert attribution["contributors"][0]["symbol"] == PLANTED_LEADER, \
        f"top contributor {attribution['contributors'][0]['symbol']} != {PLANTED_LEADER}"
    assert attribution["explained_share"] >= 0.35, \
        f"explained_share too low: {attribution['explained_share']}"
    assert abs(attribution["contributors"][0]["share"]) >= 0.4

    # ---- #3 confirmation gate ----------------------------------------- #
    assert confirmation["status"] == "ok"
    assert confirmation["state"] == "confirmed", \
        f"confirmation state {confirmation['state']} != confirmed"
    assert confirmation["target_direction"] == "up"
    assert confirmation["participation"] >= 0.55
    assert confirmation["leaders_agree"] is True

    # ---- #5 correlation regime ---------------------------------------- #
    assert correlation["status"] == "ok"
    assert correlation["regime"] == "coupled", \
        f"regime {correlation['regime']} != coupled"
    assert correlation["signals_reliable"] is True
    assert correlation["avg_pairwise_corr"] >= settings.CORR_COUPLED_THRESHOLD

    # ---- #2 stability ------------------------------------------------- #
    assert stability["status"] == "ok"
    assert stability["sessions_analyzed"] >= settings.STABILITY_MIN_SESSIONS
    assert stability["verdict"] == "tradeable", \
        f"stability verdict {stability['verdict']} != tradeable"
    assert stability["tradeable"] is True
    assert stability["leader"] == PLANTED_LEADER
    assert stability["lead_persistence"] >= settings.STABILITY_TRADEABLE_PERSISTENCE

    # ---- #4 hit-rate -------------------------------------------------- #
    assert hit_rate["status"] == "ok", \
        f"hit_rate status {hit_rate['status']} != ok"
    assert hit_rate["sample_size"] >= settings.HITRATE_MIN_SAMPLE
    assert hit_rate["hit_rate"] > hit_rate["baseline"], \
        f"hit_rate {hit_rate['hit_rate']} !> baseline {hit_rate['baseline']}"
    assert hit_rate["edge"] > 0
    # the AUTO horizon must equal the planted lead.
    assert hit_rate["horizon_mode"] == "auto"
    assert hit_rate["horizon_minutes"] == PLANTED_LAG, \
        f"auto horizon {hit_rate['horizon_minutes']} != planted lead {PLANTED_LAG}"
    assert hit_rate["horizon_minutes"] == ll["leader"]["lag_minutes"]
