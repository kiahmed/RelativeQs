"""Nasdaq-100 breadth engine.

Measures real participation under QQQ from its ~100 underlying constituents,
both ways from the SAME data (each stock's session open + latest price):

- equal_weight_pct: share of constituents advancing (every stock counts 1) —
  true breadth, "how many names are participating".
- cap_weight_pct: share of index WEIGHT advancing (weighted by each name's QQQ
  weight) — "is the move real for the index", since QQQ is heavily top-weighted.

The gap between them (divergence) is the signal: cap >> equal means a few
mega-caps are carrying QQQ; equal >> cap means broad strength the big names lag.
"""
from typing import Dict, Any
import logging

logger = logging.getLogger(__name__)


class BreadthEngine:
    def __init__(self, target: str = None):
        try:
            from app.config import settings
            self.target = target or getattr(settings, "BREADTH_TARGET", "QQQ")
        except Exception:
            self.target = target or "QQQ"

    def _empty(self, status: str, total: int = 0) -> Dict[str, Any]:
        return {
            "status": status,
            "target": self.target,
            "constituents_total": int(total),
            "measured": 0,
            "advancers": 0,
            "decliners": 0,
            "unchanged": 0,
            "equal_weight_pct": 0.0,
            "cap_weight_pct": 0.0,
            "breadth_state": "unknown",
            "divergence": 0.0,
            "message": "Breadth is warming up — no constituent quotes yet.",
        }

    def compute(
        self,
        opens: Dict[str, float],
        lasts: Dict[str, float],
        weights: Dict[str, float],
    ) -> Dict[str, Any]:
        """opens/lasts: {ticker: price}; weights: {ticker: index weight fraction}.
        A constituent is 'measured' only when it has a finite open and last."""
        total = len(weights)
        if not weights:
            return self._empty("no_data", total)

        adv = dec = unch = 0
        adv_weight = 0.0
        measured_weight = 0.0
        measured = 0

        for sym, w in weights.items():
            o = opens.get(sym)
            l = lasts.get(sym)
            if o is None or l is None:
                continue
            try:
                o = float(o)
                l = float(l)
            except (TypeError, ValueError):
                continue
            if o <= 0 or l != l or o != o:  # non-positive or NaN
                continue
            measured += 1
            w = float(w)
            measured_weight += w
            if l > o:
                adv += 1
                adv_weight += w
            elif l < o:
                dec += 1
            else:
                unch += 1

        if measured == 0:
            return self._empty("warming_up", total)

        equal_weight_pct = adv / measured
        cap_weight_pct = (adv_weight / measured_weight) if measured_weight > 0 else 0.0
        divergence = cap_weight_pct - equal_weight_pct

        if equal_weight_pct >= 0.6:
            state = "broad"
        elif equal_weight_pct >= 0.4:
            state = "mixed"
        else:
            state = "narrow"

        message = (
            f"{adv}/{measured} Nasdaq-100 names advancing "
            f"({round(equal_weight_pct * 100)}% equal-weight, "
            f"{round(cap_weight_pct * 100)}% cap-weight)."
        )
        if divergence >= 0.12:
            message += " Mega-caps are carrying the move — narrow under the surface."
        elif divergence <= -0.12:
            message += " Broad participation the largest names are lagging."

        result = {
            "status": "ok",
            "target": self.target,
            "constituents_total": int(total),
            "measured": int(measured),
            "advancers": int(adv),
            "decliners": int(dec),
            "unchanged": int(unch),
            "equal_weight_pct": float(equal_weight_pct),
            "cap_weight_pct": float(cap_weight_pct),
            "breadth_state": state,
            "divergence": float(divergence),
            "message": message,
        }
        logger.info(
            "[BREADTH] %d/%d adv | eq=%.2f cap=%.2f state=%s",
            adv, measured, equal_weight_pct, cap_weight_pct, state,
        )
        return result
