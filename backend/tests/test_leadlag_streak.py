"""Tests for the lead/lag streak filter (consecutive-occurrence promotion)."""
from app.services.market_data import MarketDataService


def _svc():
    return MarketDataService(mode="mock")


def _leader(sym="SMH", lag=15):
    return {"symbol": sym, "lag_minutes": lag, "corr": 0.6, "beta": 1.0}


def test_confirms_after_three_consecutive_new_bars():
    s = _svc()
    st = s._update_leadlag_streak("15min", _leader(), "t1", 15)
    assert st["count"] == 1 and st["confirmed"] is False
    st = s._update_leadlag_streak("15min", _leader(), "t2", 15)
    assert st["count"] == 2 and st["confirmed"] is False
    st = s._update_leadlag_streak("15min", _leader(), "t3", 15)
    assert st["count"] == 3 and st["confirmed"] is True


def test_same_bar_does_not_advance_streak():
    s = _svc()
    s._update_leadlag_streak("15min", _leader(), "t1", 15)
    st = s._update_leadlag_streak("15min", _leader(), "t1", 15)  # same window_end
    assert st["count"] == 1  # held, not advanced


def test_leader_change_resets_streak():
    s = _svc()
    s._update_leadlag_streak("15min", _leader("SMH"), "t1", 15)
    s._update_leadlag_streak("15min", _leader("SMH"), "t2", 15)
    st = s._update_leadlag_streak("15min", _leader("XLF"), "t3", 15)
    assert st["symbol"] == "XLF" and st["count"] == 1 and st["confirmed"] is False


def test_no_leader_resets():
    s = _svc()
    s._update_leadlag_streak("15min", _leader(), "t1", 15)
    st = s._update_leadlag_streak("15min", None, "t2", 15)
    assert st["count"] == 0 and st["symbol"] is None and st["confirmed"] is False


def test_lag_tolerance_keeps_streak():
    s = _svc()
    s._update_leadlag_streak("15min", _leader("SMH", 15), "t1", 15)
    st = s._update_leadlag_streak("15min", _leader("SMH", 30), "t2", 15)  # within 1 bar
    assert st["count"] == 2
