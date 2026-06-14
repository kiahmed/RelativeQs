"""SQLite persistence for the daily rotation-flow backtest.

After the close we settle ONE final intraday read (from 1m bars, session
"final") and a COARSE daily-bar read (compute_rotation on ~10d of daily bars,
windows expressed in days), plus an `agreement` score: how well the destinations
the intraday read inferred ("into") overlap the daily read's top relative
performers. One row per calendar date (PRIMARY KEY date). Read back via
/rotation/history.
"""
from __future__ import annotations

import json
import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# backend/app/services/rotation_store.py -> parents[2] == backend/
_DEFAULT_DB = Path(__file__).resolve().parents[2] / "rotation.db"


def compute_agreement(intraday: Dict[str, Any], daily: Dict[str, Any],
                      top_n: int = 3) -> float:
    """0..1 overlap: of the destinations the intraday read inferred money rotated
    INTO, how many also rank among the daily read's top relative performers.

    0.0 when the intraday read named no destination (nothing to agree on)."""
    into: set = set()
    for w in (intraday.get("windows") or {}).values():
        into.update((w.get("summary") or {}).get("into") or [])
    if not into:
        return 0.0
    top: set = set()
    for w in (daily.get("windows") or {}).values():
        rows = sorted(
            (w.get("rows") or []),
            key=lambda r: (r.get("rel") if r.get("rel") is not None else -1e9),
            reverse=True,
        )
        top.update(r["symbol"] for r in rows[:top_n])
    return round(len(into & top) / len(into), 3)


class RotationStore:
    def __init__(self, db_path: Optional[str] = None):
        self.db_path = str(db_path or _DEFAULT_DB)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        con = sqlite3.connect(self.db_path)
        con.row_factory = sqlite3.Row
        return con

    def _init_db(self) -> None:
        con = self._connect()
        con.executescript(
            """
            CREATE TABLE IF NOT EXISTS rotation_backtests (
                date           TEXT PRIMARY KEY,
                created_at     TEXT,
                intraday_final TEXT,   -- json: settled 1m read (session="final")
                daily_read     TEXT,   -- json: coarse daily-bar read
                agreement      REAL    -- 0..1 overlap score
            );
            """
        )
        con.commit()
        con.close()

    def write(self, date: str, intraday_final: Dict[str, Any],
              daily_read: Dict[str, Any], agreement: float) -> None:
        con = self._connect()
        con.execute(
            "INSERT OR REPLACE INTO rotation_backtests "
            "(date, created_at, intraday_final, daily_read, agreement) "
            "VALUES (?, ?, ?, ?, ?)",
            (
                date,
                datetime.now(timezone.utc).isoformat(),
                json.dumps(intraday_final),
                json.dumps(daily_read),
                float(agreement),
            ),
        )
        con.commit()
        con.close()

    def get_by_date(self, date: str) -> Optional[Dict[str, Any]]:
        con = self._connect()
        row = con.execute(
            "SELECT * FROM rotation_backtests WHERE date = ?", (date,)
        ).fetchone()
        con.close()
        return self._row_to_dict(row) if row else None

    def history(self, limit: int = 30) -> List[Dict[str, Any]]:
        con = self._connect()
        rows = con.execute(
            "SELECT * FROM rotation_backtests ORDER BY date DESC LIMIT ?",
            (int(limit),),
        ).fetchall()
        con.close()
        return [self._row_to_dict(r) for r in rows]

    @staticmethod
    def _row_to_dict(row: sqlite3.Row) -> Dict[str, Any]:
        return {
            "date": row["date"],
            "created_at": row["created_at"],
            "intraday_final": json.loads(row["intraday_final"]) if row["intraday_final"] else None,
            "daily_read": json.loads(row["daily_read"]) if row["daily_read"] else None,
            "agreement": row["agreement"],
        }
