"""Tests for cross-sector rotation flow.

Pure compute on small synthetic 1m close/volume frames (no network), plus a
sqlite roundtrip for the rotation backtest store.
"""
import numpy as np
import pandas as pd
import pytest

from app.core.rotation import compute_rotation, ROTATION_UNIVERSE, SUBJECT
from app.services.rotation_store import RotationStore, compute_agreement


def _frames(rets: dict, n: int = 70, base_vol: float = 1_000_000.0,
            vol_mult: dict | None = None):
    """Build aligned 1m close+volume frames from per-symbol per-bar returns.

    `rets[sym]` is a constant per-bar return; `vol_mult[sym]` scales that
    symbol's volume relative to the flat baseline (to simulate a volume surge).
    """
    idx = pd.date_range("2026-06-09 09:30", periods=n, freq="1min")
    vol_mult = vol_mult or {}
    close = {}
    volume = {}
    for sym in ROTATION_UNIVERSE:
        r = rets.get(sym, 0.0)
        close[sym] = 100.0 * np.cumprod(1.0 + np.full(n, r))
        v = np.full(n, base_vol)
        # concentrate the surge in the last 15 bars so window dvol > session norm
        m = vol_mult.get(sym, 1.0)
        if m != 1.0:
            v = v.astype(float)
            v[-15:] *= m
        volume[sym] = v
    return pd.DataFrame(close, index=idx), pd.DataFrame(volume, index=idx)


def test_qqq_out_into_sector_on_volume():
    # QQQ falls; XLF rises hard on a clear volume surge => tagged "in", and the
    # summary should read qqq_out with XLF in `into`.
    close, volume = _frames(
        {"QQQ": -0.0004, "XLF": 0.0005},
        vol_mult={"XLF": 5.0},
    )
    out = compute_rotation(close, volume)
    w = out["windows"]["15m"]
    xlf = next(r for r in w["rows"] if r["symbol"] == "XLF")
    assert xlf["tag"] == "in"
    assert w["summary"]["direction"] == "qqq_out"
    assert "XLF" in w["summary"]["into"]
    assert w["summary"]["unaccounted"] is False


def test_qqq_out_nothing_on_volume_is_unaccounted():
    # QQQ falls but nothing else lights up on volume => honest "unaccounted".
    close, volume = _frames({"QQQ": -0.0006})
    out = compute_rotation(close, volume)
    w = out["windows"]["15m"]
    assert w["summary"]["direction"] == "qqq_out"
    assert w["summary"]["unaccounted"] is True
    assert w["summary"]["into"] == []


def test_coupled_regime_when_broad_and_low_dispersion():
    # Everything drifts up together by the same small amount => coupled, not
    # rotation (broad move, low cross-sectional dispersion).
    rets = {sym: 0.0003 for sym in ROTATION_UNIVERSE}
    close, volume = _frames(rets)
    out = compute_rotation(close, volume)
    w = out["windows"]["15m"]
    assert w["regime"] == "coupled"
    assert w["summary"]["direction"] == "broad"


def test_rotation_contract_keys_present():
    close, volume = _frames({"QQQ": -0.0004, "XLF": 0.0005}, vol_mult={"XLF": 5.0})
    out = compute_rotation(close, volume)
    assert out["subject"] == SUBJECT
    for wkey in ("15m", "30m", "60m"):
        w = out["windows"][wkey]
        assert set(["regime", "subject_return", "subject_dvol_surge", "rows",
                    "summary"]).issubset(w.keys())
        for row in w["rows"]:
            assert set(["symbol", "name", "ret", "rel", "dvol_surge",
                        "tag"]).issubset(row.keys())


def test_store_roundtrip(tmp_path):
    db = tmp_path / "rotation.db"
    store = RotationStore(db_path=str(db))
    intraday = {"windows": {"15m": {"summary": {"into": ["XLF"]}}}}
    daily = {"windows": {"5m": {"rows": [
        {"symbol": "XLF", "rel": 0.01}, {"symbol": "XLE", "rel": 0.005},
    ]}}}
    agreement = compute_agreement(intraday, daily)
    store.write("2026-06-09", intraday, daily, agreement)
    got = store.get_by_date("2026-06-09")
    assert got is not None
    assert got["agreement"] == agreement
    assert got["intraday_final"]["windows"]["15m"]["summary"]["into"] == ["XLF"]
    hist = store.history(limit=10)
    assert len(hist) == 1 and hist[0]["date"] == "2026-06-09"


def test_agreement_overlap_score():
    intraday = {"windows": {"15m": {"summary": {"into": ["XLF", "XLE"]}}}}
    daily = {"windows": {"5m": {"rows": [
        {"symbol": "XLF", "rel": 0.02}, {"symbol": "GLD", "rel": 0.01},
    ]}}}
    # one of two inferred destinations (XLF) is in the daily top => 0.5
    assert compute_agreement(intraday, daily, top_n=1) == 0.5
    # no inferred destination => 0.0
    assert compute_agreement({"windows": {}}, daily) == 0.0
