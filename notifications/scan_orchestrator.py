"""
Constitutional Scan Orchestrator — Step 4.

Single execution authority for all scan jobs.
ALL workflows call ONLY this module. No workflow may call main.py directly.

Execution protocol: Acquire Lock → Run → Validate → Release Lock
Duplicate protection: EXIT immediately if same job_type already RUNNING.

Public methods:
    run_morning_report()    — 07:30 Cairo daily brief
    run_market_scan()       — 10:00-14:30 Cairo continuous signal scan
    run_position_monitor()  — standalone position health check
    run_dashboard_refresh() — presentation snapshot + dashboard rebuild

CLI:
    python -m notifications.scan_orchestrator <job_type>
    python -m notifications.scan_orchestrator dispatch  # reads env vars
"""
from __future__ import annotations

import os
import sqlite3
import subprocess
import sys
import uuid
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

BASE = Path(__file__).parent.parent
sys.path.insert(0, str(BASE))

_DB = str(BASE / "scan_execution.db")
from time_authority import now_cairo as _now_cairo_ta


def _now_iso() -> str:
    return _now_cairo_ta().isoformat(timespec="seconds")


def _commit_sha() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=str(BASE), text=True, stderr=subprocess.DEVNULL
        ).strip()
    except Exception:
        return ""


def _slot_time() -> str:
    """Round current time down to the nearest 5-minute slot."""
    now = _now_cairo_ta()
    return now.replace(minute=(now.minute // 5) * 5, second=0, microsecond=0).isoformat(timespec="minutes")


def _init_db(db_path: str = _DB) -> None:
    conn = sqlite3.connect(db_path)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS scan_execution (
            execution_id TEXT PRIMARY KEY,
            job_type     TEXT NOT NULL,
            started_at   TEXT NOT NULL,
            finished_at  TEXT,
            status       TEXT NOT NULL DEFAULT 'running',
            build_hash   TEXT DEFAULT '',
            commit_sha   TEXT DEFAULT '',
            error        TEXT DEFAULT ''
        )
    """)
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_se_job_status ON scan_execution(job_type, status)"
    )
    conn.execute("""
        CREATE TABLE IF NOT EXISTS scan_slot_history (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            slot_time       TEXT NOT NULL,
            job_type        TEXT NOT NULL,
            started_at      TEXT NOT NULL,
            finished_at     TEXT,
            status          TEXT NOT NULL DEFAULT 'running',
            duration_secs   REAL,
            execution_id    TEXT,
            dispatch_source TEXT DEFAULT 'github_actions',
            error           TEXT DEFAULT ''
        )
    """)
    conn.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_ssh_slot_job "
        "ON scan_slot_history(slot_time, job_type)"
    )
    conn.commit()
    conn.close()


class ScanOrchestrator:
    """Single execution authority for all constitutional scan jobs."""

    def __init__(self, db_path: str = _DB):
        self._db = db_path
        _init_db(db_path)

    # ── Lock management ───────────────────────────────────────────────────────

    def _is_running(self, job_type: str) -> Optional[str]:
        """Return running execution_id or None."""
        conn = sqlite3.connect(self._db)
        try:
            row = conn.execute(
                "SELECT execution_id FROM scan_execution WHERE job_type=? AND status='running'",
                (job_type,),
            ).fetchone()
            return row[0] if row else None
        finally:
            conn.close()

    def _register_slot(
        self,
        job_type: str,
        eid: str,
        status: str,
        dispatch_source: str = "github_actions",
        blocked_by: str = "",
    ) -> None:
        """Insert or update scan_slot_history for this slot+job_type."""
        slot = _slot_time()
        now  = _now_iso()
        conn = sqlite3.connect(self._db)
        try:
            error_note = f"blocked by {blocked_by[:36]}" if blocked_by else ""
            conn.execute(
                """INSERT INTO scan_slot_history
                   (slot_time, job_type, started_at, status, execution_id, dispatch_source, error)
                   VALUES (?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(slot_time, job_type) DO UPDATE SET
                       status=excluded.status,
                       error=excluded.error""",
                (slot, job_type, now, status, eid, dispatch_source, error_note),
            )
            conn.commit()
        except Exception as e:
            print(f"[Orchestrator] slot register non-fatal: {e}")
        finally:
            conn.close()

    def _close_slot(self, job_type: str, eid: str, status: str, error: str = "") -> None:
        """Mark the slot_history row finished."""
        slot = _slot_time()
        now  = _now_iso()
        conn = sqlite3.connect(self._db)
        try:
            conn.execute(
                """UPDATE scan_slot_history SET finished_at=?, status=?,
                   duration_secs=(strftime('%s', ?) - strftime('%s', started_at)),
                   error=?
                   WHERE slot_time=? AND job_type=?""",
                (now, status, now, error[:500], slot, job_type),
            )
            conn.commit()
        except Exception:
            pass
        finally:
            conn.close()

    def _cleanup_zombies(self, job_type: str, max_age_minutes: int = 30) -> None:
        """Mark stuck 'running' executions as failed if older than max_age_minutes."""
        cutoff = _now_cairo_ta() - timedelta(minutes=max_age_minutes)
        cutoff_iso = cutoff.isoformat(timespec="seconds")
        conn = sqlite3.connect(self._db)
        try:
            rows = conn.execute(
                "SELECT execution_id FROM scan_execution "
                "WHERE job_type=? AND status='running' AND started_at < ?",
                (job_type, cutoff_iso),
            ).fetchall()
            for (eid,) in rows:
                conn.execute(
                    "UPDATE scan_execution SET status='failed', finished_at=?, "
                    "error=? WHERE execution_id=?",
                    (_now_iso(), "zombie — lock exceeded 30 min", eid),
                )
                print(f"[Orchestrator] Zombie cleaned: {job_type} {eid[:8]}")
            if rows:
                conn.commit()
        except Exception as e:
            print(f"[Orchestrator] zombie cleanup non-fatal: {e}")
        finally:
            conn.close()

    def _acquire(
        self,
        job_type: str,
        dispatch_source: str = "github_actions",
    ) -> Optional[str]:
        """
        Insert a 'running' row. Returns execution_id, or None if already running.
        When blocked, records SKIPPED_BY_LOCK in scan_slot_history (not FAILED).
        """
        self._cleanup_zombies(job_type)
        running_eid = self._is_running(job_type)
        if running_eid:
            print(
                f"[Orchestrator] {job_type} already RUNNING ({running_eid[:8]}) — "
                f"scan skipped - existing execution active"
            )
            # Record the skip — success exit, not failure
            self._register_slot(job_type, running_eid, "SKIPPED_BY_LOCK",
                                 dispatch_source=dispatch_source, blocked_by=running_eid)
            return None

        eid  = str(uuid.uuid4())
        conn = sqlite3.connect(self._db)
        try:
            conn.execute(
                "INSERT INTO scan_execution (execution_id, job_type, started_at, commit_sha) "
                "VALUES (?, ?, ?, ?)",
                (eid, job_type, _now_iso(), _commit_sha()),
            )
            conn.commit()
            print(f"[Orchestrator] {job_type} LOCK ACQUIRED — execution_id={eid[:8]}")
        finally:
            conn.close()

        self._register_slot(job_type, eid, "running", dispatch_source=dispatch_source)
        return eid

    def _release(
        self,
        eid: str,
        status: str = "success",
        build_hash: str = "",
        error: str = "",
        job_type: str = "",
    ) -> None:
        conn = sqlite3.connect(self._db)
        try:
            conn.execute(
                "UPDATE scan_execution SET finished_at=?, status=?, build_hash=?, error=? "
                "WHERE execution_id=?",
                (_now_iso(), status, build_hash, error[:2000], eid),
            )
            conn.commit()
            print(f"[Orchestrator] execution_id={eid[:8]} → {status}")
        finally:
            conn.close()

        # Close the corresponding slot_history row
        self._close_slot(job_type, eid, status, error=error)

        # Update heartbeat + public_status after every execution
        try:
            from operations.heartbeat import update_heartbeat, record_scan
            from time_authority import today_iso
            record_scan(market_date=today_iso(), build_hash=build_hash, status=status)
            if job_type == "morning_report" and status == "success":
                from operations.heartbeat import record_email
                record_email(today_iso())
            if job_type == "dashboard_refresh" and status == "success":
                from operations.heartbeat import record_dashboard
                record_dashboard(build_hash=build_hash)
        except Exception as _hb_err:
            print(f"[Orchestrator] heartbeat update non-fatal: {_hb_err}")

        try:
            from operations.github_health import write_public_status
            write_public_status()
        except Exception as _ps_err:
            print(f"[Orchestrator] public_status update non-fatal: {_ps_err}")

        try:
            from operations.scan_audit import update_operations_state
            update_operations_state()
        except Exception as _sa_err:
            print(f"[Orchestrator] scan_audit update non-fatal: {_sa_err}")

    # ── Public job methods ────────────────────────────────────────────────────

    def run_morning_report(self) -> bool:
        """
        Daily morning brief — 07:30 Cairo.
        Runs daily_scan() (email + Telegram), then director self-healing cycle.
        Exactly-once protected by morning_guard + this lock.
        """
        eid = self._acquire("morning_report")
        if eid is None:
            return False
        build_hash = ""
        try:
            from main import daily_scan
            daily_scan()

            # Post-scan: self-healing + snapshot consistency check
            try:
                from operations.director import OperationsDirector
                OperationsDirector().run_full_cycle()
            except Exception as e:
                print(f"[Orchestrator] run_full_cycle non-fatal: {e}")

            # Capture build_hash from morning_delivery table
            try:
                import sqlite3 as _sq
                conn2 = _sq.connect(str(BASE / "notification_delivery.db"))
                row = conn2.execute(
                    "SELECT build_hash FROM morning_delivery ORDER BY id DESC LIMIT 1"
                ).fetchone()
                conn2.close()
                if row:
                    build_hash = row[0] or ""
            except Exception:
                pass

            self._release(eid, "success", build_hash=build_hash, job_type="morning_report")
            return True
        except Exception as e:
            self._release(eid, "failed", error=str(e), job_type="morning_report")
            raise

    def run_market_scan(self) -> bool:
        """
        Intra-day continuous scan — 10:00–14:30 Cairo.
        Detects signal changes and sends alerts. No morning report.
        """
        eid = self._acquire("market_scan")
        if eid is None:
            return False
        try:
            from main import continuous_scan
            continuous_scan()
            self._release(eid, "success", job_type="market_scan")
            return True
        except Exception as e:
            self._release(eid, "failed", error=str(e), job_type="market_scan")
            raise

    def run_position_monitor(self) -> bool:
        """
        Standalone position health check — runs monitor_positions and
        monitor_reinforcement against current prices without sending a full report.
        """
        eid = self._acquire("position_monitor")
        if eid is None:
            return False
        try:
            from main import (
                build_report, _collect_current_prices, monitor_positions,
                monitor_reinforcement, load_previous_results,
            )
            load_previous_results()
            _, results, _ = build_report(holiday_mode=False)
            cur_prices = _collect_current_prices(results)
            monitor_positions(cur_prices)
            monitor_reinforcement(cur_prices, results)
            self._release(eid, "success", job_type="position_monitor")
            return True
        except Exception as e:
            self._release(eid, "failed", error=str(e), job_type="position_monitor")
            raise

    def run_dashboard_refresh(self) -> bool:
        """
        Rebuild presentation snapshot, run self-healing cycle, regenerate dashboard.
        Called by dashboard_build workflow job.
        """
        eid = self._acquire("dashboard_refresh")
        if eid is None:
            return False
        try:
            # 1. Self-healing + snapshot rebuild
            try:
                from operations.director import OperationsDirector
                OperationsDirector().run_full_cycle()
            except Exception as e:
                print(f"[Orchestrator] run_full_cycle non-fatal: {e}")

            # 2. Dashboard HTML generation
            result = subprocess.run(
                [sys.executable, str(BASE / "dashboard.py")],
                cwd=str(BASE), capture_output=False, text=True, timeout=120,
            )
            ok = result.returncode == 0

            self._release(eid, "success" if ok else "failed",
                          error="" if ok else f"dashboard.py exited {result.returncode}",
                          job_type="dashboard_refresh")
            return ok
        except Exception as e:
            self._release(eid, "failed", error=str(e), job_type="dashboard_refresh")
            raise

    # ── Dispatcher ────────────────────────────────────────────────────────────

    def dispatch_from_env(self) -> bool:
        """
        Determine job type from environment variables (FORCE_DAILY, MANUAL_RUN)
        and current Cairo time, then dispatch to the appropriate method.
        This is the single entry point called by the workflow.

        Runs OperationsMonitor.startup_check() FIRST on every execution
        to detect and recover any missed operations before starting new work.
        """
        from time_authority import now_cairo
        manual_run  = os.getenv("MANUAL_RUN",  "False") == "True"
        force_daily = os.getenv("FORCE_DAILY", "False") == "True"
        hour = now_cairo().hour
        minute = now_cairo().minute

        print(f"[Orchestrator] dispatch_from_env — "
              f"time={hour:02d}:{minute:02d} FORCE_DAILY={force_daily} MANUAL_RUN={manual_run}")

        # Startup health check — recover any missed/failed jobs before new work
        try:
            from notifications.operations_monitor import OperationsMonitor
            OperationsMonitor().startup_check()
        except Exception as e:
            print(f"[Orchestrator] startup_check non-fatal: {e}")

        if manual_run:
            print("[Orchestrator] → run_morning_report (MANUAL_RUN)")
            return self.run_morning_report()

        if force_daily or hour == 7:
            print("[Orchestrator] → run_morning_report (FORCE_DAILY or 07:xx)")
            return self.run_morning_report()

        if 10 <= hour <= 14:
            print("[Orchestrator] → run_market_scan (market hours)")
            return self.run_market_scan()

        print(f"[Orchestrator] Outside scheduled windows ({hour:02d}:{minute:02d}) — no action")
        return True

    def recent_executions(self, limit: int = 20) -> list[dict]:
        """Return recent execution log rows."""
        conn = sqlite3.connect(self._db)
        conn.row_factory = sqlite3.Row
        try:
            rows = conn.execute(
                "SELECT * FROM scan_execution ORDER BY rowid DESC LIMIT ?", (limit,)
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()


# ── CLI ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import json
    cmd = sys.argv[1] if len(sys.argv) > 1 else "dispatch"
    orch = ScanOrchestrator()
    dispatch = {
        "morning":           orch.run_morning_report,
        "run_morning_report": orch.run_morning_report,
        "market":            orch.run_market_scan,
        "run_market_scan":   orch.run_market_scan,
        "position":          orch.run_position_monitor,
        "run_position_monitor": orch.run_position_monitor,
        "dashboard":         orch.run_dashboard_refresh,
        "run_dashboard_refresh": orch.run_dashboard_refresh,
        "dispatch":          orch.dispatch_from_env,
        "status":            lambda: print(json.dumps(orch.recent_executions(10), indent=2)),
    }
    fn = dispatch.get(cmd)
    if fn is None:
        print(f"Unknown command: {cmd}")
        print(f"Valid: {list(dispatch.keys())}")
        sys.exit(1)
    result = fn()
    sys.exit(0 if result is not False else 1)
