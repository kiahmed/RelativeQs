"""Tests for the correlation regime engine (design doc section 5).

All offline: synthetic data only, no network, no real Redis.
"""
import numpy as np
import pandas as pd

from app.core.correlation_regime import CorrelationRegimeEngine

try:
    from synthetic import make_synthetic_session
except ImportError:  # pragma: no cover - import path fallback
    from tests.synthetic import make_synthetic_session


SYMBOLS = ["QQQ", "XLK", "SMH", "MAGS", "IGV", "XLY", "XLF"]


def _one_factor_session(n_bars=120, n_syms=7, seed=1):
    """All symbols are largely driven by one common factor => high pairwise corr."""
    rng = np.random.default_rng(seed)
    idx = pd.date_range(start="2026-06-02 09:30", periods=n_bars, freq="1min")
    factor = rng.normal(0.0, 0.001, n_bars)
    data = {}
    for i in range(n_syms):
        # 90% common factor + small idiosyncratic noise
        ret = 0.9 * factor + rng.normal(0.0, 0.0002, n_bars)
        base = 100.0 + rng.uniform(-5.0, 5.0)
        data[SYMBOLS[i]] = base * np.exp(np.cumsum(ret))
    return pd.DataFrame(data, index=idx)


def _independent_session(n_bars=120, n_syms=7, seed=2):
    """Every symbol is an independent random walk => near-zero pairwise corr."""
    rng = np.random.default_rng(seed)
    idx = pd.date_range(start="2026-06-02 09:30", periods=n_bars, freq="1min")
    data = {}
    for i in range(n_syms):
        ret = rng.normal(0.0, 0.001, n_bars)
        base = 100.0 + rng.uniform(-5.0, 5.0)
        data[SYMBOLS[i]] = base * np.exp(np.cumsum(ret))
    return pd.DataFrame(data, index=idx)


def test_one_factor_is_coupled_and_reliable():
    bars = _one_factor_session(n_bars=120, seed=7)
    res = CorrelationRegimeEngine().compute(bars)
    assert res["status"] == "ok"
    assert res["regime"] == "coupled"
    assert res["signals_reliable"] is True
    assert res["avg_pairwise_corr"] >= 0.6


def test_independent_walks_are_fragmented_and_unreliable():
    bars = _independent_session(n_bars=120, seed=13)
    res = CorrelationRegimeEngine().compute(bars)
    assert res["status"] == "ok"
    assert res["regime"] == "fragmented"
    assert res["signals_reliable"] is False
    assert res["avg_pairwise_corr"] <= 0.3


def test_few_bars_warming_up():
    bars = _one_factor_session(n_bars=5, seed=3)
    res = CorrelationRegimeEngine(window=30).compute(bars)
    assert res["status"] == "warming_up"
    # fully-populated neutral shape
    for key in ("regime", "avg_pairwise_corr", "dispersion",
                "signals_reliable", "message"):
        assert key in res


def test_too_few_symbols_warming_up():
    bars = _one_factor_session(n_bars=120, n_syms=2, seed=4)
    res = CorrelationRegimeEngine().compute(bars)
    assert res["status"] == "warming_up"


def test_empty_and_none_full_shape():
    for arg in (pd.DataFrame(), None):
        res = CorrelationRegimeEngine().compute(arg)
        assert res["status"] == "warming_up"
        for key in ("status", "regime", "avg_pairwise_corr", "dispersion",
                    "signals_reliable", "message"):
            assert key in res


def test_synthetic_session_reaches_ok():
    """The shared planted-lead session has confirmers + leader driving QQQ,
    so it should be measurable (status ok)."""
    bars = make_synthetic_session(n_bars=120, seed=5)
    res = CorrelationRegimeEngine().compute(bars)
    assert res["status"] == "ok"
    assert res["regime"] in ("coupled", "transitional", "fragmented")
