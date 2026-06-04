from typing import Dict, Any, Optional
import logging

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


class LeadLagEngine:
    """Dynamic lead/lag detection via cross-correlation of 1m log returns.

    Roles (leader / confirmer / diverging / weak) are MEASURED from the
    cross-correlation profile of every non-target symbol against the target.
    Nothing is hardcoded to a specific ticker — the leader on any given day
    is whichever symbol's returns best predict the target's returns at a
    positive lag.
    """

    def __init__(self, target: str = None, max_lag: int = None,
                 min_bars: int = None, corr_threshold: float = None):
        # pull defaults from settings, with getattr fallbacks so the module
        # works standalone before the config keys land (parallel agent).
        try:
            from app.config import settings
        except Exception:  # pragma: no cover - defensive, settings should import
            settings = None

        def _get(name, default):
            return getattr(settings, name, default) if settings is not None else default

        self.target = (target if target is not None
                       else _get("PREDICTION_TARGET", "QQQ"))
        self.max_lag = int(max_lag if max_lag is not None
                           else _get("LEAD_LAG_MAX_LAG", 15))
        self.min_bars = int(min_bars if min_bars is not None
                            else _get("LEAD_LAG_MIN_BARS", 45))
        self.corr_threshold = float(corr_threshold if corr_threshold is not None
                                    else _get("LEAD_LAG_CORR_THRESHOLD", 0.25))

    # ------------------------------------------------------------------ #
    # helpers                                                             #
    # ------------------------------------------------------------------ #
    def _empty(self, status: str, bars_used: int = 0) -> Dict[str, Any]:
        """A fully-populated result used when data is insufficient."""
        return {
            "status": status,
            "bars_used": int(bars_used),
            "window_start": "",
            "window_end": "",
            "target": self.target,
            "entries": [],
            "leader": None,
            "confirmers": [],
            "diverging": [],
        }

    @staticmethod
    def _iso(ts) -> str:
        try:
            return pd.Timestamp(ts).isoformat()
        except Exception:
            return str(ts)

    @staticmethod
    def _pearson(a: np.ndarray, b: np.ndarray) -> float:
        """Pearson correlation of two aligned arrays; 0.0 on degenerate input."""
        if a.size < 2 or b.size < 2:
            return 0.0
        sa = a.std()
        sb = b.std()
        if not np.isfinite(sa) or not np.isfinite(sb) or sa == 0.0 or sb == 0.0:
            return 0.0
        c = np.corrcoef(a, b)[0, 1]
        return float(c) if np.isfinite(c) else 0.0

    # ------------------------------------------------------------------ #
    # main                                                                #
    # ------------------------------------------------------------------ #
    def compute(self, bars: pd.DataFrame) -> Dict[str, Any]:
        if bars is None or getattr(bars, "empty", True):
            return self._empty("no_data")

        try:
            close = bars.sort_index().ffill().dropna()
        except Exception:
            logger.warning("[LeadLagEngine] failed to clean bars")
            return self._empty("no_data")

        if self.target not in close.columns:
            logger.warning("[LeadLagEngine] target %s missing from bars", self.target)
            return self._empty("no_data", bars_used=len(close))

        bars_used = len(close)
        if bars_used < self.min_bars:
            res = self._empty("warming_up", bars_used=bars_used)
            if bars_used:
                res["window_start"] = self._iso(close.index[0])
                res["window_end"] = self._iso(close.index[-1])
            return res

        # 1m log returns
        rets = np.log(close).diff()
        tgt = rets[self.target]

        entries = []
        for sym in close.columns:
            if sym == self.target:
                continue
            s = rets[sym]

            corr_by_lag = {}
            for k in range(0, self.max_lag + 1):
                # S shifted forward by k => S leads the target by k minutes:
                # we correlate S_returns[t-k] with target_returns[t].
                aligned = pd.concat([s.shift(k), tgt], axis=1).dropna()
                if len(aligned) < 2:
                    corr_by_lag[k] = 0.0
                    continue
                corr_by_lag[k] = self._pearson(
                    aligned.iloc[:, 0].to_numpy(),
                    aligned.iloc[:, 1].to_numpy(),
                )

            corr_at_zero = corr_by_lag.get(0, 0.0)

            # best positive-lead lag: only positive correlations matter for
            # "leading". argmax over k of corr_k.
            best_lag = 0
            best_corr = corr_by_lag.get(0, 0.0)
            for k in range(1, self.max_lag + 1):
                if corr_by_lag[k] > best_corr:
                    best_corr = corr_by_lag[k]
                    best_lag = k

            max_corr_all = max(corr_by_lag.values()) if corr_by_lag else 0.0

            # beta = OLS slope of target_returns[t] on S_returns[t - best_lag]
            beta = 0.0
            aligned = pd.concat([s.shift(best_lag), tgt], axis=1).dropna()
            if len(aligned) >= 2:
                x = aligned.iloc[:, 0].to_numpy()
                y = aligned.iloc[:, 1].to_numpy()
                vx = x.var()
                if np.isfinite(vx) and vx > 0:
                    cov = np.cov(x, y)[0, 1]
                    b = cov / vx
                    beta = float(b) if np.isfinite(b) else 0.0

            # role classification (dynamic, never hardcoded)
            if (best_lag >= 1 and best_corr >= self.corr_threshold
                    and best_corr > corr_at_zero):
                role = "leader"
            elif corr_at_zero >= self.corr_threshold:
                role = "confirmer"
            elif (max_corr_all < 0.05
                    or corr_at_zero < -self.corr_threshold / 2.0):
                role = "diverging"
            else:
                role = "weak"

            entries.append({
                "symbol": sym,
                "best_lag": int(best_lag),
                "best_corr": float(best_corr),
                "corr_at_zero": float(corr_at_zero),
                "beta": float(beta),
                "role": role,
            })

        entries.sort(key=lambda e: e["best_corr"], reverse=True)

        # leader = the highest-corr symbol with role "leader"
        leader = None
        for e in entries:
            if e["role"] == "leader":
                leader = {
                    "symbol": e["symbol"],
                    "lag_minutes": e["best_lag"],
                    "corr": e["best_corr"],
                    "beta": e["beta"],
                }
                break

        confirmers = [e["symbol"] for e in entries if e["role"] == "confirmer"]
        diverging = [e["symbol"] for e in entries if e["role"] == "diverging"]

        result = {
            "status": "ok",
            "bars_used": int(bars_used),
            "window_start": self._iso(close.index[0]),
            "window_end": self._iso(close.index[-1]),
            "target": self.target,
            "entries": entries,
            "leader": leader,
            "confirmers": confirmers,
            "diverging": diverging,
        }
        logger.info(
            "[LeadLagEngine] bars=%d leader=%s confirmers=%d diverging=%d",
            bars_used,
            leader["symbol"] if leader else None,
            len(confirmers), len(diverging),
        )
        return result
