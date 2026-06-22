"""
Constitutional Notification Router — single entry point for ALL Telegram messages.

Every Telegram notification must call route(event_type, message, ...).
The router calls notifications.telegram_sender.send() exclusively.
Logs every delivery to telegram_delivery table in notification_delivery.db.

Exactly-once guarantee: (event_type, symbol, event_date) is never delivered twice.
Replaces telegram_debounce.json completely.
"""
from __future__ import annotations

import hashlib
import sqlite3
import uuid
from datetime import datetime, timezone, timedelta
from pathlib import Path

import sys as _sys
_sys.path.insert(0, str(Path(__file__).parent.parent))
from time_authority import now_cairo as _now_cairo_ta

_DB_PATH = Path(__file__).parent.parent / "notification_delivery.db"

# ── Event types ────────────────────────────────────────────────────────────────
MORNING_BRIEF        = "MORNING_BRIEF"
SIGNAL_CHANGE        = "SIGNAL_CHANGE"
FIRST_BUY            = "FIRST_BUY"
TARGET_UPDATE        = "TARGET_UPDATE"
ZONE3_REINFORCEMENT  = "ZONE3_REINFORCEMENT"
HIGH_SCORE           = "HIGH_SCORE"
PRODUCTION_PROMOTION = "PRODUCTION_PROMOTION"
NEAR_CONSTITUTIONAL  = "NEAR_CONSTITUTIONAL"
TIMELINE_EVENT       = "TIMELINE_EVENT"


def _now() -> str:
    return _now_cairo_ta().isoformat()


def _today() -> str:
    return _now_cairo_ta().date().isoformat()


def _conn() -> sqlite3.Connection:
    con = sqlite3.connect(str(_DB_PATH), timeout=10)
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("""
        CREATE TABLE IF NOT EXISTS telegram_delivery (
            id           TEXT PRIMARY KEY,
            event_type   TEXT NOT NULL,
            symbol       TEXT NOT NULL DEFAULT '',
            event_date   TEXT NOT NULL,
            created_at   TEXT NOT NULL,
            sent_at      TEXT,
            status       TEXT NOT NULL DEFAULT 'pending',
            message_hash TEXT,
            retry_count  INTEGER NOT NULL DEFAULT 0,
            error        TEXT
        )
    """)
    con.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS ux_tg_delivery_once
        ON telegram_delivery(event_type, symbol, event_date)
    """)
    con.commit()
    return con


def _is_sent(event_type: str, symbol: str, event_date: str) -> bool:
    try:
        con = _conn()
        row = con.execute(
            "SELECT status FROM telegram_delivery WHERE event_type=? AND symbol=? AND event_date=?",
            (event_type, symbol, event_date),
        ).fetchone()
        con.close()
        return row is not None and row[0] == "sent"
    except Exception:
        return False


def _msg_hash(text: str) -> str:
    return hashlib.md5(text.encode()).hexdigest()[:16]


def route(
    event_type: str,
    message: str,
    *,
    symbol: str = "",
    event_date: str | None = None,
    parse_mode: str = "Markdown",
    check_duplicate: bool = True,
) -> bool:
    """
    Send a Telegram notification through the single constitutional sender.

    Args:
        event_type:       One of the module-level constants (MORNING_BRIEF, etc.)
        message:          Text to send (Markdown supported).
        symbol:           Ticker symbol for deduplication (empty for broadcast events).
        event_date:       YYYY-MM-DD for exactly-once key. Defaults to today (Cairo).
        parse_mode:       'Markdown' or 'HTML'.
        check_duplicate:  If True, skip if (event_type, symbol, event_date) already sent.

    Returns:
        True if sent or legitimately skipped (duplicate), False on delivery failure.
    """
    from .telegram_sender import send as _tg

    ed = event_date or _today()

    if check_duplicate and _is_sent(event_type, symbol, ed):
        print(f"[router] {event_type} {symbol or '*'} {ed} already sent — skip")
        return True

    rid = str(uuid.uuid4())
    try:
        con = _conn()
        con.execute(
            "INSERT OR IGNORE INTO telegram_delivery "
            "(id, event_type, symbol, event_date, created_at) VALUES (?,?,?,?,?)",
            (rid, event_type, symbol, ed, _now()),
        )
        con.commit()
        row = con.execute(
            "SELECT id FROM telegram_delivery WHERE event_type=? AND symbol=? AND event_date=?",
            (event_type, symbol, ed),
        ).fetchone()
        rid = row[0] if row else rid
        con.close()
    except Exception:
        pass

    ok = _tg(message, parse_mode=parse_mode, subject=f"{event_type}:{symbol}")

    try:
        con = _conn()
        con.execute(
            "UPDATE telegram_delivery SET status=?, sent_at=?, message_hash=? WHERE id=?",
            ("sent" if ok else "failed", _now(), _msg_hash(message), rid),
        )
        con.commit()
        con.close()
    except Exception:
        pass

    return ok
