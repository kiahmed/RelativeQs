import os
from typing import Optional
import json
import asyncio
try:
    import redis.asyncio as redis
except Exception:
    redis = None

REDIS_URL = os.getenv("REDIS_URL", "redis://127.0.0.1:6379/0")


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
        v = await c.get(key)
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
        val = json.dumps(value, default=_json_encoder)
        await c.set(key, val, ex=expire)
