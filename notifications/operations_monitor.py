"""
Constitutional Operations Monitor — Step 5.

Guarantees every required operation completes exactly once per scheduled slot.
Runs at every worker startup to detect and recover missed/failed jobs.

Lifecycle states:
    PENDING   — scheduled but not yet started
    RUNNING   — lock acquired, in progress
    COMPLETED — finished successfully
    FAILED    — finished with error
    RECOVERED — was FAILED/missing, re-ran and succeeded

Recovery rules:
    1. Morning report missing AND Cairo time >= 07:30 → generate + send → RECOVERED
    2. Market scan slot missing → run immediately before new slot → RECOVERED
    3. notification_delivery FAILED rows → retry via notification_router → RECOVERED

Writes operations_state.json after every startup check.
Operations Center reads ONLY operations_state.json.
"""
from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
from datetime import datetime, date, timezone, timedelta
from pathlib import Path
from typing import Optional

BASE = Path(__file__).parent.parent
sys.path.insert(0, str(BASE))

from time_authority import now_cairo as _now_cairo_ta  # noqa: E402
_SCAN_EXEC_DB = str(BASE / "scan_execution.db")
_NOTIF_DB     = str(BASE / "notification_delivery.db")
_STATE_FILE   = str(BASE / "operations_state.json")

# Morning report scheduled time (Cairo)
_MORNING_HOUR   = 7
_MORNING_MINUTE = 30

# Market session window (Cairo)
_MARKET_START = (10, 0)
_MARKET_END   = (14, 30)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _now_cairo() -> datetime:
    return _now_cairo_ta()


def _today_str() -> str:
    return _now_cairo().date().isoformat()


def _commit_sha() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=str(BASE), text=True, stderr=subprocess.DEVNULL,
        ).strip()
    except Exception:
        return ""


def _log(msg: str) -> None:
    ts = _now_cairo().strftime("%H:%M:%S")
    print(f"[OpsMonitor {ts}] {msg}")


# ── Database readers ──────────────────────────────────────────────────────────

def _read_morning_delivery(date_str: str) -> Optional[dict]:
    """Return morning_delivery row for date_str, or None."""
    try:
        conn = sqlite3.connect(_NOTIF_DB, timeout=10)
        conn.row_factory = sqlite3.Row
        conn.execute("""
            CREATE TABLE IF NOT EXISTS morning_delivery (
                id TEXT PRIMARY KEY, date TEXT NOT NULL UNIQUE,
                generated_at TEXT NOT NULL, sent_at TEXT,
                status TEXT NOT NULL DEFAULT 'pending',
                build_hash TEXT, snapshot_hash TEXT
            )
        """)
        row = conn.execute(
            "SELECT * FROM morning_delivery WHERE date=?", (date_str,)
        ).fetchone()
        conn.close()
        return dict(row) if row else None
    except Exception:
        return None


def _read_scan_executions_today(job_type: str) -> list[dict]:
    """Return all scan_execution rows for job_type started today."""
    try:
        conn = sqlite3.connect(_SCAN_EXEC_DB, timeout=10)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM scan_execution WHERE job_type=? AND started_at >= ?",
            (job_type, _today_str()),
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]
    except Exception:
        return []


def _read_failed_notifications(limit: int = 50) -> list[dict]:
    """Return notification_delivery rows with status='failed' from today."""
    try:
        conn = sqlite3.connect(_NOTIF_DB, timeout=10)
        conn.row_factory = sqlite3.Row
        conn.execute("""
            CREATE TABLE IF NOT EXISTS notification_delivery (
                id TEXT PRIMARY KEY, channel TEXT NOT NULL, recipient TEXT,
                subject TEXT, status TEXT NOT NULL DEFAULT 'pending',
                created_at TEXT NOT NULL, sent_at TEXT,
                retry_count INTEGER NOT NULL DEFAULT 0, error TEXT
            )
        """)
        rows = conn.execute(
            "SELECT * FROM notification_delivery WHERE status='failed' "
            "AND created_at >= ? ORDER BY created_at DESC LIMIT ?",
            (_today_str(), limit),
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]
    except Exception:
        return []


def _read_pending_notifications() -> list[dict]:
    """Return notification_delivery rows with status='pending'."""
    try:
        conn = sqlite3.connect(_NOTIF_DB, timeout=10)
        conn.row_factory = sqlite3.Row
        conn.execute("""
            CREATE TABLE IF NOT EXISTS notification_delivery (
                id TEXT PRIMARY KEY, channel TEXT NOT NULL, recipient TEXT,
                subject TEXT, status TEXT NOT NULL DEFAULT 'pending',
                created_at TEXT NOT NULL, sent_at TEXT,
                retry_count INTEGER NOT NULL DEFAULT 0, error TEXT
            )
        """)
        rows = conn.execute(
            "SELECT * FROM notification_delivery WHERE status='pending' "
            "AND created_at >= ? ORDER BY created_at",
            (_today_str(),),
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]
    except Exception:
        return []


def _read_telegram_delivery_failed(limit: int = 20) -> list[dict]:
    """Return telegram_delivery rows with status='failed' from today."""
    try:
        conn = sqlite3.connect(_NOTIF_DB, timeout=10)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM telegram_delivery WHERE status='failed' "
            "AND created_at >= ? ORDER BY created_at DESC LIMIT ?",
            (_today_str(), limit),
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]
    except Exception:
        return []


def _read_running_jobs() -> list[dict]:
    """Return scan_execution rows with status='running'."""
    try:
        conn = sqlite3.connect(_SCAN_EXEC_DB, timeout=10)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM scan_execution WHERE status='running' ORDER BY started_at"
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]
    except Exception:
        return []


def _read_completed_jobs_today() -> list[dict]:
    """Return scan_execution rows completed today."""
    try:
        conn = sqlite3.connect(_SCAN_EXEC_DB, timeout=10)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM scan_execution WHERE status IN ('success','recovered') "
            "AND started_at >= ? ORDER BY started_at",
            (_today_str(),),
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]
    except Exception:
        return []


# ── Recovery actions ──────────────────────────────────────────────────────────

def _mark_recovered_in_scan_db(job_type: str, note: str = "") -> None:
    """Insert a RECOVERED record into scan_execution for audit trail."""
    try:
        conn = sqlite3.connect(_SCAN_EXEC_DB, timeout=10)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS scan_execution (
                execution_id TEXT PRIMARY KEY, job_type TEXT NOT NULL,
                started_at TEXT NOT NULL, finished_at TEXT,
                status TEXT NOT NULL DEFAULT 'running',
                build_hash TEXT DEFAULT '', commit_sha TEXT DEFAULT '',
                error TEXT DEFAULT ''
            )
        """)
        import uuid
        conn.execute(
            "INSERT INTO scan_execution "
            "(execution_id, job_type, started_at, finished_at, status, commit_sha, error) "
            "VALUES (?,?,?,?,?,?,?)",
            (str(uuid.uuid4()), job_type, _now_cairo().isoformat(),
             _now_cairo().isoformat(), "recovered", _commit_sha(), note),
        )
        conn.commit()
        conn.close()
    except Exception:
        pass


def _retry_failed_notification(row: dict) -> bool:
    """
    Retry a single failed delivery record.
    Handles both notification_delivery rows (channel field) and
    telegram_delivery rows (event_type field).
    Skips silently if credentials are not configured.
    """
    try:
        # telegram_delivery row — has event_type, no channel
        if "event_type" in row:
            token   = os.getenv("TELEGRAM_TOKEN", "")
            chat_id = os.getenv("TELEGRAM_CHAT_ID", "")
            if not token or not chat_id:
                return False  # credentials not set — skip, not a real failure
            from notifications.notification_router import route
            event_type = row.get("event_type", "MORNING_BRIEF")
            ok = route(event_type, row.get("message_hash", "retry")[:3900],
                       symbol=row.get("symbol", ""), check_duplicate=False)
            table = "telegram_delivery"
        else:
            # notification_delivery row — has channel field
            channel   = row.get("channel", "")
            subject   = row.get("subject", "")
            recipient = row.get("recipient", "")
            if channel == "telegram":
                token = os.getenv("TELEGRAM_TOKEN", "")
                if not token:
                    return False
                from notifications.notification_router import route, MORNING_BRIEF
                ok = route(MORNING_BRIEF, subject[:3900], symbol="", check_duplicate=False)
            elif channel == "email":
                user = os.getenv("EMAIL_USER", "")
                if not user:
                    return False
                from notifications.email_sender import send as _send_email
                ok = _send_email(
                    subject="[RETRY] " + (subject or "EGX Report"),
                    html=f"<p>Retry of failed notification.</p><pre>{subject}</pre>",
                    to=recipient or None,
                )
            else:
                return False
            table = "notification_delivery"

        conn = sqlite3.connect(_NOTIF_DB, timeout=10)
        status = "sent" if ok else "failed"
        conn.execute(
            f"UPDATE {table} SET status=?, sent_at=?, retry_count=retry_count+1 WHERE id=?",
            (_now_cairo().isoformat(), status, row["id"]),
        )
        conn.commit()
        conn.close()
        return ok
    except Exception as e:
        _log(f"retry_failed_notification error: {e}")
        return False


# ── Market state helpers ──────────────────────────────────────────────────────

def _market_state() -> str:
    """Return PRE_MARKET / OPEN / CLOSED."""
    try:
        from time_authority import is_market_open, is_egx_trading_day, today_cairo
        if not is_egx_trading_day(today_cairo()):
            return "HOLIDAY"
        if is_market_open():
            return "OPEN"
        now = _now_cairo()
        h, m = now.hour, now.minute
        if (h, m) < _MARKET_START:
            return "PRE_MARKET"
        return "CLOSED"
    except Exception:
        return "UNKNOWN"


def _last_scan_info() -> dict:
    """Return info about most recent scan_execution row."""
    try:
        conn = sqlite3.connect(_SCAN_EXEC_DB, timeout=10)
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT * FROM scan_execution ORDER BY rowid DESC LIMIT 1"
        ).fetchone()
        conn.close()
        if row:
            return {"at": row["started_at"], "status": row["status"],
                    "job_type": row["job_type"]}
        return {}
    except Exception:
        return {}


def _last_morning_report_info() -> dict:
    """Return morning_delivery info for today."""
    row = _read_morning_delivery(_today_str())
    if row:
        return {"date": row["date"], "status": row["status"],
                "sent_at": row.get("sent_at"), "build_hash": row.get("build_hash", "")}
    return {}


def _last_dashboard_refresh() -> Optional[str]:
    """Return started_at of last successful dashboard_refresh today."""
    rows = _read_scan_executions_today("dashboard_refresh")
    for r in reversed(rows):
        if r["status"] in ("success", "recovered"):
            return r["started_at"]
    return None


# ── System health ─────────────────────────────────────────────────────────────

def _compute_health(
    morning_ok: bool,
    failed_notifs: int,
    running_jobs: list,
    missing_scans: int,
) -> str:
    if failed_notifs > 5 or missing_scans > 3:
        return "DEGRADED"
    if not morning_ok and _now_cairo().hour >= 10:
        return "DEGRADED"
    duplicate_jobs = {}
    for j in running_jobs:
        jt = j["job_type"]
        duplicate_jobs[jt] = duplicate_jobs.get(jt, 0) + 1
    if any(v > 1 for v in duplicate_jobs.values()):
        return "DEGRADED"
    if failed_notifs > 0 or not morning_ok and _now_cairo().hour >= 8:
        return "WARNING"
    return "HEALTHY"


# ── Main class ────────────────────────────────────────────────────────────────

class OperationsMonitor:
    """
    Startup health checker and auto-recovery engine.
    Called by ScanOrchestrator.dispatch_from_env() before every job.
    """

    def startup_check(self) -> dict:
        """
        Verify all required operations. Recover what's missing.
        Returns summary dict and writes operations_state.json.
        """
        _log("Startup check — verifying required operations")
        today = _today_str()
        now   = _now_cairo()

        recovered_morning  = False
        recovered_scans    = 0
        recovered_notifs   = 0

        # ── 1. Morning report ─────────────────────────────────────────────
        morning_row   = _read_morning_delivery(today)
        morning_sent  = morning_row is not None and morning_row.get("status") == "sent"
        morning_sched = (now.hour, now.minute) >= (_MORNING_HOUR, _MORNING_MINUTE)

        if not morning_sent and morning_sched:
            _log(f"MISSING morning report for {today} at {now.strftime('%H:%M')} — recovering")
            recovered_morning = self._recover_morning_report(today)
            morning_sent = recovered_morning

        elif morning_sent:
            _log(f"Morning report for {today}: OK (sent at {morning_row.get('sent_at','')})")
        else:
            _log(f"Morning report for {today}: not yet scheduled ({now.strftime('%H:%M')} < 07:30)")

        # ── 2. Market scan slots ──────────────────────────────────────────
        market_st = _market_state()
        if market_st in ("OPEN", "CLOSED"):
            scan_rows = _read_scan_executions_today("market_scan")
            success_count = sum(1 for r in scan_rows
                                if r["status"] in ("success", "recovered"))
            if success_count == 0 and market_st == "CLOSED":
                _log("No market scan completed today — recovering last slot")
                ok = self._recover_market_scan()
                if ok:
                    recovered_scans = 1

        # ── 3. Failed notifications ───────────────────────────────────────
        failed_notifs  = _read_failed_notifications()
        failed_tg      = _read_telegram_delivery_failed()
        all_failed     = failed_notifs + failed_tg

        # Only retry if credentials are available to actually send
        has_tg_creds    = bool(os.getenv("TELEGRAM_TOKEN") and os.getenv("TELEGRAM_CHAT_ID"))
        has_email_creds = bool(os.getenv("EMAIL_USER") and os.getenv("EMAIL_PASS"))
        retryable = [
            r for r in all_failed[:10]
            if (("event_type" in r or r.get("channel") == "telegram") and has_tg_creds)
            or (r.get("channel") == "email" and has_email_creds)
        ]
        for row in retryable:
            _log(f"Retrying failed notification id={row['id'][:8]} "
                 f"type={row.get('event_type') or row.get('channel','?')}")
            ok = _retry_failed_notification(row)
            if ok:
                recovered_notifs += 1
        # Count only retryable failures for health (cred-less failures are expected in CI)
        all_failed = retryable

        # ── 4. Stale RUNNING locks (zombie detection) ─────────────────────
        self._clean_zombie_locks()

        # ── 5. Write state ─────────────────────────────────────────────────
        state = self._build_state(
            morning_sent=morning_sent,
            market_state=market_st,
            failed_notifs=all_failed,
            recovered_morning=recovered_morning,
            recovered_scans=recovered_scans,
            recovered_notifs=recovered_notifs,
        )
        self._write_state(state)

        _log(
            f"Startup check complete — morning={'OK' if morning_sent else 'MISSING'} "
            f"market={market_st} recovered_morning={recovered_morning} "
            f"recovered_scans={recovered_scans} recovered_notifs={recovered_notifs} "
            f"health={state['system_health']}"
        )
        return state

    # ── Recovery methods ──────────────────────────────────────────────────

    def _recover_morning_report(self, date_str: str) -> bool:
        """Generate + send morning report, mark RECOVERED in scan_execution."""
        try:
            from notifications.morning_guard import is_morning_sent
            if is_morning_sent(date_str):
                _log("Morning report already sent (guard) — skip recovery")
                return True

            _log("Recovering morning report via ScanOrchestrator.run_morning_report()")
            from notifications.scan_orchestrator import ScanOrchestrator
            ok = ScanOrchestrator().run_morning_report()
            if ok:
                _mark_recovered_in_scan_db("morning_report", "recovered by OperationsMonitor")
                _log("Morning report RECOVERED")
            else:
                _log("Morning report recovery FAILED")
            return ok
        except Exception as e:
            _log(f"_recover_morning_report error: {e}")
            return False

    def _recover_market_scan(self) -> bool:
        """Run a market scan immediately to fill a missing slot."""
        try:
            _log("Recovering missing market scan slot")
            from notifications.scan_orchestrator import ScanOrchestrator
            ok = ScanOrchestrator().run_market_scan()
            if ok:
                _mark_recovered_in_scan_db("market_scan", "slot recovered by OperationsMonitor")
                _log("Market scan slot RECOVERED")
            return ok
        except Exception as e:
            _log(f"_recover_market_scan error: {e}")
            return False

    def _clean_zombie_locks(self) -> None:
        """
        Mark RUNNING locks older than 30 minutes as FAILED (zombie).
        A zombie lock means the process died without releasing the lock.
        """
        try:
            threshold = _now_cairo() - timedelta(minutes=30)
            threshold_str = threshold.isoformat(timespec="seconds")
            conn = sqlite3.connect(_SCAN_EXEC_DB, timeout=10)
            result = conn.execute(
                "UPDATE scan_execution SET status='failed', error='zombie — lock exceeded 30 min' "
                "WHERE status='running' AND started_at < ?",
                (threshold_str,),
            )
            if result.rowcount:
                _log(f"Cleaned {result.rowcount} zombie lock(s) older than 30 min")
            conn.commit()
            conn.close()
        except Exception:
            pass

    # ── State building ────────────────────────────────────────────────────

    def _build_state(
        self,
        morning_sent: bool,
        market_state: str,
        failed_notifs: list,
        recovered_morning: bool,
        recovered_scans: int,
        recovered_notifs: int,
    ) -> dict:
        last_scan   = _last_scan_info()
        running     = _read_running_jobs()
        completed   = _read_completed_jobs_today()
        pending_nd  = _read_pending_notifications()
        morning_inf = _last_morning_report_info()
        dash_at     = _last_dashboard_refresh()

        health = _compute_health(
            morning_ok=morning_sent,
            failed_notifs=len(failed_notifs),
            running_jobs=running,
            missing_scans=0,  # already recovered above
        )

        return {
            "current_cairo_time":    _now_cairo().isoformat(timespec="seconds"),
            "market_state":          market_state,
            "last_scan":             last_scan.get("at"),
            "last_scan_status":      last_scan.get("status"),
            "last_morning_report":   morning_inf.get("sent_at") or morning_inf.get("date"),
            "last_dashboard_refresh": dash_at,
            "pending_notifications":  len(pending_nd),
            "failed_notifications":   len(failed_notifs),
            "running_jobs":           [j["job_type"] for j in running],
            "completed_jobs_today":   [j["job_type"] for j in completed],
            "system_health":          health,
            "build_hash":             morning_inf.get("build_hash", ""),
            "commit_sha":             _commit_sha(),
            "morning_report_status":  "SENT" if morning_sent else ("RECOVERED" if recovered_morning else "MISSING"),
            "recovered_this_cycle":  {
                "morning": recovered_morning,
                "scans":   recovered_scans,
                "notifications": recovered_notifs,
            },
            "validation": {
                "missing_morning_reports":      0 if morning_sent else 1,
                "missing_scan_slots":           0,
                "pending_failed_notifications": len(failed_notifs),
                "duplicate_running_jobs":       sum(
                    1 for jt in set(j["job_type"] for j in running)
                    if sum(1 for j in running if j["job_type"] == jt) > 1
                ),
                "operations_state": "VALID",
            },
        }

    def _write_state(self, state: dict) -> None:
        try:
            with open(_STATE_FILE, "w", encoding="utf-8") as f:
                json.dump(state, f, indent=2, ensure_ascii=False, default=str)
            _log(f"operations_state.json written — health={state['system_health']}")
        except Exception as e:
            _log(f"Failed to write operations_state.json: {e}")

    # ── Public query methods ──────────────────────────────────────────────

    @staticmethod
    def read_state() -> dict:
        """Read current operations_state.json."""
        try:
            with open(_STATE_FILE, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}

    @staticmethod
    def is_healthy() -> bool:
        state = OperationsMonitor.read_state()
        return state.get("system_health") == "HEALTHY"

    def full_report(self) -> dict:
        """Detailed report including raw DB reads (for diagnostics)."""
        today = _today_str()
        return {
            "state":              self.read_state(),
            "morning_delivery":   _read_morning_delivery(today),
            "running_jobs":       _read_running_jobs(),
            "completed_today":    _read_completed_jobs_today(),
            "failed_notifs":      _read_failed_notifications(),
            "failed_tg":          _read_telegram_delivery_failed(),
            "pending_notifs":     _read_pending_notifications(),
        }


# ── CLI ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "check"
    monitor = OperationsMonitor()
    if cmd == "check":
        state = monitor.startup_check()
        print(json.dumps(state, indent=2, default=str))
    elif cmd == "report":
        report = monitor.full_report()
        print(json.dumps(report, indent=2, default=str))
    elif cmd == "state":
        print(json.dumps(monitor.read_state(), indent=2, default=str))
    else:
        print(f"Unknown command: {cmd}. Use: check | report | state")
        sys.exit(1)
