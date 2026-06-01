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

app = FastAPI(title="Price Flow Tracker - Backend")

# Allow local frontend origins; adjust for production.
# 5173 = `npm run dev` (Vite dev server), 4173 = `npm run preview` (built app).
origins = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:4173",
    "http://127.0.0.1:4173",
]
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


async def _poll_and_broadcast():
    from app.services.cache import RedisCache, SNAPSHOT_KEY, QQQ_SCORE_KEY

    cache = RedisCache()
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
            # publish the freshest payloads to Redis — this is the process that
            # keeps the cache the frontend reads continuously up to date.
            await cache.set(SNAPSHOT_KEY, snapshot, expire=cache_ttl)
            await cache.set(QQQ_SCORE_KEY, qqq_score, expire=cache_ttl)
            # broadcast to websocket clients
            await ws_manager.broadcast({"type": "snapshot", "payload": snapshot})
            await ws_manager.broadcast({"type": "qqq_score", "payload": qqq_score})

            elapsed = time.monotonic() - started
            logger.info(
                "[POLL] cycle %d OK in %.2fs | provider=%s signals=%d qqq_dir=%s prob=%.3f ws_clients=%d",
                cycle, elapsed, qqq_score.get("provider", "?"),
                len(snapshot.get("signals", {})),
                qqq_score.get("direction", "?"),
                float(qqq_score.get("probability", 0.0) or 0.0),
                len(ws_manager.active),
            )

            # email Pro subscribers if the QQQ trend regime just flipped
            try:
                await alerts.check_regime_and_alert(qqq_score)
            except Exception:
                logger.exception("[ALERTS] regime check failed")
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
