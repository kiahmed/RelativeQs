"""Tests for MarketDataService.fetch_prediction — fully offline.

Synthetic 1m bars are monkeypatched in via _fetch_history_from_provider so no
network call (yfinance, adapters) is ever made. Asserts the prediction payload
matches the design contract (doc/rebuild-design.md section 7).
"""
import pytest

from app.config import settings
from app.services.market_data import MarketDataService

try:
    from synthetic import make_synthetic_session
except ImportError:
    from _synthetic_fallback import make_synthetic_session


@pytest.fixture
def market(monkeypatch):
    svc = MarketDataService(mode="yahoo")

    # Patch the provider fetch so NOTHING hits the network. Return a planted
    # 240-bar session restricted to the configured universe columns.
    async def _fake_fetch(self, symbols, period="7d", interval="1m"):
        bars = make_synthetic_session(n_bars=240, symbols=list(symbols))
        cols = [s for s in symbols if s in bars.columns]
        return bars[cols]

    monkeypatch.setattr(
        MarketDataService, "_fetch_history_from_provider", _fake_fetch
    )

    # Breadth fetches a different symbol set (the ~100 constituents) over its own
    # network path; stub it so the prediction tests stay fully offline. The engine
    # and the real fetch are covered in test_breadth.py.
    async def _fake_breadth(self):
        return {
            "status": "ok", "target": "QQQ", "constituents_total": 100,
            "measured": 100, "advancers": 62, "decliners": 36, "unchanged": 2,
            "equal_weight_pct": 0.62, "cap_weight_pct": 0.71, "breadth_state": "broad",
            "divergence": 0.09, "message": "62/100 advancing.",
        }

    monkeypatch.setattr(MarketDataService, "fetch_breadth", _fake_breadth)
    return svc


def _assert_payload_shape(pred):
    # top-level
    for key in ("timestamp", "status", "bars_used", "universe", "target",
                "lead_lag", "score", "projection"):
        assert key in pred, f"missing top-level key {key}"
    assert isinstance(pred["timestamp"], int)
    assert pred["status"] in ("ok", "warming_up", "no_data")
    assert isinstance(pred["bars_used"], int)
    assert pred["universe"] == list(settings.ETF_UNIVERSE)
    assert pred["target"] == settings.PREDICTION_TARGET

    # lead_lag
    ll = pred["lead_lag"]
    for key in ("status", "bars_used", "target", "entries", "leader",
                "confirmers", "diverging"):
        assert key in ll, f"missing lead_lag key {key}"
    assert isinstance(ll["entries"], list)
    assert isinstance(ll["confirmers"], list)
    assert isinstance(ll["diverging"], list)

    # score
    sc = pred["score"]
    for key in ("status", "verdict", "score", "probability_up",
                "components", "momentum_30m"):
        assert key in sc, f"missing score key {key}"
    assert sc["verdict"] in ("continue", "stall", "fragile", "warming_up")
    for comp in ("leadership", "broadening", "fragility"):
        assert comp in sc["components"]

    # projection
    pj = pred["projection"]
    for key in ("status", "horizon_minutes", "current_price", "expected_return",
                "projected_price", "band_low", "band_high", "confidence",
                "direction", "basis"):
        assert key in pj, f"missing projection key {key}"
    assert pj["direction"] in ("up", "down", "flat")

    # breadth
    br = pred["breadth"]
    for key in ("status", "target", "constituents_total", "measured", "advancers",
                "decliners", "equal_weight_pct", "cap_weight_pct", "breadth_state",
                "divergence", "message"):
        assert key in br, f"missing breadth key {key}"


@pytest.mark.asyncio
async def test_fetch_prediction_shape_no_store(market):
    pred = await market.fetch_prediction()
    _assert_payload_shape(pred)
    # 240 synthetic bars >> LEAD_LAG_MIN_BARS, so the engine emits a verdict.
    assert pred["status"] == "ok"
    assert pred["bars_used"] == 240


@pytest.mark.asyncio
async def test_fetch_prediction_detects_planted_leader(market):
    pred = await market.fetch_prediction()
    leader = pred["lead_lag"]["leader"]
    assert leader is not None
    # synthetic.make_synthetic_session plants SMH leading QQQ by 3 minutes.
    assert leader["symbol"] == "SMH"
    assert abs(leader["lag_minutes"] - 3) <= 1
    assert leader["corr"] > 0.5
    # verdict should be real, not warming_up
    assert pred["score"]["verdict"] != "warming_up"


@pytest.mark.asyncio
async def test_fetch_prediction_with_history_store(market):
    import fakeredis.aioredis
    from app.services.cache import RedisCache
    from app.services.history_store import IntradayHistoryStore

    cache = RedisCache()
    cache._client = fakeredis.aioredis.FakeRedis()
    store = IntradayHistoryStore(cache=cache, retention_days=5)

    pred = await market.fetch_prediction(history_store=store)
    _assert_payload_shape(pred)
    assert pred["status"] == "ok"

    # The store now holds the session bars (today's ET key).
    stored = await store.get_session_bars()
    assert stored is not None
    assert len(stored) > 0


def _assert_phase2_shape(pred):
    """The 5 Phase-2 sections and their contract keys (design section 8)."""
    for key in ("attribution", "confirmation", "correlation_regime",
                "stability", "hit_rate"):
        assert key in pred, f"missing phase-2 key {key}"

    attr = pred["attribution"]
    for key in ("status", "target", "window_minutes", "target_return",
                "contributors", "explained_share", "residual_share", "headline"):
        assert key in attr, f"missing attribution key {key}"
    assert isinstance(attr["contributors"], list)

    conf = pred["confirmation"]
    for key in ("status", "state", "target_direction", "participation",
                "participating_count", "universe_count", "leaders_agree",
                "fragility", "message"):
        assert key in conf, f"missing confirmation key {key}"
    assert conf["state"] in ("confirmed", "unconfirmed", "fragile")

    cr = pred["correlation_regime"]
    for key in ("status", "regime", "avg_pairwise_corr", "dispersion",
                "signals_reliable", "message"):
        assert key in cr, f"missing correlation_regime key {key}"
    assert cr["regime"] in ("coupled", "transitional", "fragmented")

    st = pred["stability"]
    for key in ("status", "leader", "sessions_analyzed", "lead_persistence",
                "intraday_consistency", "median_lag", "tradeable", "verdict",
                "message"):
        assert key in st, f"missing stability key {key}"
    assert st["verdict"] in ("tradeable", "unstable", "gathering", "no_leader")

    hr = pred["hit_rate"]
    for key in ("status", "leader", "horizon_minutes", "horizon_mode",
                "sample_size", "sessions", "hit_rate", "baseline", "edge",
                "by_horizon", "message"):
        assert key in hr, f"missing hit_rate key {key}"
    assert isinstance(hr["by_horizon"], dict)


@pytest.mark.asyncio
async def test_fetch_prediction_includes_phase2_sections(market):
    """Without a history store the 5 sections are still present and populated
    (cross-session ones degrade to warming_up/gathering)."""
    pred = await market.fetch_prediction()
    _assert_payload_shape(pred)
    _assert_phase2_shape(pred)
    # no store -> cross-session features have nothing to analyse yet
    assert pred["stability"]["status"] in ("warming_up", "gathering")
    assert pred["hit_rate"]["status"] in ("warming_up", "gathering", "no_leader")


@pytest.mark.asyncio
async def test_fetch_prediction_phase2_reaches_ok_with_history(market):
    """Seed a fakeredis history store with >= STABILITY_MIN_SESSIONS synthetic
    sessions (same planted SMH leader) across distinct ET dates so stability and
    hit_rate reach status 'ok' (not just gathering). NO network."""
    import fakeredis.aioredis
    from datetime import datetime, timedelta
    from zoneinfo import ZoneInfo

    from app.services.cache import RedisCache
    from app.services.history_store import IntradayHistoryStore

    cache = RedisCache()
    cache._client = fakeredis.aioredis.FakeRedis()
    store = IntradayHistoryStore(cache=cache, retention_days=10)

    # Seed several past ET sessions directly under their bars:{date} keys. Each
    # is a full synthetic session with the SAME planted leader (SMH @ 3min) so
    # stability sees a persistent leader and hit_rate accumulates enough samples.
    universe = list(settings.ETF_UNIVERSE)
    today = datetime.now(ZoneInfo("America/New_York")).date()
    n_seed = max(settings.STABILITY_MIN_SESSIONS + 1, 4)
    for offset in range(1, n_seed + 1):
        session_date = today - timedelta(days=offset)
        bars = make_synthetic_session(
            n_bars=240, symbols=universe, seed=100 + offset,
            start=f"{session_date.isoformat()} 09:30",
        )
        cols = [s for s in universe if s in bars.columns]
        payload = IntradayHistoryStore._frame_to_payload(bars[cols])
        await cache.set(store._key(session_date.isoformat()), payload, expire=864000)

    # Now run fetch_prediction with the store (appends today's bars too).
    pred = await market.fetch_prediction(history_store=store)
    _assert_payload_shape(pred)
    _assert_phase2_shape(pred)

    # >= min_sessions analysed with a persistent leader -> stability reaches ok.
    assert pred["stability"]["status"] == "ok"
    assert pred["stability"]["sessions_analyzed"] >= settings.STABILITY_MIN_SESSIONS
    assert pred["stability"]["leader"] == "SMH"

    # Multi-session concat -> enough samples -> hit_rate reaches ok.
    assert pred["hit_rate"]["status"] == "ok"
    assert pred["hit_rate"]["leader"] == "SMH"
    assert pred["hit_rate"]["sample_size"] >= settings.HITRATE_MIN_SAMPLE
    # auto horizon equals the measured lead (SMH @ ~3min).
    assert pred["hit_rate"]["horizon_mode"] == "auto"
    assert pred["hit_rate"]["horizon_minutes"] == pred["lead_lag"]["leader"]["lag_minutes"]


@pytest.mark.asyncio
async def test_fetch_prediction_no_data(market, monkeypatch):
    async def _empty(self, symbols, period="7d", interval="1m"):
        return None

    monkeypatch.setattr(MarketDataService, "_fetch_history_from_provider", _empty)
    pred = await market.fetch_prediction()
    _assert_payload_shape(pred)
    assert pred["status"] == "no_data"
    assert pred["bars_used"] == 0


@pytest.mark.asyncio
async def test_backfill_seeds_multiple_sessions_from_provider(market, monkeypatch):
    """A cold cache is seeded from the provider's multi-day 1m pull, split into
    one history-store key per ET date — so cross-day signals work on day one.
    Fully offline (fakeredis + synthetic), no network."""
    import fakeredis.aioredis
    import pandas as pd
    from datetime import datetime, timedelta
    from zoneinfo import ZoneInfo
    from app.services.cache import RedisCache
    from app.services.history_store import IntradayHistoryStore

    # Dates relative to "today" (ET) so the recent-session window always covers them.
    today = datetime.now(ZoneInfo("America/New_York"))
    dates = [(today - timedelta(days=k)).strftime("%Y-%m-%d") for k in (2, 1, 0)]

    frames = [
        make_synthetic_session(
            n_bars=120, symbols=list(settings.ETF_UNIVERSE), start=f"{d} 09:30"
        )
        for d in dates
    ]
    multi = pd.concat(frames).sort_index()

    async def _multi(self, symbols, period="7d", interval="1m"):
        cols = [s for s in symbols if s in multi.columns]
        return multi[cols]

    monkeypatch.setattr(MarketDataService, "_fetch_history_from_provider", _multi)

    cache = RedisCache()
    cache._client = fakeredis.aioredis.FakeRedis()
    store = IntradayHistoryStore(cache=cache, retention_days=10)

    # cold cache -> backfill should seed every distinct ET date
    await market._backfill_recent_sessions(store)

    seeded = {d for d, _ in await store.get_recent_sessions(days=10)}
    for d in dates:
        assert d in seeded, f"{d} not seeded; got {seeded}"


@pytest.mark.asyncio
async def test_backfill_disabled_when_source_none(market, monkeypatch):
    import fakeredis.aioredis
    from app.services.cache import RedisCache
    from app.services.history_store import IntradayHistoryStore

    monkeypatch.setattr(settings, "HISTORY_BACKFILL_SOURCE", "none")
    cache = RedisCache()
    cache._client = fakeredis.aioredis.FakeRedis()
    store = IntradayHistoryStore(cache=cache, retention_days=10)

    await market._backfill_recent_sessions(store)
    assert await store.get_recent_sessions(days=10) == []
