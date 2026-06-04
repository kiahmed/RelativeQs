from typing import Dict, Any
import logging

import numpy as np
import pandas as pd

try:
    from app.config import settings
except Exception:  # pragma: no cover - config optional at import time
    settings = None

logger = logging.getLogger(__name__)


class ProjectionEngine:
    """Projects the target's expected move over a fixed horizon.

    Two bases:

    - ``leader_projection``: a measured leader exists, so the projection is
      driven by the leader's recent move (over its lag window), shrunk by
      its correlation and tilted by the composite score.
    - ``momentum_only``: no leader qualifies, so the projection is the
      composite score scaled by the target's recent volatility.
    """

    VOL_WINDOW = 60  # 1m bars for the volatility estimate

    def __init__(self, horizon_minutes: int = None):
        if horizon_minutes is None:
            horizon_minutes = (
                getattr(settings, "PROJECTION_HORIZON_MINUTES", 15) if settings else 15
            )
        self.horizon_minutes = int(horizon_minutes)

    # ------------------------------------------------------------------ #
    # helpers                                                             #
    # ------------------------------------------------------------------ #
    def _warming_up(self) -> Dict[str, Any]:
        return {
            "status": "warming_up",
            "horizon_minutes": self.horizon_minutes,
            "current_price": 0.0,
            "expected_return": 0.0,
            "projected_price": 0.0,
            "band_low": 0.0,
            "band_high": 0.0,
            "confidence": 0.0,
            "direction": "flat",
            "basis": "momentum_only",
        }

    # ------------------------------------------------------------------ #
    # main                                                                #
    # ------------------------------------------------------------------ #
    def compute(self, bars: pd.DataFrame, lead_lag: Dict[str, Any],
                score: Dict[str, Any]) -> Dict[str, Any]:
        ll_ok = isinstance(lead_lag, dict) and lead_lag.get("status") == "ok"
        if not ll_ok or bars is None or getattr(bars, "empty", True):
            return self._warming_up()

        target = str(lead_lag.get("target", "QQQ")).upper()
        close = bars.sort_index()
        tgt = close.get(target)
        if tgt is None:
            return self._warming_up()
        tgt = tgt.dropna()
        if len(tgt) < 2:
            return self._warming_up()

        current_price = float(tgt.iloc[-1])
        tgt_returns = np.log(tgt).diff().dropna()

        # recent volatility scaled to the horizon
        recent = tgt_returns.iloc[-self.VOL_WINDOW:]
        if len(recent) >= 2:
            target_recent_vol = float(recent.std() * np.sqrt(self.horizon_minutes))
        else:
            target_recent_vol = 0.0

        score_val = float(score.get("score", 0.0)) if isinstance(score, dict) else 0.0

        leader = lead_lag.get("leader")
        if leader:
            basis = "leader_projection"
            sym = str(leader.get("symbol", ""))
            beta = float(leader.get("beta", 0.0))
            corr = float(leader.get("corr", 0.0))
            lag = int(leader.get("lag_minutes", 0)) or 1

            leader_series = close.get(sym)
            leader_return = 0.0
            if leader_series is not None:
                ls = leader_series.dropna()
                if len(ls) > lag:
                    try:
                        leader_return = float(ls.iloc[-1] / ls.iloc[-lag - 1] - 1.0)
                    except Exception:
                        leader_return = 0.0
                elif len(ls) >= 2:
                    leader_return = float(ls.iloc[-1] / ls.iloc[0] - 1.0)

            expected_return = (
                beta * leader_return * corr
                + 0.25 * score_val * target_recent_vol
            )
            agree = (np.sign(expected_return) == np.sign(score_val)) or score_val == 0.0
            confidence = float(
                np.clip(abs(corr) * (1.0 if agree else 0.5), 0.0, 1.0)
            )
        else:
            basis = "momentum_only"
            expected_return = score_val * target_recent_vol
            confidence = 0.2

        expected_return = float(expected_return)
        projected_price = float(current_price * (1.0 + expected_return))
        band = abs(1.0 * target_recent_vol * current_price)
        band_low = float(projected_price - band)
        band_high = float(projected_price + band)

        if expected_return > 0.0002:
            direction = "up"
        elif expected_return < -0.0002:
            direction = "down"
        else:
            direction = "flat"

        result = {
            "status": "ok",
            "horizon_minutes": self.horizon_minutes,
            "current_price": current_price,
            "expected_return": expected_return,
            "projected_price": projected_price,
            "band_low": band_low,
            "band_high": band_high,
            "confidence": confidence,
            "direction": direction,
            "basis": basis,
        }
        logger.info(
            "[ProjectionEngine] basis=%s dir=%s exp_ret=%.5f conf=%.3f "
            "price=%.2f->%.2f",
            basis, direction, expected_return, confidence,
            current_price, projected_price,
        )
        return result
