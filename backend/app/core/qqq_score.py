from typing import Dict, Any
import logging

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


class QQQScoreEngine:
    """QQQ trend-regime engine.

    The score is driven by QQQ's position relative to its long-term
    (200-day) moving average. Backtests showed this trend filter held a
    comparable Sharpe to buy-and-hold with a materially shallower drawdown,
    whereas the previous short-momentum score had no measurable edge.

    The sector-momentum figures below are kept for display only — they do
    NOT drive the score.
    """

    LEADER_TICKERS = ["XLK", "SMH"]
    BROADENERS = ["XLY", "XLF"]
    CONFIRMERS = ["XLI", "IWM", "XLE"]
    TARGET = "QQQ"

    TREND_WINDOW = 200      # trading days for the trend moving average
    MOMENTUM_WINDOW = 20    # trading days for informational momentum

    # ------------------------------------------------------------------ #
    # helpers                                                             #
    # ------------------------------------------------------------------ #
    def _momentum(self, series, periods: int = MOMENTUM_WINDOW) -> float:
        """Simple point-to-point return over `periods` bars. Display only."""
        if series is None:
            return 0.0
        values = series.dropna()
        if len(values) <= periods:
            return 0.0
        try:
            return float(values.iloc[-1] / values.iloc[-periods - 1] - 1.0)
        except Exception:
            return 0.0

    def _neutral(self, reason: str) -> Dict[str, Any]:
        """A fully-populated, neutral result used when data is insufficient."""
        logger.warning("[QQQScoreEngine] %s", reason)
        return {
            "direction": "neutral",
            "regime": "unknown",
            "raw_score": 0.0,
            "probability": 0.0,
            "fragility": 0.0,
            "above_trend": False,
            "trend_gap": 0.0,
            "sma": 0.0,
            "price": 0.0,
            "trend_window": 0,
            "leader_momentum": {t: 0.0 for t in self.LEADER_TICKERS},
            "mags_momentum": 0.0,
            "broadening_momentum": {t: 0.0 for t in self.BROADENERS},
            "broadening_avg": 0.0,
            "confirmation_momentum": {t: 0.0 for t in self.CONFIRMERS},
            "confirmation_avg": 0.0,
            "lead_lag": [],
            "lead_signal": 0.0,
            "recent_qqq": [],
            "note": reason,
        }

    # ------------------------------------------------------------------ #
    # main                                                                #
    # ------------------------------------------------------------------ #
    def compute(self, data: pd.DataFrame) -> Dict[str, Any]:
        if data is None or getattr(data, "empty", True):
            return self._neutral("no price data available")

        close = data.sort_index()
        qqq = close.get(self.TARGET)
        if qqq is None:
            return self._neutral("QQQ column missing from price data")
        qqq = qqq.dropna()
        if len(qqq) < 20:
            return self._neutral("insufficient QQQ history for a trend read")

        # --- trend regime: QQQ vs its long-term moving average ----------
        window = min(self.TREND_WINDOW, len(qqq) - 1)
        sma_series = qqq.rolling(window).mean()
        price = float(qqq.iloc[-1])
        sma = float(sma_series.iloc[-1])
        # fractional gap: how far price sits above (+) or below (-) trend
        trend_gap = (price / sma - 1.0) if sma else 0.0

        above_trend = trend_gap > 0
        direction = "bullish" if above_trend else "bearish"
        regime = "risk-on" if above_trend else "risk-off"

        raw_score = float(trend_gap)
        # probability stays in (-1, 1) so the frontend gauge maps cleanly
        probability = float(np.tanh(trend_gap * 10.0))
        # fragility rises the further price sits BELOW its trend line
        fragility = float(np.clip(-trend_gap * 5.0, 0.0, 1.0))

        # --- informational sector momentum (display only) --------------
        leader_mom = {t: self._momentum(close.get(t)) for t in self.LEADER_TICKERS}
        broadening = {t: self._momentum(close.get(t)) for t in self.BROADENERS}
        confirmation = {t: self._momentum(close.get(t)) for t in self.CONFIRMERS}
        mags_mom = float(np.mean(list(leader_mom.values()))) if leader_mom else 0.0
        broadening_avg = float(np.mean(list(broadening.values()))) if broadening else 0.0
        confirmation_avg = float(np.mean(list(confirmation.values()))) if confirmation else 0.0

        recent = []
        for idx, val in qqq.iloc[-30:].items():
            try:
                label = idx.strftime("%Y-%m-%d")
            except AttributeError:
                label = str(idx)
            recent.append({"t": label, "QQQ": float(val)})

        result = {
            "direction": direction,
            "regime": regime,
            "raw_score": raw_score,
            "probability": probability,
            "fragility": fragility,
            "above_trend": bool(above_trend),
            "trend_gap": raw_score,
            "sma": sma,
            "price": price,
            "trend_window": int(window),
            "leader_momentum": leader_mom,
            "mags_momentum": mags_mom,
            "broadening_momentum": broadening,
            "broadening_avg": broadening_avg,
            "confirmation_momentum": confirmation,
            "confirmation_avg": confirmation_avg,
            "lead_lag": [],
            "lead_signal": 0.0,
            "recent_qqq": recent,
        }
        logger.info(
            "[QQQScoreEngine] regime=%s trend_gap=%.4f fragility=%.3f window=%d",
            regime, raw_score, fragility, window,
        )
        return result
