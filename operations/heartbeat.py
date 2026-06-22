"""
Heartbeat — tracks real-time system state in heartbeat.json.
Single writer, multiple readers. Idempotent updates.

Fields written:
    current_cairo_time    — ISO timestamp of last write
    last_scan             — ISO timestamp of last successful scan
    last_scan_status      — 'success' | 'failed' | 'recovered'
    last_morning_report   — ISO timestamp of last morning report sent
    last_dashboard_refresh — ISO timestamp of last dashboard rebuild
    last_notification     — ISO timestamp of last notification sent
    last_email            — ISO timestamp of last email sent
    last_dashboard        — ISO timestamp of last dashboard write (alias)
    last_snapshot         — ISO timestamp of last snapshot build
    last_validation       — ISO timestamp of last validation run
    system_health         — HEALTHY | WARNING | DEGRADED | CRITICAL
    system_status         — alias for system_health (legacy compat)
    build_hash            — MD5[:16] of last morning email HTML
    commit_sha            — git short SHA
    commit                — alias for commit_sha (legacy compat)
    queue_size            — pending notification_delivery rows
    pending_jobs          — PENDING scan_execution rows
    running_jobs          — RUNNING scan_execution rows
    market_date           — YYYY-MM-DD of last scan
    next_scan             — ISO timestamp of next expected scan
    retry_count           — consecutive failure count
    updated_at            — alias for current_cairo_time (legacy compat)
"""
from __future__ import annotations

import json
import sqlite3
import subprocess
from pathlib import Path
import sys

BASE = Path(__file__).parent.parent
sys.path.insert(0, str(BASE))
HB_PATH = BASE / "heartbeat.json"

from time_authority import now_iso, next_scan as _next_scan_ta


def _now() -> str:
    return now_iso()


def _commit() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"], cwd=str(BASE), text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except Exception:
        return ""


def _queue_size() -> int:
    """Count pending notification_delivery rows."""
    try:
        conn = sqlite3.connect(str(BASE / "notification_delivery.db"), timeout=5)
        n = conn.execute(
            "SELECT COUNT(*) FROM notification_delivery WHERE status='pending'"
        ).fetchone()[0]
        conn.close()
        return n
    except Exception:
        return 0


def _scan_job_counts() -> tuple[int, int]:
    """Return (pending_jobs, running_jobs) from scan_execution."""
    try:
        conn = sqlite3.connect(str(BASE / "scan_execution.db"), timeout=5)
        pending = conn.execute(
            "SELECT COUNT(*) FROM scan_execution WHERE status='pending'"
        ).fetchone()[0]
        running = conn.execute(
            "SELECT COUNT(*) FROM scan_execution WHERE status='running'"
        ).fetchone()[0]
        conn.close()
        return pending, running
    except Exception:
        return 0, 0


def read_heartbeat() -> dict:
    if not HB_PATH.exists():
        return {}
    try:
        return json.loads(HB_PATH.read_text())
    except Exception:
        return {}


def update_heartbeat(**fields) -> dict:
    """Merge fields into heartbeat.json and write atomically."""
    hb = read_heartbeat()
    hb.update(fields)

    # Canonical field names (new schema)
    now = _now()
    sha = _commit()
    pending, running = _scan_job_counts()
    hb["current_cairo_time"]     = now
    hb["commit_sha"]             = sha
    hb["queue_size"]             = _queue_size()
    hb["pending_jobs"]           = pending
    hb["running_jobs"]           = running

    # Legacy compat aliases
    hb.setdefault("system_status", hb.get("system_health", "HEALTHY"))
    hb["system_health"]          = hb.get("system_health", hb.get("system_status", "HEALTHY"))
    hb.setdefault("retry_count", 0)
    hb["commit"]                 = sha        # legacy alias
    hb["updated_at"]             = now        # legacy alias

    _write(hb)
    return hb


def _write(data: dict) -> None:
    tmp = HB_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2, default=str))
    tmp.replace(HB_PATH)


def record_scan(market_date: str, build_hash: str = "", status: str = "success") -> dict:
    return update_heartbeat(
        last_scan=_now(),
        last_scan_status=status,
        market_date=market_date,
        build_hash=build_hash,
        commit=_commit(),
        next_scan=compute_next_scan(),
    )


def record_email(market_date: str) -> dict:
    return update_heartbeat(
        last_email=_now(),
        last_morning_report=_now(),
        last_notification=_now(),
        market_date=market_date,
    )


def record_dashboard(build_hash: str = "") -> dict:
    return update_heartbeat(
        last_dashboard=_now(),
        last_dashboard_refresh=_now(),
        build_hash=build_hash,
    )


def record_snapshot(market_date: str) -> dict:
    return update_heartbeat(last_snapshot=_now(), market_date=market_date)


def record_notification(channel: str = "") -> dict:
    return update_heartbeat(last_notification=_now())


def record_validation(passed: bool) -> dict:
    return update_heartbeat(
        last_validation=_now(),
        last_validation_passed=passed,
    )


def record_recovery(incident_type: str, success: bool) -> dict:
    hb = read_heartbeat()
    hb["last_recovery"]         = _now()
    hb["last_recovery_type"]    = incident_type
    hb["last_recovery_success"] = success
    hb["retry_count"]           = 0 if success else hb.get("retry_count", 0) + 1
    _write(hb)
    return hb


def set_status(status: str) -> dict:
    """status: HEALTHY | WARNING | DEGRADED | CRITICAL"""
    return update_heartbeat(system_status=status, system_health=status)


def compute_next_scan() -> str:
    """Return ISO string for next expected EGX scan. Delegates to time_authority."""
    return _next_scan_ta()
