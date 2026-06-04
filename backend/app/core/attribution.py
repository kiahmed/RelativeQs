from typing import Dict, Any, List, Optional
import logging

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# data-driven labels for the known driver/target symbols; anything else
# falls back to its lowercased ticker. NO fabricated index weights anywhere.
_LABELS = {
    "SMH": "semis",
    "IGV": "software",
    "MAGS": "mega-cap",
    "QQQ": "index",
}


class DriverAttributionEngine:
    """Attribute the target's recent move to its driver symbols via a
    data-driven multivariate OLS regression of 1m returns.

    No index weights are assumed: the per-driver coefficients (betas) are
    estimated from the actual bars, and each driver's contribution is its
    estimated beta times its realised cumulative return over the window.
    """

    def __init__(self, target: str = None, drivers: List[str] = None,
                 window: int = None):
        try:
            from app.config import settings
        except Exception:  # pragma: no cover - defensive
            settings = None

        def _get(name, default):
            return getattr(settings, name, default) if settings is not None else default

        self.target = (target if target is not None
                       else _get("PREDICTION_TARGET", "QQQ"))
        self.drivers = list(drivers if drivers is not None
                            else _get("DRIVER_SYMBOLS", ["SMH", "IGV", "MAGS"]))
        self.window = int(window if window is not None
                          else _get("ATTRIBUTION_WINDOW", 30))

    # ------------------------------------------------------------------ #
    # helpers                                                             #
    # ------------------------------------------------------------------ #
    def _label(self, symbol: str) -> str:
        return _LABELS.get(symbol.upper(), symbol.lower())

    def _empty(self, status: str, window_minutes: int = 0) -> Dict[str, Any]:
        """Fully-populated neutral result used on bad/insufficient data."""
        return {
            "status": status,
            "target": self.target,
            "window_minutes": int(window_minutes),
            "target_return": 0.0,
            "contributors": [],
            "explained_share": 0.0,
            "residual_share": 1.0,
            "headline": "Warming up — not enough data to attribute the move yet.",
        }

    @staticmethod
    def _trend(share: float) -> str:
        if share > 0.05:
            return "driving"
        if share < -0.05:
            return "lagging"
        return "flat"

    def _headline(self, contributors: List[Dict[str, Any]]) -> str:
        if not contributors:
            return "No driver signal."
        parts = []
        top = contributors[0]
        pct = int(round(abs(top["share"]) * 100))
        parts.append(
            f"{pct}% {top['label']}-driven ({top['symbol']})"
        )
        for c in contributors[1:]:
            trend = c["trend"]
            word = {"driving": "driving", "lagging": "lagging", "flat": "flat"}[trend]
            parts.append(f"{c['label']} {word}")
        return "; ".join(parts)

    # ------------------------------------------------------------------ #
    # main                                                                #
    # ------------------------------------------------------------------ #
    def compute(self, bars: pd.DataFrame) -> Dict[str, Any]:
        if bars is None or getattr(bars, "empty", True):
            return self._empty("warming_up")

        try:
            close = bars.sort_index().tail(self.window).ffill()
        except Exception:
            logger.warning("[DriverAttributionEngine] failed to clean bars")
            return self._empty("warming_up")

        if self.target not in close.columns:
            logger.warning("[DriverAttributionEngine] target %s missing", self.target)
            return self._empty("warming_up", window_minutes=len(close))

        # drivers present in the bars (subset of configured drivers)
        present = [d for d in self.drivers if d in close.columns and d != self.target]
        if not present:
            return self._empty("warming_up", window_minutes=len(close))

        # 1m returns over [target] + present drivers, dropping rows with any NaN
        cols = [self.target] + present
        try:
            rets = close[cols].pct_change().dropna()
        except Exception:
            logger.warning("[DriverAttributionEngine] failed to compute returns")
            return self._empty("warming_up", window_minutes=len(close))

        if len(rets) < 10:
            return self._empty("warming_up", window_minutes=len(close))

        y = rets[self.target].to_numpy(dtype=float)
        X_cols = rets[present].to_numpy(dtype=float)

        # design matrix with intercept
        A = np.column_stack([np.ones(len(y)), X_cols])

        try:
            coef, _resid, _rank, _sv = np.linalg.lstsq(A, y, rcond=None)
        except Exception:
            logger.warning("[DriverAttributionEngine] lstsq failed")
            return self._empty("warming_up", window_minutes=len(close))

        betas = coef[1:]  # skip intercept

        # R^2 of the regression -> explained_share
        y_hat = A @ coef
        ss_res = float(np.sum((y - y_hat) ** 2))
        ss_tot = float(np.sum((y - y.mean()) ** 2))
        if ss_tot > 0:
            r2 = 1.0 - ss_res / ss_tot
        else:
            r2 = 0.0
        explained_share = float(min(max(r2, 0.0), 1.0))
        residual_share = float(1.0 - explained_share)

        # cumulative return of the target over the window (first->last close)
        tgt_series = close[self.target].dropna()
        if len(tgt_series) >= 2 and tgt_series.iloc[0] != 0:
            target_return = float(tgt_series.iloc[-1] / tgt_series.iloc[0] - 1.0)
        else:
            target_return = 0.0

        # contribution_i = beta_i * cumulative return of driver_i over the window
        contributions = {}
        for i, sym in enumerate(present):
            ser = close[sym].dropna()
            if len(ser) >= 2 and ser.iloc[0] != 0:
                cum = float(ser.iloc[-1] / ser.iloc[0] - 1.0)
            else:
                cum = 0.0
            contributions[sym] = float(betas[i]) * cum

        denom = sum(abs(v) for v in contributions.values())

        contributors = []
        for i, sym in enumerate(present):
            contrib = contributions[sym]
            share = float(contrib / denom) if denom > 0 else 0.0
            contributors.append({
                "symbol": sym,
                "label": self._label(sym),
                "beta": float(betas[i]),
                "contribution": float(contrib),
                "share": share,
                "trend": self._trend(share),
            })

        contributors.sort(key=lambda c: abs(c["share"]), reverse=True)

        result = {
            "status": "ok",
            "target": self.target,
            "window_minutes": int(len(close)),
            "target_return": target_return,
            "contributors": contributors,
            "explained_share": explained_share,
            "residual_share": residual_share,
            "headline": self._headline(contributors),
        }
        logger.info(
            "[DriverAttributionEngine] window=%d top=%s explained=%.2f",
            len(close),
            contributors[0]["symbol"] if contributors else None,
            explained_share,
        )
        return result
