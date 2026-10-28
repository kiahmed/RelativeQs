"""
Two-tier cache: an in-process store for everything, Redis only for what must
survive a restart.

Why: the backend is ONE process (the poll loop and the API share it), so the
latest snapshot / score / prediction / rotation payloads and the 5-day price
cache never needed to live in Redis — keeping them there cost thousands of
commands and ~GB of traffic a day and blew through a managed plan's quota
(Upstash free tier: 500K commands + 10 GB bandwidth per month).

Policy
  * Every key is held in memory (JSON text, so callers still get a fresh copy
    on each ``get``) with its TTL.
  * Only keys starting with ``REDIS_PERSIST_PREFIXES`` (default ``bars:`` — the
    per-day 1-minute bar history that feeds the cross-day signals) are also
    written to Redis. Those writes are throttled to one per key per
    ``REDIS_FLUSH_SECONDS`` (default 300 s); ``flush_dirty()`` pushes the
    remainder on shutdown.
  * A persisted key is read from Redis at most once per hour (and a missing
    key is remembered for 5 minutes), then served from memory.
  * Redis is best-effort: if it is down or over quota, the in-memory tier keeps
    working and nothing raises.

Redis schema (all there is): ``bars:<ET date>`` -> JSON
``{ISO timestamp: {symbol: close}}``, TTL = HISTORY_RETENTION_DAYS. Redis has no
tables to create; the keys appear on the first flush.
"""

import asyncio
import json
import logging
import os
import time
from typing import Dict, Optional, Tuple

logger = logging.getLogger(__name__)
try:
    import redis.asyncio as redis
except Exception:
    redis = None

REDIS_URL = os.getenv("REDIS_URL", "redis://127.0.0.1:6379/0")
# Comma-separated key prefixes that are also persisted to Redis.
REDIS_PERSIST_PREFIXES: Tuple[str, ...] = tuple(
    p.strip() for p in os.getenv("REDIS_PERSIST_PREFIXES", "bars:").split(",") if p.strip()
)
# Minimum seconds between Redis writes of the same key.
REDIS_FLUSH_SECONDS: float = float(os.getenv("REDIS_FLUSH_SECONDS", "300"))

_LOADED_TTL = 3600.0   # how long a value read from Redis stays in memory
_MISS_TTL = 300.0      # how long "not in Redis" is remembered

# Keys the background poll loop writes the freshest payloads to and that the
# API reads back, so requests are served from memory without refetching.
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


def _safe_err(exc: BaseException) -> str:
    """A log-safe description of a Redis error: the exception class plus a fixed
    hint — never the exception text, which redis-py fills with the server's
    host:port (a private endpoint) and could carry other connection details."""
    name = exc.__class__.__name__
    text = str(exc).lower()
    if "limit" in text and any(w in text for w in ("max", "plan", "quota", "exceed", "reached")):
        hint = "Redis quota / plan limit exceeded"
    elif "timeout" in name.lower() or "timed out" in text:
        hint = "timeout"
    elif "connection" in name.lower() or "connection" in text:
        hint = "connection problem"
    else:
        hint = ""
    return f"{name} ({hint})" if hint else name


class RedisCache:
    # Process-wide state, shared by every RedisCache() instance (the API, the poll
    # loop, the history store and the market-data service each create their own).
    _local: Dict[str, Tuple[float, Optional[str]]] = {}   # key -> (expires_at, json|None)
    _dirty: Dict[str, int] = {}                           # key -> ttl seconds, not yet in Redis
    _last_flush: Dict[str, float] = {}                    # key -> monotonic time of last write
    _url_error_logged: bool = False

    def __init__(self, url: Optional[str] = None):
        self.url = url or REDIS_URL
        self._client = None

    @staticmethod
    def _persists(key: str) -> bool:
        return key.startswith(REDIS_PERSIST_PREFIXES) if REDIS_PERSIST_PREFIXES else False

    async def client(self):
        if redis is None:
            return None
        if self._client is None:
            try:
                self._client = redis.from_url(self.url)
            except Exception as exc:
                # a malformed REDIS_URL (e.g. a pasted `redis-cli ...` command) must
                # degrade to memory-only, not 500 every request
                if not RedisCache._url_error_logged:
                    logger.error("[CACHE] invalid REDIS_URL (%s) — running memory-only. "
                                 "Use rediss://default:<password>@<host>:6379", _safe_err(exc))
                    RedisCache._url_error_logged = True
                return None
        return self._client

    @staticmethod
    def _decode(v):
        if v is None:
            return None
        if isinstance(v, bytes):
            v = v.decode("utf-8", errors="ignore")
        try:
            return json.loads(v)
        except Exception:
            return v

    async def get(self, key: str):
        now = time.monotonic()
        entry = self._local.get(key)
        if entry and entry[0] > now:
            return self._decode(entry[1])
        if not self._persists(key):
            self._local.pop(key, None)
            return None

        # persisted key, not (or no longer) in memory: one Redis read, then memoise
        c = await self.client()
        if c is None:
            return None
        try:
            v = await c.get(key)
        except Exception as exc:
            logger.warning("[CACHE] get failed for key %s: %s", key, _safe_err(exc))
            self._local[key] = (now + _MISS_TTL, None)
            return None
        if isinstance(v, bytes):
            v = v.decode("utf-8", errors="ignore")
        if v is None:
            self._local[key] = (now + _MISS_TTL, None)
            return None
        self._local[key] = (now + _LOADED_TTL, v)
        return self._decode(v)

    async def set(self, key: str, value, expire: int = 60):
        # the cache is best-effort: a serialization or Redis error must never
        # bubble up and turn a working request into a 500.
        try:
            val = json.dumps(value, default=_json_encoder)
        except Exception as exc:
            logger.warning("[CACHE] set failed for key %s: %s", key, _safe_err(exc))
            return
        now = time.monotonic()
        self._local[key] = (now + max(float(expire), 1.0), val)
        if not self._persists(key):
            return
        if now - self._last_flush.get(key, -1e9) >= REDIS_FLUSH_SECONDS:
            await self._write(key, val, int(expire))
        else:
            self._dirty[key] = int(expire)

    async def _write(self, key: str, val: str, expire: int) -> None:
        self._last_flush[key] = time.monotonic()   # throttles retries after a failure too
        c = await self.client()
        if c is None:
            return
        try:
            await c.set(key, val, ex=max(expire, 1))
            self._dirty.pop(key, None)
        except Exception as exc:
            self._dirty[key] = expire
            logger.warning("[CACHE] set failed for key %s: %s", key, _safe_err(exc))

    @classmethod
    async def flush_dirty(cls) -> int:
        """Write every persisted key that has unsaved changes (call on shutdown)."""
        n = 0
        inst = cls()
        for key, expire in list(cls._dirty.items()):
            entry = cls._local.get(key)
            if entry and entry[1] is not None:
                await inst._write(key, entry[1], expire)
                n += 1
        return n
