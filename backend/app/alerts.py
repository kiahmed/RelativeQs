"""
Breadth-shift alerts.

The market poll loop calls `check_breadth_and_alert()` each cycle with the live
Nasdaq-100 breadth payload. When equal-weight breadth makes a MAJOR shift —
the participation state flips between broad / mixed / narrow — every Pro user
who has alerts enabled is emailed via Resend.

This aligns the alert with the intraday tech thesis: it fires on real changes in
how many Nasdaq-100 names are actually participating (true breadth), not on a
lagging long-term 200-day-SMA cross.

The "last state" is kept in process memory: the first observation after a
restart seeds it silently (no alert), so a restart never produces a spurious
alert. A flip across a restart would be missed — acceptable, since these shifts
are infrequent.
"""

import logging
from typing import Optional

import aiohttp

from app import supabase_admin
from app.config import settings

logger = logging.getLogger(__name__)

_RESEND_URL = "https://api.resend.com/emails"

# last breadth state observed by the poll loop (process-local)
_last_breadth_state: Optional[str] = None

# human copy + color per breadth state
_STATE_META = {
    "broad": ("Broad participation", "#10b981"),
    "mixed": ("Mixed participation", "#f59e0b"),
    "narrow": ("Narrow participation", "#f43f5e"),
}


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


def _email_html(previous: str, current: str, breadth: dict) -> str:
    cur_label, color = _STATE_META.get(current, (current, "#22d3ee"))
    prev_label = _STATE_META.get(previous, (previous,))[0]
    eq = float(breadth.get("equal_weight_pct", 0.0) or 0.0) * 100
    cap = float(breadth.get("cap_weight_pct", 0.0) or 0.0) * 100
    adv = breadth.get("advancers")
    measured = breadth.get("measured")
    count_txt = (f"{adv}/{measured} names advancing — "
                 if adv is not None and measured else "")
    return (
        '<div style="font-family:system-ui,sans-serif;max-width:480px;margin:0 auto">'
        f'<h2 style="color:{color};margin-bottom:4px">QQQ breadth: {cur_label}</h2>'
        f'<p style="color:#475569">Nasdaq-100 participation just shifted from '
        f"<b>{prev_label}</b> to <b>{cur_label}</b>.</p>"
        f'<p style="color:#475569">{count_txt}{eq:.0f}% equal-weight, '
        f"{cap:.0f}% cap-weight.</p>"
        '<p style="font-size:13px;color:#94a3b8">This is a market-internals '
        "signal, not investment advice.</p>"
        "</div>"
    )


def test_email_html() -> str:
    """Body for the on-demand 'send test alert' email."""
    return (
        '<div style="font-family:system-ui,sans-serif;max-width:480px;margin:0 auto">'
        '<h2 style="color:#22d3ee;margin-bottom:4px">Test alert &#10003;</h2>'
        '<p style="color:#475569">This is a test email from RelativeQs. '
        "Your breadth-shift alerts are wired up correctly — you'll get an email "
        "like this whenever Nasdaq-100 participation flips between broad, mixed "
        "and narrow.</p>"
        '<p style="font-size:13px;color:#94a3b8">No action needed. This is a '
        "market-internals signal, not investment advice.</p>"
        "</div>"
    )


async def _dispatch(previous: str, current: str, breadth: dict) -> None:
    """Email every Pro subscriber about a breadth-state shift."""
    recipients = await supabase_admin.list_alert_recipients()
    if not recipients:
        logger.info(
            "[ALERTS] breadth shift %s -> %s, but no subscribers", previous, current
        )
        return
    cur_label = _STATE_META.get(current, (current,))[0]
    subject = f"QQQ breadth shift: {cur_label}"
    html = _email_html(previous, current, breadth)
    sent = 0
    for r in recipients:
        email = r.get("email")
        if email and await send_email(email, subject, html):
            sent += 1
    logger.info(
        "[ALERTS] breadth shift %s -> %s: emailed %d/%d subscribers",
        previous, current, sent, len(recipients),
    )


async def check_breadth_and_alert(breadth: dict) -> None:
    """Called each poll cycle — detect a MAJOR equal-weight breadth shift
    (broad/mixed/narrow participation flip) and notify subscribers."""
    global _last_breadth_state
    if not isinstance(breadth, dict) or breadth.get("status") != "ok":
        return  # warming up / no data
    state = breadth.get("breadth_state")
    if state not in _STATE_META:
        return  # 'unknown' / missing
    if _last_breadth_state is None:
        _last_breadth_state = state
        logger.info("[ALERTS] baseline breadth state set to %s", state)
        return
    if state == _last_breadth_state:
        return
    previous, _last_breadth_state = _last_breadth_state, state
    logger.info("[ALERTS] breadth shift detected: %s -> %s", previous, state)
    await _dispatch(previous, state, breadth)
