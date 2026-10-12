"""Overnight / pre-market board.

A purely DESCRIPTIVE pre-open read (validated null on forecasting, so it makes
NO hold/fade prediction): the overnight tape (US futures, Asia semis, Europe),
the day's biggest Nasdaq-100 movers, and for each whether it's moving WITH the
tape or against it and WITH the crowd or alone. The one validated forward
element is a faint pre-open directional lean from the overnight Asia complex
(~60% historically) — shown only before the bell and clearly labelled as a lean,
not a call.

Walled off from the intraday score/projection exactly like the AI-dependency and
(retired) trend-regime metrics: this never feeds scoring. It's situational
awareness for the open, nothing more.

The engine is pure: compute() takes already-extracted quotes/tape and returns the
board dict. All yfinance I/O lives in the market-data service.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# Coarse sector map for the liquid Nasdaq-100 names — used only for the
# "sector-wide vs lone mover" tag. Unmapped names fall back to market breadth.
SECTORS: Dict[str, str] = {
    # semis
    "NVDA": "semis", "AMD": "semis", "AVGO": "semis", "MU": "semis", "INTC": "semis",
    "LRCX": "semis", "AMAT": "semis", "KLAC": "semis", "ASML": "semis", "MRVL": "semis",
    "MCHP": "semis", "ADI": "semis", "NXPI": "semis", "ON": "semis", "QCOM": "semis", "TXN": "semis", "ARM": "semis",
    # software / internet
    "MSFT": "software", "GOOGL": "software", "GOOG": "software", "META": "software",
    "ADBE": "software", "CRM": "software", "NOW": "software", "INTU": "software",
    "PANW": "software", "CRWD": "software", "FTNT": "software", "SNPS": "software",
    "CDNS": "software", "WDAY": "software", "ADSK": "software", "TEAM": "software",
    "DDOG": "software", "PLTR": "software", "MDB": "software", "CSCO": "software", "ANET": "software",
    # consumer / megacap
    "AAPL": "megacap", "AMZN": "consumer", "TSLA": "consumer", "NFLX": "consumer",
    "COST": "consumer", "WMT": "consumer", "PEP": "consumer", "MDLZ": "consumer",
    "SBUX": "consumer", "BKNG": "consumer", "MAR": "consumer", "ABNB": "consumer", "PDD": "consumer",
    # biotech / health
    "AMGN": "biotech", "GILD": "biotech", "REGN": "biotech", "VRTX": "biotech",
    "MRNA": "biotech", "ISRG": "biotech", "DXCM": "biotech", "BIIB": "biotech",
}


class PremarketBoard:
    def __init__(self, top_n: int = 8, min_gap: float = 0.01, force_open: bool = False):
        self.top_n = top_n
        self.min_gap = min_gap  # don't surface sub-1% noise as a "mover"
        self.force_open = force_open  # dev/testing: never auto-collapse off-hours

    def _collapse(self, phase: str) -> bool:
        return False if self.force_open else phase in ("regular", "after", "closed")

    # ------------------------------------------------------------------ #
    def _empty(self, status: str, asof_iso: str = "", phase: str = "closed") -> Dict[str, Any]:
        return {
            "status": status,
            "asof": asof_iso,
            "phase": phase,
            "collapse": self._collapse(phase),
            "minutes_to_open": None,
            "tape": {"nq": None, "es": None, "asia": None, "europe": None,
                     "breadth_up": None, "cap_breadth_up": None},
            "open_lean": {"dir": "flat", "hist_hit": 0.60, "basis": "none"},
            "movers": [],
        }

    @staticmethod
    def _phase_and_eta(asof: pd.Timestamp):
        """ET-clock phase + minutes to the 09:30 open (None outside pre-open)."""
        if asof is None:
            return "closed", None
        wd = asof.weekday()
        mins = asof.hour * 60 + asof.minute
        OPEN, CLOSE, PRE = 9 * 60 + 30, 16 * 60, 4 * 60
        if wd >= 5:
            return "closed", None
        if PRE <= mins < OPEN:
            return "pre", OPEN - mins
        if OPEN <= mins < OPEN + 30:
            return "open", 0
        if OPEN + 30 <= mins < CLOSE:
            return "regular", 0
        if CLOSE <= mins < 20 * 60:
            return "after", None
        return "closed", None

    @staticmethod
    def _pct(x) -> Optional[float]:
        return None if x is None or (isinstance(x, float) and not np.isfinite(x)) else round(float(x), 4)

    # ------------------------------------------------------------------ #
    def compute(self, quotes: Dict[str, Dict[str, float]], weights: Dict[str, float],
                tape: Dict[str, Optional[float]], asof: pd.Timestamp) -> Dict[str, Any]:
        """
        quotes:  {sym: {prev_close, ref, pm_early, pm_late}}  (ref = settled open
                 once the bell rings, else the latest pre-market print)
        weights: {sym: weight}  (Nasdaq-100 index weights, for cap-weighted breadth)
        tape:    {nq, es, asia, europe}  signed overnight % moves (any may be None)
        asof:    ET-localized (or naive-ET) timestamp of the read
        """
        asof_iso = asof.isoformat() if asof is not None else ""
        phase, eta = self._phase_and_eta(asof)

        rows = []
        for sym, q in quotes.items():
            pc = q.get("prev_close")
            ref = q.get("ref")
            if not pc or not ref or pc <= 0:
                continue
            gap = ref / pc - 1.0
            # move since the settled 09:30 open (None until the bell rings)
            last, opened = q.get("last"), q.get("opened")
            since_open = (last / ref - 1.0) if (opened and last and ref) else None
            rows.append({"symbol": sym, "gap": gap, "since_open": since_open,
                         "pm_early": q.get("pm_early"), "pm_late": q.get("pm_late")})
        if not rows:
            return self._empty("warming_up", asof_iso, phase)

        df = pd.DataFrame(rows)

        # market breadth across the scanned universe (equal-weight and cap-weight)
        up = df["gap"] > 0
        breadth_up = float(up.mean())
        w = df["symbol"].map(lambda s: weights.get(s, 0.0)).to_numpy()
        cap_up = float((w[up.to_numpy()].sum() / w.sum())) if w.sum() > 0 else breadth_up

        # per-sector direction (for the sector-wide vs lone tag)
        df["sector"] = df["symbol"].map(lambda s: SECTORS.get(s))
        sector_dir = {}
        for sec, g in df.dropna(subset=["sector"]).groupby("sector"):
            if len(g) >= 3:
                sector_dir[sec] = float((g["gap"] > 0).mean())

        nq = tape.get("nq")
        tape_sign = np.sign(nq) if nq not in (None, 0) else (np.sign(tape.get("es") or 0))

        movers = []
        for _, r in df.reindex(df["gap"].abs().sort_values(ascending=False).index).iterrows():
            if abs(r["gap"]) < self.min_gap:
                break
            sym, gap, sec = r["symbol"], r["gap"], r["sector"]
            gsign = np.sign(gap)
            # with-tape vs counter-tape
            vs_tape = None
            if tape_sign != 0:
                vs_tape = "with_tape" if gsign == tape_sign else "counter_tape"
            # sector-wide vs lone (fall back to market breadth when sector unknown)
            crowd = None
            if sec in sector_dir:
                frac_same = sector_dir[sec] if gap > 0 else (1 - sector_dir[sec])
                crowd = "sector_wide" if frac_same >= 0.6 else ("lone" if frac_same <= 0.4 else "mixed")
            else:
                mkt_same = breadth_up if gap > 0 else (1 - breadth_up)
                crowd = "with_market" if mkt_same >= 0.6 else ("against_market" if mkt_same <= 0.4 else "mixed")
            # did the pre-market move hold into the read, or fade? (descriptive)
            sustain = None
            if r.get("pm_early") and r.get("pm_late") and r["pm_early"] > 0:
                sustain = "holding" if gsign * (r["pm_late"] - r["pm_early"]) >= 0 else "fading"
            movers.append({
                "symbol": sym,
                "gap": self._pct(gap),
                "since_open": self._pct(r.get("since_open")),
                "dir": "up" if gap > 0 else "down",
                "sector": sec,
                "weight": self._pct(weights.get(sym)),
                "vs_tape": vs_tape,
                "crowd": crowd,
                "sustain": sustain,
            })
            if len(movers) >= self.top_n:
                break

        # validated pre-open lean: overnight Asia complex -> tech open dir (~60%)
        asia = tape.get("asia")
        if asia not in (None, 0):
            lean = {"dir": "up" if asia > 0 else "down", "hist_hit": 0.60, "basis": "asia"}
        elif tape_sign != 0:
            lean = {"dir": "up" if tape_sign > 0 else "down", "hist_hit": 0.60, "basis": "futures"}
        else:
            lean = {"dir": "flat", "hist_hit": 0.60, "basis": "none"}

        return {
            "status": "ok",
            "asof": asof_iso,
            "phase": phase,
            "collapse": self._collapse(phase),
            "minutes_to_open": eta,
            "tape": {
                "nq": self._pct(tape.get("nq")),
                "es": self._pct(tape.get("es")),
                "asia": self._pct(asia),
                "europe": self._pct(tape.get("europe")),
                "breadth_up": round(breadth_up, 3),
                "cap_breadth_up": round(cap_up, 3),
            },
            "open_lean": lean,
            "movers": movers,
        }
