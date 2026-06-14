import os
from typing import Optional
import json
import asyncio
import logging

logger = logging.getLogger(__name__)
try:
    import redis.asyncio as redis
except Exception:
    redis = None

REDIS_URL = os.getenv("REDIS_URL", "redis://127.0.0.1:6379/0")

# Keys the background poll loop writes the freshest payloads to and that the
# API reads back, so requests are served from Redis without refetching.
SNAPSHOT_KEY = "snapshot:latest"
QQQ_SCORE_KEY = "qqq_score:latest"
PREDICTION_KEY = "prediction:latest"
ROTATION_KEY = "rotation:latest"


def _json_encoder(obj):
    try:
        if hasattr(obj, "item"):
            return obj.item()
    except Exception:
        pass
    if isinstance(obj, bytes):
        return obj.decode("utf-8", errors="ignore")
    return str(obj)


class RedisCache:
    def __init__(self, url: Optional[str] = None):
        self.url = url or REDIS_URL
        self._client = None

    async def client(self):
        if redis is None:
            return None
        if self._client is None:
            self._client = redis.from_url(self.url)
        return self._client

    async def get(self, key: str):
        c = await self.client()
        if c is None:
            return None
        # best-effort: a Redis outage must degrade to a cache miss, not a 500.
        try:
            v = await c.get(key)
        except Exception as exc:
            logger.warning("[CACHE] get failed for key %s: %s", key, exc)
            return None
        if v is None:
            return None
        if isinstance(v, bytes):
            v = v.decode("utf-8", errors="ignore")
        try:
            return json.loads(v)
        except Exception:
            return v

    async def set(self, key: str, value, expire: int = 60):
        c = await self.client()
        if c is None:
            return
        # the cache is best-effort: a serialization or Redis error must never
        # bubble up and turn a working request into a 500.
        try:
            val = json.dumps(value, default=_json_encoder)
            await c.set(key, val, ex=expire)
        except Exception as exc:
            logger.warning("[CACHE] set failed for key %s: %s", key, exc)
