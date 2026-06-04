from typing import Dict, Any
import logging

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


class CorrelationRegimeEngine:
    """Measures whether the sector universe is moving together (coupled) or
    fragmenting (everyone doing their own thing) over a short trailing window.

    When the regime is "fragmented" the cross-sectional dispersion is high and
    pairwise correlation is low, so lead/lag and rotation signals are noise:
    `signals_reliable` is set False in that case.
    """

    def __init__(self, window: int = None, coupled: float = None,
                 fragmented: float = None):
        # pull defaults from settings, with getattr fallbacks so the module
        # works standalone before the config keys land (parallel agent).
        try:
            from app.config import settings
        except Exception:  # pragma: no cover - defensive, settings should import
            settings = None

        def _get(name, default):
            return getattr(settings, name, default) if settings is not None else default

        self.window = int(window if window is not None
                          else _get("CORR_REGIME_WINDOW", 30))
        self.coupled = float(coupled if coupled is not None
                             else _get("CORR_COUPLED_THRESHOLD", 0.6))
        self.fragmented = float(fragmented if fragmented is not None
                                else _get("CORR_FRAGMENTED_THRESHOLD", 0.3))

    # ------------------------------------------------------------------ #
    # helpers                                                             #
    # ------------------------------------------------------------------ #
    def _empty(self, status: str) -> Dict[str, Any]:
        """A fully-populated neutral result used when data is insufficient."""
        return {
            "status": status,
            "regime": "transitional",
            "avg_pairwise_corr": 0.0,
            "dispersion": 0.0,
            "signals_reliable": True,
            "message": "Gathering data — correlation regime not yet measurable.",
        }

    # ------------------------------------------------------------------ #
    # main                                                                #
    # ------------------------------------------------------------------ #
    def compute(self, bars: pd.DataFrame) -> Dict[str, Any]:
        if bars is None or getattr(bars, "empty", True):
            return self._empty("warming_up")

        try:
            close = bars.sort_index().ffill()
            # use the last `window` bars of 1m returns
            rets = np.log(close).diff().tail(self.window).dropna(how="any", axis=0)
        except Exception:
            logger.warning("[CorrelationRegimeEngine] failed to clean bars")
            return self._empty("warming_up")

        # drop columns with no variance (constant series produce NaN corr)
        try:
            rets = rets.loc[:, rets.std() > 0]
        except Exception:
            return self._empty("warming_up")

        n_rows = len(rets)
        n_syms = rets.shape[1]
        if n_rows < max(self.window // 2, 2) or n_syms < 3:
            return self._empty("warming_up")

        try:
            corr = rets.corr().to_numpy()
        except Exception:
            logger.warning("[CorrelationRegimeEngine] corr failed")
            return self._empty("warming_up")

        # mean of the upper triangle (excluding the diagonal)
        iu = np.triu_indices(corr.shape[0], k=1)
        upper = corr[iu]
        upper = upper[np.isfinite(upper)]
        avg_pairwise_corr = float(upper.mean()) if upper.size else 0.0

        # dispersion = mean cross-sectional std of returns per bar
        try:
            disp = rets.std(axis=1)
            dispersion = float(disp.mean()) if len(disp) else 0.0
        except Exception:
            dispersion = 0.0
        if not np.isfinite(dispersion):
            dispersion = 0.0

        if avg_pairwise_corr >= self.coupled:
            regime = "coupled"
        elif avg_pairwise_corr <= self.fragmented:
            regime = "fragmented"
        else:
            regime = "transitional"

        signals_reliable = regime != "fragmented"

        if regime == "coupled":
            message = ("Sectors are moving together (coupled) — lead/lag and "
                       "rotation signals are meaningful.")
        elif regime == "fragmented":
            message = ("Sectors are fragmenting — treat lead/lag as noise today.")
        else:
            message = ("Sectors are partially coupled (transitional) — lead/lag "
                       "signals are weaker than usual.")

        result = {
            "status": "ok",
            "regime": regime,
            "avg_pairwise_corr": avg_pairwise_corr,
            "dispersion": dispersion,
            "signals_reliable": bool(signals_reliable),
            "message": message,
        }
        logger.info(
            "[CorrelationRegimeEngine] rows=%d syms=%d avg_corr=%.3f regime=%s",
            n_rows, n_syms, avg_pairwise_corr, regime,
        )
        return result
