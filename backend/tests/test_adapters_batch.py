import pytest

from app.config import settings
from app.services.adapters.alphavantage import AlphaVantageAdapter
from app.services.adapters.twelvedata import TwelveDataAdapter


@pytest.fixture(autouse=True)
def no_env_keys(monkeypatch):
    # The adapters fall back to settings.* keys loaded from .env; clear them so
    # these "no key" tests stay offline regardless of the local environment.
    monkeypatch.setattr(settings, "ALPHAVANTAGE_KEY", None)
    monkeypatch.setattr(settings, "TWELVEDATA_KEY", None)


@pytest.mark.asyncio
async def test_alphavantage_no_key_returns_none():
    adapter = AlphaVantageAdapter(api_key=None)
    res = await adapter.fetch_history(["AAPL", "MSFT"])
    assert res is None


@pytest.mark.asyncio
async def test_twelvedata_no_key_returns_none():
    adapter = TwelveDataAdapter(api_key=None)
    res = await adapter.fetch_history(["AAPL", "MSFT"]) 
    assert res is None
