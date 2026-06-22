"""
Notification delivery log — notification_delivery.db (SQLite).
Append-only. Tracks every send attempt with UUID, channel, status, timing, retries.
"""
from __future__ import annotations

import sqlite3
import uuid
from datetime import datetime, timezone, timedelta
from pathlib import Path
import sys as _sys
_sys.path.insert(0, str(Path(__file__).parent.parent))
from time_authority import now_cairo as _now_cairo_ta

_DB_PATH = Path(__file__).parent.parent / "notification_delivery.db"


def _now() -> str:
    return _now_cairo_ta().isoformat()


def _conn() -> sqlite3.Connection:
    con = sqlite3.connect(str(_DB_PATH), timeout=10)
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("""
        CREATE TABLE IF NOT EXISTS notification_delivery (
            id          TEXT PRIMARY KEY,
            channel     TEXT NOT NULL,
            recipient   TEXT,
            subject     TEXT,
            status      TEXT NOT NULL DEFAULT 'pending',
            created_at  TEXT NOT NULL,
            sent_at     TEXT,
            retry_count INTEGER NOT NULL DEFAULT 0,
            error       TEXT
        )
    """)
    con.commit()
    return con


def record_attempt(channel: str, recipient: str = "", subject: str = "") -> str:
    """Insert a pending record and return its UUID."""
    rid = str(uuid.uuid4())
    con = _conn()
    con.execute(
        "INSERT INTO notification_delivery (id, channel, recipient, subject, created_at) VALUES (?,?,?,?,?)",
        (rid, channel, recipient, subject, _now()),
    )
    con.commit()
    con.close()
    return rid


def record_success(rid: str, retry_count: int = 0) -> None:
    con = _conn()
    con.execute(
        "UPDATE notification_delivery SET status='sent', sent_at=?, retry_count=? WHERE id=?",
        (_now(), retry_count, rid),
    )
    con.commit()
    con.close()


def record_failure(rid: str, error: str, retry_count: int = 0) -> None:
    con = _conn()
    con.execute(
        "UPDATE notification_delivery SET status='failed', error=?, retry_count=?, sent_at=? WHERE id=?",
        (str(error)[:500], retry_count, _now(), rid),
    )
    con.commit()
    con.close()


def recent(limit: int = 50) -> list[dict]:
    try:
        con = _conn()
        rows = con.execute(
            "SELECT * FROM notification_delivery ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
        cols = [d[0] for d in con.execute("SELECT * FROM notification_delivery LIMIT 0").description or []]
        con.close()
        if not cols:
            con2 = _conn()
            cols = [d[0] for d in con2.execute("PRAGMA table_info(notification_delivery)").fetchall()]
            # pragma returns (cid,name,...) — just use SELECT * description trick below
            con2.close()
        con3 = _conn()
        cur = con3.execute("SELECT * FROM notification_delivery ORDER BY created_at DESC LIMIT ?", (limit,))
        cols = [d[0] for d in cur.description]
        rows = cur.fetchall()
        con3.close()
        return [dict(zip(cols, r)) for r in rows]
    except Exception:
        return []
