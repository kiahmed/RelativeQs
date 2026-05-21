from .alphavantage import AlphaVantageAdapter
from .twelvedata import TwelveDataAdapter
try:
    from .polygon import PolygonAdapter  # type: ignore
except Exception:
    PolygonAdapter = None
try:
    from .alpaca import AlpacaAdapter  # type: ignore
except Exception:
    AlpacaAdapter = None
try:
    from .finnhub import FinnhubAdapter  # type: ignore
except Exception:
    FinnhubAdapter = None

__all__ = ["AlphaVantageAdapter", "TwelveDataAdapter", "PolygonAdapter", "AlpacaAdapter", "FinnhubAdapter"]
