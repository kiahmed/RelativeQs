import time
from datetime import datetime, timedelta
from typing import List, Optional

import pandas as pd

try:
    import aiohttp
except Exception:
    aiohttp = None

from app.services.rate_limiter import SimpleRateLimiter
from app.config import settings


class FinnhubAdapter:
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or settings.FINNHUB_KEY
        self.rate_limiter = SimpleRateLimiter(calls=30, per_seconds=60)

    async def fetch_history(self, symbols: List[str], period: str = "90d", interval: str = "1d") -> Optional[pd.DataFrame]:
        if not self.api_key or aiohttp is None:
            return None

        now = int(time.time())
        start = int((datetime.utcfromtimestamp(now) - timedelta(days=90)).timestamp())
        results = {}
        async with aiohttp.ClientSession() as session:
            for symbol in symbols:
                await self.rate_limiter.acquire('finnhub')
                url = (
                    "https://finnhub.io/api/v1/stock/candle"
                    f"?symbol={symbol}&resolution=D&from={start}&to={now}&token={self.api_key}"
                )
                try:
                    async with session.get(url, timeout=20) as resp:
                        if resp.status != 200:
                            continue
                        payload = await resp.json()
                        if payload.get("s") != "ok":
                            continue
                        close_values = payload.get("c", [])
                        timestamps = payload.get("t", [])
                        if not close_values or not timestamps:
                            continue
                        index = [datetime.utcfromtimestamp(int(ts)).date() for ts in timestamps]
                        results[symbol] = pd.Series(close_values, index=pd.Index(index, name="date"))
                except Exception:
                    continue

        if not results:
            return None

        return pd.DataFrame(results)
