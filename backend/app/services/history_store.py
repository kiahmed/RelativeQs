import logging
from typing import List, Optional, Tuple
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pandas as pd

from app.config import settings
from app.services.cache import RedisCache

logger = logging.getLogger(__name__)

# Full key per ET session date: bars:{YYYY-MM-DD}
BARS_KEY_PREFIX = "bars:"


def _et_today() -> str:
    return datetime.now(ZoneInfo("America/New_York")).strftime("%Y-%m-%d")


class IntradayHistoryStore:
    """Persists 1m close bars across poll cycles so the lead/lag engine runs on
    accumulated session data instead of throwing bars away each cycle.

    Storage is delegated to RedisCache, which JSON-roundtrips dicts. The stored
    payload is ``{ISO timestamp: {symbol: close, ...}, ...}`` keyed by ET date.
    """

    def __init__(self, cache: "RedisCache" = None, retention_days: int = None):
        self.cache = cache or RedisCache()
        self.retention_days = (
            retention_days
            if retention_days is not None
            else getattr(settings, "HISTORY_RETENTION_DAYS", 5)
        )

    def _key(self, session_date: str = None) -> str:
        return BARS_KEY_PREFIX + (session_date or _et_today())

    @staticmethod
    def _frame_to_payload(bars: pd.DataFrame) -> dict:
        payload = {}
        for ts, row in bars.iterrows():
            key = pd.Timestamp(ts).isoformat()
            record = {}
            for sym, val in row.items():
                # Drop NaNs so the payload stays small and JSON-clean.
                if pd.isna(val):
                    continue
                record[str(sym)] = float(val)
            payload[key] = record
        return payload

    @staticmethod
    def _payload_to_frame(payload: dict) -> Optional[pd.DataFrame]:
        if not payload:
            return None
        try:
            frame = pd.DataFrame.from_dict(payload, orient="index")
        except Exception as exc:
            logger.warning("[HISTORY] failed to rebuild frame: %s", exc)
            return None
        if frame.empty:
            return None
        frame.index = pd.to_datetime(frame.index)
        frame = frame.sort_index()
        return frame

    async def append_bars(self, bars: pd.DataFrame) -> int:
        """Merge new bars into today's stored frame, dedup by timestamp (new wins).
        Returns total bars stored."""
        if bars is None or bars.empty:
            existing = await self.get_session_bars()
            return 0 if existing is None else len(existing)

        key = self._key()
        try:
            stored = await self.cache.get(key)
        except Exception as exc:
            logger.warning("[HISTORY] get failed for %s: %s", key, exc)
            stored = None

        payload = dict(stored) if isinstance(stored, dict) else {}
        # New bars win on timestamp collision.
        payload.update(self._frame_to_payload(bars))

        try:
            await self.cache.set(
                key, payload, expire=self.retention_days * 86400
            )
        except Exception as exc:
            logger.warning("[HISTORY] set failed for %s: %s", key, exc)

        return len(payload)

    async def seed_session(self, session_date: str, bars: pd.DataFrame) -> int:
        """Merge a specific ET date's bars into its stored key (new wins). Used by
        the provider backfill to seed past sessions; append_bars only writes today.
        Returns total bars stored for that date."""
        if bars is None or bars.empty or not session_date:
            return 0
        key = self._key(session_date)
        try:
            stored = await self.cache.get(key)
        except Exception as exc:
            logger.warning("[HISTORY] get failed for %s: %s", key, exc)
            stored = None
        payload = dict(stored) if isinstance(stored, dict) else {}
        payload.update(self._frame_to_payload(bars))
        try:
            await self.cache.set(key, payload, expire=self.retention_days * 86400)
        except Exception as exc:
            logger.warning("[HISTORY] seed failed for %s: %s", key, exc)
        return len(payload)

    async def get_session_bars(
        self, session_date: str = None
    ) -> Optional[pd.DataFrame]:
        """Bars for the given ET date (default today). DatetimeIndex sorted asc,
        columns = symbols. None if nothing stored."""
        key = self._key(session_date)
        try:
            stored = await self.cache.get(key)
        except Exception as exc:
            logger.warning("[HISTORY] get failed for %s: %s", key, exc)
            return None
        if not isinstance(stored, dict):
            return None
        return self._payload_to_frame(stored)

    async def get_recent_sessions(
        self, days: int = None
    ) -> List[Tuple[str, pd.DataFrame]]:
        """Return [(et_date, frame), ...] for up to ``days`` most-recent ET dates
        that have stored bars, oldest first, today last. ``days`` None ->
        retention_days. Skips dates with no data. Each frame: DatetimeIndex
        sorted asc, columns = symbols."""
        days = self.retention_days if days is None else days
        try:
            today = datetime.now(ZoneInfo("America/New_York")).date()
        except Exception as exc:
            logger.warning("[HISTORY] failed to resolve ET today: %s", exc)
            return []

        # Walk back N calendar days; probe each bars:{date} key. Weekends and
        # holidays simply have no key. Collect newest->oldest, then reverse so
        # the result is oldest first with today last.
        sessions: List[Tuple[str, pd.DataFrame]] = []
        for offset in range(days):
            session_date = (today - timedelta(days=offset)).strftime("%Y-%m-%d")
            frame = await self.get_session_bars(session_date=session_date)
            if frame is None or frame.empty:
                continue
            sessions.append((session_date, frame))

        sessions.reverse()
        return sessions

    async def get_recent_bars(self, days: int = None) -> Optional[pd.DataFrame]:
        """Concatenate get_recent_sessions frames into one DataFrame (sorted by
        index). None if nothing stored. Used by hit-rate over multiple
        sessions."""
        sessions = await self.get_recent_sessions(days=days)
        if not sessions:
            return None
        frames = [frame for _, frame in sessions]
        try:
            combined = pd.concat(frames)
        except Exception as exc:
            logger.warning("[HISTORY] failed to concat recent bars: %s", exc)
            return None
        if combined.empty:
            return None
        return combined.sort_index()

    async def clear(self, session_date: str = None) -> None:
        key = self._key(session_date)
        # Overwrite with an empty payload and a short TTL; RedisCache exposes no
        # delete, so a vacated key is the contract-friendly way to clear.
        try:
            await self.cache.set(key, {}, expire=1)
        except Exception as exc:
            logger.warning("[HISTORY] clear failed for %s: %s", key, exc)
