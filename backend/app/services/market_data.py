import asyncio
import os
import random
import time
import json
import logging
from typing import Dict, Any, List, Optional

import numpy as np
import pandas as pd

from app.config import settings
from app.core.qqq_score import QQQScoreEngine

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

        symbols = ["XLK", "SMH", "QQQ", "XLY", "XLF", "XLI", "IWM", "XLE", "XLP", "TLT"]
        provider = self._resolve_provider()

        # Intraday bars so the momentum / breadth signals actually move during
        # the trading session, instead of being pinned to a static daily close.
        period, interval = "5d", "1m"

        try:
            from app.services.cache import RedisCache
            cache = RedisCache()
        except Exception:
            cache = None

        cache_key = f"history:{provider}:{interval}:{','.join(symbols)}"
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
        aligned = pd.DataFrame(
            {"qqq": qqq, "xlk": xlk, "smh": smh, "xly": xly, "xlp": xlp}
        ).dropna().tail(30)

        # intraday bars share a calendar date, so label points with the time too
        timestamps = [d.strftime("%m-%d %H:%M") for d in aligned.index]
        flow_series = [
            {"t": ts, "QQQ": float(aligned["qqq"].iloc[idx])}
            for idx, ts in enumerate(timestamps)
        ]

        qqq_comparison = [
            {
                "name": ts,
                "qqq": float(aligned["qqq"].iloc[idx]),
                "xlk": float(aligned["xlk"].iloc[idx]),
                "smh": float(aligned["smh"].iloc[idx]),
            }
            for idx, ts in enumerate(timestamps)
        ]

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
                df = await asyncio.to_thread(self._download_intraday_history, symbols, period=period, interval=interval)
            elif provider in ("auto", "best") and yf is not None:
                logger.info("[MARKET] Auto provider failed or unavailable, falling back to Yahoo intraday for symbols: %s", symbols)
                df = await asyncio.to_thread(self._download_intraday_history, symbols, period=period, interval=interval)

            if df is None and provider == "yahoo" and yf is not None:
                df = await asyncio.to_thread(self._download_intraday_history, symbols, period=period, interval=interval)
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

    async def fetch_intraday_history(self, symbols: List[str], period: str = "7d", interval: str = "1m") -> Optional[pd.DataFrame]:
        df = await self._fetch_history_from_provider(symbols, period=period, interval=interval)
        if df is None or df.empty:
            return None
        if isinstance(df, pd.DataFrame):
            return df.sort_index()
        return None

    async def fetch_qqq_score(self, period: str = "2y", interval: str = "1d") -> Dict[str, Any]:
        logger.info("[MARKET] Computing QQQ score for interval=%s, period=%s", interval, period)
        symbols = ["XLK", "SMH", "QQQ", "XLY", "XLF", "XLI", "IWM", "XLE"]
        data = await self.fetch_intraday_history(symbols, period=period, interval=interval)
        if data is None or data.empty:
            logger.warning("[MARKET] No intraday history available, returning mock QQQ score")
            return self._mock_qqq_score()
        score = self.qqq_engine.compute(data)
        score["timestamp"] = int(time.time())
        score["provider"] = self._resolve_provider()
        return score

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
        raw = yf.download(
            tickers=symbols,
            period=period,
            interval=interval,
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
