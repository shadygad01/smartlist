"""
Alert deduplication engine.
Tracks sent alerts in operations/sent_alerts.json.
Only sends: NEW_BUY, NEW_FIRST_BUY, NEW_REACCUMULATION, NEW_ACTIVE, NEW_PREMIUM, NEW_NEAR_ENTRY.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

ALERTS_PATH = Path(__file__).parent / "sent_alerts.json"
sys.path.insert(0, str(Path(__file__).parent.parent))
from time_authority import now_cairo, today_cairo, now_iso, today_iso

ALERT_TYPES = {
    "NEW_BUY",
    "NEW_FIRST_BUY",
    "NEW_REACCUMULATION",
    "NEW_ACTIVE",
    "NEW_PREMIUM",
    "NEW_NEAR_ENTRY",
}


def _now() -> str:
    return now_iso()


def _today() -> str:
    return today_iso()


def _load() -> dict:
    if not ALERTS_PATH.exists():
        return {"sent": []}
    try:
        return json.loads(ALERTS_PATH.read_text())
    except Exception:
        return {"sent": []}


def _save(data: dict) -> None:
    tmp = ALERTS_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2, default=str))
    tmp.replace(ALERTS_PATH)


def _key(alert_type: str, ticker: str, date: str) -> str:
    return f"{alert_type}:{ticker}:{date}"


def already_sent(alert_type: str, ticker: str, date: str | None = None) -> bool:
    date = date or _today()
    k = _key(alert_type, ticker, date)
    data = _load()
    return any(e["key"] == k for e in data["sent"])


def mark_sent(alert_type: str, ticker: str, date: str | None = None) -> None:
    date = date or _today()
    k = _key(alert_type, ticker, date)
    data = _load()
    if not any(e["key"] == k for e in data["sent"]):
        data["sent"].append({"key": k, "ts": _now()})
        # Prune older than 30 days
        cutoff = (now_cairo() - timedelta(days=30)).date().isoformat()
        data["sent"] = [
            e for e in data["sent"]
            if e["key"].split(":")[-1] >= cutoff
        ]
        _save(data)


def check_and_mark(alert_type: str, ticker: str, date: str | None = None) -> bool:
    """Return True if alert should be sent (not a duplicate). Marks as sent."""
    if already_sent(alert_type, ticker, date):
        return False
    mark_sent(alert_type, ticker, date)
    return True


def new_alerts_from_timeline(timeline: list[dict]) -> list[dict]:
    """Return timeline events that haven't been alerted yet."""
    alerts = []
    for e in timeline:
        ticker  = e.get("ticker", "")
        date    = e.get("event_date", _today())
        etype   = e.get("event_type", "")
        atype   = "NEW_FIRST_BUY" if etype == "FIRST_BUY" else "NEW_REACCUMULATION"
        if check_and_mark(atype, ticker, date):
            alerts.append({**e, "alert_type": atype})
    return alerts


def new_near_entry_alerts(approaching: list[dict]) -> list[dict]:
    """Return near-entry items not yet alerted today."""
    alerts = []
    today = _today()
    for e in approaching:
        ticker = e.get("ticker", "")
        if check_and_mark("NEW_NEAR_ENTRY", ticker, today):
            alerts.append({**e, "alert_type": "NEW_NEAR_ENTRY"})
    return alerts
