"""Shared synthetic intraday session generator for the prediction engine tests.

Produces a 1m close-price DataFrame with a PLANTED lead/lag relationship:
the leader symbol's returns reappear in the target (QQQ) `lead_minutes` later,
scaled by `lead_strength`. Confirmers move coincidentally with the target; the
rest are independent noise. All tests are offline — no network, no real data.
"""
from typing import List

import numpy as np
import pandas as pd

DEFAULT_SYMBOLS = [
    "QQQ", "XLK", "SMH", "MAGS", "IGV",
    "XLY", "XLF", "XLI", "IWM", "XLE", "XLP", "TLT",
]

# symbols that move coincidentally with the target (planted confirmers)
CONFIRMER_SYMBOLS = ["XLY", "XLF"]

TARGET = "QQQ"


def make_synthetic_session(
    n_bars: int = 240,
    lead_symbol: str = "SMH",
    lead_minutes: int = 3,
    lead_strength: float = 0.9,      # how much of leader's return shows up in target
    drift_per_bar: float = 0.0002,   # planted upward drift on the leader
    seed: int = 42,
    symbols: List[str] = None,       # default: QQQ,XLK,SMH,MAGS,IGV,XLY,XLF,XLI,IWM,XLE,XLP,TLT
    start: str = "2026-06-02 09:30",
) -> pd.DataFrame:
    """Build a 1m close DataFrame (tz-naive DatetimeIndex, columns=symbols).

    - lead_symbol returns = drift + noise
    - target (QQQ) returns = lead_strength * lead_symbol returns shifted by
      lead_minutes + small noise
    - confirmers (XLY, XLF) = 0.5 * target coincident + noise
    - rest = independent noise
    """
    if symbols is None:
        symbols = list(DEFAULT_SYMBOLS)
    else:
        symbols = list(symbols)

    # guarantee target + leader are present so the planted relationship exists
    if TARGET not in symbols:
        symbols = [TARGET] + symbols
    if lead_symbol not in symbols:
        symbols = symbols + [lead_symbol]

    rng = np.random.default_rng(seed)
    idx = pd.date_range(start=start, periods=n_bars, freq="1min")

    noise = 0.0008  # base per-bar return noise

    # leader returns: planted drift + noise
    lead_ret = drift_per_bar + rng.normal(0.0, noise, n_bars)

    # target returns: leader's returns shifted forward by lead_minutes, scaled,
    # plus a little independent noise. target_ret[t] depends on lead_ret[t-lag].
    target_ret = np.zeros(n_bars)
    shifted = np.zeros(n_bars)
    if lead_minutes > 0:
        shifted[lead_minutes:] = lead_ret[:-lead_minutes]
    else:
        shifted = lead_ret.copy()
    target_ret = lead_strength * shifted + rng.normal(0.0, noise * 0.5, n_bars)

    returns = {}
    for sym in symbols:
        if sym == lead_symbol:
            returns[sym] = lead_ret
        elif sym == TARGET:
            returns[sym] = target_ret
        elif sym in CONFIRMER_SYMBOLS:
            # coincident with the target
            returns[sym] = 0.5 * target_ret + rng.normal(0.0, noise, n_bars)
        else:
            # independent noise
            returns[sym] = rng.normal(0.0, noise, n_bars)

    # integrate returns into a price series starting near 100
    data = {}
    for sym in symbols:
        base = 100.0 + rng.uniform(-5.0, 5.0)
        prices = base * np.exp(np.cumsum(returns[sym]))
        data[sym] = prices

    df = pd.DataFrame(data, index=idx)
    df.index.name = None
    return df
