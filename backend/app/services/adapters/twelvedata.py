import os
import asyncio
from typing import List, Optional
import pandas as pd
import aiohttp
from app.services.rate_limiter import SimpleRateLimiter

# TwelveData free tier: be conservative, e.g. 8 calls per minute
_rate_limiter = SimpleRateLimiter(calls=8, per_seconds=60)

API_URL = "https://api.twelvedata.com/time_series"

class TwelveDataAdapter:
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("TWELVEDATA_API_KEY")

    async def fetch_history(self, symbols: List[str], period: str = "90d", interval: str = "1day") -> Optional[pd.DataFrame]:
        if not self.api_key:
            return None

        frames = {}
        async with aiohttp.ClientSession() as session:
            for symbol in symbols:
                # respect rate limits
                await _rate_limiter.acquire('twelvedata')
                params = {
                    "symbol": symbol,
                    "interval": interval,
                    "outputsize": 5000,
                    "apikey": self.api_key,
                }
                async with session.get(API_URL, params=params, timeout=30) as resp:
                    data = await resp.json()
                values = data.get("values") or []
                if not values:
                    continue
                df = pd.DataFrame(values)
                df.index = pd.to_datetime(df["datetime" if "datetime" in df.columns else "date"]) 
                if "close" in df.columns:
                    frames[symbol] = df["close"].astype(float).sort_index()
        if not frames:
            return None
        return pd.concat(frames, axis=1)
