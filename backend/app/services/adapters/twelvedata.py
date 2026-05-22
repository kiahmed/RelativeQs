import os
import asyncio
from typing import List, Optional
import pandas as pd
import aiohttp
from app.services.rate_limiter import SimpleRateLimiter
from app.config import settings

# TwelveData free tier: be conservative, e.g. 8 calls per minute.
# Configurable via TWELVEDATA_RATE_LIMIT in .env.
_rate_limiter = SimpleRateLimiter(calls=settings.TWELVEDATA_RATE_LIMIT, per_seconds=60)

API_URL = "https://api.twelvedata.com/time_series"

class TwelveDataAdapter:
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or settings.TWELVEDATA_KEY
    async def fetch_history(self, symbols: List[str], period: str = "90d", interval: str = "1day") -> Optional[pd.DataFrame]:
        if not self.api_key:
            return None

        # Try a single multi-symbol request first (TwelveData supports comma-separated symbols)
        symbols_str = ",".join(symbols)
        async with aiohttp.ClientSession() as session:
            try:
                await _rate_limiter.acquire('twelvedata')
                params = {
                    "symbol": symbols_str,
                    "interval": interval,
                    "outputsize": 5000,
                    "apikey": self.api_key,
                }
                async with session.get(API_URL, params=params, timeout=30) as resp:
                    data = await resp.json()

                frames = {}
                # single-symbol response
                if "values" in data:
                    df = pd.DataFrame(data.get("values", []))
                    if not df.empty and ("close" in df.columns):
                        frames[symbols[0]] = df["close"].astype(float).sort_index()
                else:
                    # multi-symbol response: keyed by symbol
                    for sym in symbols:
                        entry = data.get(sym) or data.get(sym.upper())
                        if not entry:
                            continue
                        vals = entry.get("values") or []
                        if not vals:
                            continue
                        df = pd.DataFrame(vals)
                        df.index = pd.to_datetime(df["datetime" if "datetime" in df.columns else "date"]) 
                        if "close" in df.columns:
                            frames[sym] = df["close"].astype(float).sort_index()

                if frames:
                    return pd.concat(frames, axis=1)
            except Exception:
                # fallback to per-symbol loop
                pass

            # fallback: per-symbol requests (keeps compatibility)
            frames = {}
            for symbol in symbols:
                try:
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
                except Exception:
                    continue

            if not frames:
                return None
            return pd.concat(frames, axis=1)
