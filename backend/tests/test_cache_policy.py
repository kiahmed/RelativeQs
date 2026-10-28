"""Two-tier cache: memory for everything, throttled Redis only for bars:<date>."""
import asyncio

import pytest

from app.services import cache as cache_mod
from app.services.cache import RedisCache


class FakeRedis:
    def __init__(self, fail=False):
        self.store, self.gets, self.sets, self.fail = {}, [], [], fail

    async def get(self, key):
        self.gets.append(key)
        if self.fail:
            raise RuntimeError("over quota")
        return self.store.get(key)

    async def set(self, key, val, ex=None):
        self.sets.append((key, ex))
        if self.fail:
            raise RuntimeError("over quota")
        self.store[key] = val


@pytest.fixture
def rc(monkeypatch):
    RedisCache._local.clear(); RedisCache._dirty.clear(); RedisCache._last_flush.clear()
    fake = FakeRedis()

    async def _client(self):
        return fake
    monkeypatch.setattr(RedisCache, "client", _client)
    monkeypatch.setattr(cache_mod, "REDIS_PERSIST_PREFIXES", ("bars:",))
    monkeypatch.setattr(cache_mod, "REDIS_FLUSH_SECONDS", 300.0)
    return RedisCache(), fake


def run(coro):
    return asyncio.run(coro)


def test_non_persisted_keys_never_touch_redis(rc):
    c, fake = rc

    async def go():
        for k in ("snapshot:latest", "prediction:latest", "history:yahoo:1m:x"):
            await c.set(k, {"a": 1}, expire=60)
            assert await c.get(k) == {"a": 1}
        assert await c.get("never-set") is None
    run(go())
    assert fake.gets == [] and fake.sets == []


def test_shared_between_instances(rc):
    c, _ = rc

    async def go():
        await RedisCache().set("prediction:latest", {"x": 2}, expire=60)   # the poll loop
        return await RedisCache().get("prediction:latest")                 # the API
    assert run(go()) == {"x": 2}


def test_get_returns_a_fresh_copy(rc):
    c, _ = rc

    async def go():
        await c.set("snapshot:latest", {"a": [1]}, expire=60)
        first = await c.get("snapshot:latest"); first["a"].append(2)
        return await c.get("snapshot:latest")
    assert run(go()) == {"a": [1]}


def test_bars_writes_are_throttled(rc, monkeypatch):
    c, fake = rc

    async def go():
        for i in range(50):                       # 50 poll cycles in a row
            await c.set("bars:2026-10-28", {"n": i}, expire=7 * 86400)
    run(go())
    assert len(fake.sets) == 1                    # first write only
    assert fake.gets == []                        # memory serves reads
    assert "bars:2026-10-28" in RedisCache._dirty  # latest value waits for the next flush


def test_bars_written_again_after_interval(rc, monkeypatch):
    c, fake = rc
    clock = {"t": 1000.0}
    monkeypatch.setattr(cache_mod.time, "monotonic", lambda: clock["t"])

    async def go():
        await c.set("bars:d", {"n": 1}, expire=100)
        clock["t"] += 299
        await c.set("bars:d", {"n": 2}, expire=100)
        clock["t"] += 2
        await c.set("bars:d", {"n": 3}, expire=100)
    run(go())
    assert len(fake.sets) == 2 and RedisCache._dirty == {}


def test_flush_dirty_saves_the_latest_value(rc):
    c, fake = rc

    async def go():
        await c.set("bars:d", {"n": 1}, expire=100)
        await c.set("bars:d", {"n": 2}, expire=100)    # deferred
        return await RedisCache.flush_dirty()
    assert run(go()) == 1
    assert fake.sets[-1][0] == "bars:d" and '"n": 2' in fake.store["bars:d"]


def test_persisted_miss_reads_redis_once_then_remembers(rc):
    c, fake = rc

    async def go():
        for _ in range(20):
            assert await c.get("bars:2026-01-01") is None
    run(go())
    assert fake.gets == ["bars:2026-01-01"]


def test_persisted_value_loaded_from_redis_then_served_from_memory(rc):
    c, fake = rc
    fake.store["bars:d"] = '{"t": {"QQQ": 1.5}}'

    async def go():
        a = await c.get("bars:d"); b = await c.get("bars:d")
        return a, b
    a, b = run(go())
    assert a == b == {"t": {"QQQ": 1.5}} and fake.gets == ["bars:d"]


def test_redis_down_does_not_break_the_cache(rc, monkeypatch):
    c, fake = rc
    fake.fail = True

    async def go():
        await c.set("bars:d", {"n": 1}, expire=100)    # Redis write fails, no raise
        assert await c.get("bars:d") == {"n": 1}       # memory still serves it
        assert await c.get("bars:other") is None       # Redis read fails, no raise
    run(go())


def test_malformed_redis_url_degrades_to_memory_only(monkeypatch):
    RedisCache._local.clear(); RedisCache._url_error_logged = False
    c = RedisCache(url="redis-cli --tls -u redis://default:pw@host:6379")
    assert RedisCache._persists("bars:d")

    async def go():
        await c.set("bars:d", {"n": 1}, expire=100)       # must not raise
        assert await c.get("bars:d") == {"n": 1}          # memory still serves it
        assert await c.get("bars:other") is None          # no client -> miss, no raise
    run(go())


def test_error_logs_never_contain_host_or_message(rc, caplog):
    """redis-py error text includes the server's host:port; logs must not."""
    import logging
    c, fake = rc

    class Boom(Exception):
        pass

    secret = "private-endpoint.upstash.io:6379"

    async def bad_get(key): raise Boom(f"Error 111 connecting to {secret}. Connection refused.")
    async def bad_set(key, val, ex=None): raise Boom(f"max requests limit exceeded at {secret}")
    fake.get, fake.set = bad_get, bad_set
    with caplog.at_level(logging.WARNING):
        run(c.set("bars:x", {"n": 1}, expire=10))
        run(c.get("bars:y"))
    log = caplog.text
    assert secret not in log and "Error 111" not in log
    assert "[CACHE] set failed for key bars:x" in log and "Boom" in log
    assert "quota" in log and "connection" in log


def test_safe_err_maps_known_failures_to_fixed_hints():
    f = cache_mod._safe_err
    assert f(RuntimeError("This database has reached current Fixed plan limits")) == "RuntimeError (Redis quota / plan limit exceeded)"
    assert f(ValueError("weird")) == "ValueError"
    assert "host" not in f(ConnectionError("cannot reach host:6379"))
