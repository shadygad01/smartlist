"""
SLA tracker — stores 30d/90d reliability metrics in operations/sla.json.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone, timedelta
from pathlib import Path

SLA_PATH = Path(__file__).parent / "sla.json"
_CAIRO_TZ = timezone(timedelta(hours=2))


def _now() -> str:
    return datetime.now(_CAIRO_TZ).isoformat()


def _today() -> str:
    return datetime.now(_CAIRO_TZ).date().isoformat()


def _load() -> dict:
    if not SLA_PATH.exists():
        return {"events": []}
    try:
        return json.loads(SLA_PATH.read_text())
    except Exception:
        return {"events": []}


def _save(data: dict) -> None:
    tmp = SLA_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2, default=str))
    tmp.replace(SLA_PATH)


def record_event(event_type: str, success: bool, note: str = "") -> None:
    """
    event_type: morning_report | scan | dashboard | deployment | validation | recovery
    """
    data = _load()
    data["events"].append({
        "ts":         _now(),
        "date":       _today(),
        "type":       event_type,
        "success":    success,
        "note":       note,
    })
    # Prune older than 90 days
    cutoff = (datetime.now(_CAIRO_TZ) - timedelta(days=90)).date().isoformat()
    data["events"] = [e for e in data["events"] if e.get("date", "9999") >= cutoff]
    _save(data)


def compute_metrics(days: int = 30) -> dict:
    """Return reliability metrics for the last N days."""
    data = _load()
    cutoff = (datetime.now(_CAIRO_TZ) - timedelta(days=days)).date().isoformat()
    events = [e for e in data["events"] if e.get("date", "") >= cutoff]

    def _rate(etype: str) -> dict:
        subset = [e for e in events if e["type"] == etype]
        if not subset:
            return {"total": 0, "success": 0, "pct": None}
        ok = sum(1 for e in subset if e["success"])
        return {"total": len(subset), "success": ok, "pct": round(ok / len(subset) * 100, 1)}

    morning   = _rate("morning_report")
    scans     = _rate("scan")
    dashboards= _rate("dashboard")
    deploys   = _rate("deployment")
    validations=_rate("validation")
    recoveries= _rate("recovery")

    # Overall reliability = morning+scan+deploy success / total
    total   = morning["total"] + scans["total"] + deploys["total"]
    success = morning["success"] + scans["success"] + deploys["success"]
    overall = round(success / total * 100, 1) if total else None

    return {
        "days":         days,
        "overall_pct":  overall,
        "morning":      morning,
        "scans":        scans,
        "dashboards":   dashboards,
        "deployments":  deploys,
        "validations":  validations,
        "recoveries":   recoveries,
    }


def reliability_label(pct: float | None) -> str:
    if pct is None:
        return "N/A"
    if pct >= 99:
        return f"{pct:.1f}% ✓"
    if pct >= 95:
        return f"{pct:.1f}% ⚠"
    return f"{pct:.1f}% ✗"
