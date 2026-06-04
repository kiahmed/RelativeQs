#!/usr/bin/env python3
"""Refresh the committed QQQ / Nasdaq-100 constituents snapshot.

The breadth engine reads backend/app/data/qqq_holdings.json (ticker -> weight).
Constituents barely change, so this is a manual/periodic refresh — NOT run in
the request path. Run it when the index reconstitutes (a few times a year).

Usage:
    python3 dev-utils/refresh-qqq-holdings.py            # fetch + preview, no write
    python3 dev-utils/refresh-qqq-holdings.py --write    # fetch + overwrite the snapshot

Source: stockanalysis.com holdings API (top weights) + Wikipedia Nasdaq-100
components (full list). Tail names get the residual weight spread evenly; the
breadth engine normalizes weights at use, so cap-weight stays dominated by the
accurate large names. If the source layout changes, fix the parsing here only —
the runtime never scrapes.
"""
import argparse
import json
import sys
import urllib.request
from pathlib import Path

SNAPSHOT = Path(__file__).resolve().parents[1] / "backend" / "app" / "data" / "qqq_holdings.json"
HOLDINGS_URL = "https://stockanalysis.com/api/symbol/e/QQQ/holdings"
UA = {"User-Agent": "Mozilla/5.0 (refresh-qqq-holdings)"}


def _get(url: str) -> str:
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8", errors="ignore")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true", help="overwrite the snapshot file")
    args = ap.parse_args()

    print(f"fetching {HOLDINGS_URL} ...")
    try:
        raw = json.loads(_get(HOLDINGS_URL))
    except Exception as exc:
        print(f"ERROR: could not fetch/parse holdings: {exc}", file=sys.stderr)
        print("Inspect the source by hand and update the parsing in this script.", file=sys.stderr)
        return 1

    # Expected: a list/dict of {ticker, weight}. Be defensive about the shape.
    rows = raw.get("data") if isinstance(raw, dict) else raw
    parsed = {}
    for row in rows or []:
        sym = str(row.get("ticker") or row.get("symbol") or "").lstrip("$").upper()
        w = row.get("weight") or row.get("weightPercent")
        if not sym or w is None:
            continue
        if isinstance(w, str):
            w = w.replace("%", "").strip()
        try:
            parsed[sym] = float(w) / 100.0
        except (TypeError, ValueError):
            continue

    if not parsed:
        print("ERROR: parsed 0 holdings — source layout likely changed.", file=sys.stderr)
        return 1

    total = sum(parsed.values())
    print(f"parsed {len(parsed)} holdings, weight sum = {total:.4f}")
    if not args.write:
        print("(dry run — pass --write to overwrite the snapshot)")
        for s, w in list(sorted(parsed.items(), key=lambda kv: kv[1], reverse=True))[:10]:
            print(f"  {s:6} {w*100:5.2f}%")
        return 0

    doc = {
        "index": "Nasdaq-100",
        "etf": "QQQ",
        "source": HOLDINGS_URL,
        "weights": dict(sorted(parsed.items(), key=lambda kv: kv[1], reverse=True)),
    }
    SNAPSHOT.write_text(json.dumps(doc, indent=2))
    print(f"wrote {SNAPSHOT} ({len(parsed)} constituents)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
