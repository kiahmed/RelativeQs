"""
Webull OpenAPI connectivity + capability probe (market data).
Verifies auth and inspects what we can actually pull for QQQ/SMH/XLK:
  - get_snapshot  (basic auth/connectivity check)
  - get_tick      (recent tick-by-tick prints; count<=200)
  - get_history_bar at S5 / S15  (sub-minute OHLCV bars, incl. start/end range)

Reads creds from backend/.env robustly (handles 'KEY: value' or 'KEY=value').
Makes only a few well-formed calls (rate limit is generous; we stay <1/sec).
Run:  python webull_tick_test.py
"""
from __future__ import annotations
import json, logging, sys, time
from pathlib import Path

# quiet the SDK's per-5s token-polling chatter; keep warnings/errors
logging.getLogger("webull").setLevel(logging.WARNING)

SYMBOLS = ["QQQ", "SMH", "XLK"]


def load_creds() -> tuple[str, str]:
    candidates = [
        Path(__file__).resolve().parent / ".env",
        Path.cwd() / ".env",
        Path("/mnt/c/soljet_dev/RelativeQs/backend/.env"),
    ]
    envp = next((p for p in candidates if p.exists()), None)
    key = secret = None
    if envp is not None:
        print(f"reading creds from {envp}")
        for line in envp.read_text().splitlines():
            s = line.strip()
            if not s or s.startswith("#") or "webull" not in s.lower():
                continue
            sep = ":" if (":" in s and ("=" not in s or s.index(":") < s.index("="))) else "="
            name, _, val = s.partition(sep)
            name, val = name.strip().lower(), val.strip()
            if "key" in name:
                key = val
            elif "secret" in name:
                secret = val
    if not key or not secret:
        sys.exit("ERROR: WeBull_App_Key / WeBull_App_Secret not found in backend/.env")
    return key, secret


def show(label, r, n=2):
    """Print a compact view of a response (type, length, head/tail)."""
    if hasattr(r, "json") and callable(getattr(r, "json")):   # requests.Response
        try:
            r = r.json()
        except Exception:
            r = getattr(r, "text", r)
    try:
        js = json.loads(json.dumps(r, default=str))
    except Exception:
        js = r
    if isinstance(js, list):
        print(f"  {label}: list len={len(js)}")
        for rec in js[:n]:
            print("     head:", json.dumps(rec, default=str)[:300])
        if len(js) > n:
            print("     tail:", json.dumps(js[-1], default=str)[:300])
    elif isinstance(js, dict):
        print(f"  {label}: dict keys={list(js.keys())[:12]}")
        print("    ", json.dumps(js, default=str)[:500])
    else:
        print(f"  {label}: {type(js).__name__} -> {str(js)[:400]}")


def main():
    key, secret = load_creds()
    print(f"creds loaded: key=***{key[-4:]} secret=***{secret[-4:]}  (region=us)")

    from webull.core.client import ApiClient
    from webull.data.data_client import DataClient
    from webull.data.common.category import Category

    print("constructing DataClient (this makes a live /openapi/config auth call)...")
    api = ApiClient(key, secret, "us")
    api.add_endpoint("us", "api.webull.com")
    dc = DataClient(api)
    md = dc.market_data
    print("AUTH OK -- client constructed.\n")

    # ETFs: try US_ETF first, fall back to US_STOCK if the API rejects category.
    for cat_name in ("US_ETF", "US_STOCK"):
        cat = getattr(Category, cat_name).name
        print(f"========== category={cat_name} ==========")
        for sym in SYMBOLS:
            try:
                show(f"tick {sym} (count=200)", md.get_tick(sym, cat, count="200"), n=3)
                time.sleep(0.3)
            except Exception as e:
                print(f"  tick {sym} ERROR: {type(e).__name__}: {str(e)[:200]}")
        # baseline: M1 bars are supported (sub-minute S5/S15 are NOT, per server)
        try:
            show("history_bar QQQ M1 (count=5)", md.get_history_bar("QQQ", cat, "M1", count="5"))
        except Exception as e:
            print(f"  M1 bars QQQ ERROR: {type(e).__name__}: {str(e)[:200]}")
        print()
        break  # US_ETF works; loop is just a fallback aid


if __name__ == "__main__":
    main()
