import os
from pathlib import Path
from typing import List, Optional

try:
    from dotenv import load_dotenv
    dotenv_path = Path(__file__).resolve().parents[1] / ".env"
    loaded = load_dotenv(dotenv_path=dotenv_path, verbose=True)
    if not loaded:
        print(f"Could not load .env from {dotenv_path}")
except ModuleNotFoundError:
    print("python-dotenv is not installed; environment variables from .env will not be loaded")
except Exception as e:
    print(f"Error loading .env: {e}")


def _env_int(name: str, default: int) -> int:
    """Read an int from the environment, falling back to default if unset/invalid."""
    try:
        return int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        print(f"[CONFIG] invalid value for {name}, using default {default}")
        return default


def _env_float(name: str, default: float) -> float:
    """Read a float from the environment, falling back to default if unset/invalid."""
    try:
        return float(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        print(f"[CONFIG] invalid value for {name}, using default {default}")
        return default


class Settings:
    # Data provider selection: mock, yahoo, alphavantage, twelvedata, polygon, alpaca
    DATA_PROVIDER: str = os.getenv("DATA_PROVIDER", "mock")

    # API keys
    ALPHAVANTAGE_KEY: Optional[str] = os.getenv("ALPHAVANTAGE_KEY")
    TWELVEDATA_KEY: Optional[str] = os.getenv("TWELVEDATA_KEY")
    POLYGON_KEY: Optional[str] = os.getenv("POLYGON_KEY")
    ALPACA_KEY: Optional[str] = os.getenv("ALPACA_KEY")
    ALPACA_SECRET: Optional[str] = os.getenv("ALPACA_SECRET")
    FINNHUB_KEY: Optional[str] = os.getenv("FINNHUB_KEY")

    # Redis
    REDIS_URL: Optional[str] = os.getenv("REDIS_URL")

    # Scoring behavior
    NORMALIZE_SIGNALS: bool = os.getenv("NORMALIZE_SIGNALS", "false").lower() in ("1", "true", "yes")

    # Fetch extended-hours bars (pre-market / after-hours) from the data provider
    # whenever the current time is outside the regular session (9:30-16:00 ET,
    # weekdays), so after-hours data stays visible until the next session opens.
    FETCH_PRE_POST_MARKET: bool = os.getenv("FETCH_PRE_POST_MARKET", "true").lower() in ("1", "true", "yes")

    # --- Update / refresh rates ------------------------------------------
    # How often the backend background loop re-fetches data and broadcasts
    # it over the websocket, in seconds.
    POLL_INTERVAL_SECONDS: float = _env_float("POLL_INTERVAL_SECONDS", 30.0)
    # How long fetched price history is kept in the cache before the data
    # provider is called again, in seconds.
    CACHE_TTL_SECONDS: int = _env_int("CACHE_TTL_SECONDS", 300)

    # --- Per-provider rate limits (max API calls per 60 seconds) ---------
    TWELVEDATA_RATE_LIMIT: int = _env_int("TWELVEDATA_RATE_LIMIT", 8)
    ALPHAVANTAGE_RATE_LIMIT: int = _env_int("ALPHAVANTAGE_RATE_LIMIT", 5)
    POLYGON_RATE_LIMIT: int = _env_int("POLYGON_RATE_LIMIT", 5)
    FINNHUB_RATE_LIMIT: int = _env_int("FINNHUB_RATE_LIMIT", 30)
    ALPACA_RATE_LIMIT: int = _env_int("ALPACA_RATE_LIMIT", 5)

    # --- Supabase Auth ---------------------------------------------------
    # From the Supabase project dashboard (Settings -> API).
    SUPABASE_URL: str = os.getenv("SUPABASE_URL", "")
    # JWT secret used to verify Supabase access tokens
    # (Settings -> API -> JWT Settings -> JWT Secret).
    SUPABASE_JWT_SECRET: str = os.getenv("SUPABASE_JWT_SECRET", "")
    # service_role key — secret, server-only; used by the Stripe webhook to
    # set a user's plan via the Supabase REST API.
    SUPABASE_SERVICE_KEY: str = os.getenv("SUPABASE_SERVICE_KEY", "")

    # --- Stripe billing --------------------------------------------------
    # Secret key (sk_test_... / sk_live_...) from the Stripe dashboard.
    STRIPE_SECRET_KEY: str = os.getenv("STRIPE_SECRET_KEY", "")
    # Webhook signing secret (whsec_...) — from `stripe listen` or the
    # dashboard's webhook endpoint settings.
    STRIPE_WEBHOOK_SECRET: str = os.getenv("STRIPE_WEBHOOK_SECRET", "")
    # Price ID (price_...) of the recurring Pro subscription price.
    STRIPE_PRICE_ID: str = os.getenv("STRIPE_PRICE_ID", "")
    # Frontend base URL for Stripe Checkout success/cancel redirects.
    FRONTEND_URL: str = os.getenv("FRONTEND_URL", "http://localhost:5173")

    # --- Alerts (Resend email) -------------------------------------------
    # API key from resend.com (re_...). If empty, alerts are logged, not sent.
    RESEND_API_KEY: str = os.getenv("RESEND_API_KEY", "")
    # From address. Use a verified domain in production; resend.dev for tests.
    ALERT_FROM_EMAIL: str = os.getenv(
        "ALERT_FROM_EMAIL", "RelativeQs <onboarding@resend.dev>"
    )

    # --- ETF universe / prediction engine ---------------------------------
    # Comma-separated tickers the engine fetches and scans. First-class config so the
    # engine can be restarted with a different setup. QQQ (the target) must be included.
    ETF_UNIVERSE: List[str] = [
        s.strip().upper() for s in os.getenv(
            "ETF_UNIVERSE",
            "QQQ,XLK,SMH,MAGS,IGV,XLY,XLF,XLI,IWM,XLE,XLP,TLT"
        ).split(",") if s.strip()
    ]
    # The index being predicted
    PREDICTION_TARGET: str = os.getenv("PREDICTION_TARGET", "QQQ").upper()
    # Cross-correlation scan range, in minutes (1m bars => 1 lag = 1 minute)
    LEAD_LAG_MAX_LAG: int = _env_int("LEAD_LAG_MAX_LAG", 15)
    # Minimum session bars before the engine emits a verdict (before that: "warming_up")
    LEAD_LAG_MIN_BARS: int = _env_int("LEAD_LAG_MIN_BARS", 45)
    # Correlation threshold for a symbol to qualify as leader/confirmer
    LEAD_LAG_CORR_THRESHOLD: float = _env_float("LEAD_LAG_CORR_THRESHOLD", 0.25)
    # Projection horizon in minutes
    PROJECTION_HORIZON_MINUTES: int = _env_int("PROJECTION_HORIZON_MINUTES", 15)
    # Never call the Yahoo download path more often than this (seconds) — rate-limit guard.
    YAHOO_MIN_FETCH_INTERVAL_SECONDS: float = _env_float("YAHOO_MIN_FETCH_INTERVAL_SECONDS", 60.0)
    # How many calendar days of intraday bars the history store retains.
    # 7 matches the Yahoo 1m-history cap so a backfill fills the whole window.
    HISTORY_RETENTION_DAYS: int = _env_int("HISTORY_RETENTION_DAYS", 7)

    # --- Recent-session backfill -----------------------------------------
    # Seed Redis from a data provider so the cross-day signals (stability,
    # hit-rate) work on day one instead of waiting for self-collected sessions.
    # Redis stays a short-term (~1 week) rolling cache cycled by TTL; the
    # provider is the source of truth, a call away when the cache is cold.
    HISTORY_BACKFILL_ENABLED: bool = os.getenv(
        "HISTORY_BACKFILL_ENABLED", "true").lower() in ("1", "true", "yes")
    # Where backfill bars come from: "provider" (use DATA_PROVIDER), "yahoo"
    # (force Yahoo), or "none" (disable). Yahoo caps 1m history at ~7 days.
    HISTORY_BACKFILL_SOURCE: str = os.getenv("HISTORY_BACKFILL_SOURCE", "provider").lower()
    # Calendar days of 1m history to pull when seeding a cold cache.
    HISTORY_BACKFILL_DAYS: int = _env_int("HISTORY_BACKFILL_DAYS", 7)
    # Only backfill when fewer than this many sessions are already cached.
    HISTORY_BACKFILL_MIN_SESSIONS: int = _env_int("HISTORY_BACKFILL_MIN_SESSIONS", 5)

    # --- Phase 2: driver attribution ---
    # The "engines under QQQ" to attribute its move to. Subset of ETF_UNIVERSE.
    DRIVER_SYMBOLS: List[str] = [
        s.strip().upper() for s in os.getenv("DRIVER_SYMBOLS", "SMH,IGV,MAGS").split(",") if s.strip()
    ]
    ATTRIBUTION_WINDOW: int = _env_int("ATTRIBUTION_WINDOW", 30)  # 1m bars

    # --- Phase 2: correlation regime ---
    CORR_REGIME_WINDOW: int = _env_int("CORR_REGIME_WINDOW", 30)
    CORR_COUPLED_THRESHOLD: float = _env_float("CORR_COUPLED_THRESHOLD", 0.6)
    CORR_FRAGMENTED_THRESHOLD: float = _env_float("CORR_FRAGMENTED_THRESHOLD", 0.3)

    # --- Phase 2: stability (cross-day) ---
    STABILITY_LOOKBACK_DAYS: int = _env_int("STABILITY_LOOKBACK_DAYS", 5)
    STABILITY_MIN_SESSIONS: int = _env_int("STABILITY_MIN_SESSIONS", 2)
    STABILITY_LAG_TOLERANCE: int = _env_int("STABILITY_LAG_TOLERANCE", 2)  # minutes
    STABILITY_TRADEABLE_PERSISTENCE: float = _env_float("STABILITY_TRADEABLE_PERSISTENCE", 0.6)

    # --- Phase 2: hit-rate ---
    HITRATE_MIN_SAMPLE: int = _env_int("HITRATE_MIN_SAMPLE", 30)
    # fixed horizons the dropdown can pick (minutes). Auto-horizon (= measured lead) is
    # always computed in addition to these.
    HITRATE_HORIZONS: List[int] = [
        int(x) for x in os.getenv("HITRATE_HORIZONS", "5,15,30").split(",") if x.strip()
    ]

    # --- Nasdaq-100 breadth (real constituent participation) ---
    # Measures how many of QQQ's ~100 underlying stocks are advancing, both
    # equal-weight (true breadth) and cap-weight (is the move real for the index).
    BREADTH_ENABLED: bool = os.getenv("BREADTH_ENABLED", "true").lower() in ("1", "true", "yes")
    BREADTH_TARGET: str = os.getenv("BREADTH_TARGET", "QQQ").upper()


settings = Settings()
