"""
Constitutional Time Authority — single source of truth for all time operations.
Egypt uses EET (UTC+2) year-round. No DST since 2011. Never use UTC+3 for Cairo.

ALL files must import from here. Direct datetime.now() calls are prohibited
in operational, presentation, and communications code.
"""
from __future__ import annotations

from datetime import datetime, date, timezone, timedelta

# Egypt Standard Time — UTC+2, no DST
_EET = timezone(timedelta(hours=2))

# EGX trading days: Sun=6, Mon=0, Tue=1, Wed=2, Thu=3
_TRADING_DAYS = {0, 1, 2, 3, 6}

# Market hours in Cairo
_MARKET_OPEN_H,  _MARKET_OPEN_M  = 10,  0
_MARKET_CLOSE_H, _MARKET_CLOSE_M = 14, 30

# Morning report target
_MORNING_H, _MORNING_M = 7, 30


# ── Core accessors ─────────────────────────────────────────────────────────────

def now_cairo() -> datetime:
    """Current datetime in Cairo timezone (EET UTC+2, no DST)."""
    return datetime.now(_EET)


def today_cairo() -> date:
    """Current date in Cairo timezone."""
    return datetime.now(_EET).date()


def now_iso() -> str:
    """ISO-8601 timestamp in Cairo timezone."""
    return datetime.now(_EET).isoformat()


def today_iso() -> str:
    """ISO-8601 date string in Cairo timezone."""
    return datetime.now(_EET).date().isoformat()


# ── Market state ───────────────────────────────────────────────────────────────

def is_trading_day(d: date | None = None) -> bool:
    """Return True if given date (or today) is an EGX trading day (Sun-Thu)."""
    d = d or today_cairo()
    return d.weekday() in _TRADING_DAYS


def is_market_open() -> bool:
    """Return True if EGX market is currently open."""
    now = now_cairo()
    if now.weekday() not in _TRADING_DAYS:
        return False
    mins = now.hour * 60 + now.minute
    open_mins  = _MARKET_OPEN_H  * 60 + _MARKET_OPEN_M
    close_mins = _MARKET_CLOSE_H * 60 + _MARKET_CLOSE_M
    return open_mins <= mins <= close_mins


def market_state() -> str:
    """Return 'OPEN', 'PRE_OPEN', 'CLOSED', or 'WEEKEND'."""
    now = now_cairo()
    if now.weekday() not in _TRADING_DAYS:
        return "WEEKEND"
    mins = now.hour * 60 + now.minute
    open_mins  = _MARKET_OPEN_H  * 60 + _MARKET_OPEN_M
    close_mins = _MARKET_CLOSE_H * 60 + _MARKET_CLOSE_M
    if mins < open_mins:
        return "PRE_OPEN"
    if mins <= close_mins:
        return "OPEN"
    return "CLOSED"


def market_session() -> str:
    """Human-readable session label."""
    state = market_state()
    now = now_cairo()
    labels = {
        "OPEN":     f"Open until {_MARKET_CLOSE_H}:{_MARKET_CLOSE_M:02d} Cairo",
        "PRE_OPEN": f"Pre-open  (opens {_MARKET_OPEN_H}:{_MARKET_OPEN_M:02d} Cairo)",
        "CLOSED":   f"Closed  (opens tomorrow {_MARKET_OPEN_H}:{_MARKET_OPEN_M:02d} Cairo)",
        "WEEKEND":  f"Weekend  (opens Sunday {_MARKET_OPEN_H}:{_MARKET_OPEN_M:02d} Cairo)",
    }
    return labels.get(state, state)


# ── Scheduling helpers ─────────────────────────────────────────────────────────

def next_scan() -> str:
    """ISO timestamp of the next expected EGX scan slot (every 5 min, 10:00-14:30 Cairo)."""
    now = now_cairo()
    d = now
    for _ in range(10):
        if d.weekday() in _TRADING_DAYS:
            open_t  = d.replace(hour=_MARKET_OPEN_H,  minute=_MARKET_OPEN_M,  second=0, microsecond=0)
            close_t = d.replace(hour=_MARKET_CLOSE_H, minute=_MARKET_CLOSE_M, second=0, microsecond=0)
            if d <= open_t:
                return open_t.isoformat()
            if d < close_t:
                nxt = d.replace(minute=0, second=0, microsecond=0) + timedelta(
                    minutes=((d.minute // 5) + 1) * 5 + d.hour * 60
                )
                # simpler: add 5-min slots
                slot_mins = ((d.minute // 5) + 1) * 5
                nxt = d.replace(hour=d.hour, minute=0, second=0, microsecond=0) + timedelta(minutes=slot_mins)
                return min(nxt, close_t).isoformat()
        # advance to next calendar day at market open
        d = (d + timedelta(days=1)).replace(
            hour=_MARKET_OPEN_H, minute=_MARKET_OPEN_M, second=0, microsecond=0
        )
    return ""


def next_morning_report() -> str:
    """ISO timestamp of the next expected morning report (07:30 Cairo, trading days)."""
    now = now_cairo()
    d = now
    for _ in range(10):
        target = d.replace(hour=_MORNING_H, minute=_MORNING_M, second=0, microsecond=0)
        if d.weekday() in _TRADING_DAYS and d < target:
            return target.isoformat()
        d = (d + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    return ""


def scan_slot() -> str:
    """Return current 5-minute scan slot label, e.g. '10:05'."""
    now = now_cairo()
    slot_min = (now.minute // 5) * 5
    return f"{now.hour:02d}:{slot_min:02d}"


# ── Timestamp helpers for heartbeat/presentation ───────────────────────────────

def heartbeat_time() -> str:
    """Canonical timestamp for heartbeat.json."""
    return now_iso()


def presentation_time() -> str:
    """Canonical timestamp for presentation_snapshot.json generated_at."""
    return now_iso()


def build_time() -> str:
    """Human-readable build time for display."""
    return now_cairo().strftime("%Y-%m-%d %H:%M Cairo")


def age_hours(iso_ts: str) -> float:
    """Return hours elapsed since the given ISO timestamp (Cairo-aware)."""
    try:
        dt = datetime.fromisoformat(iso_ts)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=_EET)
        return (now_cairo() - dt).total_seconds() / 3600
    except Exception:
        return float("inf")
