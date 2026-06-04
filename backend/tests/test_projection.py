import numpy as np
import pandas as pd

from app.core.projection import ProjectionEngine

try:
    from synthetic import make_synthetic_session
except ImportError:
    from _synthetic_fallback import make_synthetic_session


def _lead_lag_ok(leader=None, entries=None, target="QQQ"):
    return {
        "status": "ok",
        "bars_used": 240,
        "window_start": "2026-06-02T09:30:00",
        "window_end": "2026-06-02T13:30:00",
        "target": target,
        "entries": entries or [],
        "leader": leader,
        "confirmers": [],
        "diverging": [],
    }


def _score(score_val):
    return {
        "status": "ok",
        "verdict": "continue",
        "score": score_val,
        "probability_up": 0.5 + 0.5 * float(np.tanh(2.0 * score_val)),
        "components": {"leadership": 0.0, "broadening": 0.0, "fragility": 0.0},
        "momentum_30m": {},
    }


def test_warming_up_when_lead_lag_not_ok():
    bars = make_synthetic_session(n_bars=240)
    result = ProjectionEngine().compute(
        bars, {"status": "warming_up"}, _score(0.0)
    )
    assert result["status"] == "warming_up"
    assert result["direction"] == "flat"
    assert result["basis"] == "momentum_only"


def test_planted_upward_drift_direction_up():
    bars = make_synthetic_session(
        n_bars=240, lead_symbol="SMH", lead_minutes=3,
        lead_strength=0.9, drift_per_bar=0.001,
    )
    leader = {"symbol": "SMH", "lag_minutes": 3, "corr": 0.7, "beta": 1.1}
    lead_lag = _lead_lag_ok(leader=leader)
    result = ProjectionEngine().compute(bars, lead_lag, _score(0.5))
    assert result["status"] == "ok"
    assert result["basis"] == "leader_projection"
    assert result["direction"] == "up"
    assert result["projected_price"] > result["current_price"]
    assert result["band_low"] < result["projected_price"] < result["band_high"]
    assert 0.0 <= result["confidence"] <= 1.0


def test_no_leader_basis_momentum_only():
    bars = make_synthetic_session(n_bars=240, drift_per_bar=0.001)
    lead_lag = _lead_lag_ok(leader=None)
    result = ProjectionEngine().compute(bars, lead_lag, _score(0.5))
    assert result["status"] == "ok"
    assert result["basis"] == "momentum_only"
    assert result["confidence"] == 0.2
    # positive score with positive vol -> expected up
    assert result["direction"] in ("up", "flat")


def test_downward_drift_direction_down():
    bars = make_synthetic_session(
        n_bars=240, lead_symbol="SMH", lead_minutes=3,
        lead_strength=0.9, drift_per_bar=-0.001,
    )
    leader = {"symbol": "SMH", "lag_minutes": 3, "corr": 0.7, "beta": 1.1}
    lead_lag = _lead_lag_ok(leader=leader)
    result = ProjectionEngine().compute(bars, lead_lag, _score(-0.5))
    assert result["direction"] == "down"
    assert result["projected_price"] < result["current_price"]


def test_horizon_from_arg():
    bars = make_synthetic_session(n_bars=240)
    result = ProjectionEngine(horizon_minutes=20).compute(
        bars, _lead_lag_ok(leader=None), _score(0.1)
    )
    assert result["horizon_minutes"] == 20


def test_band_widths_finite_and_ordered():
    bars = make_synthetic_session(n_bars=240, drift_per_bar=0.0005)
    leader = {"symbol": "SMH", "lag_minutes": 3, "corr": 0.6, "beta": 1.0}
    result = ProjectionEngine().compute(bars, _lead_lag_ok(leader=leader), _score(0.3))
    assert np.isfinite(result["band_low"])
    assert np.isfinite(result["band_high"])
    assert result["band_low"] <= result["projected_price"] <= result["band_high"]
    assert result["current_price"] > 0
