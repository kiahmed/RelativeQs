from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware
import asyncio
import os

try:
    from dotenv import load_dotenv
    load_dotenv(verbose=True)
    print("Loaded .env from backend directory")
except Exception as e:
    print(f"Could not load .env file: {e}")

from app.api import router
from app.ws_manager import WSManager
from app.services.market_data import MarketDataService

app = FastAPI(title="Price Flow Tracker - Backend")

# Allow local frontend origin; adjust for production
origins = ["http://localhost:5173", "http://127.0.0.1:5173"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router, prefix="/api")

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
    try:
        while True:
            snapshot = await market.fetch_snapshot()
            # broadcast to websocket clients
            await ws_manager.broadcast({"type": "snapshot", "payload": snapshot})
            await asyncio.sleep(1.0)  # polling interval (tunable)
    except asyncio.CancelledError:
        return


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
