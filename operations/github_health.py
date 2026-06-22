"""
GitHub health checker — operations/github_health.py

Checks freshness of:
    heartbeat.json       — must be updated within HEARTBEAT_STALE_HOURS
    operations_state.json — must be updated within STATE_STALE_HOURS
    scan_execution.db    — last successful job must be within SCAN_STALE_HOURS

Returns HEALTHY or FAILED with a detailed reasons list.
Used by external triggers (cron-job.org, Google Apps Script) to decide
whether to fire a repository_dispatch recovery event.
"""
from __future__ import annotations

import json
import sqlite3
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

BASE = Path(__file__).parent.parent
sys.path.insert(0, str(BASE))

_EET = timezone(timedelta(hours=2))

HEARTBEAT_STALE_HOURS      = 2
STATE_STALE_HOURS          = 2
SCAN_STALE_HOURS           = 6      # no scan in 6h on a trading day = stale
SCAN_INTRADAY_STALE_MINS   = 15     # during market hours: stale after 15 min


def _now() -> datetime:
    return datetime.now(_EET)


def _age_hours(iso_str: str | None) -> float | None:
    if not iso_str:
        return None
    try:
        dt = datetime.fromisoformat(iso_str)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=_EET)
        return (_now() - dt).total_seconds() / 3600
    except Exception:
        return None


def _read_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text())
    except Exception:
        return {}


def _last_successful_scan_age() -> float | None:
    try:
        db = BASE / "scan_execution.db"
        if not db.exists():
            return None
        conn = sqlite3.connect(str(db), timeout=5)
        row = conn.execute(
            "SELECT started_at FROM scan_execution "
            "WHERE status IN ('success','recovered') ORDER BY rowid DESC LIMIT 1"
        ).fetchone()
        conn.close()
        return _age_hours(row[0]) if row else None
    except Exception:
        return None


def check() -> dict:
    """
    Run all health checks.
    Returns:
        {
            "status": "HEALTHY" | "FAILED",
            "checks": { name: {"ok": bool, "age_hours": float|None, "reason": str} },
            "reasons": [str],     # only failed reasons
        }
    """
    checks = {}
    reasons = []

    # ── 1. Heartbeat freshness ─────────────────────────────────────────────
    hb = _read_json(BASE / "heartbeat.json")
    hb_age = _age_hours(hb.get("current_cairo_time") or hb.get("updated_at"))
    hb_ok  = hb_age is not None and hb_age < HEARTBEAT_STALE_HOURS
    checks["heartbeat"] = {
        "ok": hb_ok,
        "age_hours": round(hb_age, 2) if hb_age is not None else None,
        "threshold_hours": HEARTBEAT_STALE_HOURS,
        "reason": "" if hb_ok else f"heartbeat stale ({hb_age:.1f}h > {HEARTBEAT_STALE_HOURS}h)" if hb_age else "heartbeat.json missing",
    }
    if not hb_ok:
        reasons.append(checks["heartbeat"]["reason"])

    # ── 2. operations_state freshness ─────────────────────────────────────
    state = _read_json(BASE / "operations_state.json")
    st_age = _age_hours(state.get("current_cairo_time"))
    st_ok  = st_age is not None and st_age < STATE_STALE_HOURS
    checks["operations_state"] = {
        "ok": st_ok,
        "age_hours": round(st_age, 2) if st_age is not None else None,
        "threshold_hours": STATE_STALE_HOURS,
        "reason": "" if st_ok else f"operations_state stale ({st_age:.1f}h)" if st_age else "operations_state.json missing",
    }
    if not st_ok:
        reasons.append(checks["operations_state"]["reason"])

    # ── 3. Last successful scan ────────────────────────────────────────────
    try:
        from time_authority import is_egx_trading_day, today_cairo
        is_trading = is_egx_trading_day(today_cairo())
    except Exception:
        is_trading = True   # conservative: assume trading day

    scan_age = _last_successful_scan_age()
    if is_trading:
        now_h = _now().hour
        now_m = _now().minute
        in_market_hours = (10, 0) <= (now_h, now_m) <= (14, 30)
        if in_market_hours:
            scan_age_min = scan_age * 60 if scan_age is not None else None
            scan_ok = scan_age_min is not None and scan_age_min < SCAN_INTRADAY_STALE_MINS
            scan_reason = "" if scan_ok else (
                f"intraday scan stale ({scan_age_min:.0f} min > {SCAN_INTRADAY_STALE_MINS} min)" if scan_age_min is not None
                else "no successful scan found during market hours"
            )
        else:
            scan_ok = scan_age is not None and scan_age < SCAN_STALE_HOURS
            scan_reason = "" if scan_ok else (
                f"no scan in {scan_age:.1f}h (>{SCAN_STALE_HOURS}h)" if scan_age is not None
                else "no successful scan found"
            )
    else:
        scan_ok = True
        scan_reason = "holiday — scan not required"

    checks["last_scan"] = {
        "ok": scan_ok,
        "age_hours": round(scan_age, 2) if scan_age is not None else None,
        "threshold_hours": SCAN_STALE_HOURS,
        "is_trading_day": is_trading,
        "reason": scan_reason,
    }
    if not scan_ok:
        reasons.append(scan_reason)

    # ── 4. Morning report ──────────────────────────────────────────────────
    try:
        conn = sqlite3.connect(str(BASE / "notification_delivery.db"), timeout=5)
        row = conn.execute(
            "SELECT status, sent_at FROM morning_delivery "
            "WHERE date = date('now', 'localtime') LIMIT 1"
        ).fetchone()
        conn.close()
        morning_sent = row and row[0] == "sent"
    except Exception:
        morning_sent = False

    now = _now()
    morning_required = is_trading and (now.hour, now.minute) >= (7, 30)
    morning_ok = morning_sent or not morning_required
    checks["morning_report"] = {
        "ok": morning_ok,
        "sent": morning_sent,
        "required": morning_required,
        "reason": "" if morning_ok else "morning report not sent and time >= 07:30",
    }
    if not morning_ok:
        reasons.append(checks["morning_report"]["reason"])

    # ── 5. System health from state ────────────────────────────────────────
    state_health = state.get("system_health", "UNKNOWN")
    health_ok = state_health in ("HEALTHY", "WARNING")
    checks["system_health"] = {
        "ok": health_ok,
        "value": state_health,
        "reason": "" if health_ok else f"system_health={state_health}",
    }
    if not health_ok:
        reasons.append(checks["system_health"]["reason"])

    overall = "HEALTHY" if not reasons else "FAILED"

    return {
        "status":    overall,
        "checked_at": _now().isoformat(timespec="seconds"),
        "checks":    checks,
        "reasons":   reasons,
    }


def write_public_status() -> dict:
    """
    Write operations/public_status.json — the public-facing health surface.
    Contains only the fields safe to expose publicly.
    """
    hb    = _read_json(BASE / "heartbeat.json")
    state = _read_json(BASE / "operations_state.json")
    result = check()

    public = {
        "system_health":    result["status"],
        "last_scan":        hb.get("last_scan") or state.get("last_scan"),
        "last_email":       hb.get("last_email") or hb.get("last_morning_report"),
        "last_dashboard":   hb.get("last_dashboard") or hb.get("last_dashboard_refresh"),
        "last_telegram":    hb.get("last_notification"),
        "build_hash":       hb.get("build_hash") or state.get("build_hash"),
        "commit_sha":       hb.get("commit_sha") or hb.get("commit"),
        "checked_at":       _now().isoformat(timespec="seconds"),
        "morning_report":   "SENT" if result["checks"]["morning_report"]["sent"] else "PENDING",
        "scan_age_hours":   result["checks"]["last_scan"]["age_hours"],
    }

    out = BASE / "operations" / "public_status.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(public, indent=2, default=str))
    return public


if __name__ == "__main__":
    result  = check()
    public  = write_public_status()
    print(json.dumps({"health_check": result, "public_status": public}, indent=2))
    sys.exit(0 if result["status"] == "HEALTHY" else 1)
