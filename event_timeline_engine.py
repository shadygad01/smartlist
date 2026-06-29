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
    timestamp: str | None = None,
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
            timestamp or _now_iso(),
            json.dumps(metadata or {}),
        ),
    )
    conn.commit()
    row_id = cur.lastrowid
    conn.close()
    return row_id


def log_scan_event(tickers_processed: int = 0, batch_label: str = "",
                   timestamp: str | None = None) -> int:
    label = batch_label or f"{tickers_processed} tickers"
    if batch_label:
        desc = f"{batch_label} — {tickers_processed} tickers processed"
    elif tickers_processed > 0:
        desc = f"Full universe scan completed — {tickers_processed} tickers processed"
    else:
        desc = "Scan completed"
    return log_event(SCAN, ticker="", badge="SCAN", description=desc,
                     metadata={"tickers_processed": tickers_processed},
                     timestamp=timestamp)


def log_buy_signal(
    ticker: str,
    description: str = "",
    entry_price: float | None = None,
    r2: float | None = None,
    score: float | None = None,
    timestamp: str | None = None,
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
                     metadata={"entry_price": entry_price, "r2": r2, "score": score},
                     timestamp=timestamp)


def log_near_entry(ticker: str, description: str = "", pct_above: float | None = None,
                   timestamp: str | None = None) -> int:
    if not description:
        if pct_above is not None and pct_above > 0.05:
            description = f"Entry zone is {pct_above:.1f}% above current price"
        elif pct_above is not None:
            description = "Price at constitutional entry zone — BUY condition met"
        else:
            description = "Price approaching accumulation zone"
    return log_event(NEAR_ENTRY, ticker=ticker, description=description,
                     metadata={"pct_above": pct_above},
                     timestamp=timestamp)


def log_vol_spike(ticker: str, description: str = "", vol_ratio: float | None = None,
                  timestamp: str | None = None) -> int:
    if not description:
        if vol_ratio is not None:
            description = f"Volume anomaly detected — {vol_ratio:.1f}× average daily volume"
        else:
            description = "Unusual volume detected"
    return log_event(VOL_SPIKE, ticker=ticker, description=description,
                     metadata={"vol_ratio": vol_ratio},
                     timestamp=timestamp)


def log_system(description: str, timestamp: str | None = None) -> int:
    return log_event(SYSTEM, ticker="", badge="SYSTEM", description=description,
                     timestamp=timestamp)


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


def clear_all_events() -> int:
    """Delete all events from the timeline. Returns count of deleted rows."""
    _init_db()
    conn = _connect()
    n = conn.execute("DELETE FROM event_timeline").rowcount
    conn.execute("DELETE FROM sqlite_sequence WHERE name='event_timeline'")
    conn.commit()
    conn.close()
    return n


def backfill_from_constitutional_timeline(days: int = 60) -> dict:
    """
    Populate event_timeline from real data sources:
      - BUY_SIGNAL: constitutional_opportunity_events.db (last N days)
      - NEAR_ENTRY: current approaching_entries from presentation_snapshot.json
      - VOL_SPIKE: CSV historical data (ratio >= 2.5x 20-day average)
      - SCAN: one synthetic scan event per day that has a constitutional event
      - SYSTEM: one initialization marker

    Clears all existing events before backfilling.
    Returns dict with counts per event type.
    """
    import sys as _sys
    import sqlite3 as _sqlite3
    import csv as _csv_mod
    from datetime import date as _date, timedelta as _td
    _sys.path.insert(0, str(BASE))

    counts: dict[str, int] = {BUY_SIGNAL: 0, NEAR_ENTRY: 0, VOL_SPIKE: 0, SCAN: 0, SYSTEM: 0}
    cutoff = (_date.today() - _td(days=days)).isoformat()

    # ── 1. Load constitutional events ─────────────────────────────────────────
    _COE_DB = BASE / "constitutional_opportunity_events.db"
    constitutional_events: list[dict] = []
    if _COE_DB.exists():
        try:
            _c = _sqlite3.connect(str(_COE_DB))
            _c.row_factory = _sqlite3.Row
            rows = _c.execute(
                "SELECT ticker, event_type, event_date, constitutional_entry_price, "
                "constitutional_r2, constitutional_score "
                "FROM constitutional_opportunity_events "
                "WHERE event_date >= ? ORDER BY event_date ASC, ticker ASC",
                (cutoff,)
            ).fetchall()
            _c.close()
            constitutional_events = [dict(r) for r in rows]
        except Exception as _e:
            print(f"[ETL backfill] constitutional events load: {_e}")

    # ── 2. Load near-entry from current snapshot ───────────────────────────────
    import json as _json_mod
    _snap_path = BASE / "presentation_snapshot.json"
    approaching: list[dict] = []
    if _snap_path.exists():
        try:
            _snap = _json_mod.loads(_snap_path.read_text())
            approaching = _snap.get("near_constitutional", [])
        except Exception:
            pass

    # ── 3. Detect real volume spikes from CSV data ─────────────────────────────
    _hist_dir = BASE / "historical_data" / "historical_data"
    vol_spikes: list[dict] = []
    if _hist_dir.exists():
        for _csv_path in sorted(_hist_dir.glob("*.CA.csv")):
            try:
                with open(_csv_path, newline="") as _fh:
                    _rows = list(_csv_mod.DictReader(_fh))
                if len(_rows) < 22:
                    continue
                _last_vol = float(_rows[-1].get("Volume") or 0)
                _avg_vol = sum(float(r.get("Volume") or 0) for r in _rows[-22:-1]) / 21
                _ratio = _last_vol / _avg_vol if _avg_vol > 0 else 0
                if _ratio >= 2.5:
                    vol_spikes.append({
                        "ticker": _csv_path.stem,
                        "vol_ratio": round(_ratio, 2),
                        "date": _rows[-1].get("Date", ""),
                    })
            except Exception:
                continue

    # ── 4. Clear and repopulate in strict chronological order ─────────────────
    # Events must be inserted oldest-first so ORDER BY id DESC gives newest-first
    # display in the frontend timeline.
    clear_all_events()

    # Group constitutional events by date
    from collections import defaultdict as _dd
    _events_by_date: dict = _dd(list)
    for ev in constitutional_events:
        _events_by_date[ev["event_date"]].append(ev)

    _all_dates = sorted(set(list(_events_by_date.keys()) +
                            [_vs["date"] for _vs in vol_spikes if _vs.get("date")]))
    _oldest_date = _all_dates[0] if _all_dates else _date.today().isoformat()

    # SYSTEM: initialization marker before everything
    log_system(
        description="Event Timeline Engine initialized — real constitutional data loaded",
        timestamp=f"{_oldest_date}T09:00:00+03:00",
    )
    counts[SYSTEM] += 1

    # Per-date: SCAN → VOL_SPIKE → BUY_SIGNAL (oldest date first)
    _universe_size = 27
    for _day in _all_dates:
        # SCAN event
        if _day in _events_by_date or any(_vs["date"] == _day for _vs in vol_spikes):
            log_scan_event(
                tickers_processed=_universe_size,
                batch_label="Full universe scan completed",
                timestamp=f"{_day}T14:00:00+03:00",
            )
            counts[SCAN] += 1

        # VOL_SPIKE events for this date
        for _vs in [v for v in vol_spikes if v.get("date") == _day]:
            log_vol_spike(
                ticker=_vs["ticker"],
                vol_ratio=_vs["vol_ratio"],
                timestamp=f"{_day}T14:30:00+03:00",
            )
            counts[VOL_SPIKE] += 1

        # BUY_SIGNAL events for this date
        for ev in _events_by_date.get(_day, []):
            _ep = ev.get("constitutional_entry_price")
            _r2 = ev.get("constitutional_r2")
            _sc = ev.get("constitutional_score")
            _ep_str = f"BUY LIMIT @ {_ep:.2f} EGP — " if _ep else ""
            _desc = f"{_ep_str}Constitutional model confirmed"
            if _r2 is not None:
                _desc += f" (R²={_r2:.1f}, Score={_sc:.0f})" if _sc is not None else f" (R²={_r2:.1f})"
            log_buy_signal(
                ticker=ev["ticker"],
                description=_desc,
                entry_price=_ep,
                r2=_r2,
                score=_sc,
                timestamp=f"{_day}T14:30:00+03:00",
            )
            counts[BUY_SIGNAL] += 1

    # NEAR_ENTRY events from current snapshot (logged last = highest IDs = top of feed)
    for _ne in approaching:
        _ticker = _ne.get("ticker", "")
        _pct = _ne.get("need_move_pct", 0.0)
        if not _ticker:
            continue
        log_near_entry(ticker=_ticker, pct_above=_pct if _pct is not None else None)
        counts[NEAR_ENTRY] += 1

    return counts
