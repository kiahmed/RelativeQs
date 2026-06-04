import numpy as np
import pandas as pd

from app.core.intraday_score import IntradayScoreEngine

try:
    from synthetic import make_synthetic_session
except ImportError:
    from _synthetic_fallback import make_synthetic_session


def _entry(symbol, role, best_corr, best_lag=0, corr_at_zero=None, beta=1.0):
    return {
        "symbol": symbol,
        "best_lag": best_lag,
        "best_corr": best_corr,
        "corr_at_zero": best_corr if corr_at_zero is None else corr_at_zero,
        "beta": beta,
        "role": role,
    }


def _lead_lag_ok(entries, leader=None, confirmers=None, diverging=None, target="QQQ"):
    return {
        "status": "ok",
        "bars_used": 240,
        "window_start": "2026-06-02T09:30:00",
        "window_end": "2026-06-02T13:30:00",
        "target": target,
        "entries": entries,
        "leader": leader,
        "confirmers": confirmers or [],
        "diverging": diverging or [],
    }


def test_warming_up_when_lead_lag_not_ok():
    bars = make_synthetic_session(n_bars=240)
    engine = IntradayScoreEngine()
    result = engine.compute(bars, {"status": "warming_up", "entries": []})
    assert result["status"] == "warming_up"
    assert result["verdict"] == "warming_up"
    assert result["probability_up"] == 0.5
    # momentum still reported for display
    assert "QQQ" in result["momentum_30m"]


def test_broad_rally_verdict_continue():
    # Strong upward drift on leader -> target rallies; confirmers participate.
    bars = make_synthetic_session(
        n_bars=240, lead_symbol="SMH", lead_minutes=3,
        lead_strength=0.9, drift_per_bar=0.001,
    )
    lead_lag = _lead_lag_ok(
        entries=[_entry("SMH", "leader", 0.7, best_lag=3, beta=1.1)],
        leader={"symbol": "SMH", "lag_minutes": 3, "corr": 0.7, "beta": 1.1},
        confirmers=["XLY", "XLF"],
    )
    result = IntradayScoreEngine().compute(bars, lead_lag)
    assert result["status"] == "ok"
    assert result["verdict"] == "continue"
    assert result["probability_up"] > 0.5
    assert result["score"] > 0.2
    assert result["components"]["leadership"] > 0.0


def test_planted_divergence_raises_fragility():
    bars = make_synthetic_session(
        n_bars=240, drift_per_bar=0.001,
    )
    # Most of the universe is flagged diverging -> fragility should be high.
    universe = [c for c in bars.columns if c != "QQQ"]
    diverging = universe[:-1]  # nearly all diverging
    lead_lag = _lead_lag_ok(
        entries=[_entry("SMH", "leader", 0.6, best_lag=3, beta=1.0)],
        leader={"symbol": "SMH", "lag_minutes": 3, "corr": 0.6, "beta": 1.0},
        confirmers=["XLY"],
        diverging=diverging,
    )
    result = IntradayScoreEngine().compute(bars, lead_lag)
    assert result["components"]["fragility"] >= 0.5
    assert result["verdict"] == "fragile"


def test_few_bars_still_ok_status_follows_lead_lag():
    # The score engine keys "warming_up" off lead_lag status, not bar count.
    bars = make_synthetic_session(n_bars=10)
    result = IntradayScoreEngine().compute(
        bars, {"status": "warming_up", "entries": []}
    )
    assert result["status"] == "warming_up"


def test_fallback_to_top_entries_without_leader():
    bars = make_synthetic_session(n_bars=240, drift_per_bar=0.001)
    # No "leader" role anywhere -> engine uses top-2 by corr.
    lead_lag = _lead_lag_ok(
        entries=[
            _entry("SMH", "confirmer", 0.5, best_lag=0),
            _entry("XLK", "weak", 0.3, best_lag=0),
        ],
        leader=None,
        confirmers=["SMH"],
    )
    result = IntradayScoreEngine().compute(bars, lead_lag)
    assert result["status"] == "ok"
    # leadership should be derived from the fallback entries, finite.
    assert -1.0 <= result["components"]["leadership"] <= 1.0


def test_components_in_range():
    bars = make_synthetic_session(n_bars=240)
    lead_lag = _lead_lag_ok(
        entries=[_entry("SMH", "leader", 0.6, best_lag=2)],
        leader={"symbol": "SMH", "lag_minutes": 2, "corr": 0.6, "beta": 1.0},
        confirmers=["XLY", "XLF"],
    )
    r = IntradayScoreEngine().compute(bars, lead_lag)
    assert -1.0 <= r["score"] <= 1.0
    assert 0.0 < r["probability_up"] < 1.0
    assert -1.0 <= r["components"]["leadership"] <= 1.0
    assert -1.0 <= r["components"]["broadening"] <= 1.0
    assert 0.0 <= r["components"]["fragility"] <= 1.0
