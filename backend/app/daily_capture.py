"""
Once-a-day persistence of "what was the picture that day".

Two captures, written to Supabase Postgres (tables in
``supabase/migrations/0003_daily_picture.sql``) and joined on ``trade_date``
(the US/Eastern calendar date):

  * 09:28 ET  ``overnight_movers_stats`` — one row per overnight mover, taken
              from the pre-market board just before the 09:30 open.
  * 10:05 ET  ``daily_highlights``      — one row for the day: breadth, rotation
              flow, AI-capex dependency (last ~2 weeks), internal health,
              strongest sector, fragility, confirmation, correlation regime.

The scheduler is driven by the backend poll loop (``tick`` is called once per
cycle), so it needs no separate process. Each capture is idempotent — an
upsert on its primary key — so a restart inside the window just rewrites the
same rows. Failures retry every cycle until the capture window closes.

The builders are pure functions over the payloads the loop already holds, which
is what the tests exercise. Health / fragility / strongest-sector are the same
formulas the dashboard computes client-side (``deriveQQQHealth`` etc.).
"""

import asyncio
import logging
import math
import time as _time
from datetime import date, datetime, time as dtime, timedelta, timezone
from typing import Any, Awaitable, Callable, Dict, List, Optional, Tuple
from zoneinfo import ZoneInfo

import aiohttp

from app.config import settings
from app.core.rotation import DISPLAY_NAMES

logger = logging.getLogger(__name__)

ET = ZoneInfo("America/New_York")
MOVERS_TABLE = "overnight_movers_stats"
HIGHLIGHTS_TABLE = "daily_highlights"

# How long after the scheduled time a capture may still run (catch-up after a
# restart or a failed write). The actual ``captured_at`` is always recorded.
MOVERS_GRACE = timedelta(minutes=15)
HIGHLIGHTS_GRACE = timedelta(minutes=30)
RETRY_AFTER_SECONDS = 60
AI_TREND_POINTS = 10  # ~2 trading weeks of daily dependency readings


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def _clean(obj: Any) -> Any:
    """Make a structure JSON-safe: non-finite floats become None."""
    if isinstance(obj, float):
        return obj if math.isfinite(obj) else None
    if isinstance(obj, dict):
        return {k: _clean(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_clean(v) for v in obj]
    return obj


def _num(x: Any) -> Optional[float]:
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return v if math.isfinite(v) else None


def _parse_hhmm(text: str, default: dtime) -> dtime:
    try:
        h, m = text.strip().split(":")
        return dtime(int(h), int(m))
    except Exception:
        logger.warning("[CAPTURE] bad time %r, using %s", text, default)
        return default


def derive_health(prediction: Dict[str, Any]) -> Tuple[Optional[int], Optional[str]]:
    """QQQ internal health (0-100) and regime — port of the dashboard's
    ``deriveQQQHealth``. (None, None) while the score is warming up."""
    score = (prediction or {}).get("score") or {}
    if (prediction or {}).get("status") != "ok" or score.get("status") != "ok":
        return None, None
    comp = score.get("components") or {}
    leadership = _num(comp.get("leadership")) or 0.0
    broadening = _num(comp.get("broadening")) or 0.0
    fragility = _num(comp.get("fragility")) or 0.0
    prob_up = _num(score.get("probability_up"))
    prob_up = 0.5 if prob_up is None else prob_up

    target = prediction.get("target") or "QQQ"
    mom = score.get("momentum_30m") or {}
    peers = [s for s in mom if s != target]
    participation = (
        sum(1 for s in peers if (_num(mom[s]) or 0.0) > 0) / len(peers) if peers else 0.5
    )

    raw = 0.45 * prob_up + 0.3 * participation + 0.25 * (1 - fragility)
    health = max(0, min(100, round(raw * 100)))
    if fragility >= 0.5:
        regime = "Narrow Participation"
    elif participation >= 0.6 and broadening > 0:
        regime = "Broad Participation"
    elif leadership > 0.2:
        regime = "Top-Sector Strength"
    else:
        regime = "Mixed Participation"
    return health, regime


def fragility_level(fragility: Optional[float], ready: bool) -> str:
    if not ready or fragility is None:
        return "Unknown"
    if fragility >= 0.5:
        return "High"
    if fragility >= 0.25:
        return "Elevated"
    return "Low"


def strongest_sector(prediction: Dict[str, Any]) -> Optional[Tuple[str, float]]:
    """Top tracked ETF by 30-minute momentum, excluding the target."""
    score = (prediction or {}).get("score") or {}
    target = (prediction or {}).get("target") or "QQQ"
    mom = {s: _num(v) for s, v in (score.get("momentum_30m") or {}).items() if s != target}
    mom = {s: v for s, v in mom.items() if v is not None}
    if not mom:
        return None
    sym = max(mom, key=mom.get)
    return sym, mom[sym]


def _rotation_summary(rotation: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    windows = (rotation or {}).get("windows") or {}
    if not windows:
        return None
    out: Dict[str, Any] = {}
    for key, w in windows.items():
        rows = (w.get("rows") or [])[:3]
        out[key] = {
            "regime": w.get("regime"),
            "subject_return": w.get("subject_return"),
            "summary": w.get("summary"),
            "top": [
                {"symbol": r.get("symbol"), "rel": r.get("rel"),
                 "dvol_surge": r.get("dvol_surge"), "tag": r.get("tag")}
                for r in rows
            ],
        }
    return out


# ---------------------------------------------------------------------------
# row builders (pure)
# ---------------------------------------------------------------------------
def build_mover_rows(board: Dict[str, Any], trade_date: date,
                     captured_at: datetime) -> List[Dict[str, Any]]:
    """Pre-market board -> one row per mover. [] if the board has no movers."""
    if not board or board.get("status") != "ok":
        return []
    tape = board.get("tape") or {}
    lean = board.get("open_lean") or {}
    rows = []
    for rank, m in enumerate(board.get("movers") or [], start=1):
        sym = str(m.get("symbol") or "").strip().upper()
        if not sym:
            continue
        rows.append({
            "trade_date": trade_date.isoformat(),
            "symbol": sym,
            "captured_at": captured_at.isoformat(),
            "rank": rank,
            "gap": _num(m.get("gap")),
            "since_open": _num(m.get("since_open")),
            "dir": m.get("dir"),
            "sector": m.get("sector"),
            "weight": _num(m.get("weight")),
            "vs_tape": m.get("vs_tape"),
            "crowd": m.get("crowd"),
            "sustain": m.get("sustain"),
            "board_phase": board.get("phase"),
            "open_lean_dir": lean.get("dir"),
            "open_lean_basis": lean.get("basis"),
            "tape_nq": _num(tape.get("nq")),
            "tape_es": _num(tape.get("es")),
            "tape_asia": _num(tape.get("asia")),
            "tape_europe": _num(tape.get("europe")),
            "breadth_up": _num(tape.get("breadth_up")),
            "cap_breadth_up": _num(tape.get("cap_breadth_up")),
        })
    return _clean(rows)


def build_highlights(prediction: Dict[str, Any], rotation: Optional[Dict[str, Any]],
                     qqq_score: Optional[Dict[str, Any]], trade_date: date,
                     captured_at: datetime) -> Dict[str, Any]:
    """The day's key takeaways -> one ``daily_highlights`` row."""
    prediction = prediction or {}
    score = prediction.get("score") or {}
    ready = prediction.get("status") == "ok" and score.get("status") == "ok"
    comp = score.get("components") or {}
    prob_up = _num(score.get("probability_up"))
    frag = _num(comp.get("fragility"))
    health, regime = derive_health(prediction)

    if not ready:
        direction = "warming up"
    else:
        pct = round((prob_up if prob_up is not None else 0.5) * 100)
        direction = "bullish" if pct >= 55 else "bearish" if pct <= 45 else "neutral"

    strong = strongest_sector(prediction)
    breadth = prediction.get("breadth") or {}
    breadth_ok = breadth.get("status") == "ok"
    ai = prediction.get("ai_dependency") or {}
    ai_ok = ai.get("status") == "ok"
    trend = (ai.get("dependency_trend") or [])[-AI_TREND_POINTS:] if ai_ok else None
    conf = prediction.get("confirmation") or {}
    corr = prediction.get("correlation_regime") or {}
    leader = ((prediction.get("lead_lag") or {}).get("leader") or {}).get("symbol")
    proj = prediction.get("projection") or {}

    row = {
        "trade_date": trade_date.isoformat(),
        "captured_at": captured_at.isoformat(),
        "qqq_price": _num((qqq_score or {}).get("price")),
        "direction": direction,
        "probability_up": prob_up if ready else None,
        "verdict": score.get("verdict"),
        "health_score": health,
        "health_regime": regime,
        "fragility": frag if ready else None,
        "fragility_level": fragility_level(frag, ready),
        "confirmation_state": conf.get("state"),
        "correlation_regime": corr.get("regime"),
        "leader_symbol": leader,
        "strongest_sector": strong[0] if strong else None,
        "strongest_sector_name": DISPLAY_NAMES.get(strong[0], strong[0]) if strong else None,
        "strongest_sector_mom": strong[1] if strong else None,
        "breadth_state": breadth.get("breadth_state") if breadth_ok else None,
        "breadth_equal_pct": _num(breadth.get("equal_weight_pct")) if breadth_ok else None,
        "breadth_cap_pct": _num(breadth.get("cap_weight_pct")) if breadth_ok else None,
        "breadth_divergence": _num(breadth.get("divergence")) if breadth_ok else None,
        "advancers": breadth.get("advancers") if breadth_ok else None,
        "decliners": breadth.get("decliners") if breadth_ok else None,
        "ai_dependency": _num(ai.get("dependency_now")) if ai_ok else None,
        "ai_dependency_change": _num(ai.get("change")) if ai_ok else None,
        "ai_dependency_2w": trend,
        "rotation": _rotation_summary(rotation),
        "detail": {
            "confirmation_message": conf.get("message"),
            "projection": {k: proj.get(k) for k in (
                "horizon_minutes", "expected_return", "band_low", "band_high",
                "confidence", "direction")} if proj else None,
            "ai_headline": ai.get("headline") if ai_ok else None,
            "breadth_message": breadth.get("message") if breadth_ok else None,
            "universe": prediction.get("universe"),
        },
    }
    return _clean(row)


# ---------------------------------------------------------------------------
# Supabase writer
# ---------------------------------------------------------------------------
async def upsert(table: str, rows: List[Dict[str, Any]], on_conflict: str) -> Tuple[bool, str]:
    """Upsert rows into ``public.<table>`` via PostgREST (service_role).
    Returns (ok, error_text)."""
    if not rows:
        return True, ""
    if not (settings.SUPABASE_URL and settings.SUPABASE_SERVICE_KEY):
        return False, "SUPABASE_URL / SUPABASE_SERVICE_KEY not configured"
    url = settings.SUPABASE_URL.rstrip("/") + f"/rest/v1/{table}"
    headers = {
        "apikey": settings.SUPABASE_SERVICE_KEY,
        "Authorization": f"Bearer {settings.SUPABASE_SERVICE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "resolution=merge-duplicates,return=minimal",
    }
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                url, headers=headers, params={"on_conflict": on_conflict},
                json=rows, timeout=aiohttp.ClientTimeout(total=20),
            ) as resp:
                if resp.status in (200, 201, 204):
                    return True, ""
                body = (await resp.text())[:300]
                if resp.status == 404:
                    body += " — apply supabase/migrations/0003_daily_picture.sql"
                return False, f"HTTP {resp.status}: {body}"
    except Exception as exc:  # network / timeout
        return False, f"{type(exc).__name__}: {exc}"


Writer = Callable[[str, List[Dict[str, Any]], str], Awaitable[Tuple[bool, str]]]


# ---------------------------------------------------------------------------
# scheduler
# ---------------------------------------------------------------------------
class DailyCapture:
    """Runs the two captures at their ET times, driven by the poll loop."""

    def __init__(self, market, writer: Writer = upsert,
                 clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc)):
        self.market = market
        self.writer = writer
        self.clock = clock
        self._state: Dict[str, str] = {}        # f"{date}:{job}" -> done|skipped|gave_up
        self._next_try: Dict[str, float] = {}   # job key -> monotonic time
        self._inflight: set = set()
        self._tasks: set = set()
        self._warned_disabled = False

    # -- schedule ---------------------------------------------------------
    def _windows(self) -> Dict[str, Tuple[dtime, timedelta]]:
        return {
            "movers": (_parse_hhmm(settings.OVERNIGHT_CAPTURE_TIME, dtime(9, 28)), MOVERS_GRACE),
            "highlights": (_parse_hhmm(settings.HIGHLIGHTS_CAPTURE_TIME, dtime(10, 5)), HIGHLIGHTS_GRACE),
        }

    def due_jobs(self, now_utc: datetime) -> List[str]:
        """Jobs whose window is open now and that haven't finished today."""
        now = now_utc.astimezone(ET)
        if now.weekday() >= 5:
            return []
        today = now.date()
        due = []
        for job, (start, grace) in self._windows().items():
            start_dt = datetime.combine(today, start, tzinfo=ET)
            if not (start_dt <= now <= start_dt + grace):
                continue
            key = f"{today}:{job}"
            if key in self._state or key in self._inflight:
                continue
            if self._next_try.get(key, 0.0) > _time.monotonic():
                continue
            due.append(job)
        return due

    # -- poll-loop hook ---------------------------------------------------
    async def tick(self, prediction: Dict[str, Any], rotation: Optional[Dict[str, Any]],
                   qqq_score: Optional[Dict[str, Any]]) -> None:
        """Call once per poll cycle. Returns immediately; captures run as tasks."""
        if not settings.DAILY_CAPTURE_ENABLED:
            return
        if not (settings.SUPABASE_URL and settings.SUPABASE_SERVICE_KEY):
            if not self._warned_disabled:
                logger.warning("[CAPTURE] Supabase not configured — daily captures disabled")
                self._warned_disabled = True
            return
        now_utc = self.clock()
        for job in self.due_jobs(now_utc):
            key = f"{now_utc.astimezone(ET).date()}:{job}"
            self._inflight.add(key)
            # snapshot the payloads now: the loop reassigns them next cycle
            task = asyncio.create_task(
                self._run(job, key, now_utc, prediction, rotation, qqq_score))
            self._tasks.add(task)
            task.add_done_callback(self._tasks.discard)

    async def _run(self, job, key, now_utc, prediction, rotation, qqq_score) -> None:
        trade_date = now_utc.astimezone(ET).date()
        try:
            if job == "movers":
                outcome = await self._capture_movers(trade_date, now_utc)
            else:
                outcome = await self._capture_highlights(
                    trade_date, now_utc, prediction, rotation, qqq_score)
        except Exception:
            logger.exception("[CAPTURE] %s crashed", job)
            outcome = "retry"
        finally:
            self._inflight.discard(key)
        if outcome == "retry":
            self._next_try[key] = _time.monotonic() + RETRY_AFTER_SECONDS
            self._maybe_give_up(job, key, now_utc)
        else:
            self._state[key] = outcome

    def _maybe_give_up(self, job: str, key: str, now_utc: datetime) -> None:
        start, grace = self._windows()[job]
        deadline = datetime.combine(now_utc.astimezone(ET).date(), start, tzinfo=ET) + grace
        if now_utc.astimezone(ET) + timedelta(seconds=RETRY_AFTER_SECONDS) > deadline:
            logger.error("[CAPTURE] %s: window closed without a successful write for %s", job, key)
            self._state[key] = "gave_up"

    # -- jobs ---------------------------------------------------------------
    async def _capture_movers(self, trade_date: date, now_utc: datetime) -> str:
        # force=True: the cached board can be up to 15 min old; this is THE read
        board = await self.market.fetch_premarket_board(force=True)
        if not board or board.get("status") != "ok":
            logger.warning("[CAPTURE] movers: board not ready (%s)", (board or {}).get("status"))
            return "retry"
        asof = board.get("asof") or ""
        try:
            asof_dt = datetime.fromisoformat(asof)
            asof_date = (asof_dt if asof_dt.tzinfo else asof_dt.replace(tzinfo=ET)).astimezone(ET).date()
        except ValueError:
            asof_date = None
        if asof_date != trade_date:
            # holiday / stale feed: do not file yesterday's board under today
            logger.warning("[CAPTURE] movers: board asof %r is not %s — skipping", asof, trade_date)
            return "skipped"
        rows = build_mover_rows(board, trade_date, now_utc)
        if not rows:
            logger.info("[CAPTURE] movers: board has no movers for %s", trade_date)
            return "skipped"
        ok, err = await self.writer(MOVERS_TABLE, rows, "trade_date,symbol")
        if not ok:
            logger.error("[CAPTURE] movers write failed: %s", err)
            return "retry"
        logger.info("[CAPTURE] movers: %d rows saved for %s", len(rows), trade_date)
        return "done"

    async def _capture_highlights(self, trade_date: date, now_utc: datetime,
                                  prediction, rotation, qqq_score) -> str:
        score = (prediction or {}).get("score") or {}
        if (prediction or {}).get("status") != "ok" or score.get("status") != "ok":
            # no live session bars yet (or a market holiday): try again next cycle
            logger.warning("[CAPTURE] highlights: prediction not ready (%s)",
                           (prediction or {}).get("status"))
            return "retry"
        row = build_highlights(prediction, rotation, qqq_score, trade_date, now_utc)
        ok, err = await self.writer(HIGHLIGHTS_TABLE, [row], "trade_date")
        if not ok:
            logger.error("[CAPTURE] highlights write failed: %s", err)
            return "retry"
        logger.info("[CAPTURE] highlights saved for %s (health=%s breadth=%s)",
                    trade_date, row.get("health_score"), row.get("breadth_state"))
        return "done"
