"""
Trend-filter experiment.

The plain backtest showed the QQQ signal engine has no edge. This script tests
whether a *well-known* effect — the 200-day moving-average trend filter — does
better, and whether combining it with the engine score helps at all.

Strategies compared (all on the same date range, no costs, no lookahead):
    1. Buy & Hold QQQ
    2. Trend filter      : long when QQQ > its 200-day SMA, else cash
    3. Engine score      : long when raw_score > 0, else cash
    4. Trend + score     : long only when BOTH agree

Usage (from backend/):  python trend_experiment.py --years 12
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from backtest import download_history, replay_signals  # noqa: E402

TRADING_DAYS = 252


def stats(daily: pd.Series, position: pd.Series | None = None) -> dict:
    """Return performance stats for a daily-return series."""
    eq = (1 + daily).cumprod()
    years = len(daily) / TRADING_DAYS
    cagr = eq.iloc[-1] ** (1 / years) - 1 if years > 0 and eq.iloc[-1] > 0 else float("nan")
    vol = daily.std() * np.sqrt(TRADING_DAYS)
    sharpe = (daily.mean() * TRADING_DAYS) / vol if vol else 0.0
    mdd = (eq / eq.cummax() - 1).min()
    exposure = float(position.mean()) if position is not None else 1.0
    return {"total": eq.iloc[-1] - 1, "cagr": cagr, "sharpe": sharpe,
            "mdd": mdd, "exposure": exposure}


def pct(x: float) -> str:
    return f"{x * 100:+.2f}%" if not np.isnan(x) else "   n/a"


def main() -> None:
    ap = argparse.ArgumentParser(description="200-day trend-filter experiment.")
    ap.add_argument("--years", type=int, default=12, help="years of history (default 12)")
    ap.add_argument("--lookback", type=int, default=252,
                    help="engine trailing window (default 252)")
    args = ap.parse_args()

    close = download_history(args.years)
    qqq = close["QQQ"]

    # 200-day simple moving average trend filter
    sma200 = qqq.rolling(200).mean()
    above_trend = (qqq > sma200).astype(float)

    # engine score replayed day-by-day, no lookahead
    print(f"Replaying engine over {len(close) - args.lookback} days...")
    signals = replay_signals(close, args.lookback)
    score_pos = (signals["raw_score"] > 0).astype(float)

    # common evaluation window = where every strategy has a defined position
    idx = signals.index.intersection(sma200.dropna().index)
    qqq_ret = qqq.pct_change().reindex(idx).fillna(0.0)

    trend_pos = above_trend.reindex(idx).fillna(0.0)
    score_pos = score_pos.reindex(idx).fillna(0.0)
    combo_pos = ((trend_pos > 0) & (score_pos > 0)).astype(float)

    # position decided on day t earns day t+1 return -> shift(1)
    strategies = {
        "Buy & Hold QQQ": (qqq_ret, None),
        "Trend filter (200-SMA)": (trend_pos.shift(1).fillna(0.0) * qqq_ret,
                                   trend_pos.shift(1).fillna(0.0)),
        "Engine score (>0)": (score_pos.shift(1).fillna(0.0) * qqq_ret,
                              score_pos.shift(1).fillna(0.0)),
        "Trend + score": (combo_pos.shift(1).fillna(0.0) * qqq_ret,
                          combo_pos.shift(1).fillna(0.0)),
    }

    print("\n" + "=" * 78)
    print(f"  TREND-FILTER EXPERIMENT  —  {idx[0].date()} -> {idx[-1].date()}  "
          f"({len(idx)} days)")
    print("=" * 78)
    header = f"  {'Strategy':<26}{'Total':>11}{'CAGR':>10}{'Sharpe':>9}{'MaxDD':>11}{'InMkt':>8}"
    print(header)
    print("  " + "-" * 74)
    for name, (daily, pos) in strategies.items():
        s = stats(daily, pos)
        print(f"  {name:<26}{pct(s['total']):>11}{pct(s['cagr']):>10}"
              f"{s['sharpe']:>9.2f}{pct(s['mdd']):>11}{s['exposure'] * 100:>7.0f}%")
    print("=" * 78)
    print("  Look for: a strategy with a HIGHER Sharpe and SHALLOWER MaxDD than")
    print("  Buy & Hold. The trend filter usually trades some return for a much")
    print("  smaller drawdown. If 'Trend + score' is no better than 'Trend filter')")
    print("  alone, the engine score is adding nothing.")
    print("=" * 78)


if __name__ == "__main__":
    main()
