import pandas as pd
import pytest

import fakeredis.aioredis

from app.services.cache import RedisCache
from app.services.history_store import IntradayHistoryStore, BARS_KEY_PREFIX


def _make_frame(timestamps, data):
    idx = pd.to_datetime(timestamps)
    return pd.DataFrame(data, index=idx)


@pytest.fixture
def store():
    cache = RedisCache()
    # Inject a fakeredis client so nothing touches a real Redis.
    cache._client = fakeredis.aioredis.FakeRedis()
    return IntradayHistoryStore(cache=cache, retention_days=5)


@pytest.mark.asyncio
async def test_append_and_roundtrip(store):
    bars = _make_frame(
        ["2026-06-02 09:30", "2026-06-02 09:31", "2026-06-02 09:32"],
        {"QQQ": [512.0, 512.5, 513.0], "SMH": [233.0, 233.4, 233.8]},
    )
    total = await store.append_bars(bars)
    assert total == 3

    out = await store.get_session_bars()
    assert out is not None
    assert list(out.columns) == ["QQQ", "SMH"] or set(out.columns) == {"QQQ", "SMH"}
    assert len(out) == 3
    # Index sorted ascending.
    assert list(out.index) == sorted(out.index)
    assert out.loc[pd.Timestamp("2026-06-02 09:31"), "QQQ"] == 512.5


@pytest.mark.asyncio
async def test_append_dedup_new_wins(store):
    first = _make_frame(
        ["2026-06-02 09:30", "2026-06-02 09:31"],
        {"QQQ": [512.0, 512.5]},
    )
    await store.append_bars(first)

    # Overlap on 09:31 (value changes) plus a new bar 09:32.
    second = _make_frame(
        ["2026-06-02 09:31", "2026-06-02 09:32"],
        {"QQQ": [999.0, 513.0]},
    )
    total = await store.append_bars(second)

    assert total == 3  # 09:30, 09:31, 09:32 (no duplicate timestamp)
    out = await store.get_session_bars()
    assert len(out) == 3
    # New bar wins on the overlapping timestamp.
    assert out.loc[pd.Timestamp("2026-06-02 09:31"), "QQQ"] == 999.0


@pytest.mark.asyncio
async def test_get_session_bars_empty_is_none(store):
    out = await store.get_session_bars()
    assert out is None


@pytest.mark.asyncio
async def test_append_empty_frame_noop(store):
    assert await store.append_bars(pd.DataFrame()) == 0
    assert await store.append_bars(None) == 0
    assert await store.get_session_bars() is None


@pytest.mark.asyncio
async def test_clear(store):
    bars = _make_frame(
        ["2026-06-02 09:30", "2026-06-02 09:31"],
        {"QQQ": [512.0, 512.5]},
    )
    await store.append_bars(bars)
    assert await store.get_session_bars() is not None

    await store.clear()
    assert await store.get_session_bars() is None


@pytest.mark.asyncio
async def test_explicit_session_date(store):
    bars = _make_frame(
        ["2026-05-30 09:30", "2026-05-30 09:31"],
        {"QQQ": [500.0, 500.5]},
    )
    # append_bars writes to today's key; verify a different explicit date misses.
    await store.append_bars(bars)
    assert await store.get_session_bars(session_date="2026-01-01") is None


@pytest.mark.asyncio
async def test_nan_values_dropped(store):
    bars = _make_frame(
        ["2026-06-02 09:30", "2026-06-02 09:31"],
        {"QQQ": [512.0, 512.5], "TLT": [float("nan"), 95.0]},
    )
    await store.append_bars(bars)
    out = await store.get_session_bars()
    # First TLT bar was NaN -> dropped from payload, reappears as NaN in frame.
    assert pd.isna(out.loc[pd.Timestamp("2026-06-02 09:30"), "TLT"])
    assert out.loc[pd.Timestamp("2026-06-02 09:31"), "TLT"] == 95.0


def test_bars_key_prefix():
    assert BARS_KEY_PREFIX == "bars:"


async def _seed_date(store, date_str, data):
    """Write a session payload directly under bars:{date} via the injected cache,
    mirroring the store's own storage contract."""
    frame = _make_frame(
        [f"{date_str} 09:30", f"{date_str} 09:31"],
        data,
    )
    payload = store._frame_to_payload(frame)
    await store.cache.set(store._key(date_str), payload)


@pytest.mark.asyncio
async def test_get_recent_sessions_oldest_first(store, monkeypatch):
    import app.services.history_store as hs

    # Pretend "today" is 2026-06-02 so the walk-back covers the seeded dates.
    monkeypatch.setattr(
        hs, "_et_today", lambda: "2026-06-02"
    )
    from datetime import datetime as _dt
    from zoneinfo import ZoneInfo as _ZI

    class _FixedDateTime(_dt):
        @classmethod
        def now(cls, tz=None):
            return _dt(2026, 6, 2, 12, 0, tzinfo=_ZI("America/New_York"))

    monkeypatch.setattr(hs, "datetime", _FixedDateTime)

    # Seed three ET dates out of chronological order.
    await _seed_date(store, "2026-05-29", {"QQQ": [500.0, 500.5]})
    await _seed_date(store, "2026-06-01", {"QQQ": [510.0, 510.5]})
    await _seed_date(store, "2026-06-02", {"QQQ": [520.0, 520.5]})

    sessions = await store.get_recent_sessions()
    dates = [d for d, _ in sessions]
    assert dates == ["2026-05-29", "2026-06-01", "2026-06-02"]
    # Today is last.
    assert dates[-1] == "2026-06-02"
    # Each entry carries a non-empty frame.
    for _, frame in sessions:
        assert frame is not None and len(frame) == 2


@pytest.mark.asyncio
async def test_get_recent_sessions_respects_days(store, monkeypatch):
    import app.services.history_store as hs
    from datetime import datetime as _dt
    from zoneinfo import ZoneInfo as _ZI

    class _FixedDateTime(_dt):
        @classmethod
        def now(cls, tz=None):
            return _dt(2026, 6, 2, 12, 0, tzinfo=_ZI("America/New_York"))

    monkeypatch.setattr(hs, "datetime", _FixedDateTime)

    await _seed_date(store, "2026-05-29", {"QQQ": [500.0, 500.5]})
    await _seed_date(store, "2026-06-02", {"QQQ": [520.0, 520.5]})

    # days=1 only looks at today; the old date is out of range.
    sessions = await store.get_recent_sessions(days=1)
    dates = [d for d, _ in sessions]
    assert dates == ["2026-06-02"]


@pytest.mark.asyncio
async def test_get_recent_bars_concatenates(store, monkeypatch):
    import app.services.history_store as hs
    from datetime import datetime as _dt
    from zoneinfo import ZoneInfo as _ZI

    class _FixedDateTime(_dt):
        @classmethod
        def now(cls, tz=None):
            return _dt(2026, 6, 2, 12, 0, tzinfo=_ZI("America/New_York"))

    monkeypatch.setattr(hs, "datetime", _FixedDateTime)

    await _seed_date(store, "2026-05-29", {"QQQ": [500.0, 500.5]})
    await _seed_date(store, "2026-06-01", {"QQQ": [510.0, 510.5]})
    await _seed_date(store, "2026-06-02", {"QQQ": [520.0, 520.5]})

    combined = await store.get_recent_bars()
    assert combined is not None
    assert len(combined) == 6
    # Sorted ascending across sessions.
    assert list(combined.index) == sorted(combined.index)
    assert combined.index[0] == pd.Timestamp("2026-05-29 09:30")
    assert combined.index[-1] == pd.Timestamp("2026-06-02 09:31")


@pytest.mark.asyncio
async def test_get_recent_sessions_empty(store, monkeypatch):
    import app.services.history_store as hs
    from datetime import datetime as _dt
    from zoneinfo import ZoneInfo as _ZI

    class _FixedDateTime(_dt):
        @classmethod
        def now(cls, tz=None):
            return _dt(2026, 6, 2, 12, 0, tzinfo=_ZI("America/New_York"))

    monkeypatch.setattr(hs, "datetime", _FixedDateTime)

    assert await store.get_recent_sessions() == []
    assert await store.get_recent_bars() is None
