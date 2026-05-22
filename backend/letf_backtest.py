"""
Leveraged-ETF drawdown backtest.

Compares buy-and-hold of a leveraged ETF (TQQQ, SOXL, ...) against the same
ETF managed by a 200-day trend filter on QQQ: hold the leveraged ETF while
QQQ is above its 200-day SMA, sit in cash otherwise.

The metric that matters is MAX DRAWDOWN. Leveraged-ETF buy-and-hold suffers
catastrophic drawdowns (volatility decay + amplification); the trend filter
is a recognised way to limit them. No lookahead: the regime is decided on
the close of day t and applied to the return from t to t+1.

Usage (from the backend/ directory):
    python letf_backtest.py                 # TQQQ (3x Nasdaq-100)
    python letf_backtest.py --etf SOXL      # 3x semiconductors
"""

from __future__ import annotations

import argparse

import numpy as np
import pandas as pd

SMA_WINDOW = 200
TRADING_DAYS = 252


def download(etf: str) -> pd.DataFrame:
    import yfinance as yf

    print(f"Downloading full history for QQQ and {etf}...")
    raw = yf.download(
        ["QQQ", etf], period="max", interval="1d",
        auto_adjust=True, progress=False, threads=False,
    )
    if raw is None or raw.empty:
        raise SystemExit("No data returned from yfinance.")
    close = raw["Close"] if isinstance(raw.columns, pd.MultiIndex) else raw
    return close


def stats(daily: pd.Series, position: pd.Series | None = None) -> dict:
    daily = daily.fillna(0.0)
    eq = (1 + daily).cumprod()
    years = len(daily) / TRADING_DAYS
    cagr = eq.iloc[-1] ** (1 / years) - 1 if years > 0 and eq.iloc[-1] > 0 else float("nan")
    vol = daily.std() * np.sqrt(TRADING_DAYS)
    sharpe = (daily.mean() * TRADING_DAYS) / vol if vol else 0.0
    dd = eq / eq.cummax() - 1.0
    return {
        "total": eq.iloc[-1] - 1.0,
        "cagr": cagr,
        "sharpe": sharpe,
        "mdd": dd.min(),
        "mdd_date": dd.idxmin(),
        "exposure": float(position.mean()) if position is not None else 1.0,
    }


def pct(x: float) -> str:
    return f"{x * 100:+.1f}%" if x == x else "   n/a"  # x==x filters NaN


def main() -> None:
    ap = argparse.ArgumentParser(description="Leveraged-ETF drawdown backtest.")
    ap.add_argument("--etf", default="TQQQ", help="leveraged ETF ticker (default TQQQ)")
    args = ap.parse_args()
    etf = args.etf.upper()

    close = download(etf)
    qqq = close["QQQ"].dropna()
    letf = close[etf].dropna()

    # regime from QQQ's 200-day simple moving average
    sma = qqq.rolling(SMA_WINDOW).mean()
    above_trend = qqq > sma

    # evaluate over the leveraged ETF's life, where the SMA is also defined
    idx = letf.index.intersection(sma.dropna().index).sort_values()
    if len(idx) < TRADING_DAYS:
        raise SystemExit("Not enough overlapping history.")

    letf_ret = letf.reindex(idx).pct_change().fillna(0.0)
    in_trend = above_trend.reindex(idx).astype(float)        # 1 = hold, 0 = cash
    held = in_trend.shift(1).fillna(0.0)                     # decided t, earns t+1

    bh = stats(letf_ret)                                    # buy & hold
    ft = stats(held * letf_ret, held)                       # trend-filtered
    switches = int((in_trend.diff().abs() > 0).sum())

    # worst calendar year for buy-and-hold, vs the filter in that same year
    by_year_bh = letf_ret.groupby(letf_ret.index.year).apply(lambda s: (1 + s).prod() - 1)
    by_year_ft = (held * letf_ret).groupby(letf_ret.index.year).apply(
        lambda s: (1 + s).prod() - 1
    )
    worst_year = by_year_bh.idxmin()

    print()
    print("=" * 70)
    print(f"  {etf} — BUY & HOLD vs 200-DAY TREND FILTER")
    print(f"  {idx[0].date()} -> {idx[-1].date()}   ({len(idx) / TRADING_DAYS:.1f} years)")
    print("=" * 70)
    print(f"  {'':24}{'Buy & Hold':>16}{'Trend-Filtered':>18}")
    print("  " + "-" * 66)
    print(f"  {'Total return':24}{pct(bh['total']):>16}{pct(ft['total']):>18}")
    print(f"  {'CAGR':24}{pct(bh['cagr']):>16}{pct(ft['cagr']):>18}")
    print(f"  {'Sharpe ratio':24}{bh['sharpe']:>16.2f}{ft['sharpe']:>18.2f}")
    print(f"  {'Max drawdown':24}{pct(bh['mdd']):>16}{pct(ft['mdd']):>18}")
    print(f"  {'  trough date':24}{str(bh['mdd_date'].date()):>16}{str(ft['mdd_date'].date()):>18}")
    print(f"  {'Time in market':24}{'100%':>16}{ft['exposure'] * 100:>17.0f}%")
    print("  " + "-" * 66)
    print(f"  Worst year for buy & hold ({worst_year}):")
    print(f"  {'':24}{pct(by_year_bh[worst_year]):>16}{pct(by_year_ft[worst_year]):>18}")
    print(f"  Trend-filter switches (in/out) over the period: {switches}")
    print("=" * 70)

    dd_cut = bh["mdd"] - ft["mdd"]  # both negative; positive result = improvement
    print(f"  HEADLINE: the trend filter cut {etf}'s worst drawdown from "
          f"{pct(bh['mdd'])} to {pct(ft['mdd'])}")
    print(f"           — a {dd_cut * 100:.0f}-point reduction in peak loss.")
    print("  Note: a trailing signal. It limits sustained downtrends; it does")
    print("  not dodge fast crashes, and the switch count above is real whipsaw.")
    print("=" * 70)


if __name__ == "__main__":
    main()
