"""
Recovery knowledge base — stores what worked, what failed, patterns.
Stored in operations/knowledge.json.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

KB_PATH = Path(__file__).parent / "knowledge.json"
sys.path.insert(0, str(Path(__file__).parent.parent))
from time_authority import now_iso


def _now() -> str:
    return now_iso()


def _load() -> dict:
    if not KB_PATH.exists():
        return {"recoveries": [], "patterns": {}}
    try:
        return json.loads(KB_PATH.read_text())
    except Exception:
        return {"recoveries": [], "patterns": {}}


def _save(data: dict) -> None:
    tmp = KB_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2, default=str))
    tmp.replace(KB_PATH)


def record_recovery(incident_type: str, action: str, success: bool, duration_s: float = 0) -> None:
    data = _load()
    data["recoveries"].append({
        "ts":           _now(),
        "incident_type": incident_type,
        "action":       action,
        "success":      success,
        "duration_s":   round(duration_s, 1),
    })
    # Update pattern success rates
    key = f"{incident_type}:{action}"
    p = data["patterns"].setdefault(key, {"total": 0, "success": 0})
    p["total"] += 1
    if success:
        p["success"] += 1
    p["rate"] = round(p["success"] / p["total"] * 100, 1)
    # Keep last 200 recovery events
    data["recoveries"] = data["recoveries"][-200:]
    _save(data)


def best_recovery_action(incident_type: str) -> str | None:
    data = _load()
    candidates = {
        k: v for k, v in data["patterns"].items()
        if k.startswith(f"{incident_type}:") and v["total"] >= 2
    }
    if not candidates:
        return None
    best = max(candidates.items(), key=lambda x: x[1]["rate"])
    return best[0].split(":", 1)[1]


def summary() -> list[dict]:
    data = _load()
    return [
        {"pattern": k, **v}
        for k, v in sorted(
            data["patterns"].items(),
            key=lambda x: -x[1].get("rate", 0)
        )
    ]
