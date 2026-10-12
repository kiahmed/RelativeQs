"""Tests for the dynamic lead/lag engine (design doc section 9).

All offline: synthetic data only, no network, no real Redis.
"""
import numpy as np
import pandas as pd
import pytest

from app.core.lead_lag import LeadLagEngine
from tests.synthetic import make_synthetic_session


def test_planted_lead_detected():
    """A planted 3-min lead on SMH must surface SMH as the leader,
    lag within +/-1 min, corr > 0.5."""
    bars = make_synthetic_session(
        n_bars=240, lead_symbol="SMH", lead_minutes=3,
        lead_strength=0.9, seed=7,
    )
    res = LeadLagEngine().compute(bars)

    assert res["status"] == "ok"
    assert res["leader"] is not None
    assert res["leader"]["symbol"] == "SMH"
    assert abs(res["leader"]["lag_minutes"] - 3) <= 1
    assert res["leader"]["corr"] > 0.5

    # the leader entry is also marked with role "leader"
    smh = next(e for e in res["entries"] if e["symbol"] == "SMH")
    assert smh["role"] == "leader"


def test_no_relationship_no_leader():
    """With no planted lead (strength 0), no symbol should qualify as leader."""
    bars = make_synthetic_session(
        n_bars=240, lead_symbol="SMH", lead_minutes=3,
        lead_strength=0.0, drift_per_bar=0.0, seed=11,
    )
    res = LeadLagEngine().compute(bars)
    assert res["status"] == "ok"
    assert res["leader"] is None


def test_insufficient_bars_warming_up():
    """Fewer bars than min_bars => status warming_up, empty entries."""
    bars = make_synthetic_session(n_bars=20, seed=3)
    res = LeadLagEngine(min_bars=45).compute(bars)
    assert res["status"] == "warming_up"
    assert res["entries"] == []
    assert res["leader"] is None
    assert res["bars_used"] == 20


def test_negative_corr_is_diverging():
    """A symbol whose returns are the negation of the target should be
    classified 'diverging'."""
    bars = make_synthetic_session(
        n_bars=240, lead_symbol="SMH", lead_minutes=3,
        lead_strength=0.9, seed=21,
    )
    # build an explicitly anti-correlated TLT from QQQ's returns
    qqq_ret = np.log(bars["QQQ"]).diff().fillna(0.0)
    inv_ret = -qqq_ret
    bars = bars.copy()
    bars["TLT"] = 100.0 * np.exp(np.cumsum(inv_ret.to_numpy()))

    res = LeadLagEngine().compute(bars)
    assert res["status"] == "ok"
    assert "TLT" in res["diverging"]
    tlt = next(e for e in res["entries"] if e["symbol"] == "TLT")
    assert tlt["role"] == "diverging"


def test_no_data_returns_full_shape():
    """Empty / None input returns a fully-populated no_data result."""
    res = LeadLagEngine().compute(pd.DataFrame())
    assert res["status"] == "no_data"
    for key in ("bars_used", "window_start", "window_end", "target",
                "entries", "leader", "confirmers", "diverging"):
        assert key in res

    res2 = LeadLagEngine().compute(None)
    assert res2["status"] == "no_data"


def test_confirmers_detected():
    """Coincident movers (XLY, XLF) should be tagged confirmers, not leaders."""
    bars = make_synthetic_session(
        n_bars=240, lead_symbol="SMH", lead_minutes=3,
        lead_strength=0.9, seed=5,
    )
    res = LeadLagEngine().compute(bars)
    # at least one of the planted coincident symbols is a confirmer
    assert any(s in res["confirmers"] for s in ("XLY", "XLF"))


def test_entries_sorted_by_corr_desc():
    bars = make_synthetic_session(n_bars=240, seed=9)
    res = LeadLagEngine().compute(bars)
    corrs = [e["best_corr"] for e in res["entries"]]
    assert corrs == sorted(corrs, reverse=True)


def test_resampled_frame_scales_lag_minutes():
    """At a 5-min frame, a reported lag of k bars means k*5 minutes."""
    bars = make_synthetic_session(n_bars=300, lead_symbol="SMH",
                                  lead_minutes=10, lead_strength=0.9, seed=4)
    res = LeadLagEngine().compute(bars, freq_minutes=5, max_lag=3, min_bars=18)
    assert res["bar_minutes"] == 5
    assert res["status"] in ("ok", "warming_up")
    if res["leader"]:
        # lag_minutes is a multiple of the 5-min frame
        assert res["leader"]["lag_minutes"] % 5 == 0
    for e in res["entries"]:
        assert e["lag_minutes"] == e["best_lag"] * 5


def test_coarser_frame_warms_up_with_few_bars():
    bars = make_synthetic_session(n_bars=40, seed=1)
    res = LeadLagEngine().compute(bars, freq_minutes=15, max_lag=2, min_bars=8)
    # 40 1-min bars -> ~3 fifteen-min bars -> below min_bars
    assert res["status"] == "warming_up"
    assert res["bar_minutes"] == 15


def test_detect_decoupling_flags_broken_rank():
    """A driver that's tightly coupled in the baseline but decoupled now
    should be flagged; one that stays coupled should not."""
    baseline = {"entries": [
        {"symbol": "SMH", "corr_at_zero": 0.85},
        {"symbol": "XLF", "corr_at_zero": 0.70},
    ]}
    current = {"entries": [
        {"symbol": "SMH", "corr_at_zero": 0.20},   # broke ranks
        {"symbol": "XLF", "corr_at_zero": 0.68},   # still coupled
    ]}
    out = LeadLagEngine.detect_decoupling(current, baseline)
    syms = [d["symbol"] for d in out]
    assert "SMH" in syms and "XLF" not in syms
    assert out[0]["drop"] >= 0.3
