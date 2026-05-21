from typing import Dict, Any
import logging
import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

class ScoreEngine:
    """Compute QQQ regime score from a set of named signals.

    Signals expected as a dict: {"XLK_mom": 0.12, "SMH_mom": 0.05, ...}
    Weights are defined in WEIGHTS below and missing signals are treated as 0.
    """

    WEIGHTS = {
        "XLK_mom": 0.25,
        "SMH_mom": 0.25,
        "MAGS_mom": 0.15,
        "XLY_conf": 0.10,
        "XLF_conf": 0.10,
        "XLI_breadth": 0.05,
        "IWM_breadth": 0.05,
        "XLE_inflation_stress": -0.05,
    }

    def compute_score(self, signals: Dict[str, float], normalize: bool = False) -> Dict[str, Any]:
        logger.debug("[SCORER] compute_score called with normalize=%s", normalize)
        logger.debug("[SCORER] Input signals: %s", signals)
        # build vector
        weights = []
        vals = []
        for k, w in self.WEIGHTS.items():
            weights.append(w)
            vals.append(float(signals.get(k, 0.0)))

        weights = np.array(weights, dtype=float)
        vals = np.array(vals, dtype=float)

        raw_score = float(np.dot(weights, vals))

        result: Dict[str, Any] = {
            "raw_score": raw_score,
            "weights_used": self.WEIGHTS,
        }

        # optionally normalize signals (z-score) before scoring
        if normalize:
            logger.debug("[SCORER] Applying z-score normalization")
            mean = float(np.mean(vals))
            std = float(np.std(vals))
            if std == 0:
                logger.debug("[SCORER] Zero std deviation, using zero vector")
                z = np.zeros_like(vals)
            else:
                z = (vals - mean) / std
            normalized_score = float(np.dot(weights, z))
            probability = float(np.tanh(normalized_score))
            fragility = float(np.clip(-normalized_score if normalized_score < 0 else 0.0, 0.0, 1.0))
            # map normalized signals for visibility
            normalized_signals = {k: float(z[i]) for i, k in enumerate(self.WEIGHTS.keys())}
            logger.info("[SCORER] Normalized score: %.4f, probability: %.4f, fragility: %.4f", 
                       normalized_score, probability, fragility)
            result.update(
                {
                    "normalized_score": normalized_score,
                    "probability": probability,
                    "fragility": fragility,
                    "normalized_signals": normalized_signals,
                }
            )
        else:
            logger.debug("[SCORER] Raw score: %.4f", raw_score)
            probability = float(np.tanh(raw_score))
            fragility = float(np.clip(-raw_score if raw_score < 0 else 0.0, 0.0, 1.0))
            logger.info("[SCORER] Raw computation: raw_score: %.4f, probability: %.4f, fragility: %.4f", 
                       raw_score, probability, fragility)
            result.update({"probability": probability, "fragility": fragility})

        return result
