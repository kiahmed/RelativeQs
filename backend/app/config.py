import os
from pathlib import Path
from typing import Optional

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
        "ALERT_FROM_EMAIL", "Price Flow Tracker <onboarding@resend.dev>"
    )


settings = Settings()
