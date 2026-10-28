"""Shared test fixtures."""
import pytest

from app.services.cache import RedisCache


@pytest.fixture(autouse=True)
def _fresh_process_cache():
    """RedisCache keeps its in-memory tier process-wide (that is the point in
    production: the poll loop and the API share it). Tests each want an isolated
    cache, so wipe that shared state before and after every test."""
    for store in (RedisCache._local, RedisCache._dirty, RedisCache._last_flush):
        store.clear()
    yield
    for store in (RedisCache._local, RedisCache._dirty, RedisCache._last_flush):
        store.clear()
