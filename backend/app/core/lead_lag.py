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
    def _empty(self, status: str, bars_used: int = 0,
               bar_minutes: int = 1) -> Dict[str, Any]:
        """A fully-populated result used when data is insufficient."""
        return {
            "status": status,
            "bars_used": int(bars_used),
            "bar_minutes": int(bar_minutes),
            "window_start": "",
            "window_end": "",
            "target": self.target,
            "entries": [],
            "leader": None,
            "confirmers": [],
            "diverging": [],
            "decoupled": [],
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

    @staticmethod
    def detect_decoupling(current: Dict[str, Any], baseline: Dict[str, Any],
                          usual_min: float = 0.5, drop_min: float = 0.3) -> list:
        """Flag drivers that are USUALLY in sync with the target but have broken
        ranks now: baseline contemporaneous corr >= usual_min and it dropped by
        >= drop_min in the current window. The early-warning 'who broke ranks' read.
        `current`/`baseline` are both compute() results at the same frame."""
        if not current or not baseline:
            return []
        base_corr = {e["symbol"]: e.get("corr_at_zero", 0.0)
                     for e in baseline.get("entries", [])}
        out = []
        for e in current.get("entries", []):
            sym = e["symbol"]
            usual = base_corr.get(sym)
            if usual is None or usual < usual_min:
                continue
            now = e.get("corr_at_zero", 0.0)
            if usual - now >= drop_min:
                out.append({
                    "symbol": sym,
                    "usual_corr": float(usual),
                    "now_corr": float(now),
                    "drop": float(usual - now),
                })
        out.sort(key=lambda d: d["drop"], reverse=True)
        return out

    # ------------------------------------------------------------------ #
    # main                                                                #
    # ------------------------------------------------------------------ #
    def compute(self, bars: pd.DataFrame, freq_minutes: int = 1,
                max_lag: Optional[int] = None,
                min_bars: Optional[int] = None,
                bar_minutes: Optional[int] = None) -> Dict[str, Any]:
        """Cross-correlation lead/lag. `freq_minutes` resamples the 1m bars to a
        coarser frame (e.g. 5 or 15) where real leads emerge; lags are reported in
        those minutes. For ALREADY-coarse bars (e.g. daily), pass freq_minutes=1
        (no resample) and bar_minutes=1440 so a 1-bar lag reads as 1 day. Defaults
        reproduce the original 1m behaviour."""
        max_lag = int(max_lag if max_lag is not None else self.max_lag)
        min_bars = int(min_bars if min_bars is not None else self.min_bars)
        freq_minutes = max(1, int(freq_minutes))
        # minutes-per-bar used for lag LABELLING (defaults to the resample freq)
        label_minutes = int(bar_minutes if bar_minutes is not None else freq_minutes)

        if bars is None or getattr(bars, "empty", True):
            return self._empty("no_data", bar_minutes=label_minutes)

        try:
            close = bars.sort_index().ffill().dropna()
            if freq_minutes > 1:
                close = close.resample(f"{freq_minutes}min").last().ffill().dropna()
        except Exception:
            logger.warning("[LeadLagEngine] failed to clean bars")
            return self._empty("no_data", bar_minutes=label_minutes)

        if self.target not in close.columns:
            logger.warning("[LeadLagEngine] target %s missing from bars", self.target)
            return self._empty("no_data", bars_used=len(close), bar_minutes=label_minutes)

        bars_used = len(close)
        if bars_used < min_bars:
            res = self._empty("warming_up", bars_used=bars_used, bar_minutes=label_minutes)
            if bars_used:
                res["window_start"] = self._iso(close.index[0])
                res["window_end"] = self._iso(close.index[-1])
            return res

        # log returns at the chosen frame
        rets = np.log(close).diff()
        tgt = rets[self.target]

        entries = []
        for sym in close.columns:
            if sym == self.target:
                continue
            s = rets[sym]

            corr_by_lag = {}
            for k in range(0, max_lag + 1):
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
            for k in range(1, max_lag + 1):
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
                "lag_minutes": int(best_lag * label_minutes),
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
                    "lag_minutes": int(e["best_lag"] * label_minutes),
                    "corr": e["best_corr"],
                    "beta": e["beta"],
                }
                break

        confirmers = [e["symbol"] for e in entries if e["role"] == "confirmer"]
        diverging = [e["symbol"] for e in entries if e["role"] == "diverging"]

        result = {
            "status": "ok",
            "bars_used": int(bars_used),
            "bar_minutes": int(label_minutes),
            "window_start": self._iso(close.index[0]),
            "window_end": self._iso(close.index[-1]),
            "target": self.target,
            "entries": entries,
            "leader": leader,
            "confirmers": confirmers,
            "diverging": diverging,
            "decoupled": [],
        }
        logger.info(
            "[LeadLagEngine] bars=%d leader=%s confirmers=%d diverging=%d",
            bars_used,
            leader["symbol"] if leader else None,
            len(confirmers), len(diverging),
        )
        return result
