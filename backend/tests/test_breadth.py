"""BreadthEngine + HoldingsProvider + MarketDataService.fetch_breadth — offline."""
import pytest
import pandas as pd

from app.core.breadth import BreadthEngine
from app.services.holdings import HoldingsProvider
from app.services.market_data import MarketDataService


# --- BreadthEngine ------------------------------------------------------------

def _weights(n):
    # n equal-weight names
    return {f"S{i}": 1.0 / n for i in range(n)}


def test_broad_participation():
    w = _weights(10)
    opens = {k: 100.0 for k in w}
    lasts = {k: (101.0 if i < 8 else 99.0) for i, k in enumerate(w)}  # 8/10 up
    r = BreadthEngine().compute(opens, lasts, w)
    assert r["status"] == "ok"
    assert r["advancers"] == 8 and r["decliners"] == 2
    assert r["equal_weight_pct"] == pytest.approx(0.8)
    assert r["breadth_state"] == "broad"


def test_narrow_participation():
    w = _weights(10)
    opens = {k: 100.0 for k in w}
    lasts = {k: (101.0 if i < 3 else 99.0) for i, k in enumerate(w)}  # 3/10 up
    r = BreadthEngine().compute(opens, lasts, w)
    assert r["equal_weight_pct"] == pytest.approx(0.3)
    assert r["breadth_state"] == "narrow"


def test_cap_vs_equal_divergence():
    # one mega-cap (90% weight) up, nine tiny names down -> equal narrow, cap broad
    w = {"BIG": 0.90, **{f"S{i}": 0.10 / 9 for i in range(9)}}
    opens = {k: 100.0 for k in w}
    lasts = {"BIG": 101.0, **{f"S{i}": 99.0 for i in range(9)}}
    r = BreadthEngine().compute(opens, lasts, w)
    assert r["equal_weight_pct"] == pytest.approx(0.1)        # 1/10 names
    assert r["cap_weight_pct"] == pytest.approx(0.90, abs=1e-6)  # 90% of weight
    assert r["divergence"] > 0.12                            # mega-caps carrying
    assert "Mega-caps" in r["message"]


def test_missing_quotes_are_skipped():
    w = _weights(10)
    opens = {k: 100.0 for k in list(w)[:5]}   # only 5 have quotes
    lasts = {k: 101.0 for k in list(w)[:5]}
    r = BreadthEngine().compute(opens, lasts, w)
    assert r["measured"] == 5
    assert r["constituents_total"] == 10
    assert r["equal_weight_pct"] == pytest.approx(1.0)


def test_no_constituents_is_no_data():
    assert BreadthEngine().compute({}, {}, {})["status"] == "no_data"


def test_no_quotes_is_warming_up():
    assert BreadthEngine().compute({}, {}, _weights(5))["status"] == "warming_up"


# --- HoldingsProvider ---------------------------------------------------------

def test_holdings_snapshot_loads():
    w = HoldingsProvider().get_constituents(force_reload=True)
    assert len(w) >= 100
    assert "NVDA" in w and "AAPL" in w
    assert sum(w.values()) == pytest.approx(1.0, abs=0.02)
    assert all(v > 0 for v in w.values())


def test_holdings_missing_file_is_empty(tmp_path):
    HoldingsProvider._cache = None
    w = HoldingsProvider(snapshot_path=tmp_path / "nope.json").get_constituents(force_reload=True)
    assert w == {}
    HoldingsProvider._cache = None  # reset for other tests


# --- MarketDataService.fetch_breadth (patched download, no network) -----------

@pytest.mark.asyncio
async def test_fetch_breadth_offline(monkeypatch):
    svc = MarketDataService(mode="yahoo")
    HoldingsProvider._cache = None
    weights = HoldingsProvider().get_constituents(force_reload=True)
    syms = list(weights.keys())

    # synthetic 2-row close frame: most names finish above their open
    idx = pd.to_datetime(["2026-06-03 09:30", "2026-06-03 15:59"])
    data = {}
    for i, s in enumerate(syms):
        last = 101.0 if i % 3 != 0 else 99.0  # ~2/3 advancing
        data[s] = [100.0, last]
    frame = pd.DataFrame(data, index=idx)

    def _fake_dl(self, symbols, period="1d", interval="1m"):
        return frame[[s for s in symbols if s in frame.columns]]

    monkeypatch.setattr(MarketDataService, "_download_intraday_history", _fake_dl)

    r = await svc.fetch_breadth()
    assert r["status"] == "ok"
    assert r["measured"] == len(syms)
    assert r["advancers"] > 0 and r["decliners"] > 0
    assert 0.0 <= r["equal_weight_pct"] <= 1.0
    assert 0.0 <= r["cap_weight_pct"] <= 1.0
