"""
Regime-change alerts.

The market poll loop calls `check_regime_and_alert()` each cycle. When the QQQ
trend regime flips (risk-on <-> risk-off), every Pro user who has alerts
enabled is emailed via Resend.

The "last regime" is kept in process memory: the first observation after a
restart seeds it silently (no alert), so a restart never produces a spurious
alert. A flip that happens exactly across a restart would be missed — an
acceptable trade-off, since regime flips are rare (a 200-day-SMA cross).
"""

import logging
from typing import Optional

import aiohttp

from app import supabase_admin
from app.config import settings

logger = logging.getLogger(__name__)

_RESEND_URL = "https://api.resend.com/emails"

# last regime observed by the poll loop (process-local)
_last_regime: Optional[str] = None


async def send_email(to_email: str, subject: str, html: str) -> bool:
    """Send one email via Resend. With no API key configured, log instead."""
    if not settings.RESEND_API_KEY:
        logger.warning(
            "[ALERTS] RESEND_API_KEY not set — would email %s: %s", to_email, subject
        )
        return False
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                _RESEND_URL,
                headers={"Authorization": f"Bearer {settings.RESEND_API_KEY}"},
                json={
                    "from": settings.ALERT_FROM_EMAIL,
                    "to": [to_email],
                    "subject": subject,
                    "html": html,
                },
                timeout=15,
            ) as resp:
                if resp.status >= 300:
                    logger.error(
                        "[ALERTS] Resend failed (%s): %s", resp.status, await resp.text()
                    )
                    return False
                return True
    except Exception as exc:
        logger.error("[ALERTS] Resend send error for %s: %s", to_email, exc)
        return False


def _email_html(previous: str, current: str, trend_gap: float) -> str:
    color = "#10b981" if current == "risk-on" else "#f43f5e"
    pct = abs(trend_gap) * 100
    side = "above" if trend_gap >= 0 else "below"
    return (
        '<div style="font-family:system-ui,sans-serif;max-width:480px;margin:0 auto">'
        f'<h2 style="color:{color};margin-bottom:4px">Market regime: {current.upper()}</h2>'
        f'<p style="color:#475569">QQQ\'s trend regime just changed from '
        f"<b>{previous}</b> to <b>{current}</b>.</p>"
        f'<p style="color:#475569">QQQ is now {pct:.1f}% {side} its 200-day '
        "trend line.</p>"
        '<p style="font-size:13px;color:#94a3b8">This is a market-internals '
        "signal, not investment advice.</p>"
        "</div>"
    )


def test_email_html() -> str:
    """Body for the on-demand 'send test alert' email."""
    return (
        '<div style="font-family:system-ui,sans-serif;max-width:480px;margin:0 auto">'
        '<h2 style="color:#22d3ee;margin-bottom:4px">Test alert &#10003;</h2>'
        '<p style="color:#475569">This is a test email from Price Flow Tracker. '
        "Your regime-change alerts are wired up correctly — you'll get an email "
        "like this whenever QQQ flips between risk-on and risk-off.</p>"
        '<p style="font-size:13px;color:#94a3b8">No action needed. This is a '
        "market-internals signal, not investment advice.</p>"
        "</div>"
    )


async def _dispatch(previous: str, current: str, qqq_score: dict) -> None:
    """Email every Pro subscriber about a regime flip."""
    recipients = await supabase_admin.list_alert_recipients()
    if not recipients:
        logger.info(
            "[ALERTS] regime flip %s -> %s, but no subscribers", previous, current
        )
        return
    subject = f"QQQ regime changed: {current.upper()}"
    html = _email_html(previous, current, float(qqq_score.get("trend_gap", 0.0) or 0.0))
    sent = 0
    for r in recipients:
        email = r.get("email")
        if email and await send_email(email, subject, html):
            sent += 1
    logger.info(
        "[ALERTS] regime flip %s -> %s: emailed %d/%d subscribers",
        previous, current, sent, len(recipients),
    )


async def check_regime_and_alert(qqq_score: dict) -> None:
    """Called each poll cycle — detect a regime flip and notify subscribers."""
    global _last_regime
    regime = qqq_score.get("regime")
    if regime not in ("risk-on", "risk-off"):
        return  # ignore 'unknown' / missing
    if _last_regime is None:
        _last_regime = regime
        logger.info("[ALERTS] baseline regime set to %s", regime)
        return
    if regime == _last_regime:
        return
    previous, _last_regime = _last_regime, regime
    logger.info("[ALERTS] regime flip detected: %s -> %s", previous, regime)
    await _dispatch(previous, regime, qqq_score)
