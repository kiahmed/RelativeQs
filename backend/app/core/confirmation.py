from typing import Dict, Any, List
import logging

import pandas as pd

try:
    from app.config import settings
except Exception:  # pragma: no cover - config optional at import time
    settings = None

logger = logging.getLogger(__name__)


class ConfirmationGate:
    """Pre-trade confirmation gate for the prediction target.

    Reads the measured target direction (from the score engine's 30m
    momentum) and asks whether the rest of the universe and the lead/lag
    leader/confirmers actually agree with that move. A confirmed move has
    broad participation and aligned leaders; an unconfirmed move is narrow
    (fade risk); a fragile move is flagged regardless when the score
    engine's fragility is elevated.

    Nothing is hardcoded to a ticker — direction, participation and leader
    agreement are all derived from the dicts handed in.
    """

    DIR_THRESHOLD = 0.0002  # 30m momentum magnitude to call a direction
    PARTICIPATION_MIN = 0.55
    FRAGILITY_MAX = 0.5

    def __init__(self, target: str = None):
        if target is None:
            target = getattr(settings, "PREDICTION_TARGET", "QQQ") if settings else "QQQ"
        self.target = str(target).upper()

    # ------------------------------------------------------------------ #
    # helpers                                                             #
    # ------------------------------------------------------------------ #
    def _warming_up(self) -> Dict[str, Any]:
        return {
            "status": "warming_up",
            "state": "unconfirmed",
            "target_direction": "flat",
            "participation": 0.0,
            "participating_count": 0,
            "universe_count": 0,
            "leaders_agree": False,
            "fragility": 0.0,
            "message": "Warming up — not enough data to confirm.",
        }

    @classmethod
    def _direction(cls, mom: float) -> str:
        if mom > cls.DIR_THRESHOLD:
            return "up"
        if mom < -cls.DIR_THRESHOLD:
            return "down"
        return "flat"

    # ------------------------------------------------------------------ #
    # main                                                                #
    # ------------------------------------------------------------------ #
    def compute(self, bars: pd.DataFrame, lead_lag: Dict[str, Any],
                score: Dict[str, Any]) -> Dict[str, Any]:
        if not isinstance(score, dict) or score.get("status") != "ok":
            return self._warming_up()

        try:
            momentum: Dict[str, float] = score.get("momentum_30m", {}) or {}
            target_mom = float(momentum.get(self.target, 0.0))
            target_direction = self._direction(target_mom)

            non_target = [str(s) for s in momentum.keys() if str(s) != self.target]
            universe_count = len(non_target)

            # participation: share of the non-target universe agreeing with
            # the target's direction. When the target is flat, "agreement"
            # means also flat (low-signal regime).
            participating_count = 0
            for s in non_target:
                if self._direction(float(momentum.get(s, 0.0))) == target_direction:
                    participating_count += 1
            participation = (
                participating_count / universe_count if universe_count else 0.0
            )

            # leaders agree: every confirmer + the leader (if any) move in the
            # target's direction.
            leader_syms: List[str] = []
            leader = lead_lag.get("leader") if isinstance(lead_lag, dict) else None
            if isinstance(leader, dict) and leader.get("symbol"):
                leader_syms.append(str(leader["symbol"]))
            for s in (lead_lag.get("confirmers", []) or []) if isinstance(lead_lag, dict) else []:
                leader_syms.append(str(s))

            if leader_syms:
                leaders_agree = all(
                    self._direction(float(momentum.get(s, 0.0))) == target_direction
                    for s in leader_syms
                )
            else:
                leaders_agree = False

            components = score.get("components", {}) or {}
            fragility = float(components.get("fragility", 0.0))

            # ---- state ------------------------------------------------ #
            if fragility >= self.FRAGILITY_MAX:
                state = "fragile"
            elif (target_direction != "flat"
                  and participation >= self.PARTICIPATION_MIN
                  and leaders_agree):
                state = "confirmed"
            else:
                state = "unconfirmed"

            message = self._message(
                state, target_direction, participating_count, universe_count,
                leaders_agree, fragility,
            )

            result = {
                "status": "ok",
                "state": state,
                "target_direction": target_direction,
                "participation": float(participation),
                "participating_count": int(participating_count),
                "universe_count": int(universe_count),
                "leaders_agree": bool(leaders_agree),
                "fragility": float(fragility),
                "message": message,
            }
            logger.info(
                "[ConfirmationGate] state=%s dir=%s part=%d/%d agree=%s frag=%.3f",
                state, target_direction, participating_count, universe_count,
                leaders_agree, fragility,
            )
            return result
        except Exception:  # pragma: no cover - defensive
            logger.exception("[ConfirmationGate] failed; degrading to warming_up")
            return self._warming_up()

    # ------------------------------------------------------------------ #
    # messaging                                                           #
    # ------------------------------------------------------------------ #
    def _message(self, state: str, direction: str, participating: int,
                 universe: int, leaders_agree: bool, fragility: float) -> str:
        tgt = self.target
        if state == "fragile":
            return (f"{tgt} move is fragile — {int(fragility * 100)}% of the "
                    f"universe is weak/diverging; stand aside.")
        if state == "confirmed":
            agree = "and the leader agree" if leaders_agree else "agree"
            return (f"{tgt} {direction} and confirmed — {participating}/{universe} "
                    f"sectors {agree}.")
        # unconfirmed
        if direction == "flat":
            return (f"{tgt} is flat — no confirmed direction "
                    f"({participating}/{universe} aligned).")
        return (f"{tgt} {direction} but unconfirmed — only {participating}/{universe} "
                f"participating; fade risk.")
