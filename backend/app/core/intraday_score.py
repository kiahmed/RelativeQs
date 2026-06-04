from typing import Dict, Any, List
import logging

import numpy as np
import pandas as pd

try:
    from app.config import settings
except Exception:  # pragma: no cover - config optional at import time
    settings = None

logger = logging.getLogger(__name__)


class IntradayScoreEngine:
    """Composite intraday score for the prediction target.

    Combines three measured components into a single score in [-1, 1]:

    - ``leadership``: tanh-scaled 30m momentum of symbols measured as
      "leader" (by the lead/lag engine), weighted by their best_corr.
    - ``broadening``: mean tanh-scaled 30m momentum of "confirmer" symbols.
    - ``fragility``: fraction of the universe diverging / showing weakness
      while the target itself is pushing higher (masked weakness).

    Roles are never hardcoded — they arrive via the ``lead_lag`` dict.
    """

    MOMENTUM_WINDOW = 30  # 1m bars used for the momentum read

    def __init__(self, target: str = None):
        if target is None:
            target = getattr(settings, "PREDICTION_TARGET", "QQQ") if settings else "QQQ"
        self.target = str(target).upper()

    # ------------------------------------------------------------------ #
    # helpers                                                             #
    # ------------------------------------------------------------------ #
    def _momentum(self, series, periods: int = MOMENTUM_WINDOW) -> float:
        """Point-to-point return over the last ``periods`` bars."""
        if series is None:
            return 0.0
        values = series.dropna()
        if len(values) <= periods:
            if len(values) >= 2:
                try:
                    return float(values.iloc[-1] / values.iloc[0] - 1.0)
                except Exception:
                    return 0.0
            return 0.0
        try:
            return float(values.iloc[-1] / values.iloc[-periods - 1] - 1.0)
        except Exception:
            return 0.0

    def _warming_up(self, bars: pd.DataFrame) -> Dict[str, Any]:
        momentum = {}
        if bars is not None and not getattr(bars, "empty", True):
            for sym in bars.columns:
                momentum[str(sym)] = self._momentum(bars.get(sym))
        return {
            "status": "warming_up",
            "verdict": "warming_up",
            "score": 0.0,
            "probability_up": 0.5,
            "components": {"leadership": 0.0, "broadening": 0.0, "fragility": 0.0},
            "momentum_30m": momentum,
        }

    # ------------------------------------------------------------------ #
    # main                                                                #
    # ------------------------------------------------------------------ #
    def compute(self, bars: pd.DataFrame, lead_lag: Dict[str, Any]) -> Dict[str, Any]:
        if not isinstance(lead_lag, dict) or lead_lag.get("status") != "ok":
            return self._warming_up(bars)

        if bars is None or getattr(bars, "empty", True):
            return self._warming_up(bars)

        close = bars.sort_index()

        # per-symbol 30m momentum
        momentum: Dict[str, float] = {}
        for sym in close.columns:
            momentum[str(sym)] = self._momentum(close.get(sym))

        target_mom = momentum.get(self.target, 0.0)

        entries: List[Dict[str, Any]] = lead_lag.get("entries", []) or []

        # ---- leadership ------------------------------------------------
        leaders = [e for e in entries if e.get("role") == "leader"]
        if not leaders:
            # fall back to top-2 entries by best_corr
            leaders = sorted(
                entries, key=lambda e: e.get("best_corr", 0.0), reverse=True
            )[:2]

        leadership = 0.0
        weight_total = 0.0
        for e in leaders:
            sym = str(e.get("symbol", ""))
            corr = abs(float(e.get("best_corr", 0.0)))
            mom = momentum.get(sym, 0.0)
            leadership += corr * float(np.tanh(mom * 100.0))
            weight_total += corr
        if weight_total > 0:
            leadership = leadership / weight_total
        leadership = float(np.clip(leadership, -1.0, 1.0))

        # ---- broadening ------------------------------------------------
        confirmers = lead_lag.get("confirmers", []) or []
        broad_vals = [
            float(np.tanh(momentum.get(str(s), 0.0) * 100.0)) for s in confirmers
        ]
        broadening = float(np.clip(np.mean(broad_vals), -1.0, 1.0)) if broad_vals else 0.0

        # ---- fragility -------------------------------------------------
        diverging = set(str(s) for s in (lead_lag.get("diverging", []) or []))
        universe = [str(s) for s in close.columns]
        non_target = [s for s in universe if s != self.target]
        weak = 0
        if non_target:
            for s in non_target:
                is_diverging = s in diverging
                # masked weakness: negative momentum while target pushes up
                masked = momentum.get(s, 0.0) < 0.0 and target_mom > 0.0
                if is_diverging or masked:
                    weak += 1
            fragility = weak / len(non_target)
        else:
            fragility = 0.0
        fragility = float(np.clip(fragility, 0.0, 1.0))

        # ---- composite -------------------------------------------------
        score = 0.5 * leadership + 0.35 * broadening - 0.4 * fragility
        score = float(np.clip(score, -1.0, 1.0))
        probability_up = float(0.5 + 0.5 * np.tanh(2.0 * score))

        # ---- verdict ---------------------------------------------------
        if fragility >= 0.5:
            verdict = "fragile"
        elif abs(score) > 0.2:
            verdict = "continue"
        else:
            verdict = "stall"

        result = {
            "status": "ok",
            "verdict": verdict,
            "score": score,
            "probability_up": probability_up,
            "components": {
                "leadership": leadership,
                "broadening": broadening,
                "fragility": fragility,
            },
            "momentum_30m": momentum,
        }
        logger.info(
            "[IntradayScoreEngine] verdict=%s score=%.3f p_up=%.3f "
            "lead=%.3f broad=%.3f frag=%.3f",
            verdict, score, probability_up, leadership, broadening, fragility,
        )
        return result
