"""
Self-healing recovery engine.
All recoveries are idempotent. Each returns True on success.
"""
from __future__ import annotations

import sys
import time
from datetime import datetime
from pathlib import Path

BASE = Path(__file__).parent.parent
sys.path.insert(0, str(BASE))
from time_authority import now_cairo, today_cairo, now_iso, today_iso, age_hours



def _log(msg: str) -> None:
    ts = now_cairo().strftime("%H:%M:%S")
    print(f"[Recovery {ts}] {msg}")


# ── Individual recovery actions ────────────────────────────────────────────────

def rebuild_universe_snapshot() -> bool:
    """Rebuild universe_snapshot.db from all sources."""
    try:
        from universe_snapshot import build_universe_snapshot
        rows = build_universe_snapshot()
        _log(f"universe_snapshot rebuilt — {len(rows)} tickers")
        return True
    except Exception as e:
        _log(f"FAILED rebuild_universe_snapshot: {e}")
        return False


def rebuild_stock_dna() -> bool:
    try:
        from stock_dna_engine import build_stock_dna
        build_stock_dna()
        _log("stock_dna rebuilt")
        return True
    except Exception as e:
        _log(f"FAILED rebuild_stock_dna: {e}")
        return False


def rebuild_presentation_snapshot() -> bool:
    try:
        from presentation.presentation_snapshot import (
            build_presentation_snapshot, write_presentation_snapshot_json
        )
        snap = build_presentation_snapshot()
        write_presentation_snapshot_json(snap)
        _log(f"presentation_snapshot rebuilt — {len(snap.universe_snapshot)} tickers")
        return True
    except Exception as e:
        _log(f"FAILED rebuild_presentation_snapshot: {e}")
        return False


def rebuild_dashboard() -> bool:
    try:
        import subprocess
        result = subprocess.run(
            [sys.executable, str(BASE / "dashboard.py")],
            cwd=str(BASE), capture_output=True, text=True, timeout=120
        )
        if result.returncode == 0:
            _log("dashboard rebuilt")
            return True
        _log(f"FAILED rebuild_dashboard: {result.stderr[-300:]}")
        return False
    except Exception as e:
        _log(f"FAILED rebuild_dashboard: {e}")
        return False


def send_morning_email() -> bool:
    try:
        import os
        if not os.getenv("EMAIL_USER") or not os.getenv("EMAIL_PASS"):
            _log("Email env not set — skipping send")
            return True  # Not a failure, just not configured
        from presentation.presentation_snapshot import build_presentation_snapshot
        from email_v2 import build_email
        snap = build_presentation_snapshot()
        html = build_email(snap)
        _log(f"Morning email built ({len(html)//1024} KB) — send via existing alert_email path")
        # Trigger the email sender in main.py-compatible way
        import smtplib
        from email.mime.multipart import MIMEMultipart
        from email.mime.text import MIMEText
        from datetime import datetime
        user = os.getenv("EMAIL_USER")
        pwd  = os.getenv("EMAIL_PASS")
        msg  = MIMEMultipart("alternative")
        msg["Subject"] = f"EGX Constitutional Morning Brief — {now_cairo().strftime('%d %b %Y')}"
        msg["From"]    = user
        msg["To"]      = user
        msg.attach(MIMEText(html, "html"))
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as s:
            s.login(user, pwd)
            s.send_message(msg)
        _log("Morning email sent")
        return True
    except Exception as e:
        _log(f"FAILED send_morning_email: {e}")
        return False


def refresh_prices() -> bool:
    """Refresh latest prices from yfinance into signal_history."""
    try:
        import subprocess
        result = subprocess.run(
            [sys.executable, "main.py"],
            cwd=str(BASE), capture_output=True, text=True,
            timeout=300, env={**__import__("os").environ, "MANUAL_RUN": "True"}
        )
        _log(f"Price refresh: returncode={result.returncode}")
        return result.returncode == 0
    except Exception as e:
        _log(f"FAILED refresh_prices: {e}")
        return False


def validate_presentation_consistency() -> bool:
    try:
        import subprocess
        result = subprocess.run(
            [sys.executable, "audit/assert_presentation_consistency.py"],
            cwd=str(BASE), capture_output=True, text=True, timeout=30
        )
        passed = result.returncode == 0
        _log(f"Presentation consistency: {'PASS' if passed else 'FAIL'}")
        if not passed:
            _log(result.stdout[-300:])
        return passed
    except Exception as e:
        _log(f"FAILED validate_presentation_consistency: {e}")
        return False


def validate_price_freshness() -> bool:
    try:
        import subprocess
        result = subprocess.run(
            [sys.executable, "audit/assert_price_freshness.py"],
            cwd=str(BASE), capture_output=True, text=True, timeout=30
        )
        passed = result.returncode == 0
        _log(f"Price freshness: {'PASS' if passed else 'FAIL'}")
        return passed
    except Exception as e:
        _log(f"FAILED validate_price_freshness: {e}")
        return False


# ── Decision tree recoveries ───────────────────────────────────────────────────

def recover_stale_snapshot(max_retries: int = 2) -> bool:
    """Snapshot stale → rebuild universe → dna → presentation → validate."""
    from .knowledge import record_recovery
    _log("RECOVERY: stale snapshot")
    t0 = time.time()
    ok = (
        rebuild_universe_snapshot()
        and rebuild_stock_dna()
        and rebuild_presentation_snapshot()
        and validate_presentation_consistency()
    )
    record_recovery("SNAPSHOT_DRIFT", "rebuild_universe+dna+presentation", ok, time.time() - t0)
    return ok


def recover_stale_price(max_retries: int = 2) -> bool:
    """Price stale → refresh → validate freshness."""
    from .knowledge import record_recovery
    _log("RECOVERY: stale price")
    t0 = time.time()
    ok = (
        rebuild_universe_snapshot()
        and validate_price_freshness()
    )
    record_recovery("PRICE_STALE", "rebuild_universe+validate_freshness", ok, time.time() - t0)
    return ok


def recover_stale_dashboard() -> bool:
    """Dashboard stale → rebuild presentation → rebuild dashboard → validate."""
    from .knowledge import record_recovery
    _log("RECOVERY: stale dashboard")
    t0 = time.time()
    ok = (
        rebuild_presentation_snapshot()
        and rebuild_dashboard()
        and validate_presentation_consistency()
    )
    record_recovery("DASHBOARD_DRIFT", "rebuild_presentation+dashboard", ok, time.time() - t0)
    return ok


def recover_missing_email() -> bool:
    """Morning email missing → rebuild snapshot → rebuild email → send."""
    from .knowledge import record_recovery
    _log("RECOVERY: missing morning email")
    t0 = time.time()
    ok = (
        rebuild_presentation_snapshot()
        and send_morning_email()
    )
    record_recovery("MISSED_MORNING_REPORT", "rebuild_snapshot+send_email", ok, time.time() - t0)
    return ok
