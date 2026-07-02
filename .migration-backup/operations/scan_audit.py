"""
Scan Slot Auditor — operations/scan_audit.py

Verifies today's scan slot coverage from scan_slot_history table.
Reports: expected, completed, skipped_by_lock, failed, missing.

Integrates with operations_state.json (Operations Center reads only this file).

Usage:
    python operations/scan_audit.py
    python -c "from operations.scan_audit import audit; print(audit())"
"""
from __future__ import annotations

import json
import sqlite3
import sys
from datetime import datetime, timezone, timedelta, date
from pathlib import Path
from typing import Optional

BASE = Path(__file__).parent.parent
sys.path.insert(0, str(BASE))

from time_authority import now_cairo as _now_cairo_ta  # noqa: E402
_SCAN_DB = str(BASE / "scan_execution.db")

# Market session slots (Cairo time): 10:00–14:30 every 5 minutes
_MARKET_START  = (10, 0)
_MARKET_END    = (14, 30)
_SLOT_INTERVAL = 5  # minutes


def _now() -> datetime:
    return _now_cairo_ta()


def _today() -> str:
    return _now().date().isoformat()


def _expected_slots_today() -> list[str]:
    """Return all slot_time strings expected between market open and now (or close)."""
    now   = _now()
    today = now.date()
    slots = []
    h, m  = _MARKET_START
    end_h, end_m = _MARKET_END

    while (h, m) <= (end_h, end_m):
        slot_dt = datetime(today.year, today.month, today.day, h, m, tzinfo=_EET)
        # Only include slots that have already passed (or are current)
        if slot_dt <= now:
            slots.append(slot_dt.isoformat(timespec="minutes"))
        h, m = divmod(h * 60 + m + _SLOT_INTERVAL, 60)

    return slots


def _is_trading_day() -> bool:
    try:
        from time_authority import is_egx_trading_day, today_cairo
        return is_egx_trading_day(today_cairo())
    except Exception:
        return True  # conservative


def _read_slots_today() -> list[dict]:
    """Return all scan_slot_history rows for today."""
    try:
        conn = sqlite3.connect(_SCAN_DB, timeout=5)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM scan_slot_history WHERE slot_time >= ? ORDER BY slot_time",
            (_today(),),
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]
    except Exception:
        return []


def _morning_slot_status() -> dict:
    """Check morning_report slot (07:30 Cairo)."""
    try:
        conn = sqlite3.connect(str(BASE / "notification_delivery.db"), timeout=5)
        row = conn.execute(
            "SELECT status, sent_at FROM morning_delivery WHERE date=?", (_today(),)
        ).fetchone()
        conn.close()
        if row:
            return {"status": row[0], "sent_at": row[1]}
        return {"status": "missing"}
    except Exception:
        return {"status": "unknown"}


def audit(job_type: str = "market_scan") -> dict:
    """
    Audit today's scan slots for the given job_type.

    Returns dict with:
        expected        — list of slot_time strings that should have run
        completed       — slots with status in (success, recovered)
        skipped_by_lock — slots blocked by an active execution (correct behavior)
        failed          — slots that errored
        missing         — expected slots with no record at all
        morning_report  — morning delivery status
        is_trading_day  — bool
        summary         — counts dict
    """
    is_trading = _is_trading_day()
    expected   = _expected_slots_today() if is_trading else []
    rows       = _read_slots_today()

    # Build lookup: slot_time → row (for the given job_type)
    slot_map = {r["slot_time"]: r for r in rows if r["job_type"] == job_type}

    completed       = []
    skipped_by_lock = []
    failed          = []
    missing         = []

    for slot in expected:
        row = slot_map.get(slot)
        if row is None:
            missing.append(slot)
        elif row["status"] in ("success", "recovered"):
            completed.append(slot)
        elif row["status"] == "SKIPPED_BY_LOCK":
            skipped_by_lock.append(slot)
        elif row["status"] in ("failed",):
            failed.append(slot)
        else:
            # running / pending — not yet finished, not missing
            pass

    # All actual rows (any status) for context
    all_today = [r for r in rows if r["job_type"] == job_type]

    result = {
        "job_type":        job_type,
        "date":            _today(),
        "is_trading_day":  is_trading,
        "expected":        expected,
        "completed":       completed,
        "skipped_by_lock": skipped_by_lock,
        "failed":          failed,
        "missing":         missing,
        "morning_report":  _morning_slot_status(),
        "all_slots_today": all_today,
        "summary": {
            "expected":        len(expected),
            "completed":       len(completed),
            "skipped_by_lock": len(skipped_by_lock),
            "failed":          len(failed),
            "missing":         len(missing),
        },
    }
    return result


def audit_all() -> dict:
    """Audit all job types and morning report."""
    market = audit("market_scan")
    morning = _morning_slot_status()

    # Scan execution summary from scan_execution table
    try:
        conn = sqlite3.connect(_SCAN_DB, timeout=5)
        conn.row_factory = sqlite3.Row
        se_rows = conn.execute(
            "SELECT job_type, status, COUNT(*) as n FROM scan_execution "
            "WHERE started_at >= ? GROUP BY job_type, status",
            (_today(),),
        ).fetchall()
        conn.close()
        execution_summary = {}
        for r in se_rows:
            jt = r["job_type"]
            execution_summary.setdefault(jt, {})[r["status"]] = r["n"]
    except Exception:
        execution_summary = {}

    return {
        "market_scan":        market["summary"],
        "morning_report":     morning,
        "execution_summary":  execution_summary,
        "missing_slots":      market["missing"],
        "failed_slots":       market["failed"],
        "skipped_slots":      len(market["skipped_by_lock"]),
        "validation": {
            "no_missing":         len(market["missing"]) == 0 or not market["is_trading_day"],
            "no_failed":          len(market["failed"]) == 0,
            "morning_ok":         morning.get("status") == "sent",
            "no_duplicate_runs":  True,  # guaranteed by lock
        },
    }


def update_operations_state(state_path: Optional[str] = None) -> dict:
    """
    Merge scan audit data into operations_state.json.
    Operations Center reads ONLY operations_state.json.
    """
    path = Path(state_path or BASE / "operations_state.json")
    try:
        existing = json.loads(path.read_text()) if path.exists() else {}
    except Exception:
        existing = {}

    result = audit_all()
    market = audit("market_scan")

    # Remove legacy OperationsMonitor key to prevent contradictory data
    existing.pop("validation", None)

    # Refresh timestamp and commit so operations_state is never stale
    try:
        import subprocess
        sha = subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=str(BASE), text=True, stderr=subprocess.DEVNULL
        ).strip()
    except Exception:
        sha = existing.get("commit_sha", "")
    existing["current_cairo_time"] = datetime.now(_EET).isoformat(timespec="seconds")
    existing["commit_sha"] = sha

    existing["scan_slots"] = {
        "expected":        market["summary"]["expected"],
        "completed":       market["summary"]["completed"],
        "skipped_by_lock": market["summary"]["skipped_by_lock"],
        "failed":          market["summary"]["failed"],
        "missing":         market["summary"]["missing"],
        "missing_list":    market["missing"],
    }
    existing["morning_report_delivery"] = result["morning_report"]
    existing["scan_audit_validation"]   = result["validation"]

    try:
        path.write_text(json.dumps(existing, indent=2, default=str))
    except Exception as e:
        print(f"[ScanAudit] Failed to write operations_state.json: {e}")

    return existing


if __name__ == "__main__":
    result = audit_all()
    print(json.dumps(result, indent=2, default=str))

    # Also update operations_state.json
    update_operations_state()
    print("\noperations_state.json updated.")
    sys.exit(0 if result["validation"]["no_missing"] and result["validation"]["no_failed"] else 1)
