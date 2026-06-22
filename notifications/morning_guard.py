"""
Morning delivery guard — one morning report per calendar day.
Idempotency key: YYYY-MM-DD (one per trading day, morning slot).
Table: morning_delivery in notification_delivery.db.
"""
from __future__ import annotations

import hashlib
import json
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
        CREATE TABLE IF NOT EXISTS morning_delivery (
            id            TEXT PRIMARY KEY,
            date          TEXT NOT NULL UNIQUE,
            generated_at  TEXT NOT NULL,
            sent_at       TEXT,
            status        TEXT NOT NULL DEFAULT 'pending',
            build_hash    TEXT,
            snapshot_hash TEXT
        )
    """)
    con.commit()
    return con


def is_morning_sent(date_str: str) -> bool:
    """Return True if morning report for this date was already successfully sent."""
    try:
        con = _conn()
        row = con.execute(
            "SELECT status FROM morning_delivery WHERE date=?", (date_str,)
        ).fetchone()
        con.close()
        return row is not None and row[0] == "sent"
    except Exception:
        return False


def record_morning_start(date_str: str) -> str:
    """
    Insert a pending record for today. Returns UUID.
    If a record already exists (duplicate run), returns the existing UUID.
    """
    mid = str(uuid.uuid4())
    try:
        con = _conn()
        con.execute(
            "INSERT OR IGNORE INTO morning_delivery (id, date, generated_at) VALUES (?,?,?)",
            (mid, date_str, _now()),
        )
        con.commit()
        row = con.execute("SELECT id FROM morning_delivery WHERE date=?", (date_str,)).fetchone()
        con.close()
        return row[0] if row else mid
    except Exception:
        return mid


def record_morning_done(mid: str, status: str, build_hash: str = "", snapshot_hash: str = "") -> None:
    """Update record with final status, sent_at timestamp, and content hashes."""
    try:
        con = _conn()
        con.execute(
            "UPDATE morning_delivery SET status=?, sent_at=?, build_hash=?, snapshot_hash=? WHERE id=?",
            (status, _now(), build_hash, snapshot_hash, mid),
        )
        con.commit()
        con.close()
    except Exception:
        pass


def html_hash(html: str) -> str:
    return hashlib.md5(html.encode()).hexdigest()[:16]


def snap_hash(snap) -> str:
    import dataclasses
    try:
        return hashlib.md5(
            json.dumps(dataclasses.asdict(snap), default=str, sort_keys=True).encode()
        ).hexdigest()[:16]
    except Exception:
        return ""
