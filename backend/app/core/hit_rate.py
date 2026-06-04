from typing import Dict, Any, Optional, List
import logging

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


class HitRateEngine:
    """Continuation probability for the CURRENT leader over a forward horizon.

    Given the leader S measured by the lead/lag engine, this asks: when S makes
    a meaningful move, how often does the target (QQQ) move the same way over the
    next H minutes? The statistic is computed purely from stored 1m bars across
    however many sessions are available — no separate setup log.

    THE HORIZON RULE: the horizon H only governs the forward-return evaluation
    window. It NEVER influences any lead/lag computation. The lead used to build
    the leader's signal comes from current_lead_lag["leader"]["lag_minutes"].
    The auto (default) horizon equals that same lag; fixed horizons from
    settings.HITRATE_HORIZONS are also evaluated into `by_horizon`.
    """

    def __init__(self, target: str = None, min_sample: int = None,
                 horizons: List[int] = None):
        try:
            from app.config import settings
        except Exception:  # pragma: no cover - defensive
            settings = None

        def _get(name, default):
            return getattr(settings, name, default) if settings is not None else default

        self.target = (target if target is not None
                       else _get("PREDICTION_TARGET", "QQQ"))
        self.min_sample = int(min_sample if min_sample is not None
                              else _get("HITRATE_MIN_SAMPLE", 30))
        if horizons is not None:
            self.horizons = [int(h) for h in horizons if int(h) >= 1]
        else:
            cfg = _get("HITRATE_HORIZONS", [5, 15, 30])
            self.horizons = [int(h) for h in cfg if int(h) >= 1]

    # ------------------------------------------------------------------ #
    # helpers                                                             #
    # ------------------------------------------------------------------ #
    def _empty(self, status: str, leader: Optional[str], horizon: int,
               horizon_mode: str, message: str) -> Dict[str, Any]:
        """A fully-populated result used when data/leader is insufficient.

        by_horizon is pre-seeded with the configured fixed horizons (value 0.0)
        even before there's enough data, so the UI horizon dropdown always has
        options to offer — the values fill in once status reaches "ok"."""
        seeded = {str(h): 0.0 for h in self.horizons if int(h) >= 1}
        return {
            "status": status,
            "leader": leader,
            "horizon_minutes": int(horizon),
            "horizon_mode": horizon_mode,
            "sample_size": 0,
            "sessions": 0,
            "hit_rate": 0.0,
            "baseline": 0.0,
            "edge": 0.0,
            "by_horizon": seeded,
            "message": message,
        }

    @staticmethod
    def _sessions_of(close: pd.DataFrame) -> List[pd.DataFrame]:
        """Split a (possibly multi-day) frame into per-ET-date sub-frames so that
        forward/leader returns never span an overnight gap."""
        try:
            dates = close.index.normalize()
        except Exception:
            return [close]
        frames = []
        for _, sub in close.groupby(dates):
            if len(sub) >= 2:
                frames.append(sub.sort_index())
        return frames

    def _measure(self, sessions: List[pd.DataFrame], leader: str,
                 lag: int, horizon: int) -> Dict[str, float]:
        """Aggregate hit/baseline over all sessions for one horizon.

        Returns dict with hit_rate, baseline, edge, sample_size, plus the raw
        counts so the caller can compute the auto stat without re-walking bars.
        """
        leader_rets: List[float] = []
        fwd_signs: List[int] = []      # sign of fwd_ret aligned to firing candidates
        leader_signs: List[int] = []
        all_fwd_up: List[int] = []     # unconditional baseline sample

        for sub in sessions:
            if leader not in sub.columns or self.target not in sub.columns:
                continue
            lead_px = sub[leader].to_numpy(dtype=float)
            tgt_px = sub[self.target].to_numpy(dtype=float)
            n = len(sub)
            # leader return over the prior `lag` bars, ending at t
            # fwd return over [t, t+horizon]
            for t in range(lag, n - horizon):
                lp0 = lead_px[t - lag]
                lp1 = lead_px[t]
                tp0 = tgt_px[t]
                tp1 = tgt_px[t + horizon]
                if not (np.isfinite(lp0) and np.isfinite(lp1)
                        and np.isfinite(tp0) and np.isfinite(tp1)):
                    continue
                if lp0 <= 0 or tp0 <= 0:
                    continue
                lr = lp1 / lp0 - 1.0
                fr = tp1 / tp0 - 1.0
                leader_rets.append(abs(lr))
                leader_signs.append(int(np.sign(lr)))
                fwd_signs.append(int(np.sign(fr)))
                all_fwd_up.append(1 if fr > 0 else 0)

        if not leader_rets:
            return {"hit_rate": 0.0, "baseline": 0.0, "edge": 0.0, "sample_size": 0}

        leader_rets_arr = np.asarray(leader_rets)
        # "signal" = leader move in the top tertile of |leader_ret|
        thresh = float(np.quantile(leader_rets_arr, 2.0 / 3.0))
        firing = leader_rets_arr >= thresh

        hits = []
        for i, fire in enumerate(firing):
            if not fire:
                continue
            ls = leader_signs[i]
            fs = fwd_signs[i]
            if ls == 0:
                continue
            hits.append(1 if fs == ls else 0)

        sample_size = len(hits)
        hit_rate = float(np.mean(hits)) if hits else 0.0

        up_rate = float(np.mean(all_fwd_up)) if all_fwd_up else 0.0
        baseline = max(up_rate, 1.0 - up_rate)
        edge = hit_rate - baseline

        return {
            "hit_rate": hit_rate,
            "baseline": baseline,
            "edge": edge,
            "sample_size": sample_size,
        }

    # ------------------------------------------------------------------ #
    # main                                                                #
    # ------------------------------------------------------------------ #
    def compute(self, bars: pd.DataFrame, current_lead_lag: Dict[str, Any],
                horizon: int = None) -> Dict[str, Any]:
        leader_obj = (current_lead_lag or {}).get("leader")
        if not leader_obj or not leader_obj.get("symbol"):
            return self._empty("no_leader", None,
                               horizon if horizon else 5,
                               "manual" if horizon else "auto",
                               "No leader to track.")

        leader = leader_obj["symbol"]
        lag = int(leader_obj.get("lag_minutes") or 0)
        if lag < 1:
            lag = 1

        # AUTO horizon = the measured lead. lag NEVER changes regardless of horizon.
        auto_horizon = max(int(leader_obj.get("lag_minutes") or 0), 1)
        if horizon is not None and int(horizon) >= 1:
            reported_horizon = int(horizon)
            horizon_mode = "manual"
        else:
            reported_horizon = auto_horizon
            horizon_mode = "auto"

        if bars is None or getattr(bars, "empty", True):
            return self._empty("warming_up", leader, reported_horizon,
                               horizon_mode, "Gathering data — no bars yet.")

        try:
            close = bars.sort_index().ffill()
        except Exception:
            logger.warning("[HitRateEngine] failed to clean bars")
            return self._empty("warming_up", leader, reported_horizon,
                               horizon_mode, "Gathering data — bad bars.")

        if leader not in close.columns or self.target not in close.columns:
            return self._empty("warming_up", leader, reported_horizon,
                               horizon_mode, "Gathering data — leader/target missing.")

        sessions = self._sessions_of(close)
        n_sessions = len(sessions)

        # the set of horizons to evaluate: configured fixed ones + auto.
        horizon_set = sorted({h for h in self.horizons if h >= 1} | {auto_horizon}
                             | {reported_horizon})

        by_horizon: Dict[str, float] = {}
        stats_by_h: Dict[int, Dict[str, float]] = {}
        for h in horizon_set:
            stats = self._measure(sessions, leader, lag, h)
            stats_by_h[h] = stats
            by_horizon[str(h)] = round(stats["hit_rate"], 4)

        reported = stats_by_h.get(reported_horizon,
                                  {"hit_rate": 0.0, "baseline": 0.0,
                                   "edge": 0.0, "sample_size": 0})
        sample_size = int(reported["sample_size"])

        if sample_size < self.min_sample:
            res = self._empty("gathering", leader, reported_horizon,
                             horizon_mode,
                             f"Gathering data — {n_sessions} session(s), "
                             f"{sample_size}/{self.min_sample} samples.")
            res["sessions"] = int(n_sessions)
            res["sample_size"] = sample_size
            res["hit_rate"] = round(float(reported["hit_rate"]), 4)
            res["baseline"] = round(float(reported["baseline"]), 4)
            res["edge"] = round(float(reported["edge"]), 4)
            res["by_horizon"] = by_horizon
            return res

        hit_pct = round(float(reported["hit_rate"]) * 100.0, 1)
        message = (
            f"QQQ followed {leader} {hit_pct}% over ~{reported_horizon}m "
            f"(n={sample_size}, {n_sessions} sessions)."
        )

        result = {
            "status": "ok",
            "leader": leader,
            "horizon_minutes": int(reported_horizon),
            "horizon_mode": horizon_mode,
            "sample_size": sample_size,
            "sessions": int(n_sessions),
            "hit_rate": round(float(reported["hit_rate"]), 4),
            "baseline": round(float(reported["baseline"]), 4),
            "edge": round(float(reported["edge"]), 4),
            "by_horizon": by_horizon,
            "message": message,
        }
        logger.info(
            "[HitRateEngine] leader=%s H=%d(%s) hit=%.3f base=%.3f edge=%.3f n=%d sessions=%d",
            leader, reported_horizon, horizon_mode, result["hit_rate"],
            result["baseline"], result["edge"], sample_size, n_sessions,
        )
        return result
