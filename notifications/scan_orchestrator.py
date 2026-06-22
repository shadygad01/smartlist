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
_EET = timezone(timedelta(hours=2))


def _now_iso() -> str:
    return datetime.now(_EET).isoformat(timespec="seconds")


def _commit_sha() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=str(BASE), text=True, stderr=subprocess.DEVNULL
        ).strip()
    except Exception:
        return ""


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
    conn.commit()
    conn.close()


class ScanOrchestrator:
    """Single execution authority for all constitutional scan jobs."""

    def __init__(self, db_path: str = _DB):
        self._db = db_path
        _init_db(db_path)

    # ── Lock management ───────────────────────────────────────────────────────

    def _is_running(self, job_type: str) -> bool:
        conn = sqlite3.connect(self._db)
        try:
            row = conn.execute(
                "SELECT execution_id FROM scan_execution WHERE job_type=? AND status='running'",
                (job_type,),
            ).fetchone()
            return row is not None
        finally:
            conn.close()

    def _acquire(self, job_type: str) -> Optional[str]:
        """
        Insert a 'running' row. Returns execution_id, or None if already running.
        Uses INSERT-then-check (not INSERT OR FAIL) so errors are distinguishable.
        """
        if self._is_running(job_type):
            print(f"[Orchestrator] {job_type} already RUNNING — EXIT (duplicate guard)")
            return None
        eid = str(uuid.uuid4())
        conn = sqlite3.connect(self._db)
        try:
            conn.execute(
                "INSERT INTO scan_execution (execution_id, job_type, started_at, commit_sha) "
                "VALUES (?, ?, ?, ?)",
                (eid, job_type, _now_iso(), _commit_sha()),
            )
            conn.commit()
            print(f"[Orchestrator] {job_type} LOCK ACQUIRED — execution_id={eid[:8]}")
            return eid
        finally:
            conn.close()

    def _release(
        self,
        eid: str,
        status: str = "success",
        build_hash: str = "",
        error: str = "",
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

            self._release(eid, "success", build_hash=build_hash)
            return True
        except Exception as e:
            self._release(eid, "failed", error=str(e))
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
            self._release(eid, "success")
            return True
        except Exception as e:
            self._release(eid, "failed", error=str(e))
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
            self._release(eid, "success")
            return True
        except Exception as e:
            self._release(eid, "failed", error=str(e))
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
                          error="" if ok else f"dashboard.py exited {result.returncode}")
            return ok
        except Exception as e:
            self._release(eid, "failed", error=str(e))
            raise

    # ── Dispatcher ────────────────────────────────────────────────────────────

    def dispatch_from_env(self) -> bool:
        """
        Determine job type from environment variables (FORCE_DAILY, MANUAL_RUN)
        and current Cairo time, then dispatch to the appropriate method.
        This is the single entry point called by the workflow.
        """
        from time_authority import now_cairo
        manual_run  = os.getenv("MANUAL_RUN",  "False") == "True"
        force_daily = os.getenv("FORCE_DAILY", "False") == "True"
        hour = now_cairo().hour
        minute = now_cairo().minute

        print(f"[Orchestrator] dispatch_from_env — "
              f"time={hour:02d}:{minute:02d} FORCE_DAILY={force_daily} MANUAL_RUN={manual_run}")

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
