"""
Live self-tuning lead-persistence runner
=========================================

Takes the validated detector from `tick_lead_persistence.py` and runs it on a
LIVE quote feed during market hours (09:30-16:00 ET), across SEVERAL candidate
configs at once (different bar sizes + WATCH thresholds). It scores each config
against what QQQ actually did next, persists everything to SQLite, and promotes
the best-performing config -- i.e. it finds its own sweet spot as the session
runs. No history needed; it learns forward.

Why multiple bar sizes
----------------------
A bar can only reveal a lead LONGER than the bar itself (a 20s lead vanishes
inside a 30s bar). And the cross-correlation needs ~20 bars in its window to be
reliable. So the runner sweeps bar sizes live and lets the outcome scoring say
which one actually predicts QQQ next -- that is the "self-evaluating" part.

Data feed
---------
Pluggable `QuoteFeed`:
  * ReplayFeed  -- replays synthetic ticks fast; lets us prove the machine now,
                   market closed.
  * YahooQuoteFeed -- live last-price polling for tomorrow. NOTE: Yahoo quotes
                   are typically ~15min delayed and may update only every
                   ~30-60s; a UNIFORM delay does not hurt lead-lag (relative
                   timing is preserved) but slow updates make sub-20s bars
                   degenerate. The runner flags low-quality (too-few-sample)
                   bars so you can see this in the data. Webull's tick endpoint
                   slots in as a third feed once the app is approved.

This is a RESEARCH / WATCH signal, not a trade trigger.

Usage (from backend/):
    python live_lead_runner.py --feed replay --speed 60     # test now, 60x
    python live_lead_runner.py --feed yahoo                 # live tomorrow
    python live_lead_runner.py --report                     # print leaderboard
"""

from __future__ import annotations

import argparse
import sqlite3
import time
from datetime import datetime, timezone, time as dtime
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from tick_lead_persistence import (
    Tick, ticks_to_bars, detect_lead_per_step, lead_persistence,
    synth_ticks, LEADERS, TARGET,
)

ET = ZoneInfo("America/New_York")
DB_PATH = Path(__file__).resolve().parent / "lead_runner.db"

# US market holidays 2026 (NYSE full closures) -- skip these days.
HOLIDAYS_2026 = {
    "2026-01-01", "2026-01-19", "2026-02-16", "2026-04-03", "2026-05-25",
    "2026-06-19", "2026-07-03", "2026-09-07", "2026-11-26", "2026-12-25",
}


# --------------------------------------------------------------------------- #
# candidate configs (the self-tuning grid)                                    #
# --------------------------------------------------------------------------- #
class Config:
    """One detector configuration. `micro_bars` is held ~constant across bar
    sizes so configs are statistically comparable (the lesson from the sweep)."""
    def __init__(self, bar_seconds: int, watch_threshold: float,
                 micro_bars: int = 20, persist_bars: int = 30,
                 max_lag_bars: int = 4):
        self.bar_seconds = bar_seconds
        self.watch_threshold = watch_threshold
        self.micro_bars = micro_bars
        self.persist_bars = persist_bars
        self.max_lag_bars = max_lag_bars

    @property
    def key(self) -> str:
        return f"bar{self.bar_seconds}s_wt{self.watch_threshold:g}"

    @property
    def window_seconds(self) -> int:
        return self.bar_seconds * (self.micro_bars + self.persist_bars)


def default_grid() -> List[Config]:
    grid = []
    for bar in (5, 10, 20, 30):
        for wt in (0.10, 0.15, 0.20):
            grid.append(Config(bar, wt))
    return grid


def fast_grid() -> List[Config]:
    """Small single-bar grid with short windows -- for quick replay smoke tests
    (fast warmup, cheap detector). Not for production tuning."""
    return [Config(5, wt, micro_bars=8, persist_bars=10, max_lag_bars=3)
            for wt in (0.10, 0.15, 0.20)]


# --------------------------------------------------------------------------- #
# quote feeds                                                                 #
# --------------------------------------------------------------------------- #
class QuoteFeed:
    symbols = [TARGET] + LEADERS

    def poll(self) -> List[Tuple[str, pd.Timestamp, float]]:
        """Return a flat list of NEW trades since the last poll, each as
        (symbol, timestamp, price). May be many per symbol (full tape) or one."""
        raise NotImplementedError

    def now(self) -> datetime:
        return datetime.now(timezone.utc)


class ReplayFeed(QuoteFeed):
    """Replays a pre-generated synthetic tick stream driven by SIM TIME, not the
    wall clock: each poll() advances the sim cursor by a fixed step and drains
    the ticks in that interval. This makes replay deterministic and immune to how
    long the detector takes (no sim-time skipping), so the full pipeline
    (bars -> detect -> score -> DB) is exercised reliably and fast.

    Tick density is kept low on purpose -- the replay tests the MACHINE, not
    liquidity; lighter buffers keep each resample cheap."""
    def __init__(self, minutes: int, poll_seconds: float, seed: int,
                 lead_seconds: float = 20.0, lead_weight: float = 0.5):
        rng = np.random.default_rng(seed)
        self.ticks = synth_ticks(minutes, rng, lead_seconds=lead_seconds,
                                 regime=True, lead_weight=lead_weight, coupling=0.8,
                                 trade_rates={"QQQ": 6.0, "SMH": 4.0, "XLK": 3.0})
        self.step = pd.Timedelta(seconds=poll_seconds)
        self.cursor = self.ticks[0].ts
        self.end = self.ticks[-1].ts
        self.i = 0
        self.done = False

    def poll(self) -> List[Tuple[str, pd.Timestamp, float]]:
        self.cursor = self.cursor + self.step
        out: List[Tuple[str, pd.Timestamp, float]] = []
        while self.i < len(self.ticks) and self.ticks[self.i].ts <= self.cursor:
            t = self.ticks[self.i]
            out.append((t.symbol, t.ts, t.price))
            self.i += 1
        if self.cursor >= self.end:
            self.done = True
        return out

    def now(self) -> datetime:
        # pretend it is always a regular-hours weekday so the gate lets replay run
        return self.cursor.floor("s").to_pydatetime().replace(tzinfo=timezone.utc)


class YahooQuoteFeed(QuoteFeed):
    """Live last-price polling via yfinance. ~15min delayed, update cadence
    varies. NOTE: Yahoo gives at best 1-min granularity and may rate-limit;
    kept only as a fallback -- prefer WebullTickFeed."""
    def __init__(self):
        import yfinance as yf
        self._yf = yf
        self._tk = yf.Tickers(" ".join(self.symbols))

    def poll(self) -> List[Tuple[str, pd.Timestamp, float]]:
        out: List[Tuple[str, pd.Timestamp, float]] = []
        ts = pd.Timestamp(self.now())
        for sym in self.symbols:
            try:
                px = float(self._tk.tickers[sym].fast_info["last_price"])
                if np.isfinite(px) and px > 0:
                    out.append((sym, ts, px))
            except Exception:
                continue
        return out


def _load_webull_creds() -> Tuple[str, str]:
    """Read WeBull_App_Key / _Secret from backend/.env (handles 'KEY: v' or
    'KEY=v'). Searches worktree, cwd, then the main checkout."""
    cands = [Path(__file__).resolve().parent / ".env", Path.cwd() / ".env",
             Path("/mnt/c/soljet_dev/RelativeQs/backend/.env")]
    envp = next((p for p in cands if p.exists()), None)
    key = secret = None
    if envp is not None:
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
        raise RuntimeError("Webull creds (WeBull_App_Key/_Secret) not found in backend/.env")
    return key, secret


class WebullTickFeed(QuoteFeed):
    """Live tick polling via the Webull OpenAPI (paid market-data account).

    Each poll() calls get_tick(symbol, US_ETF, count) and returns the trades
    NEWER than the last one seen for that symbol (dedup by ms-epoch). Webull's
    bars endpoint floors at 1-minute, so sub-minute bars MUST be built from
    these ticks. Auth uses the cached token in backend/conf/token.txt (created
    via one-time Webull-app approval); construction makes a live /openapi/config
    call. Rate limit is generous (market data ~600/min); polling 3 symbols every
    1-2s is well under it."""
    def __init__(self, count: int = 200, category: str = "US_ETF"):
        from webull.core.client import ApiClient
        from webull.data.data_client import DataClient
        from webull.data.common.category import Category
        key, secret = _load_webull_creds()
        api = ApiClient(key, secret, "us")
        api.add_endpoint("us", "api.webull.com")
        self._md = DataClient(api).market_data        # live auth happens here
        self._cat = getattr(Category, category).name
        self._count = str(count)
        self._last_ms: Dict[str, int] = {s: 0 for s in self.symbols}

    def poll(self) -> List[Tuple[str, pd.Timestamp, float]]:
        out: List[Tuple[str, pd.Timestamp, float]] = []
        for sym in self.symbols:
            try:
                resp = self._md.get_tick(sym, self._cat, count=self._count)
                data = resp.json() if hasattr(resp, "json") else resp
                rows = data.get("result", []) if isinstance(data, dict) else []
            except Exception:
                continue
            last = self._last_ms.get(sym, 0)
            newest = last
            for r in rows:
                try:
                    ms = int(r["time"]); px = float(r["price"])
                except (KeyError, ValueError, TypeError):
                    continue
                if ms <= last:
                    continue                       # already seen
                out.append((sym, pd.Timestamp(ms, unit="ms", tz="UTC"), px))
                newest = max(newest, ms)
            self._last_ms[sym] = newest
        return out


# --------------------------------------------------------------------------- #
# market-hours gate                                                           #
# --------------------------------------------------------------------------- #
def market_open(now_utc: datetime) -> bool:
    et = now_utc.astimezone(ET)
    if et.weekday() >= 5:
        return False
    if et.strftime("%Y-%m-%d") in HOLIDAYS_2026:
        return False
    return dtime(9, 30) <= et.time() < dtime(16, 0)


# --------------------------------------------------------------------------- #
# database                                                                    #
# --------------------------------------------------------------------------- #
def db_connect() -> sqlite3.Connection:
    con = sqlite3.connect(DB_PATH)
    con.executescript("""
    CREATE TABLE IF NOT EXISTS runs (
        run_id     INTEGER PRIMARY KEY AUTOINCREMENT,
        started_at TEXT, feed TEXT, note TEXT);
    CREATE TABLE IF NOT EXISTS signals (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        run_id      INTEGER,
        ts          TEXT,
        config_key  TEXT,
        bar_seconds INTEGER,
        watch_thr   REAL,
        watch       INTEGER,
        score       REAL,
        density     REAL,
        run_freq    REAL,
        mean_corr0  REAL,
        leader      TEXT,
        lag_bars    INTEGER,
        leader_dir  INTEGER,
        qqq_price   REAL,
        bar_ticks   INTEGER,
        evaluated   INTEGER DEFAULT 0,
        fwd_return  REAL,
        hit         INTEGER);
    CREATE INDEX IF NOT EXISTS ix_sig_eval ON signals(evaluated, ts);
    CREATE INDEX IF NOT EXISTS ix_sig_cfg  ON signals(config_key);
    -- one row each time the rolling-window best config is (re)chosen, so the
    -- intraday drift of the sweet spot is queryable after the session.
    CREATE TABLE IF NOT EXISTS promotions (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        run_id      INTEGER,
        ts          TEXT,
        config_key  TEXT,
        prec_recent REAL,
        n_recent    INTEGER,
        window_min  INTEGER);
    """)
    con.commit()
    return con


def start_run(con: sqlite3.Connection, feed: str, note: str) -> int:
    cur = con.execute("INSERT INTO runs(started_at, feed, note) VALUES (?,?,?)",
                      (datetime.now(timezone.utc).isoformat(), feed, note))
    con.commit()
    return cur.lastrowid


# --------------------------------------------------------------------------- #
# detector wrapper                                                            #
# --------------------------------------------------------------------------- #
def compute_combined(buffer: List[Tick], bar_seconds: int, micro_bars: int,
                     persist_bars: int, max_lag_bars: int):
    """Build bars for ONE bar size, run per-step lead detection across both
    leaders, and return (close, combined_perstep, counts) -- shared by all
    WATCH thresholds for that bar size. Only completed bars are used (the last,
    still-forming bar is dropped). Compute is bounded to the trailing window."""
    close, counts = ticks_to_bars(buffer, bar_seconds)
    if close.empty or len(close) < 2:
        return None
    close, counts = close.iloc[:-1], counts.iloc[:-1]          # drop partial bar
    need = micro_bars + persist_bars
    if len(close) < need or TARGET not in close.columns:
        return None
    if not all(L in close.columns for L in LEADERS):
        return None
    # bound compute: only the trailing window matters for the latest read
    tail = need + max_lag_bars + 2
    close, counts = close.iloc[-tail:], counts.iloc[-tail:]

    per = []
    for L in LEADERS:
        per.append(detect_lead_per_step(
            close, L, micro_bars=micro_bars, max_lag_bars=max_lag_bars,
            corr_threshold=0.30, lead_margin=0.08))
    comb = per[0].copy()
    comb["leader"] = LEADERS[0]
    for L, ps in zip(LEADERS[1:], per[1:]):
        take = ps["lead"] > comb["lead"]
        comb.loc[take, "leader"] = L
        comb["lead"] = ((comb["lead"] + ps["lead"]) > 0).astype(int)
        comb["corr0"] = np.maximum(comb["corr0"], ps["corr0"])
    return close, comb, counts


def read_last(close, comb, counts, cfg: Config) -> dict:
    """Apply one WATCH threshold to a shared combined frame -> latest bar read."""
    pers = lead_persistence(comb, persist_bars=cfg.persist_bars,
                            corr_floor=0.28, corr_strong=0.55,
                            watch_threshold=cfg.watch_threshold)
    last = pers.iloc[-1]
    row = comb.iloc[-1]
    lead_sym = row["leader"]
    win = close[lead_sym].iloc[-cfg.micro_bars:]
    leader_dir = int(np.sign(win.iloc[-1] - win.iloc[0])) if len(win) >= 2 else 0
    return {
        "ts": close.index[-1],
        "watch": int(last["watch"]),
        "score": float(last["score"]),
        "density": float(last["density"]),
        "run_freq": float(last["run_freq"]),
        "mean_corr0": float(last["mean_corr0"]),
        "leader": str(lead_sym),
        "lag_bars": int(row["lag_bars"]),
        "leader_dir": leader_dir,
        "qqq_price": float(close[TARGET].iloc[-1]),
        "bar_ticks": int(counts[TARGET].iloc[-1]) if TARGET in counts else 0,
    }


def record_signal(con, run_id, cfg: Config, r: dict):
    con.execute(
        """INSERT INTO signals(run_id, ts, config_key, bar_seconds, watch_thr,
           watch, score, density, run_freq, mean_corr0, leader, lag_bars,
           leader_dir, qqq_price, bar_ticks)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (run_id, r["ts"].isoformat(), cfg.key, cfg.bar_seconds,
         cfg.watch_threshold, r["watch"], r["score"], r["density"],
         r["run_freq"], r["mean_corr0"], r["leader"], r["lag_bars"],
         r["leader_dir"], r["qqq_price"], r["bar_ticks"]))


# --------------------------------------------------------------------------- #
# outcome scoring (the self-evaluation)                                       #
# --------------------------------------------------------------------------- #
def score_outcomes(con, run_id, qqq_series: pd.Series, horizon_s: int,
                   eps: float = 0.0003):
    """For EVERY bar old enough to evaluate (watch or not), label hit = QQQ
    continued in the predicted direction over `horizon_s`. Scoring all bars (not
    only WATCH ones) yields the BASELINE: how often QQQ follows the leader anyway,
    so we can tell whether the WATCH gate adds anything."""
    rows = con.execute(
        """SELECT id, ts, leader_dir, qqq_price FROM signals
           WHERE run_id=? AND evaluated=0""", (run_id,)).fetchall()
    if qqq_series.empty:
        return
    last_ts = qqq_series.index[-1]
    for sid, ts_s, ldir, px0 in rows:
        ts = pd.Timestamp(ts_s)
        target_ts = ts + pd.Timedelta(seconds=horizon_s)
        if last_ts < target_ts:
            continue  # horizon not elapsed yet
        fut = qqq_series[qqq_series.index >= target_ts]
        if fut.empty or not px0:
            continue
        fwd = float(fut.iloc[0] / px0 - 1.0)
        hit = int(np.sign(fwd) == ldir and abs(fwd) > eps) if ldir != 0 else 0
        con.execute("UPDATE signals SET evaluated=1, fwd_return=?, hit=? WHERE id=?",
                    (fwd, hit, sid))
    con.commit()


def leaderboard(con, run_id=None, since: Optional[pd.Timestamp] = None,
                min_n: int = 1) -> pd.DataFrame:
    """Config performance from evaluated WATCH signals. `since` restricts to a
    recent rolling window (the recency-weighting that lets the runner keep
    re-adjusting intraday instead of anchoring on the whole session)."""
    where = "WHERE evaluated=1"
    params: list = []
    if run_id is not None:
        where += " AND run_id=?"
        params.append(run_id)
    if since is not None:
        where += " AND ts >= ?"
        params.append(since.isoformat())
    # n / precision / edge are WATCH-only (via CASE); baseline is over ALL bars.
    df = pd.read_sql_query(
        f"""SELECT config_key, bar_seconds, watch_thr,
                   SUM(watch) AS n,
                   AVG(CASE WHEN watch=1 THEN hit END) AS precision,
                   AVG(hit) AS baseline,
                   AVG(CASE WHEN watch=1 THEN fwd_return*leader_dir END) AS mean_edge
            FROM signals {where}
            GROUP BY config_key
            HAVING n >= {int(min_n)}
            ORDER BY (precision - baseline) DESC, n DESC""",
        con, params=tuple(params))
    return df


# --------------------------------------------------------------------------- #
# main loop                                                                   #
# --------------------------------------------------------------------------- #
def run_live(feed: QuoteFeed, *, feed_name: str, horizon_s: int,
             poll_seconds: float, buffer_minutes: int, note: str = "",
             grid: Optional[List[Config]] = None, learn_window_min: int = 20,
             min_n: int = 8):
    con = db_connect()
    run_id = start_run(con, feed_name, note)
    grid = grid if grid is not None else default_grid()
    by_bar: Dict[int, List[Config]] = {}
    for cfg in grid:
        by_bar.setdefault(cfg.bar_seconds, []).append(cfg)
    bar_params = {b: (cfgs[0].micro_bars, cfgs[0].persist_bars, cfgs[0].max_lag_bars)
                  for b, cfgs in by_bar.items()}

    buffer: List[Tick] = []
    qqq_hist: List[Tuple[pd.Timestamp, float]] = []
    last_bar_seen: Dict[int, pd.Timestamp] = {}
    last_eval_ts: Optional[pd.Timestamp] = None
    prev_gap: Dict[str, float] = {}   # last gap per config -> trend arrow
    is_replay = isinstance(feed, ReplayFeed)
    print(f"[run {run_id}] feed={feed_name} bar_sizes={sorted(by_bar)} "
          f"configs={len(grid)} horizon={horizon_s}s db={DB_PATH.name}")

    while True:
        now = feed.now()
        if not is_replay and not market_open(now):
            print(f"[{now.astimezone(ET):%H:%M ET}] market closed -- waiting")
            time.sleep(30)
            continue

        ticks = feed.poll()
        ts_now = pd.Timestamp(now)
        for sym, ts, px in ticks:
            buffer.append(Tick(symbol=sym, ts=ts, price=px, volume=0, side=0))
            if sym == TARGET:
                qqq_hist.append((ts, px))

        cutoff = ts_now - pd.Timedelta(minutes=buffer_minutes)
        buffer = [t for t in buffer if t.ts >= cutoff]
        qqq_hist = [(t, p) for (t, p) in qqq_hist if t >= cutoff]

        # only run a bar size's detector when its current bar boundary advances
        for bar_seconds, cfgs in by_bar.items():
            boundary = ts_now.floor(f"{bar_seconds}s")
            if last_bar_seen.get(bar_seconds) == boundary:
                continue
            mb, pb, ml = bar_params[bar_seconds]
            res = compute_combined(buffer, bar_seconds, mb, pb, ml)
            if res is None:
                continue
            close, comb, counts = res
            if last_bar_seen.get(bar_seconds) == close.index[-1]:
                continue                      # no genuinely new completed bar
            last_bar_seen[bar_seconds] = boundary
            for cfg in cfgs:
                record_signal(con, run_id, cfg, read_last(close, comb, counts, cfg))
        con.commit()

        # periodically score outcomes + RE-PROMOTE the best config from the
        # recent rolling window (continuous intraday re-tuning), logging drift.
        if last_eval_ts is None or (ts_now - last_eval_ts).total_seconds() >= 60:
            qs = pd.Series(dict(qqq_hist)).sort_index()
            score_outcomes(con, run_id, qs, horizon_s)
            since = ts_now - pd.Timedelta(minutes=learn_window_min)
            roll = leaderboard(con, run_id, since=since, min_n=min_n)
            if roll.empty:                       # not enough recent data yet
                roll = leaderboard(con, run_id, since=since, min_n=1)
            if not roll.empty:
                best = roll.iloc[0]
                con.execute(
                    """INSERT INTO promotions(run_id, ts, config_key, prec_recent,
                       n_recent, window_min) VALUES (?,?,?,?,?,?)""",
                    (run_id, ts_now.isoformat(), best["config_key"],
                     float(best["precision"]), int(best["n"]), learn_window_min))
                con.commit()
                # latest read of the active config: who's leading, lead time, corr
                lr = con.execute(
                    """SELECT leader, lag_bars, bar_seconds, mean_corr0 FROM signals
                       WHERE run_id=? AND config_key=? ORDER BY ts DESC LIMIT 1""",
                    (run_id, best["config_key"])).fetchone()
                if lr and lr[1] and lr[1] >= 1:
                    lead_str = f"{lr[0]}→{TARGET} ~{int(lr[1]*lr[2])}s | corr {lr[3]*100:.0f}%"
                else:
                    lead_str = "no current lead"
                key = best["config_key"]
                prec, base = best["precision"], best["baseline"]
                prec_s = f"{prec*100:.0f}%" if prec == prec else "—"
                base_s = f"{base*100:.0f}%" if base == base else "—"
                if prec == prec and base == base:
                    gap_val = (prec - base) * 100
                    pv = prev_gap.get(key)          # this config's previous gap
                    if pv is None:                  arrow = "■"               # new
                    elif gap_val > pv + 1.0:        arrow = "\033[32m▲\033[0m"  # widening
                    elif gap_val < pv - 1.0:        arrow = "\033[31m▼\033[0m"  # shrinking
                    else:                           arrow = "■"               # flat
                    prev_gap[key] = gap_val
                    gap = f"{gap_val:+.0f}pts {arrow}"
                else:
                    gap = "—"
                print(f"[{ts_now:%H:%M:%S}] ACTIVE {best['config_key']} | {lead_str} | "
                      f"hit {prec_s} vs base {base_s} ({gap}) n={int(best['n'])} | "
                      f"edge {best['mean_edge']*1e4:+.1f}bp")
            last_eval_ts = ts_now

        if is_replay and feed.done:
            print(f"[run {run_id}] replay exhausted")
            break
        if not is_replay:
            time.sleep(poll_seconds)

    # final report: cumulative leaderboard + how the active config drifted
    qs = pd.Series({t: p for t, p in qqq_hist}).sort_index()
    score_outcomes(con, run_id, qs, horizon_s)
    print("\n=== cumulative leaderboard (this run) ===")
    print(leaderboard(con, run_id).to_string(index=False))
    drift = pd.read_sql_query(
        """SELECT ts, config_key, prec_recent, n_recent FROM promotions
           WHERE run_id=? ORDER BY ts""", con, params=(run_id,))
    if not drift.empty:
        changes = drift[drift["config_key"].ne(drift["config_key"].shift())]
        print(f"\n=== active-config drift ({len(drift)} checks, "
              f"{len(changes)} switches) ===")
        print(changes.to_string(index=False))
    con.close()


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--feed", choices=["replay", "webull", "yahoo"], default="replay")
    p.add_argument("--minutes", type=int, default=60, help="replay session length")
    p.add_argument("--seed", type=int, default=7)
    p.add_argument("--horizon-s", type=int, default=60, dest="horizon_s",
                   help="forward window over which a WATCH is graded")
    p.add_argument("--poll-seconds", type=float, default=2.0, dest="poll_seconds")
    p.add_argument("--buffer-minutes", type=int, default=30, dest="buffer_minutes")
    p.add_argument("--learn-window-min", type=int, default=20, dest="learn_window_min",
                   help="rolling window the active config is promoted from (recency)")
    p.add_argument("--report", action="store_true", help="print all-run leaderboard and exit")
    p.add_argument("--fast", action="store_true", help="small single-bar grid for quick replay smoke test")
    p.add_argument("--target", default=None,
                   help="prediction target symbol (default QQQ)")
    p.add_argument("--leaders", default=None,
                   help="comma-separated candidate leaders, e.g. XLK,SMH,IGV,XLY (default SMH,XLK). "
                        "Live (webull/yahoo) only; the replay simulator is fixed to QQQ/SMH/XLK.")
    args = p.parse_args()

    # CLI override of the hardcoded target/leaders -> propagate to BOTH modules
    # (detector globals live in tick_lead_persistence; feed/runner globals here).
    if args.target or args.leaders:
        import tick_lead_persistence as tlp
        tgt = (args.target or TARGET).upper()
        lds = ([x.strip().upper() for x in args.leaders.split(",") if x.strip()]
               if args.leaders else list(LEADERS))
        globals()["TARGET"], globals()["LEADERS"] = tgt, lds
        tlp.TARGET, tlp.LEADERS = tgt, lds
        QuoteFeed.symbols = [tgt] + lds
        print(f"tracking target={tgt} leaders={lds}")

    if args.report:
        con = db_connect()
        print("=== leaderboard (all runs) ===")
        lb = leaderboard(con)
        print(lb.to_string(index=False) if not lb.empty else "no evaluated signals yet")
        con.close()
        return

    grid = fast_grid() if args.fast else None
    if args.feed == "replay":
        feed = ReplayFeed(args.minutes, args.poll_seconds, args.seed)
        run_live(feed, feed_name="replay", horizon_s=args.horizon_s,
                 poll_seconds=0.0, buffer_minutes=args.buffer_minutes,
                 note=f"replay {args.minutes}m seed{args.seed}", grid=grid,
                 learn_window_min=args.learn_window_min)
    elif args.feed == "webull":
        feed = WebullTickFeed()
        print("Webull live tick feed -- gated to 09:30-16:00 ET. Ctrl-C to stop.")
        run_live(feed, feed_name="webull", horizon_s=args.horizon_s,
                 poll_seconds=args.poll_seconds, buffer_minutes=args.buffer_minutes,
                 note="live webull get_tick", grid=grid,
                 learn_window_min=args.learn_window_min)
    else:
        feed = YahooQuoteFeed()
        run_live(feed, feed_name="yahoo", horizon_s=args.horizon_s,
                 poll_seconds=args.poll_seconds, buffer_minutes=args.buffer_minutes,
                 note="live yahoo", grid=grid,
                 learn_window_min=args.learn_window_min)


if __name__ == "__main__":
    main()
