"""
Incident lifecycle manager.
Incidents are stored in operations/incidents.json.
Each incident: id, type, opened_at, diagnosed_at, recovered_at, validated_at, closed_at, status, notes.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone, timedelta
from pathlib import Path

BASE = Path(__file__).parent.parent
INC_PATH = Path(__file__).parent / "incidents.json"
_CAIRO_TZ = timezone(timedelta(hours=2))

INCIDENT_TYPES = {
    "MISSED_MORNING_REPORT",
    "MISSED_SCAN",
    "PRICE_DRIFT",
    "SNAPSHOT_DRIFT",
    "DASHBOARD_DRIFT",
    "PRESENTATION_DRIFT",
    "VALIDATION_FAILURE",
    "DEPLOYMENT_FAILURE",
    "WORKFLOW_FAILURE",
    "PRICE_STALE",
    "EMAIL_DRIFT",
}


def _now() -> str:
    return datetime.now(_CAIRO_TZ).isoformat()


def _load() -> list[dict]:
    if not INC_PATH.exists():
        return []
    try:
        return json.loads(INC_PATH.read_text())
    except Exception:
        return []


def _save(incidents: list[dict]) -> None:
    tmp = INC_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(incidents, indent=2, default=str))
    tmp.replace(INC_PATH)


def open_incident(incident_type: str, note: str = "") -> dict:
    incidents = _load()
    # Deduplicate: don't open same type twice if already open
    for inc in incidents:
        if inc["type"] == incident_type and inc["status"] in ("OPEN", "DIAGNOSED", "RECOVERING"):
            return inc
    inc = {
        "id":           str(uuid.uuid4())[:8],
        "type":         incident_type,
        "status":       "OPEN",
        "opened_at":    _now(),
        "diagnosed_at": None,
        "recovered_at": None,
        "validated_at": None,
        "closed_at":    None,
        "notes":        [note] if note else [],
        "retry_count":  0,
    }
    incidents.append(inc)
    _save(incidents)
    print(f"[Incident] OPENED {incident_type}: {note}")
    return inc


def diagnose_incident(incident_id: str, note: str = "") -> dict | None:
    incidents = _load()
    for inc in incidents:
        if inc["id"] == incident_id:
            inc["status"] = "DIAGNOSED"
            inc["diagnosed_at"] = _now()
            if note:
                inc["notes"].append(f"DIAG: {note}")
            _save(incidents)
            return inc
    return None


def recover_incident(incident_id: str, note: str = "") -> dict | None:
    incidents = _load()
    for inc in incidents:
        if inc["id"] == incident_id:
            inc["status"] = "RECOVERING"
            inc["recovered_at"] = _now()
            inc["retry_count"] = inc.get("retry_count", 0) + 1
            if note:
                inc["notes"].append(f"RECOVERY: {note}")
            _save(incidents)
            return inc
    return None


def validate_incident(incident_id: str, note: str = "") -> dict | None:
    incidents = _load()
    for inc in incidents:
        if inc["id"] == incident_id:
            inc["status"] = "VALIDATED"
            inc["validated_at"] = _now()
            if note:
                inc["notes"].append(f"VALIDATED: {note}")
            _save(incidents)
            return inc
    return None


def close_incident(incident_id: str, note: str = "") -> dict | None:
    incidents = _load()
    for inc in incidents:
        if inc["id"] == incident_id:
            inc["status"] = "CLOSED"
            inc["closed_at"] = _now()
            if note:
                inc["notes"].append(f"CLOSED: {note}")
            _save(incidents)
            print(f"[Incident] CLOSED {inc['type']} ({incident_id})")
            return inc
    return None


def close_by_type(incident_type: str, note: str = "") -> list[dict]:
    incidents = _load()
    closed = []
    for inc in incidents:
        if inc["type"] == incident_type and inc["status"] != "CLOSED":
            inc["status"] = "CLOSED"
            inc["closed_at"] = _now()
            if note:
                inc["notes"].append(f"CLOSED: {note}")
            closed.append(inc)
    _save(incidents)
    return closed


def list_open_incidents() -> list[dict]:
    return [i for i in _load() if i["status"] != "CLOSED"]


def list_recent(limit: int = 20) -> list[dict]:
    return sorted(_load(), key=lambda i: i["opened_at"], reverse=True)[:limit]


def incident_summary() -> dict:
    all_inc = _load()
    open_inc = [i for i in all_inc if i["status"] != "CLOSED"]
    return {
        "total":       len(all_inc),
        "open":        len(open_inc),
        "closed":      len(all_inc) - len(open_inc),
        "open_types":  [i["type"] for i in open_inc],
    }
