"""
Heartbeat — tracks real-time system state in heartbeat.json.
Single writer, multiple readers. Idempotent updates.
"""
from __future__ import annotations

import json
import sys
import subprocess
from pathlib import Path

BASE = Path(__file__).parent.parent
sys.path.insert(0, str(BASE))
HB_PATH = BASE / "heartbeat.json"

from time_authority import now_iso, next_scan as _next_scan_ta


def _now() -> str:
    return now_iso()


def _commit() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"], cwd=str(BASE), text=True
        ).strip()
    except Exception:
        return ""


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
    hb.setdefault("system_status", "HEALTHY")
    hb.setdefault("retry_count", 0)
    hb.setdefault("commit", _commit())
    hb["updated_at"] = _now()
    _write(hb)
    return hb


def _write(data: dict) -> None:
    tmp = HB_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2, default=str))
    tmp.replace(HB_PATH)


def record_scan(market_date: str, build_hash: str = "") -> dict:
    return update_heartbeat(
        last_scan=_now(),
        market_date=market_date,
        build_hash=build_hash,
        commit=_commit(),
    )


def record_email(market_date: str) -> dict:
    return update_heartbeat(last_email=_now(), market_date=market_date)


def record_dashboard(build_hash: str = "") -> dict:
    return update_heartbeat(last_dashboard=_now(), build_hash=build_hash)


def record_snapshot(market_date: str) -> dict:
    return update_heartbeat(last_snapshot=_now(), market_date=market_date)


def record_validation(passed: bool) -> dict:
    return update_heartbeat(
        last_validation=_now(),
        last_validation_passed=passed,
    )


def record_recovery(incident_type: str, success: bool) -> dict:
    hb = read_heartbeat()
    hb["last_recovery"] = _now()
    hb["last_recovery_type"] = incident_type
    hb["last_recovery_success"] = success
    if not success:
        hb["retry_count"] = hb.get("retry_count", 0) + 1
    else:
        hb["retry_count"] = 0
    _write(hb)
    return hb


def set_status(status: str) -> dict:
    """status: HEALTHY | WARNING | DEGRADED | CRITICAL"""
    return update_heartbeat(system_status=status)


def compute_next_scan() -> str:
    """Return ISO string for next expected EGX scan. Delegates to time_authority."""
    return _next_scan_ta()
