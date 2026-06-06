"""AI-capex dependency index (structural / context — NOT intraday).

Measures how much of the target's (QQQ) daily behaviour is explained by the
"AI bottleneck" complex — memory, optics/EUV, servers/networking, power, grid —
and how that dependency has trended over all available history.

This is deliberately a SLOW, daily-bar feature, walled off from the intraday
prediction thesis. It never feeds the intraday score/projection. It answers a
different, structural question for ETF analysts/commentators:

    "How dependent has the Nasdaq become on the AI build-out, and what is that
     dependency doing today?"

Method (all data-driven, nothing fabricated):
- Build a theme-balanced composite daily return: equal-weight members within a
  theme, then equal-weight across themes (so adding more memory tickers does
  not silently overweight memory).
- Dependency = rolling-window R² of target daily returns regressed on the
  composite return → "share of QQQ's daily variance explained by the complex".
- Trend = that rolling R² over all available history.
- Per-theme today = each theme's current correlation + standardized beta to the
  target, plus its change vs CHANGE_LOOKBACK days ago → which bottleneck QQQ
  leans on most and what is rising fastest.

Ragged history is handled per-window: a member only contributes to windows
where it has data; young funds are flagged ("limited_history"), never faked.
"""
from typing import Dict, Any, List, Optional
import logging

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


class AIDependencyEngine:
    def __init__(
        self,
        target: str = None,
        basket: List[dict] = None,
        window: int = None,
        min_obs: int = None,
        change_lookback: int = None,
    ):
        try:
            from app.config import settings
        except Exception:  # pragma: no cover - defensive
            settings = None

        def _get(name, default):
            return getattr(settings, name, default) if settings is not None else default

        self.target = (target if target is not None
                       else _get("AI_DEPENDENCY_TARGET", "QQQ")).upper()
        self.basket = list(basket if basket is not None
                           else _get("AI_DEPENDENCY_BASKET", []))
        self.window = int(window if window is not None
                          else _get("AI_DEPENDENCY_WINDOW", 21))
        self.min_obs = int(min_obs if min_obs is not None
                           else _get("AI_DEPENDENCY_MIN_OBS", 10))
        self.change_lookback = int(change_lookback if change_lookback is not None
                                   else _get("AI_DEPENDENCY_CHANGE_LOOKBACK", 21))

    # ------------------------------------------------------------------ #
    # helpers                                                             #
    # ------------------------------------------------------------------ #
    def all_symbols(self) -> List[str]:
        """Every symbol the engine needs fetched (target + all members)."""
        syms = {self.target}
        for theme in self.basket:
            for m in theme.get("members", []):
                s = str(m.get("symbol", "")).upper().strip()
                if s:
                    syms.add(s)
        return sorted(syms)

    def _empty(self, status: str) -> Dict[str, Any]:
        return {
            "status": status,
            "target": self.target,
            "asof": None,
            "dependency_now": 0.0,
            "dependency_trend": [],
            "change": 0.0,
            "change_lookback_days": self.change_lookback,
            "window_days": self.window,
            "themes": [],
            "headline": "Warming up — not enough daily history to measure AI dependency yet.",
        }

    @staticmethod
    def _r2(y: np.ndarray, x: np.ndarray) -> Optional[float]:
        """R² of OLS y ~ a + b·x on aligned 1-D arrays. None if degenerate."""
        if len(y) < 3 or len(y) != len(x):
            return None
        if np.std(x) == 0 or np.std(y) == 0:
            return None
        A = np.column_stack([np.ones(len(x)), x])
        try:
            coef, _r, _rk, _sv = np.linalg.lstsq(A, y, rcond=None)
        except Exception:
            return None
        y_hat = A @ coef
        ss_res = float(np.sum((y - y_hat) ** 2))
        ss_tot = float(np.sum((y - y.mean()) ** 2))
        if ss_tot <= 0:
            return None
        return float(min(max(1.0 - ss_res / ss_tot, 0.0), 1.0))

    def _composite_returns(self, rets: pd.DataFrame) -> pd.Series:
        """Theme-balanced composite of member daily returns.

        Equal-weight within each theme (over members present that day), then
        equal-weight across themes that have at least one member that day.
        """
        theme_series = []
        for theme in self.basket:
            members = [str(m.get("symbol", "")).upper().strip()
                       for m in theme.get("members", [])]
            members = [m for m in members if m in rets.columns]
            if not members:
                continue
            # row-mean across present members (skip NaNs per-row)
            theme_series.append(rets[members].mean(axis=1, skipna=True))
        if not theme_series:
            return pd.Series(dtype=float)
        comp = pd.concat(theme_series, axis=1).mean(axis=1, skipna=True)
        return comp

    def _theme_today(self, rets: pd.DataFrame, target_ret: pd.Series) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        n = len(rets)
        recent = rets.tail(self.window)
        prior_end = max(n - self.change_lookback, self.window)
        prior = rets.iloc[max(prior_end - self.window, 0):prior_end]
        tgt_recent = target_ret.tail(self.window)
        tgt_prior = target_ret.iloc[max(prior_end - self.window, 0):prior_end]

        for theme in self.basket:
            members_cfg = theme.get("members", [])
            members = [str(m.get("symbol", "")).upper().strip() for m in members_cfg]
            present = [m for m in members if m in rets.columns]
            member_rows = []
            for m_cfg in members_cfg:
                sym = str(m_cfg.get("symbol", "")).upper().strip()
                in_data = sym in rets.columns
                bars = int(rets[sym].notna().sum()) if in_data else 0
                member_rows.append({
                    "symbol": sym,
                    "label": m_cfg.get("label", sym.lower()),
                    "bars": bars,
                    "included": bool(in_data and bars >= self.min_obs),
                })

            included = [r["symbol"] for r in member_rows if r["included"]]
            corr_now = beta_now = None
            change = 0.0
            limited = len(included) == 0
            if included:
                theme_recent = recent[included].mean(axis=1, skipna=True)
                aligned = pd.concat([tgt_recent, theme_recent], axis=1).dropna()
                if len(aligned) >= self.min_obs:
                    y = aligned.iloc[:, 0].to_numpy(dtype=float)
                    x = aligned.iloc[:, 1].to_numpy(dtype=float)
                    if np.std(x) > 0 and np.std(y) > 0:
                        corr_now = float(np.corrcoef(y, x)[0, 1])
                        beta_now = float(np.cov(y, x)[0, 1] / np.var(x))
                # change vs prior window
                theme_prior = prior[[c for c in included if c in prior.columns]]
                if not theme_prior.empty:
                    tp = theme_prior.mean(axis=1, skipna=True)
                    ap = pd.concat([tgt_prior, tp], axis=1).dropna()
                    if len(ap) >= self.min_obs and corr_now is not None:
                        yp = ap.iloc[:, 0].to_numpy(dtype=float)
                        xp = ap.iloc[:, 1].to_numpy(dtype=float)
                        if np.std(xp) > 0 and np.std(yp) > 0:
                            corr_prior = float(np.corrcoef(yp, xp)[0, 1])
                            change = float(corr_now - corr_prior)

            out.append({
                "key": theme.get("key"),
                "label": theme.get("label", theme.get("key")),
                "corr_now": corr_now,
                "beta_now": beta_now,
                "change": change,
                "limited_history": limited,
                "members": member_rows,
            })

        # sort strongest current coupling first (None last)
        out.sort(key=lambda t: (t["corr_now"] is None, -(t["corr_now"] or -1)))
        return out

    def _headline(self, dep_now: float, change: float, themes: List[Dict[str, Any]]) -> str:
        pct = int(round(dep_now * 100))
        lead = next((t for t in themes if t["corr_now"] is not None), None)
        lead_txt = f" Most-coupled bottleneck: {lead['label']}." if lead else ""
        if abs(change) < 0.02:
            trend = "roughly flat vs a month ago"
        elif change > 0:
            trend = f"up {int(round(change * 100))} pts vs a month ago"
        else:
            trend = f"down {int(round(abs(change) * 100))} pts vs a month ago"
        return (f"QQQ is ~{pct}% explained by the AI build-out complex, {trend}.{lead_txt}")

    # ------------------------------------------------------------------ #
    # main                                                                #
    # ------------------------------------------------------------------ #
    def compute(self, closes: pd.DataFrame) -> Dict[str, Any]:
        """closes: DataFrame of daily close prices, columns = symbols, index =
        dates (sorted). Must contain the target column."""
        if closes is None or getattr(closes, "empty", True):
            return self._empty("warming_up")
        if self.target not in closes.columns:
            logger.warning("[AIDependency] target %s missing", self.target)
            return self._empty("warming_up")

        closes = closes.sort_index()
        rets = closes.pct_change()
        target_ret = rets[self.target]

        comp = self._composite_returns(rets.drop(columns=[self.target], errors="ignore"))
        if comp.empty:
            return self._empty("warming_up")

        joined = pd.concat([target_ret.rename("__t"), comp.rename("__c")], axis=1)
        valid = joined.dropna()
        if len(valid) < self.min_obs:
            return self._empty("warming_up")

        # rolling-window R² trend over all available history
        trend: List[Dict[str, Any]] = []
        idx = valid.index
        yv = valid["__t"].to_numpy(dtype=float)
        xv = valid["__c"].to_numpy(dtype=float)
        for end in range(self.min_obs, len(valid) + 1):
            start = max(0, end - self.window)
            w_y = yv[start:end]
            w_x = xv[start:end]
            if len(w_y) < self.min_obs:
                continue
            r2 = self._r2(w_y, w_x)
            if r2 is None:
                continue
            ts = idx[end - 1]
            trend.append({
                "date": ts.strftime("%Y-%m-%d") if hasattr(ts, "strftime") else str(ts),
                "value": round(r2, 4),
            })

        if not trend:
            return self._empty("warming_up")

        dep_now = float(trend[-1]["value"])
        # change vs change_lookback trading days ago on the trend series
        if len(trend) > self.change_lookback:
            dep_change = dep_now - float(trend[-1 - self.change_lookback]["value"])
        else:
            dep_change = dep_now - float(trend[0]["value"])

        themes = self._theme_today(rets.drop(columns=[self.target], errors="ignore"), target_ret)

        result = {
            "status": "ok",
            "target": self.target,
            "asof": trend[-1]["date"],
            "dependency_now": round(dep_now, 4),
            "dependency_trend": trend,
            "change": round(dep_change, 4),
            "change_lookback_days": self.change_lookback,
            "window_days": self.window,
            "themes": themes,
            "headline": self._headline(dep_now, dep_change, themes),
        }
        logger.info(
            "[AIDependency] dep_now=%.2f change=%+.2f points=%d themes=%d",
            dep_now, dep_change, len(trend), len(themes),
        )
        return result
