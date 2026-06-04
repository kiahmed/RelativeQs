#!/usr/bin/env python3
"""Pull the latest quotes for one or more tickers straight from Yahoo Finance.

Hits the same endpoint the backend's yahoo provider (yfinance) uses:
  https://query1.finance.yahoo.com/v8/finance/chart/{SYMBOL}

Pre/post market bars are included by default; pass --prepost false to fetch
regular-session bars only. Stdlib only — no yfinance/pandas needed.

usage:
  ./fetch-quotes.py QQQ XLK SMH
  ./fetch-quotes.py QQQ --prepost false
  ./fetch-quotes.py QQQ --range 5d --interval 5m
"""
import argparse
import json
import sys
import urllib.request
from datetime import datetime
from zoneinfo import ZoneInfo

API_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
ET = ZoneInfo("America/New_York")
# Yahoo rejects requests that don't look like they come from a browser
HEADERS = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"}


def str2bool(value: str) -> bool:
    if value.lower() in ("true", "1", "yes"):
        return True
    if value.lower() in ("false", "0", "no"):
        return False
    raise argparse.ArgumentTypeError(f"expected true/false, got {value!r}")


def session_label(dt_et: datetime) -> str:
    """Label a bar timestamp with the market session it falls in."""
    if dt_et.weekday() >= 5:
        return "weekend"
    minutes = dt_et.hour * 60 + dt_et.minute
    if 4 * 60 <= minutes < 9 * 60 + 30:
        return "pre-market"
    # 16:00 exactly is the closing print, still part of the regular session
    if 9 * 60 + 30 <= minutes <= 16 * 60:
        return "regular"
    if 16 * 60 < minutes < 20 * 60:
        return "after-hours"
    return "closed"


def fetch_chart(symbol: str, prepost: bool, range_: str, interval: str) -> dict:
    url = (
        API_URL.format(symbol=symbol)
        + f"?range={range_}&interval={interval}"
        + f"&includePrePost={'true' if prepost else 'false'}"
    )
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.load(resp)
    result = (data.get("chart", {}).get("result") or [None])[0]
    if not result:
        raise RuntimeError(f"no data: {data.get('chart', {}).get('error')}")
    return result


def last_bar(result: dict):
    """Return (timestamp, close) of the most recent bar that has a price."""
    timestamps = result.get("timestamp") or []
    quote = (result.get("indicators", {}).get("quote") or [{}])[0]
    closes = quote.get("close") or []
    for ts, close in zip(reversed(timestamps), reversed(closes)):
        if close is not None:
            return ts, close
    return None, None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("tickers", nargs="+", help="ticker symbols, e.g. QQQ XLK SMH")
    parser.add_argument(
        "--prepost", type=str2bool, default=True, metavar="true|false",
        help="include pre/post market bars (default: true)",
    )
    parser.add_argument("--range", default="1d", help="history range (default: 1d)")
    parser.add_argument("--interval", default="1m", help="bar interval (default: 1m)")
    args = parser.parse_args()

    print(f"prepost={args.prepost} range={args.range} interval={args.interval}\n")
    print(f"{'SYMBOL':<8} {'LAST BAR (ET)':<18} {'PRICE':>10}  {'SESSION':<12} {'REG CLOSE':>10}")

    failures = 0
    for symbol in args.tickers:
        symbol = symbol.upper()
        try:
            result = fetch_chart(symbol, args.prepost, args.range, args.interval)
        except Exception as exc:
            print(f"{symbol:<8} ERROR: {exc}", file=sys.stderr)
            failures += 1
            continue

        meta = result.get("meta", {})
        ts, close = last_bar(result)
        if ts is None:
            print(f"{symbol:<8} no bars returned")
            continue

        bar_dt = datetime.fromtimestamp(ts, tz=ET)
        regular_close = meta.get("regularMarketPrice")
        print(
            f"{symbol:<8} {bar_dt.strftime('%Y-%m-%d %H:%M'):<18} "
            f"{close:>10.2f}  {session_label(bar_dt):<12} "
            f"{regular_close if regular_close is not None else '-':>10}"
        )

    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
