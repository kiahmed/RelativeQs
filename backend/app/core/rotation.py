"""Cross-sector rotation-flow inference.

Replaces the old (noisy) lead/lag panel idea with an honest question: over the
last N minutes, *relative to QQQ*, which tracked instruments absorbed money
(up on heavy dollar-volume) and which shed it? We CANNOT see real fund flows
(creations/redemptions are end-of-day), so this is an EDUCATED INFERENCE across
a fixed universe from **relative return + dollar-volume**. If QQQ falls and
nothing in the universe lights up, the honest verdict is "unaccounted" — money
went to cash / bonds / names we don't track. The universe is deliberately broad
(small-cap IWM, broad SPY/DIA, all sectors, bonds TLT, gold GLD) so the common
escape routes are actually represented.

Pure compute: feed it aligned 1m `close` and `volume` frames (time x symbol);
no I/O here. `fetch_ohlcv()` (yfinance) is a convenience for validation/wiring.
"""
from __future__ import annotations

from typing import Dict, List, Optional, Sequence
import numpy as np
import pandas as pd

SUBJECT = "QQQ"

# Broad enough to contain the real alternatives to QQQ. XLK/SMH/MAGS/IGV are
# intentionally EXCLUDED — they ARE QQQ's own holdings (co-move, no rotation
# signal). See [[lead-runner-experiment]] for why that overlap is fatal.
ROTATION_UNIVERSE: List[str] = [
    "QQQ",                                  # subject
    "SPY", "IWM", "DIA",                    # broad / small-cap / old-economy
    "XLF", "XLE", "XLI", "XLV", "XLP",      # sectors...
    "XLU", "XLY", "XLB", "XLRE",
    "TLT", "GLD",                           # risk-off escape routes
]

DISPLAY_NAMES: Dict[str, str] = {
    "QQQ": "Nasdaq-100", "SPY": "S&P 500", "IWM": "Small caps", "DIA": "Dow",
    "XLF": "Financials", "XLE": "Energy", "XLI": "Industrials", "XLV": "Health",
    "XLP": "Staples", "XLU": "Utilities", "XLY": "Discretionary",
    "XLB": "Materials", "XLRE": "Real estate", "TLT": "Long bonds", "GLD": "Gold",
}

WINDOWS_MIN: Sequence[int] = (15, 30, 60)

# Heuristic thresholds (tunable). A move "counts" as rotation only with volume
# behind it and a minimum relative magnitude — keeps tiny drifts out.
_VOL_SURGE = 1.15          # window $-vol/min must be >=1.15x the session norm
_MIN_REL = 0.0008          # 8 bps of relative move vs QQQ to register a tag
_MIN_SUBJECT_MOVE = 0.0005 # QQQ must move >5 bps for a directional read
_COUPLED_SAME_SIGN = 0.80  # >=80% of universe sharing QQQ's sign...
_COUPLED_DISP = 0.0015     # ...with low dispersion => coupled, not rotating


def _window_slice(frame: pd.DataFrame, minutes: int) -> pd.DataFrame:
    """Last `minutes` of bars (assumes ~1m bars; uses bar count, robust to gaps)."""
    if frame is None or frame.empty:
        return pd.DataFrame()
    return frame.iloc[-minutes:] if len(frame) > minutes else frame


def _ret(close_win: pd.DataFrame) -> pd.Series:
    """Simple return over the window, per symbol (first valid -> last valid)."""
    out = {}
    for sym in close_win.columns:
        s = close_win[sym].dropna()
        out[sym] = float(s.iloc[-1] / s.iloc[0] - 1.0) if len(s) >= 2 else np.nan
    return pd.Series(out)


def _dollar_vol(close: pd.DataFrame, volume: pd.DataFrame, minutes: int) -> pd.Series:
    """Per-minute dollar volume in the window / per-minute dollar volume over the
    whole available session => a 'how busy vs normal' surge ratio per symbol."""
    cw, vw = _window_slice(close, minutes), _window_slice(volume, minutes)
    win_dv = (cw * vw).sum()
    win_min = max(1, len(cw))
    base_dv = (close * volume).sum()
    base_min = max(1, len(close))
    ratio = {}
    for sym in close.columns:
        wr = (win_dv.get(sym, 0) or 0) / win_min
        br = (base_dv.get(sym, 0) or 0) / base_min
        ratio[sym] = float(wr / br) if br > 0 else 1.0
    return pd.Series(ratio)


def _tag(rel: float, ret: float, surge: float) -> str:
    """IN = outperforming QQQ AND up AND busy; OUT = underperforming AND down AND
    busy; else neutral. 'Busy' (volume surge) is required so we don't read drift."""
    if np.isnan(rel) or np.isnan(ret):
        return "neutral"
    if rel >= _MIN_REL and ret > 0 and surge >= _VOL_SURGE:
        return "in"
    if rel <= -_MIN_REL and ret < 0 and surge >= _VOL_SURGE:
        return "out"
    return "neutral"


def _regime(rets: pd.Series, subject_ret: float) -> str:
    """Coupled (broad move, not rotation) vs rotating (dispersion + divergence)."""
    others = rets.drop(labels=[SUBJECT], errors="ignore").dropna()
    if others.empty or np.isnan(subject_ret):
        return "warming_up"
    same_sign = float((np.sign(others) == np.sign(subject_ret)).mean())
    disp = float(others.std())
    if same_sign >= _COUPLED_SAME_SIGN and disp < _COUPLED_DISP:
        return "coupled"
    return "rotating"


def _summarize(rows: List[dict], subject_ret: float, regime: str) -> dict:
    """Turn the per-symbol tags into a one-line flow read. 'unaccounted' when QQQ
    moved but nothing in the universe absorbed/sourced it on volume."""
    into = [r["symbol"] for r in rows if r["tag"] == "in"]
    out_of = [r["symbol"] for r in rows if r["tag"] == "out"]
    if regime == "coupled":
        return {"direction": "broad", "into": [], "from": [], "unaccounted": False,
                "text": "Broad move — whole universe together, not rotation."}
    if abs(subject_ret) < _MIN_SUBJECT_MOVE:
        return {"direction": "flat", "into": [], "from": [], "unaccounted": False,
                "text": "QQQ roughly flat — no clear rotation."}
    if subject_ret < 0:  # QQQ sold — where did it go?
        dest = into
        if not dest:
            return {"direction": "qqq_out", "into": [], "from": [], "unaccounted": True,
                    "text": "QQQ sold, but no tracked destination lit up — "
                            "likely cash / bonds / untracked names."}
        names = ", ".join(f"{DISPLAY_NAMES.get(s, s)}" for s in dest[:3])
        return {"direction": "qqq_out", "into": dest, "from": [], "unaccounted": False,
                "text": f"QQQ bleeding → {names}."}
    # QQQ bid — what got sold to fund it?
    src = out_of
    if not src:
        return {"direction": "qqq_in", "into": [], "from": [], "unaccounted": True,
                "text": "QQQ bid, no tracked source drained — fresh cash / untracked."}
    names = ", ".join(f"{DISPLAY_NAMES.get(s, s)}" for s in src[:3])
    return {"direction": "qqq_in", "into": [], "from": src, "unaccounted": False,
            "text": f"QQQ fed ← {names}."}


def compute_rotation(close: pd.DataFrame, volume: pd.DataFrame,
                     windows: Sequence[int] = WINDOWS_MIN,
                     subject: str = SUBJECT) -> dict:
    """Per-window rotation read. `close`/`volume`: 1m frames (time index, symbol
    columns). Returns a JSON-able dict for the API/UI."""
    cols = [s for s in ROTATION_UNIVERSE if s in close.columns]
    close, volume = close[cols], volume.reindex(columns=cols)
    out_windows: Dict[str, dict] = {}
    for m in windows:
        cw = _window_slice(close, m)
        rets = _ret(cw)
        surge = _dollar_vol(close, volume, m)
        subj_ret = float(rets.get(subject, np.nan))
        regime = _regime(rets, subj_ret)
        rows: List[dict] = []
        for sym in cols:
            if sym == subject:
                continue
            ret = float(rets.get(sym, np.nan))
            rel = ret - subj_ret if not (np.isnan(ret) or np.isnan(subj_ret)) else np.nan
            sg = float(surge.get(sym, 1.0))
            rows.append({
                "symbol": sym, "name": DISPLAY_NAMES.get(sym, sym),
                "ret": None if np.isnan(ret) else round(ret, 5),
                "rel": None if np.isnan(rel) else round(rel, 5),
                "dvol_surge": round(sg, 2),
                "tag": _tag(rel, ret, sg),
            })
        # rank by flow score: relative strength weighted by volume surge
        rows.sort(key=lambda r: ((r["rel"] or 0) * r["dvol_surge"]), reverse=True)
        out_windows[f"{m}m"] = {
            "regime": regime,
            "subject_return": None if np.isnan(subj_ret) else round(subj_ret, 5),
            "subject_dvol_surge": round(float(surge.get(subject, 1.0)), 2),
            "rows": rows,
            "summary": _summarize(rows, subj_ret, regime),
        }
    return {"subject": subject, "universe": cols, "windows": out_windows}


def fetch_ohlcv(symbols: Sequence[str] = ROTATION_UNIVERSE, period: str = "1d",
                interval: str = "1m"):
    """Convenience yfinance pull -> (close, volume) frames. For validation/wiring;
    the production loop should feed frames from its own provider instead."""
    import yfinance as yf
    df = yf.download(list(symbols), period=period, interval=interval,
                     progress=False, auto_adjust=False, group_by="column")
    if df is None or df.empty:
        return pd.DataFrame(), pd.DataFrame()
    close = df["Close"].copy()
    volume = df["Volume"].copy()
    if isinstance(close, pd.Series):  # single symbol edge case
        close = close.to_frame(symbols[0]); volume = volume.to_frame(symbols[0])
    return close.dropna(how="all"), volume.reindex(close.index)
