import asyncio
import os
import random
import time
import json
import logging
from datetime import datetime
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
from app.services.holdings import HoldingsProvider

logger = logging.getLogger(__name__)

try:
    import yfinance as yf
except ImportError:
    yf = None

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
                hit_rate = HitRateEngine().compute(
                    recent if recent is not None else bars, lead_lag
                )
            except Exception:
                logger.exception("[PREDICT] hit_rate failed; using warming_up")

        # Nasdaq-100 breadth — real constituent participation (own batch fetch).
        try:
            breadth = await self.fetch_breadth()
        except Exception:
            logger.exception("[PREDICT] breadth failed; using no_data")
            breadth = BreadthEngine()._empty("no_data")

        prediction = {
            "timestamp": int(time.time()),
            "status": lead_lag["status"],
            "bars_used": lead_lag["bars_used"],
            "universe": list(settings.ETF_UNIVERSE),
            "target": settings.PREDICTION_TARGET,
            "lead_lag": lead_lag,
            "score": score,
            "projection": projection,
            "attribution": attribution,
            "confirmation": confirmation,
            "correlation_regime": correlation_regime,
            "stability": stability,
            "hit_rate": hit_rate,
            "breadth": breadth,
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

    def _download_intraday_history(self, symbols: List[str], period: str = "7d", interval: str = "1m"):
        prepost = self._should_fetch_prepost()
        if prepost:
            logger.info("[YAHOO] Extended-hours window active, requesting pre/post market bars")
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
