"""
Event Timeline Engine — Separate engine + database for real-time event tracking.

Manages event_timeline.db independently from constitutional_opportunity_events.db.
Records all scan activity: buy signals, near-entry alerts, scan completions,
volume spikes, and system events.

Public API:
    log_event(event_type, ticker, badge, description, icon, metadata)
    log_scan_event(tickers_processed, batch_label)
    log_buy_signal(ticker, description, entry_price, r2, score)
    log_near_entry(ticker, description, pct_above)
    log_vol_spike(ticker, description, vol_ratio)
    log_system(description)
    get_recent_events(limit) -> list[dict]
    get_event_count() -> int
    get_engine_status() -> dict
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone, timedelta
from pathlib import Path

BASE = Path(__file__).parent
_DB_PATH = BASE / "event_timeline.db"

# Event type constants
BUY_SIGNAL = "BUY_SIGNAL"
NEAR_ENTRY  = "NEAR_ENTRY"
SCAN        = "SCAN"
VOL_SPIKE   = "VOL_SPIKE"
SYSTEM      = "SYSTEM"

# Icon names (resolved by frontend to lucide-react icons)
_ICON = {
    BUY_SIGNAL: "TrendingUp",
    NEAR_ENTRY:  "Clock",
    SCAN:        "RefreshCw",
    VOL_SPIKE:   "AlertTriangle",
    SYSTEM:      "Settings",
}

_BADGE = {
    BUY_SIGNAL: "BUY SIGNAL",
    NEAR_ENTRY:  "NEAR ENTRY",
    SCAN:        "SCAN",
    VOL_SPIKE:   "VOL SPIKE",
    SYSTEM:      "SYSTEM",
}


def _now_iso() -> str:
    try:
        from time_authority import now_cairo
        return now_cairo().isoformat(timespec="seconds")
    except Exception:
        return datetime.now(timezone(timedelta(hours=3))).isoformat(timespec="seconds")


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(str(_DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def _init_db() -> None:
    conn = _connect()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS event_timeline (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            event_type  TEXT NOT NULL,
            ticker      TEXT DEFAULT '',
            badge       TEXT DEFAULT '',
            description TEXT DEFAULT '',
            icon        TEXT DEFAULT '',
            timestamp   TEXT NOT NULL,
            metadata    TEXT DEFAULT '{}'
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_et_ts ON event_timeline(timestamp DESC)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_et_type ON event_timeline(event_type)")
    conn.commit()
    conn.close()


def log_event(
    event_type: str,
    ticker: str = "",
    badge: str = "",
    description: str = "",
    icon: str = "",
    metadata: dict | None = None,
) -> int:
    """Insert a new event. Returns the new row id."""
    _init_db()
    conn = _connect()
    cur = conn.execute(
        """INSERT INTO event_timeline
           (event_type, ticker, badge, description, icon, timestamp, metadata)
           VALUES (?,?,?,?,?,?,?)""",
        (
            event_type,
            ticker,
            badge or _BADGE.get(event_type, event_type),
            description,
            icon or _ICON.get(event_type, "Circle"),
            _now_iso(),
            json.dumps(metadata or {}),
        ),
    )
    conn.commit()
    row_id = cur.lastrowid
    conn.close()
    return row_id


def log_scan_event(tickers_processed: int = 0, batch_label: str = "") -> int:
    label = batch_label or f"{tickers_processed} tickers"
    if batch_label:
        desc = f"{batch_label} — {tickers_processed} tickers processed"
    elif tickers_processed > 0:
        desc = f"Full universe scan completed — {tickers_processed} tickers processed"
    else:
        desc = "Scan completed"
    return log_event(SCAN, ticker="", badge="SCAN", description=desc,
                     metadata={"tickers_processed": tickers_processed})


def log_buy_signal(
    ticker: str,
    description: str = "",
    entry_price: float | None = None,
    r2: float | None = None,
    score: float | None = None,
) -> int:
    if not description:
        parts = []
        if entry_price:
            parts.append(f"BUY LIMIT @ {entry_price:.2f} EGP")
        if r2 is not None:
            parts.append(f"R²={r2:.0f}")
        if score is not None:
            parts.append(f"Score={score:.0f}")
        if not parts:
            parts.append("Constitutional model confirmed")
        description = " — ".join(parts) if len(parts) > 1 else (parts[0] + " — Constitutional model confirmed")
    return log_event(BUY_SIGNAL, ticker=ticker, description=description,
                     metadata={"entry_price": entry_price, "r2": r2, "score": score})


def log_near_entry(ticker: str, description: str = "", pct_above: float | None = None) -> int:
    if not description:
        if pct_above is not None:
            description = f"Entered near-entry zone — {pct_above:.1f}% above limit price"
        else:
            description = "Price approaching accumulation zone"
    return log_event(NEAR_ENTRY, ticker=ticker, description=description,
                     metadata={"pct_above": pct_above})


def log_vol_spike(ticker: str, description: str = "", vol_ratio: float | None = None) -> int:
    if not description:
        if vol_ratio is not None:
            description = f"Volume anomaly detected — {vol_ratio:.1f}× average daily volume"
        else:
            description = "Unusual volume detected"
    return log_event(VOL_SPIKE, ticker=ticker, description=description,
                     metadata={"vol_ratio": vol_ratio})


def log_system(description: str) -> int:
    return log_event(SYSTEM, ticker="", badge="SYSTEM", description=description)


def get_recent_events(limit: int = 50) -> list[dict]:
    """Return the most recent events, newest first."""
    try:
        _init_db()
        conn = _connect()
        rows = conn.execute(
            "SELECT * FROM event_timeline ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]
    except Exception:
        return []


def get_event_count() -> int:
    try:
        _init_db()
        conn = _connect()
        n = conn.execute("SELECT COUNT(*) FROM event_timeline").fetchone()[0]
        conn.close()
        return n
    except Exception:
        return 0


def get_engine_status() -> dict:
    """Return engine health: last event timestamp and total count."""
    try:
        _init_db()
        conn = _connect()
        row = conn.execute(
            "SELECT timestamp FROM event_timeline ORDER BY id DESC LIMIT 1"
        ).fetchone()
        count = conn.execute("SELECT COUNT(*) FROM event_timeline").fetchone()[0]
        conn.close()
        return {
            "last_event_ts": row["timestamp"] if row else None,
            "total_events": count,
            "db_path": str(_DB_PATH),
        }
    except Exception as e:
        return {"last_event_ts": None, "total_events": 0, "error": str(e)}
