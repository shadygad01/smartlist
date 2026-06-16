"""
Autonomous Scheduler — Layer 10 trigger.
Runs daily: scan → measure → research → optimize → validate → deploy → learn.
Designed for cron or direct invocation; safe to call multiple times per day.
"""
import json
import os
import sqlite3
import sys
import time
import traceback
from datetime import datetime, timedelta
from typing import Optional

STATE_FILE = "scheduler_state.json"
DB_PATH    = "egx_research.db"
CONFIG_DIR = "config/"
LOG_FILE   = "scheduler.log"

_DEFAULT_STATE = {
    "schema_version": 1,
    "last_scan_at": None,
    "last_learning_cycle_at": None,
    "last_error": None,
    "consecutive_errors": 0,
    "total_runs": 0,
    "total_promotions": 0,
}


# ── State helpers ──────────────────────────────────────────────────────────────

def _load_state() -> dict:
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, encoding="utf-8") as f:
                data = json.load(f)
            for k, v in _DEFAULT_STATE.items():
                data.setdefault(k, v)
            return data
        except Exception:
            pass
    return dict(_DEFAULT_STATE)


def _save_state(state: dict) -> None:
    tmp = STATE_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)
    os.replace(tmp, STATE_FILE)


def _log(msg: str) -> None:
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


# ── Sub-steps ─────────────────────────────────────────────────────────────────

def _run_scan() -> bool:
    """Trigger daily scan via main.daily_scan()."""
    try:
        import main as _main
        if hasattr(_main, "daily_scan"):
            _main.daily_scan()
            return True
        _log("WARNING: main.daily_scan() not found")
        return False
    except Exception as exc:
        _log(f"ERROR in scan: {exc}")
        return False


def _measure_outcomes(db_path: str = DB_PATH) -> int:
    """Trigger bottom_quality measurement; return count of newly measured rows."""
    try:
        import bottom_quality as bq
        if hasattr(bq, "run_all"):
            return bq.run_all(db_path=db_path) or 0
        if hasattr(bq, "measure_all"):
            return bq.measure_all(db_path=db_path) or 0
    except ImportError:
        pass
    except Exception as exc:
        _log(f"WARNING: bottom_quality measurement failed: {exc}")
    return 0


def _run_learning(db_path: str = DB_PATH, dry_run: bool = False) -> Optional[dict]:
    """Run continuous learning cycle."""
    try:
        from continuous_learning import run_learning_cycle
        return run_learning_cycle(db_path=db_path, config_dir=CONFIG_DIR, dry_run=dry_run)
    except Exception as exc:
        _log(f"ERROR in learning cycle: {exc}")
        traceback.print_exc()
        return None


def _update_knowledge_base(cycle_result: Optional[dict]) -> None:
    """Log cycle result to knowledge base."""
    try:
        from knowledge_base import get_kb
        kb = get_kb()
        if cycle_result:
            kb.log_cycle(cycle_result)
    except Exception:
        pass


# ── Main orchestration ────────────────────────────────────────────────────────

def run_once(dry_run: bool = False, skip_scan: bool = False) -> dict:
    """
    Execute one full autonomous cycle.
    Returns status dict with outcomes of each stage.
    """
    state = _load_state()
    now   = datetime.now()
    status = {
        "started_at": now.isoformat(),
        "scan_ok": False,
        "outcomes_measured": 0,
        "learning_result": None,
        "promoted": False,
        "verdict": None,
        "error": None,
    }

    try:
        state["total_runs"] = state.get("total_runs", 0) + 1

        # Step 1: Scan
        if not skip_scan:
            _log("Step 1/3: Running daily scan …")
            scan_ok = _run_scan()
            status["scan_ok"] = scan_ok
            state["last_scan_at"] = now.isoformat()
        else:
            _log("Step 1/3: Scan skipped (skip_scan=True)")
            status["scan_ok"] = True

        # Step 2: Measure outcomes
        _log("Step 2/3: Measuring outcomes …")
        n = _measure_outcomes()
        status["outcomes_measured"] = n
        _log(f"         {n} outcome rows updated")

        # Step 3: Learning cycle
        _log("Step 3/3: Running learning cycle …")
        result = _run_learning(dry_run=dry_run)
        status["learning_result"] = result
        if result:
            status["promoted"] = result.get("promoted", False)
            status["verdict"]  = result.get("verdict")
            if result.get("promoted"):
                state["total_promotions"] = state.get("total_promotions", 0) + 1
            _log(f"         verdict={result.get('verdict')}  promoted={result.get('promoted')}")

        _update_knowledge_base(result)
        state["last_learning_cycle_at"] = now.isoformat()
        state["consecutive_errors"] = 0
        state["last_error"] = None

        # Reconcile total_promotions from authoritative LearningMemory
        try:
            from continuous_learning import LearningMemory
            mem_summary = LearningMemory().get_summary()
            state["total_promotions"] = mem_summary.get("total_promoted", state.get("total_promotions", 0))
        except Exception:
            if result and result.get("promoted"):
                state["total_promotions"] = state.get("total_promotions", 0) + 1

    except Exception as exc:
        msg = str(exc)
        _log(f"FATAL ERROR in run_once: {msg}")
        traceback.print_exc()
        state["consecutive_errors"] = state.get("consecutive_errors", 0) + 1
        state["last_error"] = msg
        status["error"] = msg

    finally:
        status["finished_at"] = datetime.now().isoformat()
        _save_state(state)

    return status


def run_loop(interval_hours: float = 24.0, dry_run: bool = False) -> None:
    """
    Run continuously, sleeping `interval_hours` between cycles.
    Intended for background execution (systemd, screen, etc.).
    """
    _log(f"Scheduler loop started  interval={interval_hours}h  dry_run={dry_run}")
    while True:
        _log("─" * 60)
        status = run_once(dry_run=dry_run)
        _log(f"Cycle complete: verdict={status.get('verdict')}  promoted={status.get('promoted')}")
        sleep_sec = interval_hours * 3600
        _log(f"Sleeping {interval_hours}h until next cycle …")
        time.sleep(sleep_sec)


def status_report() -> dict:
    """Return current scheduler state and system health snapshot.

    LearningMemory is the authoritative source for cycle counts and promotion
    history. scheduler_state.json tracks scan timestamps only.
    """
    state = _load_state()
    report = dict(state)

    # Authoritative cycle state from LearningMemory
    try:
        from continuous_learning import LearningMemory
        mem = LearningMemory()
        mem_summary = mem.get_summary()
        report["learning_memory"] = mem_summary
        # Reconcile scheduler_state total_promotions with actual count
        if mem_summary.get("total_promoted", 0) != state.get("total_promotions", 0):
            state["total_promotions"] = mem_summary["total_promoted"]
            _save_state(state)
    except Exception:
        pass

    try:
        conn = sqlite3.connect(DB_PATH)
        n_signals = conn.execute("SELECT COUNT(*) FROM signals").fetchone()[0]
        n_outcomes = conn.execute(
            "SELECT COUNT(*) FROM bottom_quality WHERE r20d IS NOT NULL"
        ).fetchone()[0]
        n_validations = conn.execute("SELECT COUNT(*) FROM validation_runs").fetchone()[0]
        last_verdict = conn.execute(
            "SELECT verdict FROM validation_runs ORDER BY id DESC LIMIT 1"
        ).fetchone()
        n_promotions = conn.execute(
            "SELECT COUNT(*) FROM deployment_log WHERE action='PROMOTE'"
        ).fetchone()[0]
        conn.close()
        report["db"] = {
            "n_signals": n_signals,
            "n_outcomes": n_outcomes,
            "n_validations": n_validations,
            "last_verdict": last_verdict[0] if last_verdict else None,
            "n_promotions": n_promotions,
        }
    except Exception as exc:
        report["db"] = {"error": str(exc)}

    try:
        from knowledge_base import get_kb
        report["knowledge_base"] = get_kb().summary()
    except Exception:
        pass

    return report


# ── CLI ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse, pprint
    parser = argparse.ArgumentParser(description="EGX Autonomous Scheduler")
    parser.add_argument("command", choices=["run", "loop", "status"], nargs="?", default="run")
    parser.add_argument("--dry-run",      action="store_true")
    parser.add_argument("--skip-scan",    action="store_true")
    parser.add_argument("--interval",     type=float, default=24.0, help="Loop interval in hours")
    args = parser.parse_args()

    if args.command == "status":
        pprint.pprint(status_report())
    elif args.command == "loop":
        run_loop(interval_hours=args.interval, dry_run=args.dry_run)
    else:
        result = run_once(dry_run=args.dry_run, skip_scan=args.skip_scan)
        pprint.pprint(result)
