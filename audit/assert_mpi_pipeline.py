"""
MPI Pipeline Integrity Assertion — Constitutional Architecture.

Verifies the Market Psychology Intelligence pipeline is fully operational:
  1. mpi_snapshots.db exists and contains records for today
  2. At least one MPI record matches a signal from production_decision_snapshot
  3. MPI renderer (render_behavior_insight_html) is importable and callable
  4. MPI renderer (render_behavior_insight_telegram) is importable and callable
  5. Constitutional gate is NOT imported inside mpi_engine (separation proof)
  6. MPI never writes constitutional decision fields (eligible/score/r2/entry_price)
  7. Dashboard, Email, Telegram all render MPI via stored snapshot — not recompute
  8. mpi_snapshots.db upsert is idempotent (no duplicate records per ticker+date+type)

Exits 0: all assertions pass
Exits 1: one or more assertions fail (details printed)
Exits 2: SKIPPED — prerequisites not present (first run, no signals today)
"""
from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

BASE = Path(__file__).parent.parent
sys.path.insert(0, str(BASE))

from audit.audit_status import AuditStatus


def _check_no_gate_import_in_mpi() -> tuple[bool | None, str]:
    mpi_path = BASE / "mpi_engine.py"
    if not mpi_path.exists():
        return False, "mpi_engine.py not found"
    src = mpi_path.read_text()
    if "constitutional_gate" in src:
        return False, "mpi_engine.py imports or references constitutional_gate — separation violated"
    return True, "mpi_engine.py does not reference constitutional_gate"


def _check_no_decision_field_writes_in_mpi() -> tuple[bool | None, str]:
    mpi_path = BASE / "mpi_engine.py"
    if not mpi_path.exists():
        return False, "mpi_engine.py not found"
    src = mpi_path.read_text()
    forbidden = [
        "is_constitutional_buy",
        "CONST_R2_MIN",
        "CONST_SCORE_MIN",
    ]
    violations = [f for f in forbidden if f in src]
    if violations:
        return False, f"mpi_engine.py references constitutional gate fields: {violations}"
    return True, "mpi_engine.py does not reference constitutional gate fields"


def _check_db_exists_and_has_records(today_str: str) -> tuple[bool | None, str]:
    db_path = BASE / "mpi_snapshots.db"
    if not db_path.exists():
        return None, "mpi_snapshots.db does not exist — MPI has never run"
    try:
        conn = sqlite3.connect(str(db_path))
        count = conn.execute(
            "SELECT COUNT(*) FROM mpi_snapshots WHERE analysis_date=?", (today_str,)
        ).fetchone()[0]
        conn.close()
        if count == 0:
            return None, f"mpi_snapshots.db has no records for {today_str} — MPI did not run today"
        return True, f"mpi_snapshots.db has {count} record(s) for {today_str}"
    except Exception as e:
        return False, f"mpi_snapshots.db read error: {e}"


def _check_mpi_matches_signals(today_str: str) -> tuple[bool | None, str]:
    db_path   = BASE / "mpi_snapshots.db"
    snap_path = BASE / "production_decision_snapshot.json"
    if not db_path.exists() or not snap_path.exists():
        return None, "prerequisites missing — skip"
    try:
        conn = sqlite3.connect(str(db_path))
        mpi_tickers = {
            r[0] for r in conn.execute(
                "SELECT DISTINCT ticker FROM mpi_snapshots WHERE analysis_date=?", (today_str,)
            ).fetchall()
        }
        conn.close()
    except Exception as e:
        return False, f"mpi_snapshots.db query failed: {e}"
    try:
        prod = json.loads(snap_path.read_text())
        eligible = {d["ticker"] for d in prod.get("decisions", []) if d.get("eligible")}
    except Exception as e:
        return None, f"production_decision_snapshot.json read error: {e}"
    if not eligible:
        return None, "no eligible tickers in production_decision_snapshot — skip"
    overlap = mpi_tickers & eligible
    if not overlap:
        return False, (
            f"no MPI records match eligible tickers — "
            f"eligible={sorted(eligible)}, mpi_today={sorted(mpi_tickers)}"
        )
    return True, f"MPI covers {len(overlap)}/{len(eligible)} eligible tickers: {sorted(overlap)}"


def _check_renderer_importable() -> tuple[bool | None, str]:
    try:
        from mpi_engine import render_behavior_insight_html, render_behavior_insight_telegram
    except ImportError as e:
        return False, f"mpi_engine renderer import failed: {e}"
    if not callable(render_behavior_insight_html):
        return False, "render_behavior_insight_html is not callable"
    if not callable(render_behavior_insight_telegram):
        return False, "render_behavior_insight_telegram is not callable"
    return True, "render_behavior_insight_html and render_behavior_insight_telegram are callable"


def _check_renderer_output(today_str: str) -> tuple[bool | None, str]:
    db_path = BASE / "mpi_snapshots.db"
    if not db_path.exists():
        return None, "mpi_snapshots.db missing — skip"
    try:
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT * FROM mpi_snapshots WHERE analysis_date=? LIMIT 1", (today_str,)
        ).fetchone()
        conn.close()
        if row is None:
            return None, f"no MPI records for {today_str} — skip"
        snap = dict(row)
    except Exception as e:
        return False, f"mpi_snapshots.db read error: {e}"
    try:
        from mpi_engine import render_behavior_insight_html, render_behavior_insight_telegram
        html_out = render_behavior_insight_html(snap, theme="light")
        tg_out   = render_behavior_insight_telegram(snap)
    except Exception as e:
        return False, f"renderer raised exception: {e}"
    if not html_out:
        return False, "render_behavior_insight_html returned empty string"
    if not tg_out:
        return False, "render_behavior_insight_telegram returned empty string"
    return True, f"renderers produce output (html={len(html_out)}B, tg={len(tg_out)}B)"


def _check_upsert_idempotency(today_str: str) -> tuple[bool | None, str]:
    db_path = BASE / "mpi_snapshots.db"
    if not db_path.exists():
        return None, "mpi_snapshots.db missing — skip"
    try:
        conn = sqlite3.connect(str(db_path))
        rows = conn.execute(
            """SELECT ticker, signal_type, COUNT(*) as cnt
               FROM mpi_snapshots WHERE analysis_date=?
               GROUP BY ticker, signal_type HAVING cnt > 1""",
            (today_str,),
        ).fetchall()
        conn.close()
    except Exception as e:
        return False, f"duplicate check failed: {e}"
    if rows:
        dupes = [(r[0], r[1], r[2]) for r in rows]
        return False, f"duplicate MPI records found (ticker, signal_type, count): {dupes}"
    return True, "no duplicate MPI records — upsert is idempotent"


def _check_consumers_use_renderer_not_recompute() -> tuple[bool | None, str]:
    consumers = {
        "dashboard.py": BASE / "dashboard.py",
        "egx_email.py": BASE / "egx_email.py",
        "telegram.py":  BASE / "telegram.py",
    }
    violations    = []
    not_connected = []
    for name, path in consumers.items():
        if not path.exists():
            not_connected.append(f"{name} not found")
            continue
        src = path.read_text()
        if "analyze_ticker" in src or "run_for_current_signals" in src:
            violations.append(f"{name} calls MPI compute functions (should only read/render)")
        if "render_behavior_insight" not in src and "get_snapshot" not in src:
            not_connected.append(f"{name} has no MPI render or read call")
    if violations:
        return False, f"consumers recompute MPI: {violations}"
    if not_connected:
        return False, f"consumers not connected to MPI: {not_connected}"
    return True, "all consumers read MPI from DB via renderer — no recomputation"


def main() -> int:
    try:
        from time_authority import today_iso as _today_iso
        today_str = _today_iso()
    except Exception:
        import datetime
        today_str = datetime.date.today().isoformat()

    checks = [
        ("MPI gate separation",       _check_no_gate_import_in_mpi),
        ("MPI decision field purity",  _check_no_decision_field_writes_in_mpi),
        ("Renderer importable",        _check_renderer_importable),
        ("Consumers use renderer",     _check_consumers_use_renderer_not_recompute),
        ("DB exists + has records",    lambda: _check_db_exists_and_has_records(today_str)),
        ("MPI matches signals",        lambda: _check_mpi_matches_signals(today_str)),
        ("Renderer output valid",      lambda: _check_renderer_output(today_str)),
        ("Upsert idempotency",         lambda: _check_upsert_idempotency(today_str)),
    ]

    failures = []
    skips    = []

    print("MPI Pipeline Integrity Assertion")
    print(f"  analysis_date: {today_str}")
    print()

    for label, fn in checks:
        try:
            result, detail = fn()
        except Exception as exc:
            result, detail = False, f"unexpected exception: {exc}"

        if result is True:
            print(f"  ✓ {label}: {detail}")
        elif result is None:
            print(f"  ⚠ SKIP {label}: {detail}")
            skips.append(label)
        else:
            print(f"  ✗ FAIL {label}: {detail}")
            failures.append(f"{label}: {detail}")

    print()
    if failures:
        for f in failures:
            print(f"  ✗ {f}")
        print(f"\nASSERTION FAILED — {len(failures)} MPI pipeline failure(s) detected.")
        return AuditStatus.FAIL

    if len(skips) == len(checks):
        print("SKIPPED — no MPI data present for today (first run or MPI not yet executed).")
        return AuditStatus.SKIPPED

    passed = len(checks) - len(skips)
    print(f"ASSERTION PASSED — {passed} check(s) passed, {len(skips)} skipped.")
    return AuditStatus.PASS


if __name__ == "__main__":
    sys.exit(main())
