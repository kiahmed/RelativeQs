"""Acceptance test: incremental session simulation through the full stack.

Feeds a synthetic 240-bar session in 30-bar chunks (simulated poll cycles)
through the IntradayHistoryStore (fakeredis, NO real Redis, NO network) and the
three engines (lead/lag -> score -> projection), exactly like the live poll loop.

Asserts the contract acceptance criteria:
  - status transitions "warming_up" -> "ok" at LEAD_LAG_MIN_BARS,
  - the detected leader == the planted leader, lag within +/-1 of planted,
  - the final verdict is a real verdict (not "warming_up"),
  - the projection points in the planted (upward) direction.

Run with output:  python3 -m pytest tests/test_simulation.py -q -s
"""
import pandas as pd
import pytest

import fakeredis.aioredis

from app.config import settings
from app.services.cache import RedisCache
from app.services.history_store import IntradayHistoryStore
from app.core.lead_lag import LeadLagEngine
from app.core.intraday_score import IntradayScoreEngine
from app.core.projection import ProjectionEngine

from tests.synthetic import make_synthetic_session

# Planted relationship (must match what we assert is detected).
PLANTED_LEADER = "SMH"
PLANTED_LAG = 3
N_BARS = 240
CHUNK = 30


@pytest.fixture
def store():
    cache = RedisCache()
    # Inject a fakeredis client so nothing touches a real Redis / network.
    cache._client = fakeredis.aioredis.FakeRedis()
    return IntradayHistoryStore(cache=cache, retention_days=5)


@pytest.mark.asyncio
async def test_incremental_session_reaches_verdict(store):
    # Strong planted upward drift so the signal robustly dominates the noise
    # over the projection's short lag window (engine contract is unchanged).
    session = make_synthetic_session(
        n_bars=N_BARS,
        lead_symbol=PLANTED_LEADER,
        lead_minutes=PLANTED_LAG,
        lead_strength=0.9,
        drift_per_bar=0.0015,
        seed=42,
    )

    lead_lag_engine = LeadLagEngine()
    score_engine = IntradayScoreEngine()
    projection_engine = ProjectionEngine()

    statuses = []
    rows = []
    final = None

    # Simulated poll cycles: each cycle appends a fresh chunk, then the engines
    # run on the WHOLE accumulated session pulled back out of the store.
    for start in range(0, N_BARS, CHUNK):
        chunk_df = session.iloc[start:start + CHUNK]
        total_stored = await store.append_bars(chunk_df)

        bars = await store.get_session_bars()
        assert bars is not None
        assert len(bars) == total_stored

        lead_lag = lead_lag_engine.compute(bars)
        score = score_engine.compute(bars, lead_lag)
        projection = projection_engine.compute(bars, lead_lag, score)

        statuses.append(lead_lag["status"])
        leader_sym = lead_lag["leader"]["symbol"] if lead_lag["leader"] else None
        leader_lag = lead_lag["leader"]["lag_minutes"] if lead_lag["leader"] else None
        rows.append({
            "chunk": (start // CHUNK) + 1,
            "bars": lead_lag["bars_used"],
            "status": lead_lag["status"],
            "leader": leader_sym,
            "lag": leader_lag,
            "verdict": score["verdict"],
            "direction": projection["direction"],
            "proj_price": projection["projected_price"],
        })
        final = {"lead_lag": lead_lag, "score": score, "projection": projection}

    # ---- visible table (shows in -s mode) -----------------------------
    print()
    print(f"{'chunk':>5} {'bars':>4} {'status':>10} {'leader':>7} {'lag':>3} "
          f"{'verdict':>10} {'dir':>5} {'proj_price':>11}")
    for r in rows:
        print(f"{r['chunk']:>5} {r['bars']:>4} {r['status']:>10} "
              f"{str(r['leader']):>7} {str(r['lag']):>3} {r['verdict']:>10} "
              f"{r['direction']:>5} {r['proj_price']:>11.4f}")

    # ---- status transition: warming_up -> ok at min_bars --------------
    assert statuses[0] == "warming_up", \
        f"first chunk should be warming_up, got {statuses[0]}"
    assert "ok" in statuses, "engine never reached 'ok' status"
    first_ok = statuses.index("ok")
    # everything before first ok is warming_up; everything after stays ok
    assert all(s == "warming_up" for s in statuses[:first_ok])
    assert all(s == "ok" for s in statuses[first_ok:])
    # ok arrives once enough bars accumulate (>= configured min)
    assert rows[first_ok]["bars"] >= settings.LEAD_LAG_MIN_BARS

    ll = final["lead_lag"]
    sc = final["score"]
    pj = final["projection"]

    # ---- detected leader == planted leader, lag ~ planted -------------
    assert ll["status"] == "ok"
    assert ll["leader"] is not None, "no leader detected on the full session"
    assert ll["leader"]["symbol"] == PLANTED_LEADER, \
        f"detected {ll['leader']['symbol']}, planted {PLANTED_LEADER}"
    assert abs(ll["leader"]["lag_minutes"] - PLANTED_LAG) <= 1, \
        f"detected lag {ll['leader']['lag_minutes']}, planted {PLANTED_LAG}"
    assert ll["leader"]["corr"] > 0.5

    # ---- real verdict (no longer warming_up) --------------------------
    assert sc["status"] == "ok"
    assert sc["verdict"] != "warming_up"
    assert sc["probability_up"] > 0.5  # planted upward bias

    # ---- projection points in the planted (up) direction --------------
    assert pj["status"] == "ok"
    assert pj["direction"] == "up", f"projection direction was {pj['direction']}"
    assert pj["projected_price"] > pj["current_price"]
    assert pj["band_low"] < pj["projected_price"] < pj["band_high"]
    assert pj["basis"] == "leader_projection"
