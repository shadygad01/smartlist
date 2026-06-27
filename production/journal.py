"""
Execution Journal — Constitutional Architecture Phase 11 (Phase 7).

Immutable forensic log of every production side effect.

Every call to ProductionTransaction.execute() writes one row:
    scan_id, phase, operation_name, status, started_at, finished_at, artifact, error

Table: production_execution_journal in notification_delivery.db
Idempotent: rows are INSERT — never UPDATE. The journal is append-only.
"""
from __future__ import annotations

import hashlib
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

BASE     = Path(__file__).parent.parent
_DB_PATH = BASE / "notification_delivery.db"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def _conn() -> sqlite3.Connection:
    con = sqlite3.connect(str(_DB_PATH), timeout=15)
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("""
        CREATE TABLE IF NOT EXISTS production_execution_journal (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            scan_id      TEXT    NOT NULL,
            phase        TEXT    NOT NULL,
            phase_order  INTEGER NOT NULL,
            operation    TEXT    NOT NULL,
            status       TEXT    NOT NULL,
            started_at   TEXT    NOT NULL,
            finished_at  TEXT,
            artifact     TEXT    DEFAULT '',
            checksum     TEXT    DEFAULT '',
            error        TEXT    DEFAULT ''
        )
    """)
    con.execute(
        "CREATE INDEX IF NOT EXISTS idx_pej_scan_id "
        "ON production_execution_journal(scan_id)"
    )
    con.commit()
    return con


def record(
    scan_id:     str,
    phase:       str,
    phase_order: int,
    operation:   str,
    status:      str,
    started_at:  str,
    finished_at: Optional[str] = None,
    artifact:    str = "",
    checksum:    str = "",
    error:       str = "",
) -> None:
    """Append one immutable journal row. Non-fatal on any DB error."""
    try:
        con = _conn()
        con.execute(
            """INSERT INTO production_execution_journal
               (scan_id, phase, phase_order, operation, status,
                started_at, finished_at, artifact, checksum, error)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (scan_id, phase, phase_order, operation, status,
             started_at, finished_at or _now(), artifact, checksum, error[:2000]),
        )
        con.commit()
        con.close()
    except Exception as exc:
        print(f"[Journal] non-fatal write error: {exc}")


def query_scan(scan_id: str) -> list[dict]:
    """Return all journal rows for a given scan_id, in phase order."""
    try:
        con = _conn()
        con.row_factory = sqlite3.Row
        rows = con.execute(
            "SELECT * FROM production_execution_journal WHERE scan_id=? ORDER BY id",
            (scan_id,),
        ).fetchall()
        con.close()
        return [dict(r) for r in rows]
    except Exception:
        return []


def latest_scan_rows(limit: int = 50) -> list[dict]:
    """Return the most recent N journal rows across all scans."""
    try:
        con = _conn()
        con.row_factory = sqlite3.Row
        rows = con.execute(
            "SELECT * FROM production_execution_journal ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
        con.close()
        return [dict(r) for r in rows]
    except Exception:
        return []


def artifact_checksum(content: str) -> str:
    """Return MD5 hex of string content (16 chars)."""
    return hashlib.md5(content.encode()).hexdigest()[:16]
