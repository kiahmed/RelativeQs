import os
import asyncio
import logging
from typing import List, Optional
import pandas as pd
import aiohttp
from app.services.rate_limiter import SimpleRateLimiter
from app.config import settings

logger = logging.getLogger(__name__)

# AlphaVantage free tier is very limited; default to 5 calls per minute
_rate_limiter = SimpleRateLimiter(calls=5, per_seconds=60)

API_URL = "https://www.alphavantage.co/query"

class AlphaVantageAdapter:
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or settings.ALPHAVANTAGE_KEY

    async def fetch_history(self, symbols: List[str], period: str = "90d", interval: str = "1d") -> Optional[pd.DataFrame]:
        if not self.api_key:
            return None
        # AlphaVantage only allows one symbol per request for free tier.
        # Parallelize requests while respecting the shared rate limiter.
        async def _fetch_one(session, symbol: str):
            try:
                await _rate_limiter.acquire('alphavantage')
                intraday_map = {
                    "1m": "1min",
                    "5m": "5min",
                    "15m": "15min",
                    "30m": "30min",
                    "60m": "60min",
                }
                if interval != "1d":
                    av_interval = intraday_map.get(interval, interval)
                    params = {
                        "function": "TIME_SERIES_INTRADAY",
                        "symbol": symbol,
                        "interval": av_interval,
                        "outputsize": "compact",
                        "apikey": self.api_key,
                    }
                else:
                    params = {
                        "function": "TIME_SERIES_DAILY_ADJUSTED",
                        "symbol": symbol,
                        "outputsize": "compact",
                        "apikey": self.api_key,
                    }
                logger.debug("[ALPHAVANTAGE] fetching %s with params %s", symbol, params)
                async with session.get(API_URL, params=params, timeout=30) as resp:
                    if resp.status != 200:
                        text = await resp.text()
                        logger.warning("[ALPHAVANTAGE] %s returned status %s: %s", symbol, resp.status, text)
                        return symbol, None
                    data = await resp.json()
                if "Error Message" in data or "Note" in data or "Information" in data:
                    logger.warning("[ALPHAVANTAGE] %s API message: %s", symbol, data)
                    return symbol, None
                if interval != "1d":
                    ts = data.get(f"Time Series ({av_interval})") or {}
                else:
                    ts = data.get("Time Series (Daily)") or {}
                if not ts:
                    logger.warning("[ALPHAVANTAGE] %s no time series returned, payload keys=%s", symbol, list(data.keys()))
                    return symbol, None
                df = pd.DataFrame.from_dict(ts, orient="index")
                df.index = pd.to_datetime(df.index)
                # determine close column
                close_col = None
                for col in df.columns:
                    if 'adjusted' in col.lower() or col.lower().endswith('5'):
                        close_col = col
                        break
                if close_col is None and '4. close' in df.columns:
                    close_col = '4. close'
                if close_col:
                    return symbol, df[close_col].astype(float).sort_index()
                logger.warning("[ALPHAVANTAGE] %s no close column found, columns=%s", symbol, list(df.columns))
                return symbol, None
            except Exception:
                return symbol, None

        frames = {}
        async with aiohttp.ClientSession() as session:
            tasks = [_fetch_one(session, s) for s in symbols]
            results = await asyncio.gather(*tasks)
            for sym, series in results:
                if series is not None:
                    frames[sym] = series

        if not frames:
            return None
        return pd.concat(frames, axis=1)
