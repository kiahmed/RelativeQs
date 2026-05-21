from fastapi import APIRouter, HTTPException
import os
import logging
from typing import Optional
from app.services.market_data import MarketDataService
from app.core.score_engine import ScoreEngine
from app.config import settings

router = APIRouter()
logger = logging.getLogger(__name__)

provider_mode = settings.DATA_PROVIDER or os.getenv("DATA_PROVIDER", "mock")
market = MarketDataService(mode=provider_mode)
engine = ScoreEngine()

@router.get("/health")
async def health():
    logger.info("[API] GET /health")
    response = {"status": "ok"}
    logger.debug("[API] Response: %s", response)
    return response

@router.get("/snapshot")
async def snapshot():
    logger.info("[API] GET /snapshot")
    snap = await market.fetch_snapshot()
    logger.info("[API] Snapshot retrieved with %d signals", len(snap.get("signals", {})))
    logger.debug("[API] Snapshot data: timestamp=%s", snap.get("timestamp"))
    return snap

@router.get("/qqq-score")
async def qqq_score(interval: Optional[str] = "1m", period: Optional[str] = "7d"):
    logger.info("[API] GET /qqq-score interval=%s period=%s", interval, period)
    score = await market.fetch_qqq_score(period=period or "7d", interval=interval or "1m")
    logger.debug("[API] QQQ score payload: %s", score)
    return score

@router.post("/score")
async def score(payload: dict, normalize: Optional[bool] = None):
    logger.info("[API] POST /score - normalize=%s", normalize)
    logger.debug("[API] Request payload signals: %s", list(payload.get("signals", {}).keys()))
    # expect payload.signals dict
    signals = payload.get("signals")
    if not signals:
        logger.warning("[API] Missing signals in payload")
        raise HTTPException(status_code=400, detail="signals required")
    # determine normalize behavior: explicit param takes precedence, otherwise config
    if normalize is None:
        normalize = settings.NORMALIZE_SIGNALS
    logger.debug("[API] Using normalize=%s", normalize)
    result = engine.compute_score(signals, normalize=bool(normalize))
    logger.info("[API] Score computed: raw_score=%.4f, probability=%.4f, fragility=%.4f", 
                result.get("raw_score", 0), result.get("probability", 0), result.get("fragility", 0))
    logger.debug("[API] Score result: %s", result)
    return result
