import pytest

from app.services.adapters.alphavantage import AlphaVantageAdapter
from app.services.adapters.twelvedata import TwelveDataAdapter


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
