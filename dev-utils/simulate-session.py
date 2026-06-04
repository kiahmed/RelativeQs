#!/usr/bin/env python3
"""Standalone incremental session simulation for the QQQ prediction engine.

Runs the SAME pipeline as tests/test_simulation.py but outside pytest: it feeds
a synthetic 240-bar session in 30-bar chunks (simulated poll cycles) through the
IntradayHistoryStore (backed by in-memory fakeredis) and the three engines
(lead/lag -> score -> projection), printing a per-chunk table.

NO network calls. NO real Redis. Purely offline / synthetic.

Usage:
    python3 dev-utils/simulate-session.py
    python3 dev-utils/simulate-session.py --bars 240 --chunk 30 --leader SMH \\
            --lag 3 --drift 0.0015 --seed 42

Run from the repo root (it adds backend/ to sys.path automatically).
"""
import argparse
import asyncio
import os
import sys

# Make `app` and `tests` importable regardless of CWD.
_HERE = os.path.dirname(os.path.abspath(__file__))
_BACKEND = os.path.join(os.path.dirname(_HERE), "backend")
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

from datetime import datetime, timedelta  # noqa: E402
from zoneinfo import ZoneInfo  # noqa: E402

import fakeredis.aioredis  # noqa: E402

from app.services.cache import RedisCache  # noqa: E402
from app.services.history_store import IntradayHistoryStore  # noqa: E402
from app.core.lead_lag import LeadLagEngine  # noqa: E402
from app.core.intraday_score import IntradayScoreEngine  # noqa: E402
from app.core.projection import ProjectionEngine  # noqa: E402
from app.core.attribution import DriverAttributionEngine  # noqa: E402
from app.core.confirmation import ConfirmationGate  # noqa: E402
from app.core.correlation_regime import CorrelationRegimeEngine  # noqa: E402
from app.core.stability import StabilityEngine  # noqa: E402
from app.core.hit_rate import HitRateEngine  # noqa: E402

from tests.synthetic import make_synthetic_session  # noqa: E402
from tests.test_simulation_phase2 import (  # noqa: E402
    make_broad_rally_session, DAY_SEEDS,
)


def _et_date(offset_back: int) -> str:
    today = datetime.now(ZoneInfo("America/New_York")).date()
    return (today - timedelta(days=offset_back)).strftime("%Y-%m-%d")


async def run(args) -> int:
    # In-memory fakeredis -> no network, no real Redis.
    cache = RedisCache()
    cache._client = fakeredis.aioredis.FakeRedis()
    store = IntradayHistoryStore(cache=cache, retention_days=10)

    # --- seed prior sessions so stability / hit-rate reach "ok" --------- #
    # Use the broad-rally generator (same planted SMH leader every day) so the
    # Phase-2 sections demonstrate their "good" states. Dates are real-today
    # relative so get_recent_sessions() finds them.
    n_days = len(DAY_SEEDS)
    session_dates = [_et_date(n_days - 1 - i) for i in range(n_days)]
    today_date = session_dates[-1]
    for ds, seed in zip(session_dates[:-1], DAY_SEEDS[:-1]):
        prior = make_broad_rally_session(
            n_bars=args.bars, seed=seed, start=ds + " 09:30")
        await cache.set("bars:" + ds,
                        IntradayHistoryStore._frame_to_payload(prior),
                        expire=10 * 86400)

    # today's session is fed in chunks (poll cycles)
    session = make_broad_rally_session(
        n_bars=args.bars, seed=DAY_SEEDS[-1], start=today_date + " 09:30")

    lead_lag_engine = LeadLagEngine()
    score_engine = IntradayScoreEngine()
    projection_engine = ProjectionEngine()
    attr_engine = DriverAttributionEngine()
    conf_engine = ConfirmationGate()
    corr_engine = CorrelationRegimeEngine()
    stab_engine = StabilityEngine()
    hr_engine = HitRateEngine()

    print(f"Planted (broad rally): leader=SMH lag=3m bars={args.bars} "
          f"chunk={args.chunk} prior_sessions={n_days - 1} dates={session_dates}")
    header = (f"{'chunk':>5} {'bars':>4} {'status':>10} {'leader':>7} "
              f"{'lag':>3} {'verdict':>10} {'dir':>5} {'cur_price':>10} "
              f"{'proj_price':>11}")
    print(header)
    print("-" * len(header))

    statuses = []
    final = None
    for i, start in enumerate(range(0, args.bars, args.chunk), start=1):
        chunk_df = session.iloc[start:start + args.chunk]
        await store.append_bars(chunk_df)
        bars = await store.get_session_bars()

        lead_lag = lead_lag_engine.compute(bars)
        score = score_engine.compute(bars, lead_lag)
        projection = projection_engine.compute(bars, lead_lag, score)
        statuses.append(lead_lag["status"])

        leader = lead_lag["leader"]["symbol"] if lead_lag["leader"] else None
        lag = lead_lag["leader"]["lag_minutes"] if lead_lag["leader"] else None
        print(f"{i:>5} {lead_lag['bars_used']:>4} {lead_lag['status']:>10} "
              f"{str(leader):>7} {str(lag):>3} {score['verdict']:>10} "
              f"{projection['direction']:>5} "
              f"{projection['current_price']:>10.4f} "
              f"{projection['projected_price']:>11.4f}")

        # ---- the 5 Phase-2 sections, per chunk ------------------------- #
        attribution = attr_engine.compute(bars)
        confirmation = conf_engine.compute(bars, lead_lag, score)
        correlation = corr_engine.compute(bars)
        sessions = await store.get_recent_sessions()
        stability = stab_engine.compute(sessions, lead_lag)
        recent = await store.get_recent_bars()
        hit_rate = hr_engine.compute(recent, lead_lag)

        _top = attribution["contributors"][0] if attribution["contributors"] else None
        _top_sym = _top["symbol"] if _top else None
        _top_share = f"{_top['share']:+.2f}" if _top else "n/a"
        print(f"        #1 attribution  : {attribution['status']:>10} "
              f"top={_top_sym} share={_top_share} "
              f"explained={attribution['explained_share']:.2f}")
        print(f"        #3 confirmation : {confirmation['status']:>10} "
              f"state={confirmation['state']} "
              f"part={confirmation['participating_count']}/{confirmation['universe_count']} "
              f"agree={confirmation['leaders_agree']}")
        print(f"        #5 correlation  : {correlation['status']:>10} "
              f"regime={correlation['regime']} "
              f"avg_corr={correlation['avg_pairwise_corr']:.2f} "
              f"reliable={correlation['signals_reliable']}")
        print(f"        #2 stability    : {stability['status']:>10} "
              f"verdict={stability['verdict']} "
              f"sessions={stability['sessions_analyzed']} "
              f"persistence={stability['lead_persistence']:.2f} "
              f"median_lag={stability['median_lag']}")
        print(f"        #4 hit_rate     : {hit_rate['status']:>10} "
              f"hit={hit_rate['hit_rate']:.3f} base={hit_rate['baseline']:.3f} "
              f"edge={hit_rate['edge']:+.3f} n={hit_rate['sample_size']} "
              f"H={hit_rate['horizon_minutes']}m({hit_rate['horizon_mode']})")

        final = (lead_lag, score, projection, attribution, confirmation,
                 correlation, stability, hit_rate)

    print("-" * len(header))
    ll, sc, pj, attribution, confirmation, correlation, stability, hit_rate = final
    print(f"transitions : {' -> '.join(statuses)}")
    if ll["leader"]:
        print(f"detected    : leader={ll['leader']['symbol']} "
              f"lag={ll['leader']['lag_minutes']}m corr={ll['leader']['corr']:.3f}")
    print(f"verdict     : {sc['verdict']} "
          f"(score={sc['score']:+.3f}, p_up={sc['probability_up']:.3f})")
    print(f"projection  : {pj['direction']} "
          f"({pj['current_price']:.2f} -> {pj['projected_price']:.2f}, "
          f"band [{pj['band_low']:.2f}, {pj['band_high']:.2f}], "
          f"conf={pj['confidence']:.2f}, basis={pj['basis']})")
    print(f"#1 driver   : {attribution['headline']}")
    print(f"#3 confirm  : {confirmation['message']}")
    print(f"#5 corr     : {correlation['message']}")
    print(f"#2 stability: {stability['message']}")
    print(f"#4 hit-rate : {hit_rate['message']}  "
          f"(auto horizon == planted lead: "
          f"{hit_rate['horizon_minutes'] == (ll['leader']['lag_minutes'] if ll['leader'] else None)})")
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--bars", type=int, default=240)
    p.add_argument("--chunk", type=int, default=30)
    p.add_argument("--leader", default="SMH")
    p.add_argument("--lag", type=int, default=3)
    p.add_argument("--strength", type=float, default=0.9)
    p.add_argument("--drift", type=float, default=0.0015)
    p.add_argument("--seed", type=int, default=42)
    args = p.parse_args()
    return asyncio.run(run(args))


if __name__ == "__main__":
    raise SystemExit(main())
