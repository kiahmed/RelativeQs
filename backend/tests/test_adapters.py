import pytest

from app.services.adapters.alphavantage import AlphaVantageAdapter
from app.services.adapters.twelvedata import TwelveDataAdapter


@pytest.mark.asyncio
async def test_alphavantage_no_key():
    adapter = AlphaVantageAdapter(api_key=None)
    result = await adapter.fetch_history(["QQQ"])  # no key -> None
    assert result is None


@pytest.mark.asyncio
async def test_twelvedata_no_key():
    adapter = TwelveDataAdapter(api_key=None)
    result = await adapter.fetch_history(["QQQ"])  # no key -> None
    assert result is None
