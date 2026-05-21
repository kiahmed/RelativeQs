from typing import Dict, Any, List
import logging
import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


class QQQScoreEngine:
    """Prototype QQQ direction scoring using leader, broadening, and confirmation signals."""

    LEADER_TICKERS = ["XLK", "SMH"]
    BROADENERS = ["XLY", "XLF"]
    CONFIRMERS = ["XLI", "IWM", "XLE"]
    TARGET = "QQQ"

    def _momentum(self, series: pd.Series, periods: int = 5) -> float:
        values = series.dropna()
        if len(values) <= periods:
            return 0.0
        try:
            return float(values.iloc[-1] / values.iloc[-periods - 1] - 1.0)
        except Exception:
            return 0.0

    def _lagged_correlation(self, returns: pd.DataFrame, symbol: str, max_lag: int = 5) -> Dict[str, float]:
        if symbol not in returns.columns or self.TARGET not in returns.columns:
            return {"symbol": symbol, "bestLag": 0, "corr": 0.0, "lead": False}

        target = returns[self.TARGET]
        best_corr = 0.0
        best_lag = 0
        for lag in range(-max_lag, max_lag + 1):
            shifted = returns[symbol].shift(-lag)
            corr = float(shifted.corr(target) or 0.0)
            if abs(corr) > abs(best_corr):
                best_corr = corr
                best_lag = lag

        return {
            "symbol": symbol,
            "bestLag": int(best_lag),
            "corr": float(best_corr),
            "lead": best_lag > 0,
        }

    def compute(self, data: pd.DataFrame) -> Dict[str, Any]:
        if data is None or data.empty:
            logger.warning("[QQQScoreEngine] Empty data provided")
            return {"error": "no intraday data available"}

        data = data.sort_index()
        close = data
        result: Dict[str, Any] = {}

        leader_signal = []
        leader_mom = {}
        for symbol in self.LEADER_TICKERS:
            series = close.get(symbol)
            if series is None:
                leader_mom[symbol] = 0.0
            else:
                leader_mom[symbol] = self._momentum(series, periods=5)
            leader_signal.append(leader_mom[symbol])

        mags_mom = float(np.mean(leader_signal)) if leader_signal else 0.0
        broadening_mom = []
        broadening = {}
        for symbol in self.BROADENERS:
            series = close.get(symbol)
            if series is None:
                broadening[symbol] = 0.0
            else:
                broadening[symbol] = self._momentum(series, periods=5)
            broadening_mom.append(broadening[symbol])

        confirmation_mom = []
        confirmation = {}
        for symbol in self.CONFIRMERS:
            series = close.get(symbol)
            if series is None:
                confirmation[symbol] = 0.0
            else:
                confirmation[symbol] = self._momentum(series, periods=5)
            confirmation_mom.append(confirmation[symbol])

        leader_avg = float(np.mean(leader_signal)) if leader_signal else 0.0
        broadening_avg = float(np.mean(broadening_mom)) if broadening_mom else 0.0
        confirmation_avg = float(np.mean(confirmation_mom)) if confirmation_mom else 0.0

        returns = close.pct_change().dropna()
        lead_lag = [self._lagged_correlation(returns, symbol) for symbol in self.LEADER_TICKERS]
        lead_corr_values = [item["corr"] if item["lead"] else 0.0 for item in lead_lag]
        lead_signal = float(np.mean(lead_corr_values)) if lead_corr_values else 0.0

        raw_score = (
            0.45 * leader_avg
            + 0.20 * broadening_avg
            + 0.20 * confirmation_avg
            + 0.15 * lead_signal
        )
        probability = float(np.tanh(raw_score * 2.0))
        fragility = float(np.clip(-confirmation_avg * 0.7 + max(0.0, -broadening_avg) * 0.3, 0.0, 1.0))
        direction = "bullish" if raw_score >= 0 else "bearish"

        qqq_series = close.get(self.TARGET)
        recent = []
        if qqq_series is not None:
            last_points = qqq_series.dropna().iloc[-30:]
            recent = [
                {"t": idx.strftime("%Y-%m-%d %H:%M"), "QQQ": float(value)}
                for idx, value in last_points.items()
            ]

        result.update(
            {
                "direction": direction,
                "raw_score": raw_score,
                "probability": probability,
                "fragility": fragility,
                "leader_momentum": leader_mom,
                "mags_momentum": mags_mom,
                "broadening_momentum": broadening,
                "broadening_avg": broadening_avg,
                "confirmation_momentum": confirmation,
                "confirmation_avg": confirmation_avg,
                "lead_lag": lead_lag,
                "lead_signal": lead_signal,
                "recent_qqq": recent,
            }
        )

        logger.info(
            "[QQQScoreEngine] Computed score raw=%.4f probability=%.4f direction=%s",
            raw_score,
            probability,
            direction,
        )
        return result
