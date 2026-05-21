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
