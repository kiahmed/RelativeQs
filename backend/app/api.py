from fastapi import APIRouter, HTTPException, Depends, Response
import os
import logging
from typing import Optional
from app.services.market_data import MarketDataService
from app.core.score_engine import ScoreEngine
from app.config import settings
from app import auth, supabase_admin, alerts

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
async def qqq_score(interval: Optional[str] = "1d", period: Optional[str] = "2y"):
    # The trend-regime engine needs ~200 daily bars, so default to daily data.
    logger.info("[API] GET /qqq-score interval=%s period=%s", interval, period)
    score = await market.fetch_qqq_score(period=period or "2y", interval=interval or "1d")
    logger.debug("[API] QQQ score payload: %s", score)
    return score

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
        email, "Test alert — Price Flow Tracker", alerts.test_email_html()
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
