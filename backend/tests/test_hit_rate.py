"""Tests for the hit-rate / continuation-probability engine (design section 7).

All offline: synthetic multi-session data only, no network, no real Redis.
Critical contract checks: the AUTO horizon equals the measured leader lag, and
by_horizon carries the configured fixed horizons (str keys).
"""
import pandas as pd
import pytest

from app.core.lead_lag import LeadLagEngine
from app.core.hit_rate import HitRateEngine

try:
    from synthetic import make_synthetic_session
except ImportError:  # pragma: no cover - rootdir fallback
    from tests.synthetic import make_synthetic_session


PLANTED_LEAD = 3
HORIZONS = [5, 15, 30]


def _multi_session(dates, lead_symbol="SMH", lead_minutes=PLANTED_LEAD):
    """Concatenate several planted sessions into one frame (history_store.get_recent_bars)."""
    frames = []
    for i, d in enumerate(dates):
        frames.append(make_synthetic_session(
            n_bars=240, lead_symbol=lead_symbol, lead_minutes=lead_minutes,
            lead_strength=0.95, seed=i + 1, start=d + " 09:30",
        ))
    return pd.concat(frames).sort_index()


def _current_lead_lag(bars):
    # use the last session for the "current" reading
    last_day = bars.index.normalize().unique()[-1]
    today = bars[bars.index.normalize() == last_day]
    return LeadLagEngine().compute(today)


def test_planted_lead_beats_baseline():
    dates = ["2026-05-26", "2026-05-27", "2026-05-28", "2026-05-29", "2026-06-01"]
    bars = _multi_session(dates)
    current = _current_lead_lag(bars)
    assert current["leader"] is not None
    assert current["leader"]["symbol"] == "SMH"

    res = HitRateEngine(horizons=HORIZONS).compute(bars, current)
    assert res["status"] == "ok"
    assert res["leader"] == "SMH"
    assert res["sample_size"] >= 30
    assert res["hit_rate"] > res["baseline"]
    assert res["edge"] > 0
    assert res["sessions"] == len(dates)


def test_auto_horizon_equals_planted_lead():
    dates = ["2026-05-26", "2026-05-27", "2026-05-28", "2026-05-29"]
    bars = _multi_session(dates, lead_minutes=PLANTED_LEAD)
    current = _current_lead_lag(bars)
    assert current["leader"]["lag_minutes"] == PLANTED_LEAD

    res = HitRateEngine(horizons=HORIZONS).compute(bars, current)
    assert res["horizon_mode"] == "auto"
    assert res["horizon_minutes"] == PLANTED_LEAD
    assert res["horizon_minutes"] == current["leader"]["lag_minutes"]


def test_by_horizon_has_configured_keys():
    dates = ["2026-05-26", "2026-05-27", "2026-05-28", "2026-05-29"]
    bars = _multi_session(dates)
    current = _current_lead_lag(bars)

    res = HitRateEngine(horizons=HORIZONS).compute(bars, current)
    for h in HORIZONS:
        assert str(h) in res["by_horizon"]
    # auto horizon also present under its int-as-str key
    assert str(res["horizon_minutes"]) in res["by_horizon"]
    for v in res["by_horizon"].values():
        assert 0.0 <= v <= 1.0


def test_manual_horizon_does_not_change_lag():
    """A manual horizon governs only the forward window; the auto horizon (= lag)
    must still equal the measured lead, and by_horizon stays consistent."""
    dates = ["2026-05-26", "2026-05-27", "2026-05-28", "2026-05-29"]
    bars = _multi_session(dates)
    current = _current_lead_lag(bars)
    lag = current["leader"]["lag_minutes"]

    auto = HitRateEngine(horizons=HORIZONS).compute(bars, current)
    manual = HitRateEngine(horizons=HORIZONS).compute(bars, current, horizon=30)

    assert manual["horizon_mode"] == "manual"
    assert manual["horizon_minutes"] == 30
    # the lead-derived auto horizon is independent of the chosen horizon:
    assert auto["horizon_minutes"] == lag
    # by_horizon (which is lag-based signal, horizon-based fwd) is the same set
    assert set(manual["by_horizon"].keys()) >= {str(h) for h in HORIZONS}


def test_small_data_gathering():
    bars = _multi_session(["2026-06-01"], lead_minutes=PLANTED_LEAD)
    # truncate to very few bars so firing sample < min_sample
    bars = bars.iloc[:20]
    current = {"leader": {"symbol": "SMH", "lag_minutes": PLANTED_LEAD}}

    res = HitRateEngine(horizons=HORIZONS).compute(bars, current)
    assert res["status"] == "gathering"
    assert res["sample_size"] < 30
    # still fully populated
    for key in ("leader", "horizon_minutes", "horizon_mode", "sessions",
                "hit_rate", "baseline", "edge", "by_horizon", "message"):
        assert key in res


def test_no_leader():
    bars = _multi_session(["2026-06-01"])
    res = HitRateEngine(horizons=HORIZONS).compute(bars, {"leader": None})
    assert res["status"] == "no_leader"
    assert res["leader"] is None
    assert res["horizon_mode"] == "auto"
    for key in ("horizon_minutes", "sample_size", "sessions", "hit_rate",
                "baseline", "edge", "by_horizon", "message"):
        assert key in res


def test_full_shape_on_bad_input():
    res = HitRateEngine(horizons=HORIZONS).compute(None, {})
    assert res["status"] == "no_leader"
    for key in ("status", "leader", "horizon_minutes", "horizon_mode",
                "sample_size", "sessions", "hit_rate", "baseline", "edge",
                "by_horizon", "message"):
        assert key in res
