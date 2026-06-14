"""Tests for the overnight / pre-market board engine."""
import pandas as pd
from app.core.premarket import PremarketBoard


def _quotes():
    return {
        "NVDA": {"prev_close": 100, "ref": 103, "pm_early": 101, "pm_late": 103},
        "AMD":  {"prev_close": 50,  "ref": 51,  "pm_early": 50.5, "pm_late": 51},
        "AVGO": {"prev_close": 200, "ref": 205, "pm_early": 202,  "pm_late": 205},
        "LUNR": {"prev_close": 10,  "ref": 9.2, "pm_early": 9.6,  "pm_late": 9.2},
        "MSFT": {"prev_close": 400, "ref": 399, "pm_early": 400,  "pm_late": 399},
    }


_W = {"NVDA": .086, "AMD": .036, "AVGO": .034, "LUNR": .002, "MSFT": .054}
_TAPE = {"nq": 0.004, "es": 0.003, "asia": 0.011, "europe": 0.002}
_ASOF = pd.Timestamp("2026-06-12 06:40", tz="America/New_York")


def test_movers_sorted_by_abs_gap_and_tagged():
    r = PremarketBoard().compute(_quotes(), _W, _TAPE, _ASOF)
    assert r["status"] == "ok"
    gaps = [abs(m["gap"]) for m in r["movers"]]
    assert gaps == sorted(gaps, reverse=True)          # ranked by |gap|
    top = r["movers"][0]
    assert top["symbol"] == "LUNR" and top["dir"] == "down"
    assert top["vs_tape"] == "counter_tape"            # down vs up tape


def test_sub_min_gap_dropped():
    # MSFT is -0.25% — below the 1% floor, must not surface as a mover
    syms = [m["symbol"] for m in PremarketBoard(min_gap=0.01).compute(_quotes(), _W, _TAPE, _ASOF)["movers"]]
    assert "MSFT" not in syms


def test_phase_and_eta():
    b = PremarketBoard()
    assert b._phase_and_eta(pd.Timestamp("2026-06-12 06:40", tz="America/New_York")) == ("pre", 170)
    assert b._phase_and_eta(pd.Timestamp("2026-06-12 09:40", tz="America/New_York"))[0] == "open"
    assert b._phase_and_eta(pd.Timestamp("2026-06-12 11:00", tz="America/New_York"))[0] == "regular"
    assert b._phase_and_eta(pd.Timestamp("2026-06-13 10:00", tz="America/New_York"))[0] == "closed"  # Saturday


def test_collapse_after_open_window():
    reg = PremarketBoard().compute(_quotes(), _W, _TAPE,
                                   pd.Timestamp("2026-06-12 11:00", tz="America/New_York"))
    assert reg["collapse"] is True
    pre = PremarketBoard().compute(_quotes(), _W, _TAPE, _ASOF)
    assert pre["collapse"] is False


def test_open_lean_from_asia():
    up = PremarketBoard().compute(_quotes(), _W, {"nq": -0.01, "asia": 0.02}, _ASOF)["open_lean"]
    assert up["dir"] == "up" and up["basis"] == "asia"   # Asia wins over futures
    flat = PremarketBoard().compute(_quotes(), _W, {"nq": 0, "es": 0, "asia": None}, _ASOF)["open_lean"]
    assert flat["dir"] == "flat"


def test_empty_when_no_valid_quotes():
    r = PremarketBoard().compute({"X": {"prev_close": 0, "ref": 0}}, {}, _TAPE, _ASOF)
    assert r["status"] == "warming_up" and r["movers"] == []
