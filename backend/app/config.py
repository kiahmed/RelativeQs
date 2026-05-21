import os
from typing import Optional

try:
    from dotenv import load_dotenv
    load_dotenv(verbose=True)
except Exception:
    pass


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


settings = Settings()
