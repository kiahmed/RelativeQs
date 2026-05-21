import os
from typing import List, Optional
import pandas as pd

try:
    import aiohttp
except Exception:
    aiohttp = None

from app.services.rate_limiter import SimpleRateLimiter
from app.config import settings


class PolygonAdapter:
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or settings.POLYGON_KEY
        self.rate_limiter = SimpleRateLimiter("polygon", calls_per_minute=5)

    async def fetch_history(self, symbols: List[str], period: str = "90d", interval: str = "1d") -> Optional[pd.DataFrame]:
        """Fetch historical close prices for `symbols` using Polygon APIs.

        This is a lightweight scaffold. If no API key available, returns None
        so caller can fallback to other providers.
        """
        if not self.api_key:
            return None
        if aiohttp is None:
            return None

        # simple rate-limited loop; production code should batch requests and
        # use Polygon's multi-symbol endpoints when available.
        results = {}
        async with aiohttp.ClientSession() as session:
            for sym in symbols:
                await self.rate_limiter.wait_for_slot()
                url = f"https://api.polygon.io/v2/aggs/ticker/{sym}/range/1/day/0/0?adjusted=true&sort=asc&limit=500&apiKey={self.api_key}"
                try:
                    async with session.get(url, timeout=15) as resp:
                        if resp.status != 200:
                            continue
                        data = await resp.json()
                        results[sym] = [r.get("c") for r in data.get("results", [])]
                except Exception:
                    continue

        if not results:
            return None

        # align into DataFrame with an index of integer days (caller expects pandas Series by symbol)
        df = pd.DataFrame({k: pd.Series(v) for k, v in results.items()})
        return df
