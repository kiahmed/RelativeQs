"""Daily capture: row builders, health port, schedule windows, retry/skip rules."""
import asyncio
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

import pytest

from app import daily_capture as dc
from app.config import settings

ET = ZoneInfo("America/New_York")
TD = date(2026, 10, 13)  # a Tuesday


def et(h, m, d=TD):
    return datetime(d.year, d.month, d.day, h, m, tzinfo=ET).astimezone(timezone.utc)


BOARD = {
    "status": "ok", "asof": "2026-10-13T09:28:00-04:00", "phase": "premarket",
    "tape": {"nq": 0.004, "es": 0.002, "asia": 0.011, "europe": None,
             "breadth_up": 0.62, "cap_breadth_up": 0.7},
    "open_lean": {"dir": "up", "basis": "asia", "hist_hit": 0.6},
    "movers": [
        {"symbol": "arm", "gap": 0.06, "since_open": None, "dir": "up", "sector": "Semis",
         "weight": 0.3, "vs_tape": "counter_tape", "crowd": "lone", "sustain": "holding"},
        {"symbol": "MU", "gap": float("nan"), "dir": "down", "sector": "Semis"},
    ],
}

PRED = {
    "status": "ok", "target": "QQQ",
    "score": {"status": "ok", "probability_up": 0.62, "verdict": "continue",
              "components": {"leadership": 0.3, "broadening": 0.2, "fragility": 0.1},
              "momentum_30m": {"QQQ": 0.2, "XLK": 0.4, "SMH": 0.9, "XLE": -0.3}},
    "breadth": {"status": "ok", "breadth_state": "broad", "equal_weight_pct": 0.7,
                "cap_weight_pct": 0.65, "divergence": -0.05, "advancers": 70, "decliners": 30},
    "ai_dependency": {"status": "ok", "dependency_now": 0.55, "change": 0.04, "headline": "h",
                      "dependency_trend": [{"date": f"2026-09-{i:02d}", "value": i / 100}
                                           for i in range(1, 21)]},
    "confirmation": {"state": "confirmed", "message": "m"},
    "correlation_regime": {"regime": "coupled"},
    "lead_lag": {"leader": {"symbol": "SMH"}},
}
ROT = {"windows": {"30m": {"regime": "rotating", "subject_return": -0.002,
                           "summary": {"direction": "qqq_out", "text": "t"},
                           "rows": [{"symbol": "XLE", "rel": 0.01, "dvol_surge": 1.5, "tag": "in"}] * 5}}}


def test_mover_rows_shape_and_nan_scrubbed():
    rows = dc.build_mover_rows(BOARD, TD, et(9, 28))
    assert [r["symbol"] for r in rows] == ["ARM", "MU"]
    assert [r["rank"] for r in rows] == [1, 2]
    assert rows[0]["trade_date"] == "2026-10-13" and rows[0]["open_lean_basis"] == "asia"
    assert rows[1]["gap"] is None  # NaN would be invalid JSON


def test_mover_rows_empty_when_board_not_ok():
    assert dc.build_mover_rows({"status": "warming_up"}, TD, et(9, 28)) == []


def test_health_port_matches_dashboard_formula():
    # peers XLK+, SMH+, XLE- -> participation 2/3; raw = .45*.62 + .3*(2/3) + .25*.9
    score, regime = dc.derive_health(PRED)
    assert score == round((0.45 * 0.62 + 0.3 * (2 / 3) + 0.25 * 0.9) * 100)
    assert regime == "Broad Participation"
    assert dc.derive_health({"status": "warming_up"}) == (None, None)


def test_highlights_row():
    row = dc.build_highlights(PRED, ROT, {"price": 612.5}, TD, et(10, 5))
    assert row["strongest_sector"] == "SMH" and row["strongest_sector_mom"] == 0.9
    assert row["fragility_level"] == "Low" and row["direction"] == "bullish"
    assert row["breadth_state"] == "broad" and row["advancers"] == 70
    assert len(row["ai_dependency_2w"]) == dc.AI_TREND_POINTS
    assert row["ai_dependency_2w"][-1]["date"] == "2026-09-20"
    assert len(row["rotation"]["30m"]["top"]) == 3
    assert row["qqq_price"] == 612.5 and row["leader_symbol"] == "SMH"


def test_highlights_warming_up_has_nulls_not_fake_numbers():
    row = dc.build_highlights({"status": "warming_up"}, None, None, TD, et(10, 5))
    assert row["direction"] == "warming up" and row["health_score"] is None
    assert row["fragility_level"] == "Unknown" and row["rotation"] is None


class FakeMarket:
    def __init__(self, board):
        self.board = board

    async def fetch_premarket_board(self, force=False):
        return self.board


@pytest.fixture(autouse=True)
def _supabase(monkeypatch):
    monkeypatch.setattr(settings, "SUPABASE_URL", "https://x.supabase.co")
    monkeypatch.setattr(settings, "SUPABASE_SERVICE_KEY", "k")
    monkeypatch.setattr(settings, "DAILY_CAPTURE_ENABLED", True)


def make(board=BOARD, ok=True, now=None):
    calls = []

    async def writer(table, rows, conflict):
        calls.append((table, len(rows), conflict))
        return (ok, "" if ok else "boom")

    cap = dc.DailyCapture(FakeMarket(board), writer=writer, clock=lambda: now or et(9, 28))
    return cap, calls


def run_ticks(cap, *args, times=1):
    async def go():
        for _ in range(times):
            await cap.tick(*args)
            while cap._tasks:
                await asyncio.gather(*list(cap._tasks))
    asyncio.run(go())


def test_windows_and_weekend():
    cap, _ = make()
    assert cap.due_jobs(et(9, 27)) == []
    assert cap.due_jobs(et(9, 28)) == ["movers"]
    assert cap.due_jobs(et(9, 42)) == ["movers"]
    assert cap.due_jobs(et(9, 50)) == []
    assert cap.due_jobs(et(10, 5)) == ["highlights"]
    assert cap.due_jobs(et(10, 36)) == []
    assert cap.due_jobs(et(9, 28, date(2026, 10, 17))) == []  # Saturday


def test_movers_written_once_per_day():
    cap, calls = make()
    run_ticks(cap, PRED, ROT, {}, times=2)  # second cycle: already done
    assert calls == [("overnight_movers_stats", 2, "trade_date,symbol")]


def test_stale_board_is_skipped_not_filed_under_today():
    cap, calls = make(board=dict(BOARD, asof="2026-10-12T09:28:00-04:00"))
    run_ticks(cap, PRED, ROT, {})
    assert calls == [] and cap._state[f"{TD}:movers"] == "skipped"


def test_failed_write_backs_off_instead_of_retrying_every_cycle():
    cap, calls = make(ok=False)
    run_ticks(cap, PRED, ROT, {}, times=2)  # second cycle is inside the 60 s back-off
    assert len(calls) == 1 and f"{TD}:movers" not in cap._state


def test_highlights_waits_for_ready_prediction():
    cap, calls = make(now=et(10, 5))
    run_ticks(cap, {"status": "warming_up"}, None, {})
    assert calls == [] and f"{TD}:highlights" not in cap._state


def test_highlights_saved_when_ready():
    cap, calls = make(now=et(10, 5))
    run_ticks(cap, PRED, ROT, {"price": 1.0})
    assert calls == [("daily_highlights", 1, "trade_date")]


def test_disabled_without_supabase(monkeypatch):
    monkeypatch.setattr(settings, "SUPABASE_URL", "")
    cap, calls = make()
    run_ticks(cap, PRED, ROT, {})
    assert calls == []
