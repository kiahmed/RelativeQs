"""QQQ / Nasdaq-100 constituents provider.

Constituents are a slow-moving fact (the index reconstitutes occasionally), so
they're loaded from a committed snapshot (app/data/qqq_holdings.json) rather than
scraped live every cycle. The fast-moving part — live quotes for those names — is
fetched each poll cycle by the market-data service. Refresh the snapshot with
dev-utils/refresh-qqq-holdings.py when the index reconstitutes.

Returns a {ticker: weight} mapping where weights are fractions summing to ~1.0.
"""
import json
import logging
from pathlib import Path
from typing import Dict, Optional

logger = logging.getLogger(__name__)

_SNAPSHOT_PATH = Path(__file__).resolve().parents[1] / "data" / "qqq_holdings.json"


class HoldingsProvider:
    """Loads the committed constituents snapshot (cached in-process)."""

    _cache: Optional[Dict[str, float]] = None

    def __init__(self, snapshot_path: Path = None):
        self.snapshot_path = snapshot_path or _SNAPSHOT_PATH

    def get_constituents(self, force_reload: bool = False) -> Dict[str, float]:
        """Return {ticker: weight} (weights are fractions). Empty dict if the
        snapshot is missing/unreadable — callers degrade to a no_data breadth."""
        if HoldingsProvider._cache is not None and not force_reload:
            return HoldingsProvider._cache
        try:
            with open(self.snapshot_path) as f:
                doc = json.load(f)
            weights = {str(k).upper(): float(v) for k, v in (doc.get("weights") or {}).items()}
        except Exception as exc:
            logger.warning("[HOLDINGS] could not load snapshot %s: %s", self.snapshot_path, exc)
            weights = {}
        HoldingsProvider._cache = weights
        logger.info("[HOLDINGS] loaded %d constituents from snapshot", len(weights))
        return weights
