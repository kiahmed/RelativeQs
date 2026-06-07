"""
Tick-level lead-persistence prototype  (synthetic data, no live feed yet)
=========================================================================

Goal
----
Test the hypothesis: at a fine (3-5 second) granularity, does a leader like
SMH / XLK *momentarily* lead QQQ, and -- more importantly -- can we measure the
**frequency / persistence** of those tiny lead-streaks inside a rolling window
and use it as a forward "watch QQQ next" signal?

Why this shape
--------------
A single 3-second lead is mostly microstructure noise (bid/ask bounce, the fact
that SMH/XLK print less often than QQQ). It is NOT predictive on its own. But a
*regime* in which that lead keeps re-appearing across ~a minute -- many short
streaks, breaks, more streaks, with strong contemporaneous correlation -- is a
real, persistent state, and a regime that lasts ~a minute is the only thing even
theoretically actionable (a single 3s lead is gone by the time you detect it).

So we measure on TWO timescales:
  * micro window  (~60s): per-step lead read. The lead is detected as an
                          ASYMMETRY in the cross-correlation (corr at +lag >
                          corr at -lag and > lag-0), NOT just a positive-lag
                          peak -- that's what separates a real lead from mere
                          co-movement.
  * persist window (~90s): density + run-frequency of those reads, gated by
                          contemporaneous correlation -> the WATCH score.

KEY VALIDATED FINDING (synthetic ground-truth sweep, see git history)
---------------------------------------------------------------------
A 3-second lead CANNOT be read off 2-3 bars -- at that scale it is
indistinguishable from microstructure noise AND from plain co-movement. You
need ~20 bars (~60s) of cross-correlation for the lead-asymmetry to clear
estimation noise. With a 60s micro window the detector cleanly separates:
    real lead regime  -> WATCH ~15% of bars
    pure noise        -> WATCH  ~0%
    co-move, NO lead  -> WATCH  ~1-2%   (proves it tracks LEAD, not correlation)
At 30s windows the co-move/no-lead case leaks badly (~15%); at 120s the real
signal over-smooths away. So the actionable unit is a lead REGIME sustained
~a minute -- a single flickering 3s streak is not a reliable signal.

Data schema mirrors Webull's tick endpoint (trade time / price / volume / side)
so real ticks drop in later with no change to the analysis code.

This is a RESEARCH / WATCH signal, not a trade trigger. History cannot prove
live tradability (latency + spread/fees can eat the edge).

Usage (from backend/):
    python tick_lead_persistence.py                 # run both validation scenarios
    python tick_lead_persistence.py --bar 3 --minutes 10
    python tick_lead_persistence.py --scenario noise
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

# ---- knobs that map to real-world expectations ---------------------------- #
# rough consolidated-tape trade rates (prints/sec) during regular hours.
# divide by ~10-30x if a feed only carries a partial (e.g. IEX-like) subset.
DEFAULT_TRADE_RATES = {"QQQ": 80.0, "SMH": 25.0, "XLK": 15.0}
LEADERS = ["SMH", "XLK"]
TARGET = "QQQ"


# --------------------------------------------------------------------------- #
# 1. tick schema  (mirrors Webull /quote tick: time, price, volume, side)     #
# --------------------------------------------------------------------------- #
@dataclass
class Tick:
    symbol: str
    ts: pd.Timestamp     # trade time
    price: float
    volume: int
    side: int            # +1 buy / -1 sell (Webull 'direction'); unused for now


def ticks_to_bars(ticks: List[Tick], bar_seconds: int):
    """Resample a tick list into N-second OHLC-close bars, one column per symbol.

    Returns (close, tick_counts): close prices and per-bar trade counts, both
    DataFrames indexed by bar timestamp with one column per symbol.

    Real ticks from the Webull endpoint slot in here unchanged -- the only
    contract is the Tick fields above.
    """
    if not ticks:
        return pd.DataFrame(), pd.DataFrame()
    df = pd.DataFrame(
        {"symbol": [t.symbol for t in ticks],
         "ts": [t.ts for t in ticks],
         "price": [t.price for t in ticks]}
    ).set_index("ts").sort_index()

    rule = f"{bar_seconds}s"
    closes: Dict[str, pd.Series] = {}
    counts: Dict[str, pd.Series] = {}
    for sym, g in df.groupby("symbol"):
        bars = g["price"].resample(rule)
        closes[sym] = bars.last()
        counts[sym] = bars.count()
    close = pd.DataFrame(closes).sort_index().ffill()
    tick_counts = pd.DataFrame(counts).reindex(close.index)
    return close, tick_counts


# --------------------------------------------------------------------------- #
# 2. synthetic tick generator with an intermittent lead regime                #
# --------------------------------------------------------------------------- #
def synth_ticks(
    minutes: int,
    rng: np.random.Generator,
    *,
    lead_seconds: float,
    regime: bool,
    regime_on_frac: float = 0.5,
    regime_block_s: int = 20,
    coupling: float = 0.8,
    lead_weight: float = 0.4,
    noise: float = 1.0,
    trade_rates: Optional[Dict[str, float]] = None,
) -> List[Tick]:
    """Generate ticks on a 1-second latent grid, then sample Poisson trades.

    Realistic structure: during regime-ON blocks QQQ co-moves with the leader
    BOTH contemporaneously (shared driver) AND with a smaller lagged component
    `lead_seconds` behind -- i.e. the leader moves first and QQQ mostly catches
    up the same second but partly a few seconds later. `lead_weight` is the
    fraction of the coupled move that is lagged (the rest is contemporaneous).
    During regime-OFF blocks (and everywhere when regime=False) QQQ moves on its
    own noise -> no coupling, no lead. Gives a KNOWN ground truth to validate.
    """
    trade_rates = trade_rates or DEFAULT_TRADE_RATES
    n = minutes * 60
    t0 = pd.Timestamp("2026-06-03 14:30:00", tz="UTC")  # a fixed weekday session

    # latent 1-Hz log-price paths
    leader_steps = rng.normal(0, 0.0004, n)             # the common driver
    leader_path = np.cumsum(leader_steps)

    # which seconds are "regime ON"
    on = np.zeros(n, dtype=bool)
    if regime:
        b = max(1, regime_block_s)
        for start in range(0, n, b):
            if rng.random() < regime_on_frac:
                on[start:start + b] = True

    lag = int(round(lead_seconds))
    own = rng.normal(0, 0.0004, n)              # QQQ idiosyncratic move
    qqq_steps = np.empty(n)
    for i in range(n):
        if regime and on[i] and i - lag >= 0:
            # coupled move: mostly same-second (shared driver) + a lagged tail
            coupled = ((1 - lead_weight) * leader_steps[i]
                       + lead_weight * leader_steps[i - lag])
            qqq_steps[i] = coupling * coupled + (1 - coupling) * own[i] * noise
        else:
            qqq_steps[i] = own[i] * noise
    qqq_path = np.cumsum(qqq_steps)

    # second leader (XLK) shares the driver but with its own noise
    xlk_path = np.cumsum(0.7 * leader_steps + 0.3 * rng.normal(0, 0.0004, n))

    base = {"QQQ": 470.0, "SMH": 250.0, "XLK": 235.0}
    paths = {
        "QQQ": base["QQQ"] * np.exp(qqq_path),
        "SMH": base["SMH"] * np.exp(leader_path),
        "XLK": base["XLK"] * np.exp(xlk_path),
    }

    ticks: List[Tick] = []
    for sym, path in paths.items():
        rate = trade_rates[sym]
        for sec in range(n):
            k = rng.poisson(rate)                       # trades this second
            if k <= 0:
                continue
            # spread offsets within the second around the latent price
            px = path[sec]
            offs = rng.normal(0, px * 2e-5, k)          # ~ sub-bp microstructure
            frac = np.sort(rng.random(k))               # spread across the second
            for j in range(k):
                ticks.append(Tick(
                    symbol=sym,
                    ts=t0 + pd.Timedelta(seconds=int(sec)) + pd.Timedelta(seconds=float(frac[j])),
                    price=float(px + offs[j]),
                    volume=int(rng.integers(1, 50)),
                    side=1 if rng.random() < 0.5 else -1,
                ))
    ticks.sort(key=lambda t: t.ts)
    return ticks


# --------------------------------------------------------------------------- #
# 3. per-step lead detection (micro window) + lead-persistence score          #
# --------------------------------------------------------------------------- #
def _pearson(a: np.ndarray, b: np.ndarray) -> float:
    if a.size < 2 or b.size < 2:
        return 0.0
    sa, sb = a.std(), b.std()
    if not np.isfinite(sa) or not np.isfinite(sb) or sa == 0 or sb == 0:
        return 0.0
    c = np.corrcoef(a, b)[0, 1]
    return float(c) if np.isfinite(c) else 0.0


def detect_lead_per_step(
    close: pd.DataFrame,
    leader: str,
    *,
    micro_bars: int,
    max_lag_bars: int,
    corr_threshold: float,
    lead_margin: float = 0.08,
) -> pd.DataFrame:
    """For each bar t, look back `micro_bars` bars and ask: over that short
    window does `leader` genuinely LEAD target -- not merely co-move with it?

    A true lead is an ASYMMETRY in the cross-correlation: correlation at a
    POSITIVE lag (leader ahead of target) must beat both lag-0 AND the best
    NEGATIVE lag (leader behind target) by `lead_margin`. This is what
    separates "SMH leads QQQ" from "SMH and QQQ just move together" -- pure
    co-movement is symmetric around lag 0 and fails the asymmetry test.

    Returns a per-bar frame: lead (0/1), lag_bars, best_corr (best +lag corr),
    corr0 (contemporaneous, used as the co-movement gate downstream).
    """
    rets = np.log(close[[leader, TARGET]]).diff()
    idx = close.index
    out = {"lead": [], "lag_bars": [], "best_corr": [], "corr0": []}

    def _xcorr(s, tgt, k):
        # k>0: leader shifted forward k bars -> leader LEADS target by k.
        # k<0: leader shifted back -> leader LAGS (target leads).
        al = pd.concat([s.shift(k), tgt], axis=1).dropna()
        if len(al) < 2:
            return 0.0
        return _pearson(al.iloc[:, 0].to_numpy(), al.iloc[:, 1].to_numpy())

    for end in range(len(idx)):
        start = end - micro_bars + 1
        if start < 1:                       # need at least micro_bars returns
            out["lead"].append(0); out["lag_bars"].append(0)
            out["best_corr"].append(0.0); out["corr0"].append(0.0)
            continue
        s = rets[leader].iloc[start:end + 1]
        tgt = rets[TARGET].iloc[start:end + 1]
        corr0 = _pearson(s.to_numpy(), tgt.to_numpy())

        best_pos_lag, best_pos_corr = 0, -1.0
        best_neg_corr = -1.0
        for k in range(1, max_lag_bars + 1):
            cp = _xcorr(s, tgt, k)          # leader leads by k
            if cp > best_pos_corr:
                best_pos_corr, best_pos_lag = cp, k
            cn = _xcorr(s, tgt, -k)         # leader lags by k (target leads)
            if cn > best_neg_corr:
                best_neg_corr = cn

        # genuine lead: positive-lag corr is strong AND asymmetrically beats
        # both the contemporaneous and the target-leads direction.
        is_lead = int(
            best_pos_corr >= corr_threshold
            and best_pos_corr >= corr0 + lead_margin
            and best_pos_corr >= best_neg_corr + lead_margin
        )
        out["lead"].append(is_lead)
        out["lag_bars"].append(best_pos_lag if is_lead else 0)
        out["best_corr"].append(best_pos_corr)
        out["corr0"].append(corr0)
    return pd.DataFrame(out, index=idx)


def lead_persistence(
    per_step: pd.DataFrame,
    *,
    persist_bars: int,
    corr_floor: float,
    corr_strong: float,
    watch_threshold: float,
) -> pd.DataFrame:
    """Roll the per-step lead flags into a persistence/frequency score.

    score = (0.6*density + 0.4*run_frequency) * corr_gate
      density        = fraction of bars in window flagged as lead
      run_frequency  = (# of distinct lead-streaks) / (max possible streaks)
                       -> rewards the "many short, broken streaks" pattern
      corr_gate      = ramp of mean contemporaneous corr from floor..strong
    WATCH fires when score >= watch_threshold.
    """
    lead = per_step["lead"].to_numpy()
    corr0 = per_step["corr0"].to_numpy()
    n = len(lead)
    out = {"density": [], "runs": [], "run_freq": [],
           "mean_corr0": [], "score": [], "watch": []}
    max_runs = max(1, persist_bars // 2)    # alternating lead/no-lead ceiling
    for end in range(n):
        start = max(0, end - persist_bars + 1)
        win = lead[start:end + 1]
        if win.size == 0:
            for kk in out:
                out[kk].append(0.0)
            continue
        density = float(win.mean())
        runs = int(np.sum((win == 1) & (np.concatenate([[0], win[:-1]]) == 0)))
        run_freq = min(1.0, runs / max_runs)
        mean_c = float(np.nanmean(corr0[start:end + 1]))
        gate = float(np.clip((mean_c - corr_floor) / (corr_strong - corr_floor), 0, 1))
        score = (0.6 * density + 0.4 * run_freq) * gate
        out["density"].append(density)
        out["runs"].append(runs)
        out["run_freq"].append(run_freq)
        out["mean_corr0"].append(mean_c)
        out["score"].append(score)
        out["watch"].append(int(score >= watch_threshold))
    return pd.DataFrame(out, index=per_step.index)


# --------------------------------------------------------------------------- #
# 4. validation harness                                                       #
# --------------------------------------------------------------------------- #
def run_scenario(name: str, *, regime: bool, args, rng) -> dict:
    ticks = synth_ticks(
        args.minutes, rng,
        lead_seconds=args.lead_seconds,
        regime=regime,
        regime_on_frac=args.regime_on_frac,
        regime_block_s=args.regime_block_s,
        coupling=args.coupling,
        lead_weight=args.lead_weight,
    )
    close, counts = ticks_to_bars(ticks, args.bar)

    micro_bars = max(4, int(round(args.micro_seconds / args.bar)))
    persist_bars = max(8, int(round(args.persist_seconds / args.bar)))
    max_lag_bars = max(1, int(round(args.max_lag_seconds / args.bar)))

    # combine both leaders: a bar is a "lead" if ANY leader leads QQQ
    per_steps = []
    for leader in LEADERS:
        if leader in close.columns:
            per_steps.append(detect_lead_per_step(
                close, leader,
                micro_bars=micro_bars, max_lag_bars=max_lag_bars,
                corr_threshold=args.corr_threshold,
                lead_margin=args.lead_margin,
            ))
    combined = per_steps[0].copy()
    for ps in per_steps[1:]:
        combined["lead"] = ((combined["lead"] + ps["lead"]) > 0).astype(int)
        combined["corr0"] = np.maximum(combined["corr0"], ps["corr0"])
    persist = lead_persistence(
        combined,
        persist_bars=persist_bars,
        corr_floor=args.corr_floor,
        corr_strong=args.corr_strong,
        watch_threshold=args.watch_threshold,
    )

    watch_frac = float(persist["watch"].mean())
    median_ticks = {sym: float(np.nanmedian(counts[sym].dropna()))
                    for sym in counts.columns} if counts is not None else {}

    print(f"\n=== scenario: {name}  (regime={'ON' if regime else 'OFF/noise'}) ===")
    print(f"  bars: {len(close)} x {args.bar}s   "
          f"micro={micro_bars}b ({micro_bars*args.bar}s)  "
          f"persist={persist_bars}b ({persist_bars*args.bar}s)  "
          f"max_lag={max_lag_bars}b ({max_lag_bars*args.bar}s)")
    print(f"  median ticks / {args.bar}s bar: "
          + "  ".join(f"{s}={v:.0f}" for s, v in median_ticks.items()))
    print(f"  per-step lead density:   {combined['lead'].mean():.3f}")
    print(f"  WATCH fires on:          {watch_frac:.1%} of bars")
    print(f"  mean score:              {persist['score'].mean():.3f}")
    return {"name": name, "regime": regime, "watch_frac": watch_frac,
            "lead_density": float(combined["lead"].mean()),
            "mean_score": float(persist["score"].mean()),
            "median_ticks": median_ticks}


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--scenario", choices=["both", "regime", "noise"], default="both")
    p.add_argument("--minutes", type=int, default=40, help="session length to synth (>=30 for the selective detector)")
    p.add_argument("--bar", type=int, default=3, help="bar size in seconds (3-5)")
    p.add_argument("--lead-seconds", type=float, default=3.0, dest="lead_seconds")
    p.add_argument("--micro-seconds", type=float, default=60.0, dest="micro_seconds")
    p.add_argument("--persist-seconds", type=float, default=90.0, dest="persist_seconds")
    p.add_argument("--max-lag-seconds", type=float, default=9.0, dest="max_lag_seconds")
    p.add_argument("--corr-threshold", type=float, default=0.30, dest="corr_threshold")
    p.add_argument("--lead-margin", type=float, default=0.08, dest="lead_margin",
                   help="how much +lag corr must beat lag-0 AND -lag (asymmetry test)")
    p.add_argument("--corr-floor", type=float, default=0.28, dest="corr_floor")
    p.add_argument("--corr-strong", type=float, default=0.55, dest="corr_strong")
    p.add_argument("--watch-threshold", type=float, default=0.12, dest="watch_threshold")
    p.add_argument("--regime-on-frac", type=float, default=0.5, dest="regime_on_frac")
    p.add_argument("--regime-block-s", type=int, default=20, dest="regime_block_s")
    p.add_argument("--coupling", type=float, default=0.8,
                   help="how strongly QQQ follows the leader during regime-ON")
    p.add_argument("--lead-weight", type=float, default=0.5, dest="lead_weight",
                   help="fraction of the coupled move that is lagged (vs same-bar)")
    p.add_argument("--seed", type=int, default=7)
    args = p.parse_args()

    rng = np.random.default_rng(args.seed)
    results = []
    if args.scenario in ("both", "regime"):
        results.append(run_scenario("real lead regime", regime=True, args=args, rng=rng))
    if args.scenario in ("both", "noise"):
        results.append(run_scenario("pure noise", regime=False, args=args, rng=rng))

    if len(results) == 2:
        r, nse = results[0], results[1]
        print("\n--- validation verdict ---")
        sep = r["watch_frac"] - nse["watch_frac"]
        print(f"  WATCH fires {r['watch_frac']:.1%} in regime vs "
              f"{nse['watch_frac']:.1%} in noise  (separation {sep:+.1%})")
        # the stricter asymmetry detector is SELECTIVE by design: it should fire
        # on a meaningful minority of regime bars while staying near-silent on
        # noise. Pass = regime fires materially AND dominates noise by >=4x.
        if (r["watch_frac"] >= 0.08 and nse["watch_frac"] <= 0.04
                and r["watch_frac"] >= 4 * max(nse["watch_frac"], 0.005)):
            print("  PASS: detector lights up on a real lead regime and stays "
                  "quiet on noise.")
        else:
            print("  TUNE: separation weak -- adjust thresholds / windows.")


if __name__ == "__main__":
    main()
