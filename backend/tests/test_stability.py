"""Tests for the cross-day stability engine (design doc section 6).

All offline: synthetic multi-session data only, no network, no real Redis.
"""
import pandas as pd
import pytest

from app.core.lead_lag import LeadLagEngine
from app.core.stability import StabilityEngine

try:
    from synthetic import make_synthetic_session
except ImportError:  # pragma: no cover - rootdir fallback
    from tests.synthetic import make_synthetic_session


def _session(date_str, lead_symbol="SMH", seed=7):
    """Build a (date_str, frame) tuple with a planted leader on that ET date."""
    frame = make_synthetic_session(
        n_bars=240, lead_symbol=lead_symbol, lead_minutes=3,
        lead_strength=0.9, seed=seed, start=date_str + " 09:30",
    )
    return (date_str, frame)


def _current_lead_lag(frame):
    return LeadLagEngine().compute(frame)


def test_consistent_leader_tradeable():
    """Same planted leader across days -> tradeable True, high persistence."""
    sessions = [
        _session("2026-05-28", seed=1),
        _session("2026-05-29", seed=2),
        _session("2026-06-01", seed=3),
        _session("2026-06-02", seed=4),
    ]
    current = _current_lead_lag(sessions[-1][1])
    assert current["leader"] is not None

    res = StabilityEngine().compute(sessions, current)
    assert res["status"] == "ok"
    assert res["verdict"] == "tradeable"
    assert res["tradeable"] is True
    assert res["leader"] == "SMH"
    assert res["lead_persistence"] >= 0.6
    assert res["sessions_analyzed"] == 4
    assert res["median_lag"] > 0


def test_changing_leader_unstable():
    """A different planted leader each day -> unstable."""
    sessions = [
        _session("2026-05-28", lead_symbol="SMH", seed=1),
        _session("2026-05-29", lead_symbol="IGV", seed=2),
        _session("2026-06-01", lead_symbol="XLE", seed=3),
        _session("2026-06-02", lead_symbol="IWM", seed=4),
    ]
    # current leader comes from today's frame (IWM)
    current = _current_lead_lag(sessions[-1][1])
    assert current["leader"] is not None

    res = StabilityEngine().compute(sessions, current)
    assert res["status"] == "ok"
    assert res["verdict"] == "unstable"
    assert res["tradeable"] is False
    assert res["lead_persistence"] < 0.6


def test_single_session_gathering():
    """Only one session -> gathering (below min_sessions)."""
    sessions = [_session("2026-06-02", seed=5)]
    current = _current_lead_lag(sessions[-1][1])

    res = StabilityEngine().compute(sessions, current)
    assert res["status"] == "gathering"
    assert res["verdict"] == "gathering"
    assert res["tradeable"] is False
    assert res["sessions_analyzed"] == 1


def test_no_leader():
    """current_lead_lag with no leader -> no_leader verdict."""
    sessions = [_session("2026-06-02", seed=5)]
    res = StabilityEngine().compute(sessions, {"leader": None})
    assert res["status"] == "ok"
    assert res["verdict"] == "no_leader"
    assert res["leader"] is None
    assert res["tradeable"] is False


def test_full_shape_on_bad_input():
    """Empty sessions + no leader still returns a fully-populated dict."""
    res = StabilityEngine().compute([], {})
    for key in ("status", "leader", "sessions_analyzed", "lead_persistence",
                "intraday_consistency", "median_lag", "tradeable",
                "verdict", "message"):
        assert key in res
    assert res["verdict"] == "no_leader"


def test_intraday_consistency_populated():
    """Tradeable case reports an intraday_consistency in 0..1."""
    sessions = [
        _session("2026-05-28", seed=1),
        _session("2026-06-02", seed=4),
    ]
    current = _current_lead_lag(sessions[-1][1])
    res = StabilityEngine().compute(sessions, current)
    assert 0.0 <= res["intraday_consistency"] <= 1.0
