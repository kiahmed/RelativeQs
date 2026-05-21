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
        self.rate_limiter = SimpleRateLimiter("alpaca", calls_per_minute=5)

    async def fetch_history(self, symbols: List[str], period: str = "90d", interval: str = "1d") -> Optional[pd.DataFrame]:
        """Fetch historical close prices for `symbols` using Alpaca Market Data API.
        Returns None if keys missing.
        """
        if not (self.api_key and self.secret):
            return None
        if aiohttp is None:
            return None

        headers = {"APCA-API-KEY-ID": self.api_key, "APCA-API-SECRET-KEY": self.secret}
        results = {}
        base = "https://data.alpaca.markets/v2/stocks"
        async with aiohttp.ClientSession(headers=headers) as session:
            for sym in symbols:
                await self.rate_limiter.wait_for_slot()
                url = f"{base}/{sym}/bars?timeframe=1Day&limit=500"
                try:
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
