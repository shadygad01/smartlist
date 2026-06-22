"""
Scheduler — defines expected job windows for EGX constitutional operations.
Does NOT run jobs itself (GitHub Actions does). Used for SLA tracking.
"""
from __future__ import annotations

from datetime import datetime, date, timezone, timedelta

_CAIRO_TZ  = timezone(timedelta(hours=2))
_TRADING   = {0, 1, 2, 3, 6}  # Mon-Thu + Sun (EGX)

JOBS = {
    "morning_report": {
        "description": "Constitutional Morning Brief Email",
        "days":        "trading",
        "window_open": (7, 25),   # 07:25 Cairo
        "window_sla":  (7, 45),   # must land by 07:45
    },
    "auto_scan": {
        "description": "Market-hours auto scan (every 5 min)",
        "days":        "trading",
        "window_open": (10, 0),
        "window_sla":  (14, 35),
    },
    "dashboard_build": {
        "description": "Dashboard build & deploy",
        "days":        "trading",
        "window_open": (7, 0),
        "window_sla":  (8, 0),
    },
    "golden_master": {
        "description": "Golden master validation",
        "days":        "trading",
        "window_open": (7, 0),
        "window_sla":  (8, 0),
    },
}


def is_trading_day(d: date | None = None) -> bool:
    d = d or datetime.now(_CAIRO_TZ).date()
    return d.weekday() in _TRADING


def is_market_open() -> bool:
    now = datetime.now(_CAIRO_TZ)
    if now.weekday() not in _TRADING:
        return False
    mins = now.hour * 60 + now.minute
    return 600 <= mins <= 870  # 10:00-14:30


def expected_today(job_name: str) -> bool:
    """Was this job expected to have run today?"""
    job = JOBS.get(job_name)
    if not job:
        return False
    now  = datetime.now(_CAIRO_TZ)
    if job["days"] == "trading" and not is_trading_day():
        return False
    open_h, open_m = job["window_open"]
    open_mins = open_h * 60 + open_m
    cur_mins  = now.hour * 60 + now.minute
    return cur_mins >= open_mins


def sla_violated(job_name: str, last_run_ts: str | None) -> bool:
    """Return True if job is overdue."""
    job = JOBS.get(job_name)
    if not job:
        return False
    if not expected_today(job_name):
        return False
    if not last_run_ts:
        return True
    try:
        last = datetime.fromisoformat(last_run_ts)
        if last.tzinfo is None:
            last = last.replace(tzinfo=_CAIRO_TZ)
        last_date = last.astimezone(_CAIRO_TZ).date()
        today = datetime.now(_CAIRO_TZ).date()
        return last_date < today
    except Exception:
        return True
