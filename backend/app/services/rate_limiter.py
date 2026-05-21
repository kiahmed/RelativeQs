import time
from collections import deque
from typing import Deque

class SimpleRateLimiter:
    """Simple per-key rate limiter using a sliding window of timestamps."""
    def __init__(self, calls: int = 5, per_seconds: int = 1):
        self.calls = calls
        self.per_seconds = per_seconds
        self._buckets: dict[str, Deque[float]] = {}

    async def acquire(self, key: str):
        now = time.time()
        bucket = self._buckets.setdefault(key, deque())
        # drop old timestamps
        while bucket and bucket[0] <= now - self.per_seconds:
            bucket.popleft()
        if len(bucket) < self.calls:
            bucket.append(now)
            return
        # need to wait
        wait = self.per_seconds - (now - bucket[0])
        if wait > 0:
            await _sleep(wait)
        bucket.append(time.time())

async def _sleep(sec: float):
    import asyncio
    await asyncio.sleep(sec)
