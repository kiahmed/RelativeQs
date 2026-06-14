import asyncio
import os
import random
import threading
import time
import json
import logging
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from app.config import settings
from app.core.qqq_score import QQQScoreEngine
from app.core.lead_lag import LeadLagEngine
from app.core.intraday_score import IntradayScoreEngine
from app.core.projection import ProjectionEngine
from app.core.attribution import DriverAttributionEngine
from app.core.confirmation import ConfirmationGate
from app.core.correlation_regime import CorrelationRegimeEngine
from app.core.stability import StabilityEngine
from app.core.hit_rate import HitRateEngine
from app.core.breadth import BreadthEngine
from app.core.ai_dependency import AIDependencyEngine
from app.core.premarket import PremarketBoard
from app.services.holdings import HoldingsProvider

logger = logging.getLogger(__name__)

try:
    import yfinance as yf
except ImportError:
    yf = None

# yf.download is NOT thread-safe: concurrent calls (run via asyncio.to_thread)
# with different intervals clobber each other's state, so a "1d" daily pull can
# come back as 1m intraday data. This process-wide lock serializes every
# download so the AI-dependency daily fetch can't be corrupted by a concurrent
# intraday/breadth fetch. Module-level => shared across all MarketDataService
# instances (the poll loop's and the API's).
_YF_DOWNLOAD_LOCK = threading.Lock()

class MarketDataService:
    """Market data service with both mock and Yahoo Finance adapters.

    For real product usage, set DATA_PROVIDER=yahoo and the service will pull
    free ETF price data from Yahoo Finance to compute momentum, confirmation,
    breadth, and inflation stress signals.
    """

    def __init__(self, mode: str = "mock"):
        self.mode = mode
        self._tick = 0
        self.qqq_engine = QQQScoreEngine()
        # Yahoo fetch throttle: remember the last download path call (monotonic)
        # and the frame it returned, so repeated calls inside the throttle window
        # reuse the in-process frame instead of hammering the provider.
        self._last_yahoo_fetch: float = 0.0
        self._last_yahoo_frame: Optional[pd.DataFrame] = None
        # (period, interval) of the remembered frame — the throttle only reuses
        # it for an identical request so a 7d backfill never gets served a 1d frame.
        self._last_yahoo_params: tuple = (None, None)
        # AI-capex dependency is a slow DAILY metric — cache it in-process and
        # only refetch daily bars every AI_DEPENDENCY_REFRESH_SECONDS so the
        # ~12s intraday poll never re-pulls 2y of daily history.
        self._ai_dep_cache: Optional[Dict[str, Any]] = None
        self._ai_dep_fetched: float = 0.0
        # Per-timeframe lead/lag streak state {tf: {symbol, lag_minutes, count,
        # confirmed, window_end}} — promotes a lead only after it recurs on N
        # consecutive new bars (see LEAD_LAG_STREAK_MIN).
        self._leadlag_streak: Dict[str, Dict[str, Any]] = {}
        # cached daily-bar frame for the universe (cross-day lead/lag) — slow
        # metric, refetched on the AI-dependency cadence so the poll never repulls.
        self._daily_universe_cache: Optional[pd.DataFrame] = None
        self._daily_universe_fetched: float = 0.0
        # cross-sector rotation-flow read (1m OHLCV) — cached in-process for ~one
        # poll interval so the loop and on-demand API don't both hammer yfinance.
        self._rotation_cache: Optional[Dict[str, Any]] = None
        self._rotation_fetched: float = 0.0
        # overnight / pre-market board — refreshed on a slow (~15 min) cadence
        # since it's pre-open situational context, not part of the intraday poll.
        self._premarket_cache: Optional[Dict[str, Any]] = None
        self._premarket_fetched: float = 0.0

    def _resolve_provider(self) -> str:
        provider = (self.mode or settings.DATA_PROVIDER or os.getenv("DATA_PROVIDER", "mock")).lower()
        logger.info("[MARKET] initial provider setting: %s", provider)
        if provider in ("auto", "best"):
            candidates = [
                ("twelvedata", getattr(settings, "TWELVEDATA_KEY", None)),
                ("alpaca", getattr(settings, "ALPACA_KEY", None)),
                ("polygon", getattr(settings, "POLYGON_KEY", None)),
                ("yahoo", None),
                ("finnhub", getattr(settings, "FINNHUB_KEY", None)),
                ("alphavantage", getattr(settings, "ALPHAVANTAGE_KEY", None)),
            ]
            chosen = None
            for name, key in candidates:
                if name == "yahoo":
                    if yf is not None:
                        chosen = "yahoo"
                        break
                    continue
                if key:
                    chosen = name
                    break
            provider = chosen or "yahoo"
        logger.info("[MARKET] resolved provider: %s", provider)
        return provider

    def _should_fetch_prepost(self) -> bool:
        """True when extended-hours fetching is enabled and the current time is
        outside the regular session (9:30-16:00 ET, weekdays). This keeps
        pre-market, after-hours, overnight, and weekend fetches returning
        extended-hours bars until the next session opens."""
        if not settings.FETCH_PRE_POST_MARKET:
            return False
        now = datetime.now(ZoneInfo("America/New_York"))
        minutes = now.hour * 60 + now.minute
        regular_session = now.weekday() < 5 and (9 * 60 + 30 <= minutes < 16 * 60)
        return not regular_session

    async def fetch_snapshot(self, use_cache: bool = True) -> Dict[str, Any]:
        if self.mode != "mock":
            return await self._yahoo_snapshot(use_cache=use_cache)
        return await self._mock_snapshot()

    async def _mock_snapshot(self) -> Dict[str, Any]:
        # create deterministic-ish mock signals
        self._tick += 1
        np.random.seed(int(time.time()) % 100000 + self._tick)
        logger.info("[MOCK] Generating mock snapshot (tick=%d)", self._tick)

        names = [
            "XLK_mom",
            "SMH_mom",
            "MAGS_mom",
            "XLY_conf",
            "XLF_conf",
            "XLI_breadth",
            "IWM_breadth",
            "XLE_inflation_stress",
        ]

        signals = {
            name: float(np.random.normal(loc=0.0, scale=0.02) + (0.01 if idx % 3 == 0 else 0.0))
            for idx, name in enumerate(names)
        }

        # simple series for frontend charting
        flow_series = [
            {"t": i, "QQQ": float(100 + np.cumsum(np.random.normal(0, 0.5, 60))[i])}
            for i in range(60)
        ]

        return {
            "timestamp": int(time.time()),
            "signals": signals,
            "flow_series": flow_series,
        }

    async def _yahoo_snapshot(self, use_cache: bool = True) -> Dict[str, Any]:
        logger.info("[YAHOO] Fetching intraday snapshot from provider: %s", self.mode)
        if yf is None:
            return await self._mock_snapshot()

        symbols = list(settings.ETF_UNIVERSE)
        provider = self._resolve_provider()

        # Intraday bars so the momentum / breadth signals actually move during
        # the trading session, instead of being pinned to a static daily close.
        period, interval = "5d", "1m"

        try:
            from app.services.cache import RedisCache
            cache = RedisCache()
        except Exception:
            cache = None

        # include the extended-hours state so a regular-hours frame cached just
        # before a window transition isn't served as extended-hours data (and vice versa)
        cache_key = f"history:{provider}:{interval}:prepost={int(self._should_fetch_prepost())}:{','.join(symbols)}"
        df = None
        # The background poll loop fetches fresh every cycle (use_cache=False);
        # the read-through cache only shields rare on-demand API fallbacks so a
        # burst of direct requests can't hammer the provider.
        if use_cache and cache is not None:
            cached = await cache.get(cache_key)
            if cached:
                logger.info("[CACHE] Snapshot history hit for key: %s", cache_key)
                df = pd.DataFrame(cached)
                # the index was stringified before caching; restore the datetime index
                df.index = pd.to_datetime(df.index, errors="coerce")
                df = df[df.index.notna()].sort_index()

        if df is None:
            logger.info("[PROVIDER] Fetching intraday history (%s/%s) from: %s", period, interval, provider)
            df = await self._fetch_history_from_provider(symbols, period=period, interval=interval)
            if df is not None:
                df = df.sort_index()
                if cache is not None:
                    logger.info("[CACHE] Storing snapshot history with key: %s", cache_key)
                    # store as dict for simple JSON serialization;
                    # stringify the datetime index so the dict keys are valid JSON keys
                    payload = df.copy()
                    payload.index = payload.index.map(str)
                    await cache.set(cache_key, payload.to_dict(), expire=settings.CACHE_TTL_SECONDS)
            else:
                logger.warning("[PROVIDER] No intraday data returned, falling back to mock")

        data = df
        if data is None or data.empty:
            return await self._mock_snapshot()

        def series(symbol: str):
            if symbol not in data.columns:
                return data.iloc[:, 0].copy()
            return data[symbol].dropna()

        def momentum(series_data: np.ndarray, window: int = 20) -> float:
            values = series_data.dropna()
            if len(values) <= window:
                return 0.0
            return float(values.iloc[-1] / values.iloc[-window - 1] - 1.0)

        def trend_confirmation(series_data: np.ndarray, short: int = 5, long: int = 20) -> float:
            values = series_data.dropna()
            if len(values) < long:
                return 0.0
            short_ma = values.rolling(short).mean().iloc[-1]
            long_ma = values.rolling(long).mean().iloc[-1]
            return float(short_ma / long_ma - 1.0) if long_ma != 0 else 0.0

        def breadth_measure(series_data: np.ndarray) -> float:
            values = series_data.dropna()
            if len(values) < 20:
                return 0.0
            return float(values.pct_change(1).rolling(5).mean().iloc[-1])

        xlk = series("XLK")
        smh = series("SMH")
        qqq = series("QQQ")
        xly = series("XLY")
        xlf = series("XLF")
        xli = series("XLI")
        iwm = series("IWM")
        xle = series("XLE")
        xlp = series("XLP")
        tlt = series("TLT")

        xlk_mom = momentum(xlk)
        smh_mom = momentum(smh)
        mags_mom = float((xlk_mom + smh_mom) / 2.0)
        xly_conf = trend_confirmation(xly)
        xlf_conf = trend_confirmation(xlf)
        xli_breadth = breadth_measure(xli)
        iwm_breadth = breadth_measure(iwm)
        xle_inflation_stress = float((momentum(xle) - momentum(tlt)) / 2.0)

        signals = {
            "XLK_mom": xlk_mom,
            "SMH_mom": smh_mom,
            "MAGS_mom": mags_mom,
            "XLY_conf": xly_conf,
            "XLF_conf": xlf_conf,
            "XLI_breadth": xli_breadth,
            "IWM_breadth": iwm_breadth,
            "XLE_inflation_stress": xle_inflation_stress,
        }
        logger.info("[SIGNALS] Computed signals: %s", signals)

        # Align every series onto a shared date index before slicing, otherwise
        # the per-symbol series can differ in length and idx-based access both
        # misaligns dates/values and raises IndexError on the shorter series.
        # ffill before dropna: extended-hours bars are sparse for thin ETFs (XLP),
        # so requiring all symbols to trade in the same minute would truncate the
        # series at the close; carry the last trade forward instead.
        # Build the chart frame only from columns actually present, so a custom
        # ETF_UNIVERSE without XLK/SMH/XLY/XLP doesn't crash the snapshot. The
        # chart symbols are all in the default universe, so they normally appear.
        chart_cols = {"qqq": qqq}
        for name, sym in (("xlk", "XLK"), ("smh", "SMH"), ("xly", "XLY"), ("xlp", "XLP")):
            if sym in data.columns:
                chart_cols[name] = series(sym)
        aligned = pd.DataFrame(chart_cols).ffill().dropna().tail(30)

        # intraday bars share a calendar date, so label points with the time too
        timestamps = [d.strftime("%m-%d %H:%M") for d in aligned.index]
        flow_series = [
            {"t": ts, "QQQ": float(aligned["qqq"].iloc[idx])}
            for idx, ts in enumerate(timestamps)
        ]

        def _col(idx, col):
            return float(aligned[col].iloc[idx]) if col in aligned.columns else 0.0

        qqq_comparison = [
            {
                "name": ts,
                "qqq": float(aligned["qqq"].iloc[idx]),
                "xlk": _col(idx, "xlk"),
                "smh": _col(idx, "smh"),
            }
            for idx, ts in enumerate(timestamps)
        ]

        xly_xlp_ratio = []
        if "xly" in aligned.columns and "xlp" in aligned.columns:
            xly_xlp_ratio = [
                {"name": ts, "value": float(aligned["xly"].iloc[idx] / aligned["xlp"].iloc[idx])}
                for idx, ts in enumerate(timestamps)
                if aligned["xlp"].iloc[idx] != 0
            ]

        def rolling_corr(series_a, series_b, window=10, key="qqqXlk"):
            aligned = pd.DataFrame({"a": series_a, "b": series_b}).dropna()
            if len(aligned) < window:
                return []
            corr = aligned["a"].pct_change().rolling(window).corr(aligned["b"].pct_change()).dropna()
            return [
                {"name": idx.strftime("%m-%d %H:%M"), key: float(corr.iloc[i])}
                for i, idx in enumerate(corr.index)
            ]

        qqq_xlk_corr = rolling_corr(qqq, xlk, key="qqqXlk")
        qqq_smh_corr = rolling_corr(qqq, smh, key="qqqSmh")
        rolling_correlation = []
        for i in range(min(len(qqq_xlk_corr), len(qqq_smh_corr))):
            rolling_correlation.append(
                {
                    "name": qqq_xlk_corr[i]["name"],
                    "qqqXlk": qqq_xlk_corr[i]["qqqXlk"],
                    "qqqSmh": qqq_smh_corr[i]["qqqSmh"] if i < len(qqq_smh_corr) else 0.0,
                    "breadth": float(np.clip((xli_breadth + iwm_breadth) / 2.0, 0.0, 1.0)),
                }
            )

        breadth_history = [
            {"name": ts, "value": float(np.clip((xli_breadth + iwm_breadth) / 2.0, 0.0, 1.0))}
            for ts in timestamps
        ]

        snapshot = {
            "timestamp": int(time.time()),
            "signals": signals,
            "flow_series": flow_series,
            "qqqComparison": qqq_comparison,
            "xlyXlpRatio": xly_xlp_ratio,
            "rollingCorrelation": rolling_correlation,
            "breadthHistory": breadth_history,
        }
        logger.info("[SNAPSHOT] Generated snapshot with %d signals, timestamp=%d", len(signals), snapshot["timestamp"])

        # Persisting the snapshot to Redis is owned by the background poll loop
        # (it writes SNAPSHOT_KEY each cycle), so the computation stays pure here.
        return snapshot

    async def _fetch_history_from_provider(self, symbols: List[str], period: str = "7d", interval: str = "1m") -> Optional[pd.DataFrame]:
        provider = self._resolve_provider()
        df = None

        try:
            from app.services.adapters import AlphaVantageAdapter, TwelveDataAdapter, FinnhubAdapter
        except Exception:
            AlphaVantageAdapter = None
            TwelveDataAdapter = None
            FinnhubAdapter = None
        try:
            from app.services.adapters.polygon import PolygonAdapter
        except Exception:
            PolygonAdapter = None
        try:
            from app.services.adapters.alpaca import AlpacaAdapter
        except Exception:
            AlpacaAdapter = None

        started = time.monotonic()
        logger.info(
            "[FETCH] pulling %d symbols | provider=%s period=%s interval=%s",
            len(symbols), provider, period, interval,
        )
        try:
            if provider == "alphavantage" and AlphaVantageAdapter is not None:
                adapter = AlphaVantageAdapter()
                df = await adapter.fetch_history(symbols, period=period, interval=interval)
            elif provider == "twelvedata" and TwelveDataAdapter is not None:
                adapter = TwelveDataAdapter()
                df = await adapter.fetch_history(symbols, period=period, interval=interval)
            elif provider == "polygon" and PolygonAdapter is not None:
                adapter = PolygonAdapter()
                df = await adapter.fetch_history(symbols, period=period, interval=interval)
            elif provider == "alpaca" and AlpacaAdapter is not None:
                adapter = AlpacaAdapter()
                df = await adapter.fetch_history(symbols, period=period, interval=interval)
            elif provider == "finnhub" and FinnhubAdapter is not None:
                adapter = FinnhubAdapter()
                df = await adapter.fetch_history(symbols, period=period, interval=interval)
            elif provider == "yahoo" and yf is not None:
                df = await self._throttled_yahoo_download(symbols, period=period, interval=interval)
            elif provider in ("auto", "best") and yf is not None:
                logger.info("[MARKET] Auto provider failed or unavailable, falling back to Yahoo intraday for symbols: %s", symbols)
                df = await self._throttled_yahoo_download(symbols, period=period, interval=interval)

            if df is None and provider == "yahoo" and yf is not None:
                df = await self._throttled_yahoo_download(symbols, period=period, interval=interval)
        except Exception:
            elapsed = time.monotonic() - started
            logger.exception(
                "[FETCH] ERROR provider=%s after %.2fs (symbols=%s)", provider, elapsed, symbols
            )
            return None

        elapsed = time.monotonic() - started
        if df is not None and not df.empty:
            logger.info(
                "[FETCH] OK provider=%s in %.2fs | rows=%d cols=%d",
                provider, elapsed, len(df), len(df.columns),
            )
            return df
        logger.warning(
            "[FETCH] NO DATA provider=%s in %.2fs (symbols=%s)", provider, elapsed, symbols
        )
        return None

    async def _throttled_yahoo_download(self, symbols: List[str], period: str, interval: str):
        """Call the Yahoo download path at most once per
        YAHOO_MIN_FETCH_INTERVAL_SECONDS; otherwise return the remembered frame.

        Guards against hammering the free Yahoo endpoint when several callers
        (poll loop, on-demand API fallbacks) fetch in quick succession.
        """
        now = time.monotonic()
        elapsed = now - self._last_yahoo_fetch
        if (self._last_yahoo_frame is not None
                and self._last_yahoo_params == (period, interval)
                and elapsed < settings.YAHOO_MIN_FETCH_INTERVAL_SECONDS):
            logger.info(
                "[YAHOO] throttle: reusing %s/%s frame fetched %.1fs ago (< %.1fs)",
                period, interval, elapsed, settings.YAHOO_MIN_FETCH_INTERVAL_SECONDS,
            )
            return self._last_yahoo_frame
        df = await asyncio.to_thread(
            self._download_intraday_history, symbols, period=period, interval=interval
        )
        self._last_yahoo_fetch = time.monotonic()
        if df is not None and not getattr(df, "empty", True):
            self._last_yahoo_frame = df
            self._last_yahoo_params = (period, interval)
        return df

    def _split_bars_by_et_date(self, bars: pd.DataFrame) -> Dict[str, pd.DataFrame]:
        """Group a multi-day 1m frame into {ET-date: sub-frame} so each day can be
        seeded under its own history-store key."""
        if bars is None or getattr(bars, "empty", True):
            return {}
        idx = bars.index
        try:
            et_idx = idx.tz_convert(ZoneInfo("America/New_York")) if idx.tz is not None else idx
        except (AttributeError, TypeError):
            et_idx = idx
        labels = [pd.Timestamp(ts).strftime("%Y-%m-%d") for ts in et_idx]
        groups: Dict[str, pd.DataFrame] = {}
        for label in sorted(set(labels)):
            mask = [l == label for l in labels]
            groups[label] = bars.loc[mask]
        return groups

    async def _backfill_recent_sessions(self, history_store) -> None:
        """Seed the history store from a data provider when the cache is cold, so
        cross-day signals (stability, hit-rate) work on day one. Redis stays a
        short-term rolling cache; the provider is the source of truth.

        Source is settings.HISTORY_BACKFILL_SOURCE: "provider" (DATA_PROVIDER),
        "yahoo" (force Yahoo), or "none" (disabled).
        """
        if not getattr(settings, "HISTORY_BACKFILL_ENABLED", True):
            return
        source = getattr(settings, "HISTORY_BACKFILL_SOURCE", "provider")
        if source == "none":
            return
        min_sessions = getattr(settings, "HISTORY_BACKFILL_MIN_SESSIONS", 5)
        try:
            existing = await history_store.get_recent_sessions()
        except Exception:
            logger.exception("[BACKFILL] could not read existing sessions")
            existing = []
        if existing and len(existing) >= min_sessions:
            return  # cache already warm enough

        days = getattr(settings, "HISTORY_BACKFILL_DAYS", 7)
        symbols = list(settings.ETF_UNIVERSE)
        period = f"{days}d"
        logger.info("[BACKFILL] cold cache (%d sessions) — seeding %s from %s",
                    len(existing), period, source)
        try:
            if source == "yahoo":
                # bypass the provider router and the in-process throttle: backfill is
                # rare (cold cache only) and needs its own wide-window frame.
                frame = await asyncio.to_thread(
                    self._download_intraday_history, symbols, period=period, interval="1m"
                )
            else:
                frame = await self._fetch_history_from_provider(
                    symbols, period=period, interval="1m"
                )
        except Exception:
            logger.exception("[BACKFILL] provider fetch failed")
            return
        if frame is None or getattr(frame, "empty", True):
            logger.warning("[BACKFILL] no data returned; skipping seed")
            return

        seeded_bars = 0
        groups = self._split_bars_by_et_date(frame.sort_index())
        for date_label, sub in groups.items():
            try:
                seeded_bars += await history_store.seed_session(date_label, sub)
            except Exception:
                logger.exception("[BACKFILL] seed failed for %s", date_label)
        logger.info("[BACKFILL] seeded %d bars across %d sessions from %s",
                    seeded_bars, len(groups), source)

    async def fetch_intraday_history(self, symbols: List[str], period: str = "7d", interval: str = "1m") -> Optional[pd.DataFrame]:
        df = await self._fetch_history_from_provider(symbols, period=period, interval=interval)
        if df is None or df.empty:
            return None
        if isinstance(df, pd.DataFrame):
            return df.sort_index()
        return None

    async def fetch_qqq_score(self, period: str = "2y", interval: str = "1d") -> Dict[str, Any]:
        logger.info("[MARKET] Computing QQQ score for interval=%s, period=%s", interval, period)
        symbols = list(settings.ETF_UNIVERSE)
        data = await self.fetch_intraday_history(symbols, period=period, interval=interval)
        if data is None or data.empty:
            logger.warning("[MARKET] No intraday history available, returning mock QQQ score")
            return self._mock_qqq_score()
        score = self.qqq_engine.compute(data)
        score["timestamp"] = int(time.time())
        score["provider"] = self._resolve_provider()
        return score

    async def fetch_breadth(self) -> Dict[str, Any]:
        """Nasdaq-100 breadth from the constituents' session open vs latest price.

        One batched 1m fetch of the ~100 constituents (offloaded to a thread);
        both equal-weight and cap-weight breadth are computed from that single
        pull. Separate symbol set from the ETF universe, so it's its own batch —
        run once per poll cycle, which is already within the rate-limit guard.
        """
        engine = BreadthEngine()
        if not getattr(settings, "BREADTH_ENABLED", True):
            return engine._empty("no_data")

        weights = HoldingsProvider().get_constituents()
        if not weights:
            return engine._empty("no_data")

        symbols = list(weights.keys())
        try:
            # constituents are a distinct symbol set from the ETF universe, so
            # fetch directly (bypassing the universe throttle which memoizes one
            # frame); this runs once per ~1-minute cycle.
            bars = await asyncio.to_thread(
                self._download_intraday_history, symbols, "1d", "1m"
            )
        except Exception:
            logger.exception("[BREADTH] constituent fetch failed")
            return engine._empty("warming_up", len(weights))

        if bars is None or getattr(bars, "empty", True):
            return engine._empty("warming_up", len(weights))

        bars = bars.sort_index()
        opens: Dict[str, float] = {}
        lasts: Dict[str, float] = {}
        for sym in symbols:
            if sym not in bars.columns:
                continue
            series = bars[sym].dropna()
            if len(series) < 1:
                continue
            opens[sym] = float(series.iloc[0])
            lasts[sym] = float(series.iloc[-1])

        return engine.compute(opens, lasts, weights)

    async def fetch_ai_dependency(self, force: bool = False) -> Dict[str, Any]:
        """AI-capex dependency index (structural, daily). Cached in-process and
        only recomputed every AI_DEPENDENCY_REFRESH_SECONDS — it is a slow daily
        metric and must never be tied to the intraday poll cadence or thesis."""
        engine = AIDependencyEngine()
        if not getattr(settings, "AI_DEPENDENCY_ENABLED", True):
            return engine._empty("no_data")

        now = time.monotonic()
        if (not force and self._ai_dep_cache is not None
                and now - self._ai_dep_fetched < settings.AI_DEPENDENCY_REFRESH_SECONDS):
            return self._ai_dep_cache

        symbols = engine.all_symbols()
        period = getattr(settings, "AI_DEPENDENCY_PERIOD", "2y")
        try:
            closes = await asyncio.to_thread(
                self._download_intraday_history, symbols, period, "1d"
            )
        except Exception:
            logger.exception("[AIDEP] daily fetch failed")
            return self._ai_dep_cache or engine._empty("warming_up")

        if closes is None or getattr(closes, "empty", True):
            return self._ai_dep_cache or engine._empty("warming_up")

        # Sanity guard: a "2y" daily pull is ~500 rows. Far more = we were handed
        # intraday data (a thread-safety clobber). Reject rather than memoize
        # garbage for an hour; serve the last good value instead.
        if len(closes) > 800:
            logger.warning("[AIDEP] daily pull looks intraday (%d rows) — rejecting",
                           len(closes))
            return self._ai_dep_cache or engine._empty("warming_up")

        result = engine.compute(closes)
        self._ai_dep_cache = result
        self._ai_dep_fetched = now
        return result

    async def _get_daily_universe_bars(self) -> Optional[pd.DataFrame]:
        """Daily close bars for the ETF universe (cross-day lead/lag). Cached in
        process and refetched on the AI-dependency cadence — it's a slow daily
        frame, no need to repull every poll cycle."""
        now = time.monotonic()
        refresh = int(getattr(settings, "AI_DEPENDENCY_REFRESH_SECONDS", 3600))
        if (self._daily_universe_cache is not None
                and now - self._daily_universe_fetched < refresh):
            return self._daily_universe_cache
        try:
            df = await asyncio.to_thread(
                self._download_intraday_history, list(settings.ETF_UNIVERSE), "1y", "1d"
            )
        except Exception:
            logger.exception("[DAILY-LL] universe daily fetch failed")
            return self._daily_universe_cache
        if df is None or getattr(df, "empty", True) or len(df) > 800:
            return self._daily_universe_cache
        self._daily_universe_cache = df
        self._daily_universe_fetched = now
        return df

    async def fetch_premarket_board(self, force: bool = False) -> Dict[str, Any]:
        """Overnight / pre-market board (descriptive — never feeds scoring).
        Cached in-process and refreshed every PREMARKET_REFRESH_SECONDS so it is
        decoupled from the intraday poll cadence."""
        board = PremarketBoard(
            top_n=int(getattr(settings, "PREMARKET_TOP_N", 8)),
            min_gap=float(getattr(settings, "PREMARKET_MIN_GAP", 0.01)),
            force_open=bool(getattr(settings, "PREMARKET_FORCE_OPEN", False)),
        )
        if not getattr(settings, "PREMARKET_ENABLED", True):
            return board._empty("no_data")

        now = time.monotonic()
        refresh = int(getattr(settings, "PREMARKET_REFRESH_SECONDS", 900))
        if (not force and self._premarket_cache is not None
                and now - self._premarket_fetched < refresh):
            return self._premarket_cache

        asof = datetime.now(ZoneInfo("America/New_York"))
        weights = HoldingsProvider().get_constituents()
        universe = list(weights.keys())
        if not universe:
            return self._premarket_cache or board._empty("warming_up", asof.isoformat())
        fut = ["NQ=F", "ES=F"]
        asia = list(getattr(settings, "PREMARKET_ASIA_BASKET",
                            ["2330.TW", "005930.KS", "000660.KS", "8035.T", "6857.T"]))
        europe = list(getattr(settings, "PREMARKET_EUROPE", ["ASML.AS"]))

        try:
            intraday = await asyncio.to_thread(
                self._download_intraday_history, universe + fut, "2d", "5m", True)
            odaily = await asyncio.to_thread(
                self._download_intraday_history, asia + europe, "5d", "1d", False)
        except Exception:
            logger.exception("[PREMKT] fetch failed")
            return self._premarket_cache or board._empty("warming_up", asof.isoformat())

        if intraday is None or getattr(intraday, "empty", True):
            return self._premarket_cache or board._empty("warming_up", asof.isoformat())

        quotes = self._extract_premarket_quotes(intraday, universe + fut)
        tape = {
            "nq": self._gap_from_quote(quotes.get("NQ=F")),
            "es": self._gap_from_quote(quotes.get("ES=F")),
            "asia": self._daily_basket_return(odaily, asia),
            "europe": self._daily_basket_return(odaily, europe),
        }
        mover_quotes = {s: q for s, q in quotes.items() if s in weights}
        result = board.compute(mover_quotes, weights, tape, pd.Timestamp(asof))
        self._premarket_cache = result
        self._premarket_fetched = now
        return result

    def _extract_premarket_quotes(self, cl, symbols) -> Dict[str, Dict[str, float]]:
        """From a 5m Close frame (cols=symbols), pull per-symbol prev RTH close,
        today's reference price (settled 09:30 open once the bell rings, else the
        latest pre-market print), and the pre-market early/late prints."""
        ET = ZoneInfo("America/New_York")
        idx = cl.index
        idx = idx.tz_localize("UTC") if idx.tz is None else idx
        cl = cl.copy(); cl.index = idx.tz_convert(ET)
        dates = sorted(set(cl.index.normalize()))
        if not dates:
            return {}
        today = dates[-1]
        prior = [d for d in dates if d < today]
        t930 = pd.Timestamp("09:30").time(); t1600 = pd.Timestamp("16:00").time()
        out: Dict[str, Dict[str, float]] = {}
        for sym in symbols:
            if sym not in cl.columns:
                continue
            s = cl[sym].dropna()
            if s.empty:
                continue
            prev_close = None
            for d in reversed(prior):
                rth = s[(s.index.normalize() == d) & (s.index.time >= t930) & (s.index.time <= t1600)]
                if len(rth):
                    prev_close = float(rth.iloc[-1]); break
            if prev_close is None:
                before = s[s.index.normalize() < today]
                prev_close = float(before.iloc[-1]) if len(before) else None
            td = s[s.index.normalize() == today]
            if td.empty or not prev_close:
                continue
            rth_today = td[td.index.time >= t930]
            opened = len(rth_today) > 0
            # ref = settled 09:30 open once the bell rings, else latest pre-market
            ref = float(rth_today.iloc[0]) if opened else float(td.iloc[-1])
            pm = td[td.index.time < t930]
            out[sym] = {
                "prev_close": prev_close, "ref": ref,
                "last": float(td.iloc[-1]), "opened": opened,
                "pm_early": float(pm.iloc[0]) if len(pm) else None,
                "pm_late": float(pm.iloc[-1]) if len(pm) else None,
            }
        return out

    @staticmethod
    def _gap_from_quote(q) -> Optional[float]:
        if not q or not q.get("prev_close") or not q.get("ref"):
            return None
        return q["ref"] / q["prev_close"] - 1.0

    @staticmethod
    def _daily_basket_return(daily, syms) -> Optional[float]:
        """Mean most-recent daily close-to-close return across a basket (the
        overnight read for Asia/Europe sessions that closed before the US open)."""
        if daily is None or getattr(daily, "empty", True):
            return None
        rets = []
        for s in syms:
            if s in getattr(daily, "columns", []):
                ser = daily[s].dropna()
                if len(ser) >= 2 and ser.iloc[-2] > 0:
                    rets.append(float(ser.iloc[-1] / ser.iloc[-2] - 1.0))
        return float(np.mean(rets)) if rets else None

    def _empty_rotation(self, session: str) -> Dict[str, Any]:
        """Contract-shaped placeholder when no OHLCV is available yet."""
        from app.core import rotation as rot
        windows = {
            f"{m}m": {
                "regime": "warming_up",
                "subject_return": None,
                "subject_dvol_surge": 1.0,
                "rows": [],
                "summary": {"direction": "flat", "into": [], "from": [],
                            "unaccounted": False, "text": "Warming up — no data yet."},
            }
            for m in rot.WINDOWS_MIN
        }
        return {
            "subject": rot.SUBJECT, "universe": [],
            "asof": datetime.now(timezone.utc).isoformat(),
            "session": session, "windows": windows,
        }

    async def fetch_rotation(self, use_cache: bool = True,
                             session: str = "live") -> Dict[str, Any]:
        """Cross-sector rotation flow from 1m OHLCV over today's session.

        The shared `_fetch_history_from_provider` path is close-only (volume is
        dropped), and rotation NEEDS dollar-volume, so this pulls its own OHLCV
        via `rotation.fetch_ohlcv` (yfinance). Cached in-process for ~one poll
        interval so the loop and on-demand API calls don't both hit the provider.
        Adds `asof` (UTC) and `session` to the pure compute_rotation dict.
        """
        from app.core import rotation as rot
        now = time.monotonic()
        ttl = float(getattr(settings, "POLL_INTERVAL_SECONDS", 30.0))
        if (use_cache and self._rotation_cache is not None
                and self._rotation_cache.get("session") == session
                and now - self._rotation_fetched < ttl):
            return self._rotation_cache
        try:
            close, volume = await asyncio.to_thread(
                rot.fetch_ohlcv, rot.ROTATION_UNIVERSE, "1d", "1m"
            )
        except Exception:
            logger.exception("[ROTATION] 1m OHLCV fetch failed")
            return self._rotation_cache or self._empty_rotation(session)
        if close is None or getattr(close, "empty", True):
            logger.warning("[ROTATION] no 1m OHLCV returned")
            return self._rotation_cache or self._empty_rotation(session)
        result = rot.compute_rotation(close, volume)
        result["asof"] = datetime.now(timezone.utc).isoformat()
        result["session"] = session
        self._rotation_cache = result
        self._rotation_fetched = now
        logger.info("[ROTATION] computed session=%s universe=%d",
                    session, len(result.get("universe", [])))
        return result

    async def fetch_rotation_daily(self) -> Dict[str, Any]:
        """Coarse daily-bar rotation read (windows in DAYS) — the settled
        cross-check for the after-hours backtest. Not cached; called once/day."""
        from app.core import rotation as rot
        try:
            close, volume = await asyncio.to_thread(
                rot.fetch_ohlcv, rot.ROTATION_UNIVERSE, "10d", "1d"
            )
        except Exception:
            logger.exception("[ROTATION] daily OHLCV fetch failed")
            return self._empty_rotation("daily")
        if close is None or getattr(close, "empty", True):
            return self._empty_rotation("daily")
        result = rot.compute_rotation(close, volume, windows=(1, 2, 5))
        result["asof"] = datetime.now(timezone.utc).isoformat()
        result["session"] = "daily"
        return result

    def _update_leadlag_streak(self, tf: str, leader: Optional[Dict[str, Any]],
                               window_end: Optional[str], freq_minutes: int) -> Dict[str, Any]:
        """Advance the consecutive-occurrence streak for a timeframe's leader.

        Counts a new occurrence only when a NEW bar has formed (window_end moved),
        so the streak measures real repetition across bars — not poll redundancy.
        Same leader (within one bar of lag tolerance) on consecutive new bars
        increments; a change or no-leader resets. Confirmed at LEAD_LAG_STREAK_MIN.
        """
        min_streak = int(getattr(settings, "LEAD_LAG_STREAK_MIN", 3))
        prev = self._leadlag_streak.get(tf) or {}

        # no new bar since last check → hold the current streak unchanged
        if window_end and prev.get("window_end") == window_end:
            return {k: prev[k] for k in
                    ("symbol", "lag_minutes", "count", "confirmed")
                    if k in prev} or {
                        "symbol": None, "lag_minutes": 0, "count": 0, "confirmed": False}

        if leader and leader.get("symbol"):
            sym = leader["symbol"]
            lag = int(leader.get("lag_minutes") or 0)
            same = (prev.get("symbol") == sym
                    and abs(int(prev.get("lag_minutes") or 0) - lag) <= freq_minutes)
            count = (int(prev.get("count") or 0) + 1) if same else 1
            state = {"symbol": sym, "lag_minutes": lag, "count": count,
                     "confirmed": count >= min_streak}
        else:
            state = {"symbol": None, "lag_minutes": 0, "count": 0, "confirmed": False}

        self._leadlag_streak[tf] = {**state, "window_end": window_end}
        return state

    async def fetch_prediction(self, history_store=None) -> Dict[str, Any]:
        """Compute the intraday QQQ prediction from accumulated session bars.

        Fetches 1m bars for the configured ETF universe, optionally merges them
        into the supplied history store (so lead/lag runs on the whole session,
        not just the latest fetch), then runs the lead/lag, composite-score, and
        projection engines and assembles the prediction payload.
        """
        logger.info("[PREDICT] computing prediction for universe=%s", settings.ETF_UNIVERSE)
        symbols = list(settings.ETF_UNIVERSE)

        # Extended-hours window: pull a slightly wider span so the session frame
        # spans pre/post-market bars; regular session uses today's bars only.
        period = "5d" if self._should_fetch_prepost() else "1d"
        bars = await self.fetch_intraday_history(symbols, period=period, interval="1m")

        if history_store is not None:
            try:
                # Seed past sessions from the provider when the cache is cold so the
                # cross-day signals work on day one (no multi-day self-collection wait).
                await self._backfill_recent_sessions(history_store)
            except Exception:
                logger.exception("[PREDICT] backfill failed; continuing")
            try:
                if bars is not None and not getattr(bars, "empty", True):
                    await history_store.append_bars(bars)
                stored = await history_store.get_session_bars()
                if stored is not None and not getattr(stored, "empty", True):
                    bars = stored
            except Exception:
                logger.exception("[PREDICT] history store merge failed; using fetched bars")

        lead_lag = LeadLagEngine().compute(bars)
        score = IntradayScoreEngine().compute(bars, lead_lag)
        projection = ProjectionEngine().compute(bars, lead_lag, score)

        # Coarser-timeframe lead/lag (5m / 15m) — real leads emerge above 1m;
        # each also flags drivers that USUALLY track QQQ but broke ranks now
        # (decoupling) vs a recent multi-day baseline. Default UI frame is 15m.
        lead_lag_tf: Dict[str, Any] = {}
        try:
            ll_engine = LeadLagEngine()
            tf_baseline = None
            if history_store is not None:
                try:
                    tf_baseline = await history_store.get_recent_bars()
                except Exception:
                    tf_baseline = None
            for key, fm, mlag, mbars in (("5min", 5, 3, 18), ("15min", 15, 2, 8)):
                cur = ll_engine.compute(bars, freq_minutes=fm, max_lag=mlag, min_bars=mbars)
                if tf_baseline is not None and not getattr(tf_baseline, "empty", True):
                    base = ll_engine.compute(tf_baseline, freq_minutes=fm,
                                             max_lag=mlag, min_bars=mbars)
                    cur["decoupled"] = ll_engine.detect_decoupling(cur, base)
                # streak filter: only confirm a leader once it recurs on N new bars
                streak = self._update_leadlag_streak(key, cur.get("leader"),
                                                     cur.get("window_end"), fm)
                cur["streak"] = streak
                cur["confirmed_leader"] = cur.get("leader") if streak["confirmed"] else None
                lead_lag_tf[key] = cur

            # Daily / cross-day frame — measured over ~1y of daily bars, where a
            # real multi-day lead is most likely. The measurement already spans
            # months, so it's self-confirming (no live streak wait); bar=1 day.
            daily_bars = await self._get_daily_universe_bars()
            if daily_bars is not None and not getattr(daily_bars, "empty", True):
                d = ll_engine.compute(daily_bars, freq_minutes=1, max_lag=5,
                                      min_bars=30, bar_minutes=1440)
                d["confirmed_leader"] = d.get("leader")
                d["streak"] = {
                    "symbol": (d.get("leader") or {}).get("symbol"),
                    "lag_minutes": (d.get("leader") or {}).get("lag_minutes", 0),
                    "count": int(d.get("bars_used", 0)),
                    "confirmed": d.get("leader") is not None,
                }
                lead_lag_tf["daily"] = d
        except Exception:
            logger.exception("[PREDICT] lead_lag_tf failed; using empty")
            lead_lag_tf = {}

        # --- Phase 2 value features (each guarded; degrade to the engine's own
        # warming_up shape rather than throwing). ---
        try:
            attribution = DriverAttributionEngine().compute(bars)
        except Exception:
            logger.exception("[PREDICT] attribution failed; using warming_up")
            attribution = DriverAttributionEngine()._empty("warming_up")
        try:
            confirmation = ConfirmationGate().compute(bars, lead_lag, score)
        except Exception:
            logger.exception("[PREDICT] confirmation failed; using warming_up")
            confirmation = ConfirmationGate()._warming_up()
        try:
            correlation_regime = CorrelationRegimeEngine().compute(bars)
        except Exception:
            logger.exception("[PREDICT] correlation regime failed; using warming_up")
            correlation_regime = CorrelationRegimeEngine()._empty("warming_up")

        # Cross-session features need the history store. Without one they stay
        # in a populated warming_up/gathering shape.
        stability = StabilityEngine()._result(
            "warming_up", None, "gathering", "Gathering data — 0 sessions so far."
        )
        hit_rate = HitRateEngine()._empty(
            "warming_up", None, 5, "auto", "Gathering data — no history yet."
        )
        if history_store is not None:
            try:
                sessions = await history_store.get_recent_sessions()
                stability = StabilityEngine().compute(sessions, lead_lag)
            except Exception:
                logger.exception("[PREDICT] stability failed; using warming_up")
            try:
                recent = await history_store.get_recent_bars()
                # a CONFIRMED (streak) leader takes priority — hit-rate then scores
                # follow-through on the repeating lead; otherwise fall back to the
                # measured leader so the continuation stat stays available.
                confirmed = (lead_lag_tf.get("15min") or {}).get("confirmed_leader")
                hit_lead = {"leader": confirmed} if confirmed else lead_lag
                hit_rate = HitRateEngine().compute(
                    recent if recent is not None else bars, hit_lead
                )
            except Exception:
                logger.exception("[PREDICT] hit_rate failed; using warming_up")

        # Nasdaq-100 breadth — real constituent participation (own batch fetch).
        try:
            breadth = await self.fetch_breadth()
        except Exception:
            logger.exception("[PREDICT] breadth failed; using no_data")
            breadth = BreadthEngine()._empty("no_data")

        # AI-capex dependency — structural/daily, cached in-process (cheap here).
        try:
            ai_dependency = await self.fetch_ai_dependency()
        except Exception:
            logger.exception("[PREDICT] ai_dependency failed; using warming_up")
            ai_dependency = AIDependencyEngine()._empty("warming_up")

        prediction = {
            "timestamp": int(time.time()),
            "status": lead_lag["status"],
            "bars_used": lead_lag["bars_used"],
            "universe": list(settings.ETF_UNIVERSE),
            "target": settings.PREDICTION_TARGET,
            "lead_lag": lead_lag,
            "lead_lag_tf": lead_lag_tf,
            "score": score,
            "projection": projection,
            "attribution": attribution,
            "confirmation": confirmation,
            "correlation_regime": correlation_regime,
            "stability": stability,
            "hit_rate": hit_rate,
            "breadth": breadth,
            "ai_dependency": ai_dependency,
        }
        logger.info(
            "[PREDICT] status=%s bars=%d verdict=%s direction=%s",
            prediction["status"], prediction["bars_used"],
            score.get("verdict"), projection.get("direction"),
        )
        return prediction

    def _mock_qqq_score(self) -> Dict[str, Any]:
        np.random.seed(int(time.time()) % 100000 + self._tick)
        score_value = float(np.random.normal(loc=0.0, scale=0.2))
        probability = float(np.tanh(score_value * 2.0))
        direction = "bullish" if score_value >= 0 else "bearish"
        return {
            "timestamp": int(time.time()),
            "direction": direction,
            "raw_score": score_value,
            "probability": probability,
            "fragility": float(np.clip(-score_value, 0.0, 1.0)),
            "leader_momentum": {"XLK": 0.0, "SMH": 0.0},
            "mags_momentum": 0.0,
            "broadening_momentum": {"XLY": 0.0, "XLF": 0.0},
            "broadening_avg": 0.0,
            "confirmation_momentum": {"XLI": 0.0, "IWM": 0.0, "XLE": 0.0},
            "confirmation_avg": 0.0,
            "lead_lag": [],
            "lead_signal": 0.0,
            "recent_qqq": [],
            "provider": self._resolve_provider(),
        }

    def _download_intraday_history(self, symbols: List[str], period: str = "7d", interval: str = "1m",
                                   prepost: Optional[bool] = None):
        if prepost is None:
            prepost = self._should_fetch_prepost()
        if prepost:
            logger.info("[YAHOO] Extended-hours window active, requesting pre/post market bars")
        with _YF_DOWNLOAD_LOCK:
            raw = yf.download(
                tickers=symbols,
                period=period,
                interval=interval,
                prepost=prepost,
                auto_adjust=True,
                progress=False,
                threads=False,
                group_by="column",
            )
        if raw is None or raw.empty:
            return None
        if isinstance(raw.columns, pd.MultiIndex):
            if "Close" in raw.columns.get_level_values(0):
                close = raw["Close"]
            else:
                close = raw
        elif "Close" in raw.columns:
            close = raw["Close"]
        else:
            close = raw
        if isinstance(close, np.ndarray):
            close = pd.DataFrame(close, columns=symbols)
        return close

    def _download_history(self, symbols: List[str]):
        with _YF_DOWNLOAD_LOCK:
            raw = yf.download(
                tickers=symbols,
                period="90d",
                interval="1d",
                auto_adjust=True,
                progress=False,
                threads=False,
                group_by="column",
            )
        if raw is None or raw.empty:
            return None
        if isinstance(raw.columns, pd.MultiIndex):
            if "Close" in raw.columns.get_level_values(0):
                close = raw["Close"]
            else:
                close = raw
        elif "Close" in raw.columns:
            close = raw["Close"]
        else:
            close = raw
        if isinstance(close, np.ndarray):
            close = pd.DataFrame(close, columns=symbols)
        return close
