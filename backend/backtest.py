"""
Backtest harness for the QQQ signal engine.

Replays the *real* `QQQScoreEngine` over historical daily data, one day at a
time, with no lookahead — at each day the engine only sees prices up to and
including that day. It then measures whether the engine's `raw_score` and
`fragility` outputs actually preceded QQQ moves.

Usage (run from the backend/ directory):
    python backtest.py                       # 6 years, 20-day horizon
    python backtest.py --years 8 --horizon 10
    python backtest.py --csv results.csv     # also dump per-day signals

This is a research tool: it uses yfinance for historical data, which is fine
for internal analysis. It does NOT prove the signals work in the future — it
tells you whether they had any edge in the sample tested.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

# make `app` importable regardless of where the script is invoked from
sys.path.insert(0, str(Path(__file__).resolve().parent))
from app.core.qqq_score import QQQScoreEngine  # noqa: E402

SYMBOLS = ["QQQ", "XLK", "SMH", "XLY", "XLF", "XLI", "IWM", "XLE"]
TRADING_DAYS = 252


# --------------------------------------------------------------------------
# data
# --------------------------------------------------------------------------
def download_history(years: int) -> pd.DataFrame:
    """Download adjusted daily closes for all engine symbols."""
    import yfinance as yf

    print(f"Downloading {years}y of daily data for {len(SYMBOLS)} symbols...")
    raw = yf.download(
        SYMBOLS, period=f"{years}y", interval="1d",
        auto_adjust=True, progress=False, threads=False,
    )
    if raw is None or raw.empty:
        raise SystemExit("No data returned from yfinance — check your connection.")
    close = raw["Close"] if isinstance(raw.columns, pd.MultiIndex) else raw
    close = close[SYMBOLS].dropna()
    print(f"Got {len(close)} aligned trading days: "
          f"{close.index[0].date()} -> {close.index[-1].date()}\n")
    return close


# --------------------------------------------------------------------------
# signal replay (no lookahead)
# --------------------------------------------------------------------------
def replay_signals(close: pd.DataFrame, lookback: int) -> pd.DataFrame:
    """Run the engine day-by-day; each day sees only a trailing `lookback` window."""
    engine = QQQScoreEngine()
    idx = close.index
    rows = []
    for i in range(lookback, len(close)):
        window = close.iloc[i - lookback + 1: i + 1]   # data up to & including day i
        res = engine.compute(window)
        rows.append({
            "date": idx[i],
            "raw_score": float(res.get("raw_score", 0.0) or 0.0),
            "fragility": float(res.get("fragility", 0.0) or 0.0),
            "direction": res.get("direction", "n/a"),
        })
    return pd.DataFrame(rows).set_index("date")


# --------------------------------------------------------------------------
# forward outcomes
# --------------------------------------------------------------------------
def add_forward_outcomes(signals: pd.DataFrame, qqq: pd.Series, horizon: int) -> pd.DataFrame:
    """Attach forward QQQ return and forward max-drawdown over `horizon` days."""
    df = signals.copy()
    qqq = qqq.reindex(df.index.union(qqq.index)).sort_index()

    fwd_ret, fwd_dd = [], []
    for d in df.index:
        loc = qqq.index.get_loc(d)
        future = qqq.iloc[loc: loc + horizon + 1]
        if len(future) < horizon + 1:
            fwd_ret.append(np.nan)
            fwd_dd.append(np.nan)
            continue
        path = future.values / future.values[0] - 1.0
        fwd_ret.append(path[-1])           # return at end of horizon
        fwd_dd.append(path[1:].min())      # worst point reached during horizon
    df["fwd_return"] = fwd_ret
    df["fwd_drawdown"] = fwd_dd
    return df.dropna(subset=["fwd_return"])


# --------------------------------------------------------------------------
# metrics
# --------------------------------------------------------------------------
def pct(x: float) -> str:
    return f"{x * 100:+.2f}%"


def evaluate(df: pd.DataFrame, qqq: pd.Series, horizon: int) -> None:
    n = len(df)
    base_rate = float((df["fwd_return"] > 0).mean())

    print("=" * 66)
    print(f"  BACKTEST REPORT  —  {n} observations, {horizon}-day forward horizon")
    print(f"  {df.index[0].date()} -> {df.index[-1].date()}")
    print("=" * 66)

    # --- 1. raw_score vs forward return -----------------------------------
    pearson = df["raw_score"].corr(df["fwd_return"])
    spearman = df["raw_score"].corr(df["fwd_return"], method="spearman")
    print("\n[1] raw_score  vs  forward return")
    print(f"    Pearson correlation : {pearson:+.3f}")
    print(f"    Spearman correlation: {spearman:+.3f}")
    print("    (>0 means a higher score preceded higher returns; "
          "|r|>0.1 is notable for daily data)")

    # --- 2. quintile analysis ---------------------------------------------
    print("\n[2] Forward return by raw_score quintile (Q1=lowest score)")
    try:
        df["_q"] = pd.qcut(df["raw_score"].rank(method="first"), 5,
                           labels=["Q1", "Q2", "Q3", "Q4", "Q5"])
        table = df.groupby("_q", observed=True)["fwd_return"].agg(["mean", "count"])
        for q, row in table.iterrows():
            print(f"    {q}:  mean fwd return {pct(row['mean']):>9}   (n={int(row['count'])})")
        spread = table["mean"].iloc[-1] - table["mean"].iloc[0]
        print(f"    Q5 - Q1 spread: {pct(spread)}  "
              f"({'monotonic edge' if table['mean'].is_monotonic_increasing else 'NOT monotonic'})")
    except ValueError:
        print("    (not enough distinct values to quintile)")

    # --- 3. direction hit rate --------------------------------------------
    bull = df[df["direction"] == "bullish"]
    bear = df[df["direction"] == "bearish"]
    print("\n[3] Direction hit rate (forward return > 0)")
    print(f"    Base rate (any day)      : {base_rate * 100:.1f}%")
    if len(bull):
        print(f"    After 'bullish' signal   : {(bull['fwd_return'] > 0).mean() * 100:.1f}%  "
              f"(n={len(bull)})")
    if len(bear):
        print(f"    After 'bearish' signal   : {(bear['fwd_return'] > 0).mean() * 100:.1f}%  "
              f"(n={len(bear)})")
    print("    (a useful signal beats the base rate for bullish, "
          "trails it for bearish)")

    # --- 4. fragility check -----------------------------------------------
    print("\n[4] Fragility meter — does high fragility precede weakness?")
    if df["fragility"].nunique() > 2:
        hi = df[df["fragility"] >= df["fragility"].quantile(0.70)]
        lo = df[df["fragility"] <= df["fragility"].quantile(0.30)]
        print(f"    High-fragility days: mean fwd return {pct(hi['fwd_return'].mean()):>9}, "
              f"mean fwd drawdown {pct(hi['fwd_drawdown'].mean())}  (n={len(hi)})")
        print(f"    Low-fragility  days: mean fwd return {pct(lo['fwd_return'].mean()):>9}, "
              f"mean fwd drawdown {pct(lo['fwd_drawdown'].mean())}  (n={len(lo)})")
        print("    (signal works if high-fragility days show LOWER returns / DEEPER drawdowns)")
    else:
        print("    fragility was ~constant in this sample — not informative")

    # --- 5. strategy backtest ---------------------------------------------
    print("\n[5] Toy strategy: long QQQ when raw_score > 0, else cash (no costs)")
    qqq_ret = qqq.pct_change().reindex(df.index).fillna(0.0)
    # position decided on day t, earns the NEXT day's return -> shift(1)
    position = (df["raw_score"] > 0).astype(float)
    strat_ret = position.shift(1).fillna(0.0) * qqq_ret

    def stats(daily: pd.Series) -> dict:
        eq = (1 + daily).cumprod()
        years = len(daily) / TRADING_DAYS
        cagr = eq.iloc[-1] ** (1 / years) - 1 if years > 0 else 0.0
        vol = daily.std() * np.sqrt(TRADING_DAYS)
        sharpe = (daily.mean() * TRADING_DAYS) / vol if vol else 0.0
        mdd = (eq / eq.cummax() - 1).min()
        return {"total": eq.iloc[-1] - 1, "cagr": cagr, "sharpe": sharpe, "mdd": mdd,
                "exposure": None}

    s = stats(strat_ret)
    b = stats(qqq_ret)
    s["exposure"] = position.shift(1).fillna(0.0).mean()
    print(f"    {'':22}{'Strategy':>14}{'Buy & Hold QQQ':>18}")
    print(f"    {'Total return':22}{pct(s['total']):>14}{pct(b['total']):>18}")
    print(f"    {'CAGR':22}{pct(s['cagr']):>14}{pct(b['cagr']):>18}")
    print(f"    {'Sharpe ratio':22}{s['sharpe']:>14.2f}{b['sharpe']:>18.2f}")
    print(f"    {'Max drawdown':22}{pct(s['mdd']):>14}{pct(b['mdd']):>18}")
    print(f"    {'Time in market':22}{s['exposure'] * 100:>13.0f}%{'100%':>18}")

    print("\n" + "=" * 66)
    print("  How to read this:")
    print("  - A CONTINUOUS predictor needs [1] positive and [2] quintiles")
    print("    rising — 'higher score => higher forward return'.")
    print("  - A BINARY trend filter (long when score > 0) is judged by [5]:")
    print("    a Sharpe close to buy & hold but a SHALLOWER max drawdown,")
    print("    plus [3] bullish hit-rate above the base rate. Quintile/")
    print("    correlation tests can stay flat for a valid trend filter.")
    print("=" * 66)


# --------------------------------------------------------------------------
def main() -> None:
    ap = argparse.ArgumentParser(description="Backtest the QQQ signal engine.")
    ap.add_argument("--years", type=int, default=6, help="years of history (default 6)")
    ap.add_argument("--horizon", type=int, default=20,
                    help="forward return horizon in trading days (default 20)")
    ap.add_argument("--lookback", type=int, default=252,
                    help="trailing window the engine sees each day (default 252)")
    ap.add_argument("--csv", type=str, default=None,
                    help="optional path to dump per-day signals + outcomes")
    args = ap.parse_args()

    close = download_history(args.years)
    if len(close) <= args.lookback + args.horizon:
        raise SystemExit("Not enough history for the chosen lookback/horizon.")

    print(f"Replaying engine over {len(close) - args.lookback} days "
          f"(lookback={args.lookback})...")
    signals = replay_signals(close, args.lookback)
    df = add_forward_outcomes(signals, close["QQQ"], args.horizon)

    evaluate(df, close["QQQ"], args.horizon)

    if args.csv:
        out = df.drop(columns=[c for c in ["_q"] if c in df.columns])
        out.to_csv(args.csv)
        print(f"\nPer-day results written to {args.csv}")


if __name__ == "__main__":
    main()
