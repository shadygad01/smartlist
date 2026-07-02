"""
Signal State Store — constitutional signal state machine with idempotency guarantee.

TWO separate, independent concerns:

  TRANSACTIONS  (signal_event_log table)
    - Immutable historical record of every state transition.
    - UNIQUE(ticker, event_date, to_state) enforced at DB level.
    - One row per ticker per target-state per trading day.
    - Source of truth for "did this ticker actually change state today?"

  NOTIFICATIONS  (telegram_delivery / notification_delivery tables — separate module)
    - Transient delivery records only.
    - Consumers of events; they never own business state.

Idempotency guarantee:
  record_transition(ticker, from, to, date) called N times with same args:
    - First call  → inserts row → returns True  → caller sends notification
    - Call 2..N   → UNIQUE fires, INSERT ignored → returns False → caller sends NOTHING

Running detect_signal_changes() any number of times with identical market data
produces at most ONE notification per ticker per trading day.
"""
from __future__ import annotations

import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path

_DB = Path(__file__).parent.parent / "notification_delivery.db"

# Constitutional signal states (ordered by severity)
STATE_NONE        = "NONE"
STATE_NEAR_ENTRY  = "NEAR_ENTRY"
STATE_CONST_BUY   = "CONSTITUTIONAL_BUY"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _conn() -> sqlite3.Connection:
    con = sqlite3.connect(str(_DB), timeout=10)
    con.execute("PRAGMA journal_mode=WAL")
    con.executescript("""
        CREATE TABLE IF NOT EXISTS signal_state_current (
            ticker      TEXT PRIMARY KEY,
            state       TEXT NOT NULL DEFAULT 'NONE',
            state_date  TEXT NOT NULL,
            updated_at  TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS signal_event_log (
            id              TEXT PRIMARY KEY,
            ticker          TEXT NOT NULL,
            from_state      TEXT NOT NULL,
            to_state        TEXT NOT NULL,
            event_date      TEXT NOT NULL,
            notified_email  INTEGER NOT NULL DEFAULT 0,
            notified_tg     INTEGER NOT NULL DEFAULT 0,
            created_at      TEXT NOT NULL
        );

        CREATE UNIQUE INDEX IF NOT EXISTS ux_sel_ticker_date_state
            ON signal_event_log(ticker, event_date, to_state);
    """)
    con.commit()
    return con


def get_current_state(ticker: str) -> str:
    """Return the last persisted state for this ticker (NONE if never seen)."""
    try:
        con = _conn()
        row = con.execute(
            "SELECT state FROM signal_state_current WHERE ticker=?", (ticker,)
        ).fetchone()
        con.close()
        return row[0] if row else STATE_NONE
    except Exception:
        return STATE_NONE


def record_transition(
    ticker: str,
    from_state: str,
    to_state: str,
    event_date: str,
) -> bool:
    """
    Attempt to record a state transition as a transaction.

    Returns True  if this is a NEW transition (row inserted for first time).
    Returns False if this (ticker, event_date, to_state) was already recorded.

    Safe to call any number of times — idempotent by design.
    """
    try:
        con = _conn()
        rid = str(uuid.uuid4())
        now = _now()

        cur = con.execute(
            """INSERT OR IGNORE INTO signal_event_log
               (id, ticker, from_state, to_state, event_date, created_at)
               VALUES (?,?,?,?,?,?)""",
            (rid, ticker, from_state, to_state, event_date, now),
        )
        is_new = cur.rowcount > 0  # rowcount is per-statement; total_changes is connection-wide

        # Always keep signal_state_current up to date (non-NONE states only)
        if to_state != STATE_NONE:
            con.execute(
                """INSERT INTO signal_state_current (ticker, state, state_date, updated_at)
                   VALUES (?,?,?,?)
                   ON CONFLICT(ticker) DO UPDATE SET
                       state=excluded.state,
                       state_date=excluded.state_date,
                       updated_at=excluded.updated_at""",
                (ticker, to_state, event_date, now),
            )
        else:
            # Ticker exited buy zone — reset current state to NONE
            con.execute(
                "UPDATE signal_state_current SET state=?, state_date=?, updated_at=? WHERE ticker=?",
                (STATE_NONE, event_date, now, ticker),
            )

        con.commit()
        con.close()
        return is_new
    except Exception as e:
        print(f"[signal_state_store] record_transition error: {e}")
        return False


def mark_notified(
    ticker: str,
    to_state: str,
    event_date: str,
    *,
    channel: str = "all",
) -> None:
    """Mark that a notification was sent for this transition."""
    try:
        con = _conn()
        if channel in ("email", "all"):
            con.execute(
                "UPDATE signal_event_log SET notified_email=1 "
                "WHERE ticker=? AND event_date=? AND to_state=?",
                (ticker, event_date, to_state),
            )
        if channel in ("telegram", "all"):
            con.execute(
                "UPDATE signal_event_log SET notified_tg=1 "
                "WHERE ticker=? AND event_date=? AND to_state=?",
                (ticker, event_date, to_state),
            )
        con.commit()
        con.close()
    except Exception as e:
        print(f"[signal_state_store] mark_notified error: {e}")


def has_notified_today(
    ticker: str,
    to_state: str,
    event_date: str,
    *,
    channel: str = "all",
) -> bool:
    """Return True if notification was already sent for this ticker+state today."""
    try:
        con = _conn()
        if channel == "email":
            col = "notified_email"
        elif channel == "telegram":
            col = "notified_tg"
        else:
            col = "(notified_email AND notified_tg)"
        row = con.execute(
            f"SELECT {col} FROM signal_event_log "
            "WHERE ticker=? AND event_date=? AND to_state=?",
            (ticker, event_date, to_state),
        ).fetchone()
        con.close()
        return bool(row and row[0])
    except Exception:
        return False


def get_todays_events(event_date: str) -> list[dict]:
    """Return all signal transitions recorded for the given trading day."""
    try:
        con = _conn()
        rows = con.execute(
            "SELECT ticker, from_state, to_state, notified_email, notified_tg, created_at "
            "FROM signal_event_log WHERE event_date=? ORDER BY created_at",
            (event_date,),
        ).fetchall()
        con.close()
        return [
            {
                "ticker":           r[0],
                "from_state":       r[1],
                "to_state":         r[2],
                "notified_email":   bool(r[3]),
                "notified_tg":      bool(r[4]),
                "created_at":       r[5],
            }
            for r in rows
        ]
    except Exception:
        return []


def get_unnotified_transitions(event_date: str) -> list[dict]:
    """Return CONST_BUY transitions recorded today where notification was never sent.

    Used by detect_signal_changes() to retry alerts that were recorded but whose
    send_change_alert() call failed silently (e.g. morning scan exception, old
    code path that did not call send_change_alert).

    Only returns rows where BOTH channels are still unnotified — if at least one
    channel succeeded we consider the event partially delivered and skip retry.
    """
    try:
        con = _conn()
        rows = con.execute(
            """SELECT ticker, from_state, to_state
               FROM signal_event_log
               WHERE event_date=? AND to_state=? AND notified_email=0 AND notified_tg=0""",
            (event_date, STATE_CONST_BUY),
        ).fetchall()
        con.close()
        return [{"ticker": r[0], "from_state": r[1], "to_state": r[2]} for r in rows]
    except Exception:
        return []


def get_duplicate_count(event_date: str) -> int:
    """CI helper: returns number of duplicate transition attempts blocked today."""
    try:
        con = _conn()
        row = con.execute(
            "SELECT COUNT(*) FROM signal_event_log WHERE event_date=?", (event_date,)
        ).fetchone()
        con.close()
        return row[0] if row else 0
    except Exception:
        return 0
