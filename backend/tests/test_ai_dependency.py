"""Tests for the AI-capex dependency engine.

All offline: synthetic daily-close data only, no network, no real Redis.
"""
import numpy as np
import pandas as pd
import pytest

from app.core.ai_dependency import AIDependencyEngine


BASKET = [
    {"key": "memory", "label": "Memory", "members": [
        {"symbol": "DRAM", "label": "Memory ETF"},
        {"symbol": "MU", "label": "Micron"},
    ]},
    {"key": "power", "label": "Power", "members": [
        {"symbol": "AIPO", "label": "AI power ETF"},
    ]},
    {"key": "grid", "label": "Grid", "members": [
        {"symbol": "GRID", "label": "Smart-grid ETF"},
    ]},
]


def _engine(**kw):
    kw.setdefault("target", "QQQ")
    kw.setdefault("basket", BASKET)
    kw.setdefault("window", 21)
    kw.setdefault("min_obs", 10)
    kw.setdefault("change_lookback", 21)
    return AIDependencyEngine(**kw)


def _prices_from_returns(rets: dict, n: int) -> pd.DataFrame:
    idx = pd.date_range("2025-01-01", periods=n, freq="B")
    out = {}
    for sym, r in rets.items():
        out[sym] = 100.0 * np.cumprod(1.0 + np.asarray(r))
    return pd.DataFrame(out, index=idx)


def _coupled_session(n=120, dep=0.95, seed=1):
    """QQQ daily returns driven mostly by the basket composite."""
    rng = np.random.default_rng(seed)
    base = rng.normal(0.0, 0.012, n)  # the shared AI-complex factor
    syms = ["DRAM", "MU", "AIPO", "GRID"]
    rets = {s: base + rng.normal(0.0, 0.004, n) for s in syms}
    comp = np.mean([rets[s] for s in syms], axis=0)
    rets["QQQ"] = dep * comp + np.sqrt(max(1 - dep * dep, 0)) * rng.normal(0.0, 0.012, n)
    return _prices_from_returns(rets, n)


# --------------------------------------------------------------------------- #
# warming-up / degenerate                                                      #
# --------------------------------------------------------------------------- #
def test_empty_on_none():
    r = _engine().compute(None)
    assert r["status"] == "warming_up"
    assert r["dependency_trend"] == []
    assert r["themes"] == []


def test_empty_on_missing_target():
    df = _prices_from_returns({"MU": np.full(40, 0.001), "DRAM": np.full(40, 0.001)}, 40)
    r = _engine().compute(df)
    assert r["status"] == "warming_up"


def test_warming_up_too_few_rows():
    df = _coupled_session(n=8)
    r = _engine().compute(df)
    assert r["status"] == "warming_up"


# --------------------------------------------------------------------------- #
# core behaviour                                                               #
# --------------------------------------------------------------------------- #
def test_high_dependency_detected():
    df = _coupled_session(n=150, dep=0.95)
    r = _engine().compute(df)
    assert r["status"] == "ok"
    assert r["dependency_now"] > 0.5
    assert 0.0 <= r["dependency_now"] <= 1.0
    assert len(r["dependency_trend"]) > 0
    assert all(0.0 <= p["value"] <= 1.0 for p in r["dependency_trend"])


def test_low_dependency_when_independent():
    rng = np.random.default_rng(7)
    n = 150
    syms = ["DRAM", "MU", "AIPO", "GRID", "QQQ"]
    rets = {s: rng.normal(0.0, 0.012, n) for s in syms}  # all independent
    df = _prices_from_returns(rets, n)
    r = _engine().compute(df)
    assert r["status"] == "ok"
    assert r["dependency_now"] < 0.4


def test_trend_dates_sorted_and_valued():
    df = _coupled_session(n=120)
    r = _engine().compute(df)
    dates = [p["date"] for p in r["dependency_trend"]]
    assert dates == sorted(dates)
    assert r["asof"] == dates[-1]


def test_themes_present_with_members():
    df = _coupled_session(n=120)
    r = _engine().compute(df)
    keys = {t["key"] for t in r["themes"]}
    assert {"memory", "power", "grid"} <= keys
    mem = next(t for t in r["themes"] if t["key"] == "memory")
    assert {m["symbol"] for m in mem["members"]} == {"DRAM", "MU"}


# --------------------------------------------------------------------------- #
# ragged history — young funds flagged, never faked                            #
# --------------------------------------------------------------------------- #
def test_limited_history_member_flagged_not_faked():
    df = _coupled_session(n=120)
    # blank out most of DRAM's history (a young fund)
    df.loc[df.index[:-5], "DRAM"] = np.nan
    r = _engine().compute(df)
    mem = next(t for t in r["themes"] if t["key"] == "memory")
    dram = next(m for m in mem["members"] if m["symbol"] == "DRAM")
    mu = next(m for m in mem["members"] if m["symbol"] == "MU")
    assert dram["included"] is False  # too few bars
    assert dram["bars"] < 10
    assert mu["included"] is True
    # theme still computable from MU alone
    assert mem["limited_history"] is False


def test_all_basket_missing_warms_up():
    # only target present, no basket data at all
    df = _prices_from_returns({"QQQ": np.full(60, 0.001)}, 60)
    r = _engine().compute(df)
    assert r["status"] == "warming_up"


def test_all_symbols_includes_target_and_members():
    syms = _engine().all_symbols()
    assert "QQQ" in syms
    assert {"DRAM", "MU", "AIPO", "GRID"} <= set(syms)


def test_change_computed_against_lookback():
    df = _coupled_session(n=150)
    r = _engine().compute(df)
    assert "change" in r
    assert isinstance(r["change"], float)
    assert r["change_lookback_days"] == 21


def test_headline_mentions_percent():
    df = _coupled_session(n=150, dep=0.95)
    r = _engine().compute(df)
    assert "%" in r["headline"]
    assert "QQQ" in r["headline"]
