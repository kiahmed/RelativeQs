"""
Probe: does Webull OpenAPI expose OPTION tick-by-tick prints WITH a buy/sell
(aggressor) side? That's the one field Tradier lacks and Tradytics needs.

Steps:
  1. auth
  2. snapshot a grid of SPY 0DTE strikes -> find symbols that return data
  3. get_option_tick on the most active -> dump RAW response keys + sample rows
     looking for a side / direction / bsFlag / tradeBsFlag field.
Reads creds from backend/.env (reuses webull_tick_test loader).
"""
from __future__ import annotations
import json, logging, sys, time
from pathlib import Path

logging.getLogger("webull").setLevel(logging.WARNING)

# today's 0DTE expiry (system date 2026-06-19, Fri) -- override via argv[1]
EXPIRY = sys.argv[1] if len(sys.argv) > 1 else "260619"
UNDERLYING = sys.argv[2] if len(sys.argv) > 2 else "SPY"
# wide strike grid; we don't know SPY spot exactly, so cast a net
STRIKES = list(range(560, 781, 5))


def load_creds() -> tuple[str, str]:
    envp = Path(__file__).resolve().parent / ".env"
    key = secret = None
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
        sys.exit("ERROR: webull creds not found in backend/.env")
    return key, secret


def osym(strike: int, cp: str) -> str:
    return f"{UNDERLYING}{EXPIRY}{cp}{int(strike*1000):08d}"


def as_json(r):
    if hasattr(r, "json") and callable(getattr(r, "json")):
        try:
            return r.json()
        except Exception:
            return getattr(r, "text", r)
    return r


def main():
    key, secret = load_creds()
    print(f"creds ***{key[-4:]} / ***{secret[-4:]}  expiry={EXPIRY} underlying={UNDERLYING}")

    from webull.core.client import ApiClient
    from webull.data.data_client import DataClient
    from webull.data.common.category import Category

    api = ApiClient(key, secret, "us")
    api.add_endpoint("us", "api.webull.com")
    dc = DataClient(api)
    md = dc.option_market_data
    cat = Category.US_OPTION.name
    print("AUTH OK\n")

    # 1. snapshot grid -> find live symbols (batch 20)
    syms = [osym(s, cp) for s in STRIKES for cp in ("C", "P")]
    live = []
    for i in range(0, len(syms), 20):
        batch = syms[i:i+20]
        try:
            r = as_json(md.get_option_snapshot(",".join(batch), cat))
        except Exception as e:
            print(f"  snapshot batch {i} ERR {type(e).__name__}: {str(e)[:160]}")
            time.sleep(0.4); continue
        rows = r if isinstance(r, list) else r.get("data") if isinstance(r, dict) else None
        if rows:
            for row in rows:
                sym = row.get("symbol") or row.get("instrumentId") or "?"
                vol = row.get("volume") or row.get("totalVolume") or 0
                live.append((sym, vol, row))
        time.sleep(0.4)

    if not live:
        print("NO live option snapshots returned. Try a different EXPIRY (argv1) / UNDERLYING (argv2).")
        # still dump one raw snapshot so we can see the shape
        try:
            print("raw snapshot sample:", json.dumps(as_json(md.get_option_snapshot(syms[0], cat)), default=str)[:600])
        except Exception as e:
            print("snapshot sample err:", e)
        return

    live.sort(key=lambda t: float(t[1] or 0), reverse=True)
    print(f"LIVE option symbols: {len(live)}; top by volume:")
    for sym, vol, _ in live[:6]:
        print(f"   {sym}  vol={vol}")
    print("  snapshot row keys:", list(live[0][2].keys()))

    # 2. option tick on the most active -> hunt for a side/aggressor field
    target = live[0][0]
    print(f"\n=== get_option_tick({target}, count=200) ===")
    try:
        r = as_json(md.get_option_tick(target, cat, count="200"))
    except Exception as e:
        print(f"tick ERR {type(e).__name__}: {str(e)[:200]}"); return
    rows = r if isinstance(r, list) else r.get("data") if isinstance(r, dict) else r
    if isinstance(rows, list) and rows:
        print(f"tick rows: {len(rows)}")
        print("tick row keys:", list(rows[0].keys()))
        side_keys = [k for k in rows[0].keys()
                     if any(t in k.lower() for t in ("side", "direction", "bs", "flag", "trade"))]
        print(">>> candidate side/aggressor keys:", side_keys or "NONE")
        for row in rows[:8]:
            print("   ", json.dumps(row, default=str)[:240])
    else:
        print("raw tick response:", json.dumps(r, default=str)[:800])


if __name__ == "__main__":
    main()
