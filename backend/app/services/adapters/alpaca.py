import os
from typing import List, Optional
import pandas as pd

try:
    import aiohttp
except Exception:
    aiohttp = None

from app.services.rate_limiter import SimpleRateLimiter
from app.config import settings


class AlpacaAdapter:
    def __init__(self, api_key: Optional[str] = None, secret: Optional[str] = None):
        self.api_key = api_key or settings.ALPACA_KEY
        self.secret = secret or settings.ALPACA_SECRET
        self.rate_limiter = SimpleRateLimiter(calls=settings.ALPACA_RATE_LIMIT, per_seconds=60)

    async def fetch_history(self, symbols: List[str], period: str = "90d", interval: str = "1d") -> Optional[pd.DataFrame]:
        """Fetch historical close prices for `symbols` using Alpaca Market Data API.
        Returns None if keys missing.
        """
        if not (self.api_key and self.secret):
            return None
        if aiohttp is None:
            return None

        timeframe_map = {
            "1m": "1Min",
            "5m": "5Min",
            "15m": "15Min",
            "1h": "1Hour",
            "1d": "1Day",
        }
        timeframe = timeframe_map.get(interval, "1Day")
        headers = {"APCA-API-KEY-ID": self.api_key, "APCA-API-SECRET-KEY": self.secret}
        results = {}
        base = "https://data.alpaca.markets/v2/stocks"
        async with aiohttp.ClientSession(headers=headers) as session:
            # try batch bars endpoint
            try:
                await self.rate_limiter.acquire('alpaca')
                symbols_param = ",".join(symbols)
                url = f"{base}/bars"
                params = {"symbols": symbols_param, "timeframe": timeframe, "limit": 500}
                async with session.get(url, params=params, timeout=30) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        bars_root = data.get("bars") or data
                        if isinstance(bars_root, dict):
                            for sym, arr in bars_root.items():
                                items = arr if isinstance(arr, list) else arr.get("bars", [])
                                results[sym] = [b.get("c") for b in items]
                        else:
                            pass
            except Exception:
                pass

            # fallback per-symbol (if batch failed or partial)
            for sym in symbols:
                if sym in results:
                    continue
                try:
                    await self.rate_limiter.acquire('alpaca')
                    url = f"{base}/{sym}/bars?timeframe={timeframe}&limit=500"
                    async with session.get(url, timeout=15) as resp:
                        if resp.status != 200:
                            continue
                        data = await resp.json()
                        bars = data.get("bars", [])
                        results[sym] = [b.get("c") for b in bars]
                except Exception:
                    continue

        if not results:
            return None

        df = pd.DataFrame({k: pd.Series(v) for k, v in results.items()})
        return df
