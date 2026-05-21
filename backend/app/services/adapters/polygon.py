import os
from typing import List, Optional
import math
import logging
import pandas as pd

try:
    import aiohttp
except Exception:
    aiohttp = None

from app.services.rate_limiter import SimpleRateLimiter
from app.config import settings

logger = logging.getLogger(__name__)


class PolygonAdapter:
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or settings.POLYGON_KEY
        self.rate_limiter = SimpleRateLimiter(calls=5, per_seconds=60)

    async def _fetch_snapshot_batch(self, session, batch: List[str]) -> dict:
        """Call Polygon snapshot multi-ticker endpoint for a batch of tickers.

        Returns mapping symbol -> latest_close_price (float) when available.
        """
        url = "https://api.polygon.io/v2/snapshot/locale/us/markets/stocks/tickers"
        params = {"tickers": ",".join(batch), "apiKey": self.api_key}
        try:
            async with session.get(url, params=params, timeout=20) as resp:
                if resp.status != 200:
                    text = await resp.text()
                    logger.debug("Polygon snapshot batch failed: %s %s", resp.status, text)
                    return {}
                data = await resp.json()
        except Exception as exc:
            logger.debug("Polygon snapshot request exception: %s", exc)
            return {}

        out = {}
        for t in data.get("tickers", []):
            sym = t.get("ticker")
            # prefer day close, fallback to lastTrade price
            price = None
            day = t.get("day") or {}
            if day:
                price = day.get("c")
            if price is None:
                last = t.get("lastTrade") or {}
                price = last.get("p")
            try:
                if price is not None and not math.isnan(price):
                    out[sym] = float(price)
            except Exception:
                continue
        return out

    async def fetch_history(self, symbols: List[str], period: str = "90d", interval: str = "1d") -> Optional[pd.DataFrame]:
        """Fetch historical close prices for `symbols` using Polygon APIs.

        Behavior:
        - If `symbols` has multiple tickers, attempt to use the snapshot multi-ticker
          endpoint in chunked requests to fetch latest closes (batch path).
        - If snapshot doesn't return results or more history is requested, fall
          back to the per-symbol aggregates (`v2/aggs/ticker/.../range`) loop.

        Returns a DataFrame where each column is a symbol and rows are numeric indices
        (consistent with other adapters which may return short series).
        """
        if not self.api_key:
            return None
        if aiohttp is None:
            return None

        results = {}
        async with aiohttp.ClientSession() as session:
            if interval == "1m":
                for sym in symbols:
                    await self.rate_limiter.acquire('polygon')
                    url = f"https://api.polygon.io/v2/aggs/ticker/{sym}/range/1/minute/0/0"
                    params = {"adjusted": "true", "sort": "asc", "limit": 500, "apiKey": self.api_key}
                    try:
                        async with session.get(url, params=params, timeout=20) as resp:
                            if resp.status != 200:
                                continue
                            data = await resp.json()
                            rows = data.get("results", []) or []
                            results[sym] = [r.get("c") for r in rows]
                    except Exception as exc:
                        logger.debug("Polygon 1m fetch error for %s: %s", sym, exc)
                        continue
            else:
                # Try batch snapshot path for multi-symbol quick fetches
                if len(symbols) > 1:
                    chunk_size = 50
                    for i in range(0, len(symbols), chunk_size):
                        batch = symbols[i:i + chunk_size]
                        await self.rate_limiter.acquire('polygon')
                        batch_out = await self._fetch_snapshot_batch(session, batch)
                        for s, price in batch_out.items():
                            results[s] = [price]

                # If we have no results (or caller likely wants more than a single point),
                # fall back to per-symbol aggregate history fetch.
                if not results:
                    for sym in symbols:
                        await self.rate_limiter.acquire('polygon')
                        url = f"https://api.polygon.io/v2/aggs/ticker/{sym}/range/1/day/0/0"
                        params = {"adjusted": "true", "sort": "asc", "limit": 500, "apiKey": self.api_key}
                        try:
                            async with session.get(url, params=params, timeout=20) as resp:
                                if resp.status != 200:
                                    continue
                                data = await resp.json()
                                rows = data.get("results", []) or []
                                results[sym] = [r.get("c") for r in rows]
                        except Exception as exc:
                            logger.debug("Polygon per-symbol fetch error for %s: %s", sym, exc)
                            continue

        if not results:
            return None

        df = pd.DataFrame({k: pd.Series(v) for k, v in results.items()})
        return df
