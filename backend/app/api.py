from fastapi import APIRouter, HTTPException, Depends, Response
import os
import logging
from typing import Optional
from app.services.market_data import MarketDataService
from app.services.cache import RedisCache, SNAPSHOT_KEY, QQQ_SCORE_KEY, PREDICTION_KEY, ROTATION_KEY
from app.services.rotation_store import RotationStore
from app.core.score_engine import ScoreEngine
from app.config import settings
from app import auth, supabase_admin, alerts

router = APIRouter()
logger = logging.getLogger(__name__)

provider_mode = settings.DATA_PROVIDER or os.getenv("DATA_PROVIDER", "mock")
market = MarketDataService(mode=provider_mode)
engine = ScoreEngine()
cache = RedisCache()
rotation_store = RotationStore()

@router.get("/health")
async def health():
    logger.info("[API] GET /health")
    response = {"status": "ok"}
    logger.debug("[API] Response: %s", response)
    return response

@router.get("/snapshot")
async def snapshot():
    logger.info("[API] GET /snapshot")
    # Served from the Redis cache the background poll loop keeps fresh; only
    # compute on demand if the cache is empty (Redis down, or loop not started).
    snap = await cache.get(SNAPSHOT_KEY)
    if snap:
        logger.info("[API] Snapshot served from Redis (timestamp=%s)", snap.get("timestamp"))
        return snap
    logger.info("[API] Snapshot cache miss — computing on demand")
    snap = await market.fetch_snapshot()
    logger.info("[API] Snapshot retrieved with %d signals", len(snap.get("signals", {})))
    return snap

@router.get("/qqq-score")
async def qqq_score(interval: Optional[str] = "1d", period: Optional[str] = "2y"):
    # The trend-regime engine needs ~200 daily bars, so default to daily data.
    logger.info("[API] GET /qqq-score interval=%s period=%s", interval, period)
    # The cached payload is computed with the defaults; for non-default params
    # fall through to an on-demand compute.
    if (interval or "1d") == "1d" and (period or "2y") == "2y":
        cached = await cache.get(QQQ_SCORE_KEY)
        if cached:
            logger.info("[API] QQQ score served from Redis")
            return cached
    score = await market.fetch_qqq_score(period=period or "2y", interval=interval or "1d")
    logger.debug("[API] QQQ score payload: %s", score)
    return score

@router.get("/prediction")
async def prediction():
    logger.info("[API] GET /prediction")
    # Served from the Redis cache the background poll loop keeps fresh; only
    # compute on demand if the cache is empty (Redis down, or loop not started).
    cached = await cache.get(PREDICTION_KEY)
    if cached:
        logger.info("[API] Prediction served from Redis (status=%s)", cached.get("status"))
        return cached
    logger.info("[API] Prediction cache miss — computing on demand")
    pred = await market.fetch_prediction()
    logger.info("[API] Prediction computed (status=%s)", pred.get("status"))
    return pred


@router.get("/rotation")
async def rotation():
    """Cross-sector rotation flow (1m). Served from the Redis cache the poll loop
    keeps fresh; computed on demand only when the cache is cold."""
    logger.info("[API] GET /rotation")
    cached = await cache.get(ROTATION_KEY)
    if cached:
        logger.info("[API] Rotation served from Redis (session=%s)", cached.get("session"))
        return cached
    logger.info("[API] Rotation cache miss — computing on demand")
    return await market.fetch_rotation()


@router.get("/rotation/history")
async def rotation_history(limit: Optional[int] = 30):
    """Persisted daily rotation backtests (intraday-final vs daily-read agreement)."""
    logger.info("[API] GET /rotation/history limit=%s", limit)
    return {"history": rotation_store.history(limit=limit or 30)}


@router.get("/premarket")
async def premarket():
    """Overnight / pre-market board — the day's biggest Nasdaq-100 movers, the
    overnight tape (US futures, Asia semis, Europe), and how each mover sits
    vs the tape and the crowd. Descriptive pre-open context; never feeds scoring.
    Served from the service's own ~15-min in-process cache."""
    logger.info("[API] GET /premarket")
    return await market.fetch_premarket_board()


@router.get("/ai-dependency")
async def ai_dependency():
    """Public AI-capex dependency index — structural/daily metric for the
    landing-page highlight. Served from the cached prediction when warm,
    otherwise computed on demand (its own in-process daily cache keeps it cheap)."""
    logger.info("[API] GET /ai-dependency")
    cached = await cache.get(PREDICTION_KEY)
    if cached and cached.get("ai_dependency"):
        return cached["ai_dependency"]
    return await market.fetch_ai_dependency()


# --------------------------------------------------------------------------
# Authentication
# --------------------------------------------------------------------------
# Signup / login / sessions are handled by Supabase Auth directly from the
# frontend. The backend only verifies the resulting access token.
@router.get("/auth/me")
def auth_me(user: dict = Depends(auth.get_current_user)):
    """Verify the Supabase Bearer token and return the current user."""
    return {"user": user}


# --------------------------------------------------------------------------
# Pro-only endpoints (gated by require_pro -> 403 for free users)
# --------------------------------------------------------------------------
@router.get("/export/history.csv")
async def export_history_csv(user: dict = Depends(auth.require_pro)):
    """Pro feature: download recent QQQ vs sector history as CSV."""
    logger.info("[API] GET /export/history.csv user=%s", user.get("id"))
    snap = await market.fetch_snapshot()
    rows = snap.get("qqqComparison") or []
    lines = ["date,qqq,xlk,smh"]
    for r in rows:
        lines.append(
            f"{r.get('name', '')},{r.get('qqq', '')},{r.get('xlk', '')},{r.get('smh', '')}"
        )
    return Response(
        content="\n".join(lines),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="price-flow-history.csv"'},
    )


@router.get("/alerts/preferences")
async def get_alert_preferences(user: dict = Depends(auth.require_pro)):
    """Pro: read the current regime-alert email preference."""
    enabled = await supabase_admin.get_alerts_enabled(user["id"])
    return {"alerts_enabled": bool(enabled)}


@router.post("/alerts/preferences")
async def set_alert_preferences(payload: dict, user: dict = Depends(auth.require_pro)):
    """Pro: enable or disable regime-alert emails."""
    enabled = bool(payload.get("alerts_enabled", True))
    ok = await supabase_admin.update_profile(user["id"], {"alerts_enabled": enabled})
    if not ok:
        raise HTTPException(status_code=500, detail="Could not update alert preference")
    logger.info("[API] alerts_enabled=%s for user %s", enabled, user["id"])
    return {"alerts_enabled": enabled}


@router.post("/alerts/test")
async def send_test_alert(user: dict = Depends(auth.require_pro)):
    """Pro: send a sample alert email to the user's own address — verifies
    the email path end to end, on demand."""
    email = user.get("email")
    if not email:
        raise HTTPException(status_code=400, detail="No email address on this account.")
    if not settings.RESEND_API_KEY:
        raise HTTPException(
            status_code=503,
            detail="Email is not configured on the server (RESEND_API_KEY is not set).",
        )
    ok = await alerts.send_email(
        email, "Test alert — RelativeQs", alerts.test_email_html()
    )
    if not ok:
        raise HTTPException(
            status_code=502, detail="Email send failed — check the server logs."
        )
    logger.info("[API] test alert email sent to %s", email)
    return {"sent": True, "to": email}


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
