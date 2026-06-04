"""Cross-day lead/lag stability + tradeability engine (design doc section 6).

Runs the LeadLagEngine across multiple stored session frames to measure
whether the CURRENT leader has persisted day-over-day (and within today's
session), then verdicts whether the relationship is tradeable.
"""
from typing import Dict, Any, List, Tuple, Optional
import logging

import numpy as np
import pandas as pd

from app.core.lead_lag import LeadLagEngine

logger = logging.getLogger(__name__)


class StabilityEngine:
    """Measures cross-day persistence of the current lead/lag leader."""

    def __init__(self, target: str = None, lookback_days: int = None,
                 min_sessions: int = None, lag_tolerance: int = None,
                 tradeable_persistence: float = None):
        try:
            from app.config import settings
        except Exception:  # pragma: no cover - defensive
            settings = None

        def _get(name, default):
            return getattr(settings, name, default) if settings is not None else default

        self.target = (target if target is not None
                       else _get("PREDICTION_TARGET", "QQQ"))
        self.lookback_days = int(lookback_days if lookback_days is not None
                                 else _get("STABILITY_LOOKBACK_DAYS", 5))
        self.min_sessions = int(min_sessions if min_sessions is not None
                                else _get("STABILITY_MIN_SESSIONS", 2))
        self.lag_tolerance = int(lag_tolerance if lag_tolerance is not None
                                 else _get("STABILITY_LAG_TOLERANCE", 2))
        self.tradeable_persistence = float(
            tradeable_persistence if tradeable_persistence is not None
            else _get("STABILITY_TRADEABLE_PERSISTENCE", 0.6))

    # ------------------------------------------------------------------ #
    # helpers                                                             #
    # ------------------------------------------------------------------ #
    def _result(self, status: str, leader: Optional[str], verdict: str,
                message: str, sessions_analyzed: int = 0,
                lead_persistence: float = 0.0, intraday_consistency: float = 0.0,
                median_lag: float = 0.0) -> Dict[str, Any]:
        return {
            "status": status,
            "leader": leader,
            "sessions_analyzed": int(sessions_analyzed),
            "lead_persistence": float(lead_persistence),
            "intraday_consistency": float(intraday_consistency),
            "median_lag": float(median_lag),
            "tradeable": bool(
                sessions_analyzed >= self.min_sessions
                and lead_persistence >= self.tradeable_persistence
            ),
            "verdict": verdict,
            "message": message,
        }

    def _intraday_consistency(self, frame: pd.DataFrame,
                              current_leader: str) -> float:
        """Split today's frame into cumulative thirds, run lead_lag on each,
        return the fraction whose leader == current leader."""
        try:
            engine = LeadLagEngine(target=self.target)
            n = len(frame)
            if n < 3:
                return 0.0
            thirds = [frame.iloc[: int(n * k / 3)] for k in (1, 2, 3)]
            matches = 0
            counted = 0
            for chunk in thirds:
                res = engine.compute(chunk)
                if res.get("status") != "ok":
                    continue
                counted += 1
                ldr = res.get("leader")
                if ldr is not None and ldr.get("symbol") == current_leader:
                    matches += 1
            if counted == 0:
                return 0.0
            return matches / counted
        except Exception:
            logger.warning("[StabilityEngine] intraday consistency failed", exc_info=True)
            return 0.0

    # ------------------------------------------------------------------ #
    # main                                                                #
    # ------------------------------------------------------------------ #
    def compute(self, sessions: List[Tuple[str, pd.DataFrame]],
                current_lead_lag: Dict[str, Any]) -> Dict[str, Any]:
        try:
            leader_obj = (current_lead_lag or {}).get("leader")
            if not leader_obj:
                return self._result(
                    "ok", None, "no_leader", "No leader to track.",
                )

            current_leader = leader_obj.get("symbol")
            current_lag = leader_obj.get("lag_minutes", 0)
            if current_leader is None:
                return self._result(
                    "ok", None, "no_leader", "No leader to track.",
                )

            engine = LeadLagEngine(target=self.target)

            analyzed = 0
            matching_lags: List[float] = []
            today_frame = None
            for _date, frame in (sessions or []):
                today_frame = frame  # sessions oldest first -> today last
                res = engine.compute(frame)
                if res.get("status") != "ok":
                    continue
                analyzed += 1
                ldr = res.get("leader")
                if ldr is None:
                    continue
                if (ldr.get("symbol") == current_leader
                        and abs(ldr.get("lag_minutes", 0) - current_lag)
                        <= self.lag_tolerance):
                    matching_lags.append(float(ldr.get("lag_minutes", 0)))

            if analyzed < self.min_sessions:
                return self._result(
                    "gathering", current_leader, "gathering",
                    "Gathering data — %d session%s so far." % (
                        analyzed, "" if analyzed == 1 else "s"),
                    sessions_analyzed=analyzed,
                )

            lead_persistence = len(matching_lags) / analyzed if analyzed else 0.0
            median_lag = float(np.median(matching_lags)) if matching_lags else 0.0

            intraday_consistency = (
                self._intraday_consistency(today_frame, current_leader)
                if today_frame is not None else 0.0
            )

            tradeable = lead_persistence >= self.tradeable_persistence

            if tradeable:
                verdict = "tradeable"
                message = "Lead held %d/%d sessions @ ~%gmin — tradeable." % (
                    len(matching_lags), analyzed, median_lag)
            else:
                verdict = "unstable"
                message = "Leader keeps changing — unstable."

            return self._result(
                "ok", current_leader, verdict, message,
                sessions_analyzed=analyzed,
                lead_persistence=lead_persistence,
                intraday_consistency=intraday_consistency,
                median_lag=median_lag,
            )
        except Exception:
            logger.warning("[StabilityEngine] compute failed", exc_info=True)
            return self._result(
                "warming_up", None, "gathering", "Gathering data — 0 sessions so far.",
            )
