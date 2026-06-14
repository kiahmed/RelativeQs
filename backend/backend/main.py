from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware
import asyncio
import logging
import os
import time

try:
    from dotenv import load_dotenv
    from pathlib import Path
    dotenv_path = Path(__file__).resolve().parents[1] / ".env"
    load_dotenv(dotenv_path=dotenv_path, verbose=True)
    print(f"Loaded .env from {dotenv_path}")
except ModuleNotFoundError:
    print("python-dotenv not installed; .env will not be loaded")
except Exception as e:
    print(f"Could not load .env file: {e}")

# Configure logging before importing app modules so their import-time logs
# (and every later [API]/[MARKET]/[CACHE] line) land in backend/logs/app.log.
from app.logging_config import setup_logging
setup_logging()
logger = logging.getLogger(__name__)

print(f"DATA_PROVIDER environment value: {os.getenv('DATA_PROVIDER')}")
print(f"ALPHAVANTAGE_KEY present: {'ALPHAVANTAGE_KEY' in os.environ and bool(os.environ.get('ALPHAVANTAGE_KEY'))}")

from app.api import router
from app.billing import router as billing_router
from app.ws_manager import WSManager
from app.services.market_data import MarketDataService
from app.config import settings
from app import alerts

app = FastAPI(title="RelativeQs - Backend")

# Allow local frontend origins; adjust for production.
# 5173 = `npm run dev` (Vite dev server), 4173 = `npm run preview` (built app).
origins = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:4173",
    "http://127.0.0.1:4173",
]
# Production origins (the deployed Vercel site, preview deploys, etc.) come from
# CORS_ORIGINS as a comma-separated list, e.g.
# CORS_ORIGINS="https://relativeqs.vercel.app,https://relativeqs.com"
_extra_origins = os.getenv("CORS_ORIGINS", "")
origins += [o.strip() for o in _extra_origins.split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router, prefix="/api")
app.include_router(billing_router, prefix="/api")

provider_mode = os.getenv("DATA_PROVIDER", "mock")
print(f"Using data provider mode: {provider_mode}")
market = MarketDataService(mode=provider_mode)

ws_manager = WSManager()

@app.on_event("startup")
async def startup_event():
    # start background task to poll market data and broadcast
    app.state._market_task = asyncio.create_task(_poll_and_broadcast())

@app.on_event("shutdown")
async def shutdown_event():
    task = getattr(app.state, "_market_task", None)
    if task:
        task.cancel()


def _market_closed_et(now_utc):
    """True on a weekday after the 16:00 ET close — when the settled after-hours
    rotation backtest can be finalized. (Holidays simply won't produce fresh
    bars; the finalize is idempotent per date so a no-op write is harmless.)"""
    from datetime import time as dtime
    from zoneinfo import ZoneInfo
    et = now_utc.astimezone(ZoneInfo("America/New_York"))
    return et.weekday() < 5 and et.time() >= dtime(16, 0)


async def _finalize_rotation_backtest(market, store, et_date):
    """Settle the day's rotation read once: final 1m intraday + coarse daily read
    + their agreement score, persisted under the calendar date."""
    from app.services.rotation_store import compute_agreement
    intraday_final = await market.fetch_rotation(use_cache=False, session="final")
    daily_read = await market.fetch_rotation_daily()
    agreement = compute_agreement(intraday_final, daily_read)
    await asyncio.to_thread(
        store.write, et_date, intraday_final, daily_read, agreement
    )
    logger.info("[ROTATION] finalized backtest for %s (agreement=%.3f)",
                et_date, agreement)


# background task handle for the de-duplicated pre-market board pre-warm
_premkt_task = None


async def _poll_and_broadcast():
    from datetime import datetime, timezone
    from zoneinfo import ZoneInfo
    from app.services.cache import (
        RedisCache, SNAPSHOT_KEY, QQQ_SCORE_KEY, PREDICTION_KEY, ROTATION_KEY,
    )
    from app.services.history_store import IntradayHistoryStore
    from app.services.rotation_store import RotationStore

    cache = RedisCache()
    rotation_store = RotationStore()
    # Guard so the after-hours finalize writes at most once per calendar date
    # per process (the loop keeps spinning every poll interval after the close).
    finalized_date = None
    # One history store for the loop's lifetime: it accumulates 1m bars across
    # cycles so the lead/lag engine sees the whole session, not just one fetch.
    history_store = IntradayHistoryStore(cache=cache)
    # Keep the cached payloads alive a few cycles longer than the poll interval
    # so one slow/failed fetch doesn't leave the API serving an empty cache.
    cache_ttl = max(int(settings.POLL_INTERVAL_SECONDS) * 3, 60)
    cycle = 0

    logger.info("[POLL] background loop started (interval=%ss)", settings.POLL_INTERVAL_SECONDS)
    while True:
        cycle += 1
        started = time.monotonic()
        # One failed cycle must not kill the loop — log it and try again next tick.
        try:
            # use_cache=False: the poll interval is the throttle, so each cycle
            # pulls genuinely fresh data and writes it to Redis for the API/UI.
            snapshot = await market.fetch_snapshot(use_cache=False)
            qqq_score = await market.fetch_qqq_score()
            # The score is computed from daily bars, so its "price" is pinned to
            # the last regular-session close. Override with the freshest intraday
            # price from the snapshot (includes pre/post market bars when active).
            flow = snapshot.get("flow_series") or []
            if flow and qqq_score.get("price"):
                qqq_score["price"] = float(flow[-1]["QQQ"])

            # Intraday prediction: accumulate session bars in the history store
            # and run the lead/lag, score, and projection engines.
            prediction = await market.fetch_prediction(history_store=history_store)

            # Cross-sector rotation flow (cached ~one poll interval inside the
            # service, so this is cheap and won't re-hit yfinance every cycle).
            rotation = await market.fetch_rotation(use_cache=False, session="live")

            # Pre-warm the overnight/pre-market board OFF the critical path — its
            # ~100-ticker pull is slow (~40s cold) but only runs once every
            # PREMARKET_REFRESH_SECONDS thanks to its in-process cache. Fire it as
            # a background task (de-duplicated) so the API always serves it warm
            # and the prediction poll never stalls on it.
            global _premkt_task
            if _premkt_task is None or _premkt_task.done():
                _premkt_task = asyncio.create_task(market.fetch_premarket_board())
            # Backfill the legacy qqq_score fields the existing UI reads, so the
            # measured lead/lag and composite signal show up without a schema break.
            try:
                qqq_score["lead_lag"] = prediction["lead_lag"]["entries"]
                qqq_score["lead_signal"] = prediction["score"]["score"]
            except Exception:
                logger.exception("[POLL] failed to backfill qqq_score from prediction")

            # publish the freshest payloads to Redis — this is the process that
            # keeps the cache the frontend reads continuously up to date.
            await cache.set(SNAPSHOT_KEY, snapshot, expire=cache_ttl)
            await cache.set(QQQ_SCORE_KEY, qqq_score, expire=cache_ttl)
            await cache.set(PREDICTION_KEY, prediction, expire=cache_ttl)
            await cache.set(ROTATION_KEY, rotation, expire=cache_ttl)
            # broadcast to websocket clients
            await ws_manager.broadcast({"type": "snapshot", "payload": snapshot})
            await ws_manager.broadcast({"type": "qqq_score", "payload": qqq_score})
            await ws_manager.broadcast({"type": "prediction", "payload": prediction})
            await ws_manager.broadcast({"type": "rotation", "payload": rotation})

            # After-hours: settle the day's rotation backtest exactly once.
            now_utc = datetime.now(timezone.utc)
            et_date = now_utc.astimezone(
                ZoneInfo("America/New_York")
            ).strftime("%Y-%m-%d")
            if _market_closed_et(now_utc) and finalized_date != et_date:
                try:
                    await _finalize_rotation_backtest(market, rotation_store, et_date)
                    finalized_date = et_date
                except Exception:
                    logger.exception("[ROTATION] finalize failed for %s", et_date)

            elapsed = time.monotonic() - started
            logger.info(
                "[POLL] cycle %d OK in %.2fs | provider=%s signals=%d qqq_dir=%s prob=%.3f ws_clients=%d",
                cycle, elapsed, qqq_score.get("provider", "?"),
                len(snapshot.get("signals", {})),
                qqq_score.get("direction", "?"),
                float(qqq_score.get("probability", 0.0) or 0.0),
                len(ws_manager.active),
            )

            # email Pro subscribers on a major Nasdaq-100 breadth-state shift
            try:
                await alerts.check_breadth_and_alert(prediction.get("breadth", {}))
            except Exception:
                logger.exception("[ALERTS] breadth check failed")
        except asyncio.CancelledError:
            logger.info("[POLL] background loop cancelled — stopping")
            raise
        except Exception:
            elapsed = time.monotonic() - started
            logger.exception("[POLL] cycle %d FAILED after %.2fs", cycle, elapsed)

        # polling interval — configurable via POLL_INTERVAL_SECONDS in .env
        await asyncio.sleep(settings.POLL_INTERVAL_SECONDS)


@app.websocket("/ws/market")
async def ws_market(ws: WebSocket):
    await ws_manager.connect(ws)
    try:
        while True:
            data = await ws.receive_text()
            # echo or allow simple control messages in the future
            await ws.send_text(f"ack: {data}")
    except Exception:
        await ws_manager.disconnect(ws)
