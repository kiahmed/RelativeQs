import os
import asyncio
from typing import List, Optional
import pandas as pd
import aiohttp
from app.services.rate_limiter import SimpleRateLimiter

# AlphaVantage free tier is very limited; default to 5 calls per minute
_rate_limiter = SimpleRateLimiter(calls=5, per_seconds=60)

API_URL = "https://www.alphavantage.co/query"

class AlphaVantageAdapter:
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("ALPHAVANTAGE_API_KEY")

    async def fetch_history(self, symbols: List[str], period: str = "90d", interval: str = "1d") -> Optional[pd.DataFrame]:
        if not self.api_key:
            return None

        # AlphaVantage only allows one symbol per request for free tier
        frames = {}
        async with aiohttp.ClientSession() as session:
            for symbol in symbols:
                # respect rate limits for the free tier
                await _rate_limiter.acquire('alphavantage')
                params = {
                    "function": "TIME_SERIES_DAILY_ADJUSTED",
                    "symbol": symbol,
                    "outputsize": "compact",
                    "apikey": self.api_key,
                }
                async with session.get(API_URL, params=params, timeout=30) as resp:
                    data = await resp.json()
                ts = data.get("Time Series (Daily)") or {}
                if not ts:
                    continue
                df = pd.DataFrame.from_dict(ts, orient="index")
                df.index = pd.to_datetime(df.index)
                # close is in '5. adjusted close' or '5. adjusted close' depending on API
                close_col = None
                for col in df.columns:
                    if 'adjusted' in col.lower() or col.lower().endswith('5'):
                        close_col = col
                        break
                if close_col is None and '4. close' in df.columns:
                    close_col = '4. close'
                if close_col:
                    frames[symbol] = df[close_col].astype(float).sort_index()
        if not frames:
            return None
        return pd.concat(frames, axis=1)
