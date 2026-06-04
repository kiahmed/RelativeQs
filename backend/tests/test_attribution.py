"""Tests for the driver attribution engine (design doc section 3).

All offline: synthetic data only, no network, no real Redis.
"""
import numpy as np
import pandas as pd
import pytest

try:
    from synthetic import make_synthetic_session
except ImportError:  # pragma: no cover - rootdir fallback
    from tests.synthetic import make_synthetic_session

from app.core.attribution import DriverAttributionEngine


def _coincident_session(n_bars=60, driver="SMH", strength=0.95, seed=3):
    """QQQ moves (almost) entirely with `driver` contemporaneously, so the
    multivariate OLS attributes the move to that driver."""
    rng = np.random.default_rng(seed)
    idx = pd.date_range(start="2026-06-02 09:30", periods=n_bars, freq="1min")
    symbols = ["QQQ", driver, "IGV", "MAGS", "XLP"]
    noise = 0.0008

    driver_ret = 0.0003 + rng.normal(0.0, noise, n_bars)
    qqq_ret = strength * driver_ret + rng.normal(0.0, noise * 0.2, n_bars)

    rets = {}
    for sym in symbols:
        if sym == driver:
            rets[sym] = driver_ret
        elif sym == "QQQ":
            rets[sym] = qqq_ret
        else:
            rets[sym] = rng.normal(0.0, noise, n_bars)

    data = {}
    for sym in symbols:
        data[sym] = 100.0 * np.exp(np.cumsum(rets[sym]))
    return pd.DataFrame(data, index=idx)


def test_planted_driver_is_top_contributor():
    bars = _coincident_session(n_bars=60, driver="SMH", strength=0.95, seed=3)
    res = DriverAttributionEngine(window=60).compute(bars)

    assert res["status"] == "ok"
    assert res["target"] == "QQQ"
    assert res["contributors"], "expected contributors"
    top = res["contributors"][0]
    assert top["symbol"] == "SMH"
    assert abs(top["share"]) > 0.5  # majority share
    assert res["explained_share"] > 0.7
    assert 0.0 <= res["explained_share"] <= 1.0
    assert abs(res["explained_share"] + res["residual_share"] - 1.0) < 1e-9


def test_headline_mentions_top_driver():
    bars = _coincident_session(n_bars=60, driver="SMH", strength=0.95, seed=5)
    res = DriverAttributionEngine(window=60).compute(bars)
    assert "semis" in res["headline"]
    assert "SMH" in res["headline"]


def test_contributors_sorted_by_abs_share():
    bars = _coincident_session(n_bars=60, seed=9)
    res = DriverAttributionEngine(window=60).compute(bars)
    shares = [abs(c["share"]) for c in res["contributors"]]
    assert shares == sorted(shares, reverse=True)


def test_contributor_shape_and_labels():
    bars = _coincident_session(n_bars=60, seed=11)
    res = DriverAttributionEngine(window=60).compute(bars)
    for c in res["contributors"]:
        for key in ("symbol", "label", "beta", "contribution", "share", "trend"):
            assert key in c
        assert c["trend"] in ("driving", "lagging", "flat")
    labels = {c["symbol"]: c["label"] for c in res["contributors"]}
    assert labels.get("SMH") == "semis"
    assert labels.get("IGV") == "software"
    assert labels.get("MAGS") == "mega-cap"


def test_few_bars_warming_up():
    bars = _coincident_session(n_bars=5, seed=2)
    res = DriverAttributionEngine(window=30).compute(bars)
    assert res["status"] == "warming_up"
    assert res["contributors"] == []
    assert res["explained_share"] == 0.0
    assert res["residual_share"] == 1.0
    for key in ("status", "target", "window_minutes", "target_return",
                "contributors", "explained_share", "residual_share", "headline"):
        assert key in res


def test_no_data_full_shape():
    res = DriverAttributionEngine().compute(pd.DataFrame())
    assert res["status"] == "warming_up"
    for key in ("status", "target", "window_minutes", "target_return",
                "contributors", "explained_share", "residual_share", "headline"):
        assert key in res

    res2 = DriverAttributionEngine().compute(None)
    assert res2["status"] == "warming_up"


def test_target_missing_warming_up():
    bars = _coincident_session(n_bars=60, seed=4).drop(columns=["QQQ"])
    res = DriverAttributionEngine(window=60).compute(bars)
    assert res["status"] == "warming_up"


def test_no_drivers_present_warming_up():
    idx = pd.date_range(start="2026-06-02 09:30", periods=60, freq="1min")
    bars = pd.DataFrame({
        "QQQ": np.linspace(100, 101, 60),
        "XLP": np.linspace(100, 100.5, 60),
    }, index=idx)
    res = DriverAttributionEngine(window=60, drivers=["SMH", "IGV", "MAGS"]).compute(bars)
    assert res["status"] == "warming_up"


def test_window_truncation():
    """Engine only uses the last `window` bars."""
    bars = _coincident_session(n_bars=120, seed=7)
    res = DriverAttributionEngine(window=30).compute(bars)
    assert res["status"] == "ok"
    assert res["window_minutes"] == 30
