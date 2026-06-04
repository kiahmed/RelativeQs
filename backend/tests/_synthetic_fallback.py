"""Local fallback copy of the shared synthetic session generator.

Used ONLY when ``tests/synthetic.py`` (owned by the lead/lag agent) is not yet
present, so this agent's tests run in isolation. Mirrors design doc section 9.
"""
from typing import List

import numpy as np
import pandas as pd

DEFAULT_SYMBOLS = [
    "QQQ", "XLK", "SMH", "MAGS", "IGV", "XLY",
    "XLF", "XLI", "IWM", "XLE", "XLP", "TLT",
]

CONFIRMERS = ["XLY", "XLF"]


def make_synthetic_session(
    n_bars: int = 240,
    lead_symbol: str = "SMH",
    lead_minutes: int = 3,
    lead_strength: float = 0.9,
    drift_per_bar: float = 0.0002,
    seed: int = 42,
    symbols: List[str] = None,
    start: str = "2026-06-02 09:30",
) -> pd.DataFrame:
    """1m close DataFrame with a planted lead/lag relationship."""
    if symbols is None:
        symbols = list(DEFAULT_SYMBOLS)
    target = "QQQ"
    rng = np.random.default_rng(seed)
    idx = pd.date_range(start=start, periods=n_bars, freq="1min")

    noise = 0.0008
    returns = {s: rng.normal(0.0, noise, n_bars) for s in symbols}

    # leader: planted drift + noise
    returns[lead_symbol] = drift_per_bar + rng.normal(0.0, noise, n_bars)

    # target: lead_strength * leader returns shifted forward by lead_minutes
    lead_ret = returns[lead_symbol]
    shifted = np.zeros(n_bars)
    if lead_minutes > 0:
        shifted[lead_minutes:] = lead_ret[:-lead_minutes]
    else:
        shifted = lead_ret.copy()
    returns[target] = lead_strength * shifted + rng.normal(0.0, noise * 0.3, n_bars)

    # confirmers: coincident with the target
    for c in CONFIRMERS:
        if c in returns:
            returns[c] = 0.5 * returns[target] + rng.normal(0.0, noise, n_bars)

    closes = {}
    base = 100.0
    for s in symbols:
        prices = base * np.exp(np.cumsum(returns[s]))
        closes[s] = prices

    df = pd.DataFrame(closes, index=idx)
    df = df[[s for s in symbols]]
    return df
