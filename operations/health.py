"""
Health checker — derives system_status from heartbeat + incidents.
Returns: HEALTHY | WARNING | DEGRADED | CRITICAL
"""
from __future__ import annotations

from datetime import datetime, timezone, timedelta
from pathlib import Path

_CAIRO_TZ = timezone(timedelta(hours=2))
BASE = Path(__file__).parent.parent


def _age_hours(ts: str | None) -> float | None:
    if not ts:
        return None
    try:
        dt = datetime.fromisoformat(ts)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=_CAIRO_TZ)
        return (datetime.now(_CAIRO_TZ) - dt).total_seconds() / 3600
    except Exception:
        return None


def system_health(heartbeat: dict, open_incidents: list[dict]) -> dict:
    """
    Returns {status, reasons, checks} where:
      status  = HEALTHY | WARNING | DEGRADED | CRITICAL
      reasons = list of strings explaining non-healthy status
      checks  = dict of check_name: pass/fail/unknown
    """
    reasons = []
    checks  = {}

    # 1. Open incidents
    critical_types = {"WORKFLOW_FAILURE", "VALIDATION_FAILURE", "DEPLOYMENT_FAILURE"}
    warning_types  = {"MISSED_MORNING_REPORT", "MISSED_SCAN", "PRICE_STALE"}
    open_types     = {i["type"] for i in open_incidents}

    if open_types & critical_types:
        reasons.append(f"Critical incidents open: {open_types & critical_types}")
    if open_types & warning_types:
        reasons.append(f"Warning incidents open: {open_types & warning_types}")

    checks["no_critical_incidents"] = not bool(open_types & critical_types)
    checks["no_warning_incidents"]  = not bool(open_types & warning_types)

    # 2. Heartbeat freshness
    scan_age = _age_hours(heartbeat.get("last_scan"))
    if scan_age is None:
        checks["scan_fresh"] = None
    elif scan_age > 26:
        reasons.append(f"Last scan {scan_age:.1f}h ago (>26h)")
        checks["scan_fresh"] = False
    else:
        checks["scan_fresh"] = True

    email_age = _age_hours(heartbeat.get("last_email"))
    if email_age is None:
        checks["email_fresh"] = None
    elif email_age > 26:
        reasons.append(f"Last email {email_age:.1f}h ago (>26h)")
        checks["email_fresh"] = False
    else:
        checks["email_fresh"] = True

    dashboard_age = _age_hours(heartbeat.get("last_dashboard"))
    if dashboard_age is None:
        checks["dashboard_fresh"] = None
    elif dashboard_age > 26:
        reasons.append(f"Last dashboard {dashboard_age:.1f}h ago (>26h)")
        checks["dashboard_fresh"] = False
    else:
        checks["dashboard_fresh"] = True

    snap_age = _age_hours(heartbeat.get("last_snapshot"))
    if snap_age is None:
        checks["snapshot_fresh"] = None
    elif snap_age > 26:
        reasons.append(f"Last snapshot {snap_age:.1f}h ago (>26h)")
        checks["snapshot_fresh"] = False
    else:
        checks["snapshot_fresh"] = True

    # 3. Validation
    val_passed = heartbeat.get("last_validation_passed")
    if val_passed is False:
        reasons.append("Last golden master validation FAILED")
        checks["validation"] = False
    elif val_passed is True:
        checks["validation"] = True
    else:
        checks["validation"] = None

    # 4. Retry count
    retry_count = heartbeat.get("retry_count", 0)
    if retry_count >= 3:
        reasons.append(f"High retry count: {retry_count}")
        checks["retry_ok"] = False
    else:
        checks["retry_ok"] = True

    # Derive status
    critical = (
        not checks.get("no_critical_incidents", True)
        or checks.get("validation") is False
    )
    degraded = (
        checks.get("scan_fresh") is False
        or checks.get("dashboard_fresh") is False
        or checks.get("retry_ok") is False
    )
    warning = bool(reasons) and not critical and not degraded

    if critical:
        status = "CRITICAL"
    elif degraded:
        status = "DEGRADED"
    elif warning:
        status = "WARNING"
    else:
        status = "HEALTHY"

    return {
        "status":  status,
        "reasons": reasons,
        "checks":  checks,
    }
