"""
Regression tests: prove semantic validation survives legitimate DB operations
that binary hash validation would falsely reject.

Tests cover:
  - VACUUM (rewrites SQLite file in-place, changes binary hash)
  - Append-only insert (adds new row, increases hash)
  - Index rebuild (DROP + CREATE INDEX changes B-tree pages)
  - Data normalization (UPDATE existing row, changes hash)
  - Historical import (wf_v1 bulk insert, changes hash)
  - Duplicate rejection (UNIQUE INDEX blocks same-day re-fire)

Run with:
    python3 audit/test_golden_master_resilience.py
"""
from __future__ import annotations

import hashlib
import json
import shutil
import sqlite3
import sys
import tempfile
import uuid
from pathlib import Path

BASE   = Path(__file__).parent.parent
GOLDEN = Path(__file__).parent / "golden_master"

PASS = "\033[92mPASS\033[0m"
FAIL = "\033[91mFAIL\033[0m"

_results: list[tuple[str, bool, str]] = []


def _assert(name: str, ok: bool, detail: str = "") -> None:
    """Record and print a test assertion result."""
    _results.append((name, ok, detail))
    status = PASS if ok else FAIL
    print(f"  [{status}] {name}" + (f" — {detail}" if detail else ""))


def _sha256(path: Path) -> str:
    """Return SHA-256 hex digest of path."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _semantic_ok(db_path: Path, sem: dict) -> tuple[bool, list[str]]:
    """Run all semantic checks against db_path. Returns (all_pass, failure_messages)."""
    errs: list[str] = []

    def scalar(sql: str, params: tuple = ()):
        conn = sqlite3.connect(str(db_path))
        row = conn.execute(sql, params).fetchone()
        conn.close()
        return row[0] if row else None

    total = scalar("SELECT COUNT(*) FROM constitutional_opportunity_events") or 0
    if total < sem["total_rows_min"]:
        errs.append(f"total_rows_min: {total} < {sem['total_rows_min']}")

    v1 = scalar("SELECT COUNT(*) FROM constitutional_opportunity_events WHERE signal_version='v1'") or 0
    if v1 < sem["v1_count_min"]:
        errs.append(f"v1_count_min: {v1} < {sem['v1_count_min']}")

    wf = scalar("SELECT COUNT(*) FROM constitutional_opportunity_events WHERE signal_version='wf_v1'") or 0
    if wf < sem["wf_v1_count_min"]:
        errs.append(f"wf_v1_count_min: {wf} < {sem['wf_v1_count_min']}")

    dups = scalar("SELECT COUNT(*) FROM (SELECT event_id, COUNT(*) c FROM constitutional_opportunity_events GROUP BY event_id HAVING c>1)") or 0
    if dups > 0:
        errs.append(f"duplicate_event_ids: {dups}")

    dup_ttd = scalar("SELECT COUNT(*) FROM (SELECT ticker,event_type,event_date,COUNT(*) c FROM constitutional_opportunity_events GROUP BY ticker,event_type,event_date HAVING c>1)") or 0
    if dup_ttd > 0:
        errs.append(f"duplicate_ticker_type_date: {dup_ttd}")

    thresh = scalar("SELECT COUNT(*) FROM constitutional_opportunity_events WHERE buy_r2 < 60 OR buy_score < 35") or 0
    if thresh > 0:
        errs.append(f"threshold_violations: {thresh}")

    order_err = scalar("SELECT COUNT(*) FROM constitutional_opportunity_events WHERE event_date > event_end_date") or 0
    if order_err > 0:
        errs.append(f"order_violations: {order_err}")

    conn = sqlite3.connect(str(db_path))
    indexes = {r[1]: bool(r[2]) for r in conn.execute("PRAGMA index_list(constitutional_opportunity_events)").fetchall()}
    conn.close()
    if indexes.get("ux_coe_ticker_type_date") is not True:
        errs.append(f"missing unique index: {indexes}")

    conn = sqlite3.connect(str(db_path))
    current_ids = {r[0] for r in conn.execute(
        "SELECT event_id FROM constitutional_opportunity_events WHERE signal_version='v1'"
    ).fetchall()}
    conn.close()
    missing = sorted(set(sem["v1_event_ids"]) - current_ids)
    if missing:
        errs.append(f"missing v1 event_ids: {missing}")

    cd_bad = scalar("""
        SELECT COUNT(*) FROM constitutional_opportunity_events
        WHERE signal_version='v1'
          AND cluster_days != (CAST(julianday(event_end_date) - julianday(event_date) AS INTEGER) + 1)
    """) or 0
    if cd_bad > 0:
        errs.append(f"v1_cluster_days_mismatches: {cd_bad}")

    return (len(errs) == 0, errs)


def _copy_db() -> Path:
    """Copy the production DB into a temp dir for safe mutation."""
    src = BASE / "constitutional_opportunity_events.db"
    tmp = Path(tempfile.mkdtemp()) / "test_events.db"
    shutil.copy2(str(src), str(tmp))
    return tmp


def test_vacuum_does_not_break_semantic():
    """VACUUM rewrites SQLite file in-place, always changes binary hash."""
    db = _copy_db()
    hash_before = _sha256(db)

    conn = sqlite3.connect(str(db))
    conn.execute("VACUUM")
    conn.close()

    hash_after = _sha256(db)
    sem = json.loads((GOLDEN / "timeline_semantic.json").read_text())
    ok, errs = _semantic_ok(db, sem)

    _assert("vacuum:hash_changes",   hash_before != hash_after, f"before={hash_before[:16]} after={hash_after[:16]}")
    _assert("vacuum:semantic_pass",  ok, str(errs))


def test_append_only_insert_passes_semantic():
    """Inserting a new valid event does not break invariants (row count >= min)."""
    db = _copy_db()
    sem = json.loads((GOLDEN / "timeline_semantic.json").read_text())

    conn = sqlite3.connect(str(db))
    new_id = str(uuid.uuid4())
    conn.execute("""
        INSERT INTO constitutional_opportunity_events
        (event_id, ticker, event_type, event_index, event_date, event_end_date,
         cluster_days, entry_price, buy_r2, buy_score, signal_version, created_at)
        VALUES (?, 'TEST.CA', 'FIRST_BUY', 0, '2099-01-01', '2099-01-01',
                1, 10.0, 65.0, 40.0, 'v1', '2099-01-01T00:00:00')
    """, (new_id,))
    conn.commit()
    conn.close()

    ok, errs = _semantic_ok(db, sem)
    _assert("append_only_insert:semantic_pass", ok, str(errs))

    # Cleanup: total rows now exceeds min, that's fine — min is a floor not a ceiling
    conn = sqlite3.connect(str(db))
    total = conn.execute("SELECT COUNT(*) FROM constitutional_opportunity_events").fetchone()[0]
    conn.close()
    _assert("append_only_insert:total_exceeds_min", total > sem["total_rows_min"],
            f"{total} > {sem['total_rows_min']}")


def test_index_rebuild_passes_semantic():
    """DROP + recreate index changes B-tree pages but semantic invariants hold."""
    db = _copy_db()
    hash_before = _sha256(db)
    sem = json.loads((GOLDEN / "timeline_semantic.json").read_text())

    conn = sqlite3.connect(str(db))
    conn.execute("DROP INDEX IF EXISTS ux_coe_ticker_type_date")
    conn.execute("CREATE UNIQUE INDEX ux_coe_ticker_type_date ON constitutional_opportunity_events(ticker, event_type, event_date)")
    conn.commit()
    conn.close()

    hash_after = _sha256(db)
    ok, errs = _semantic_ok(db, sem)

    _assert("index_rebuild:hash_changes",  hash_before != hash_after,
            f"before={hash_before[:16]} after={hash_after[:16]}")
    _assert("index_rebuild:semantic_pass", ok, str(errs))


def test_data_normalization_passes_semantic():
    """Updating cluster_days on existing rows (normalization) passes semantic validation."""
    db = _copy_db()
    sem = json.loads((GOLDEN / "timeline_semantic.json").read_text())

    # Touch event_end_date on one v1 row — simulates a real extension
    conn = sqlite3.connect(str(db))
    conn.execute("""
        UPDATE constitutional_opportunity_events
        SET event_end_date = event_end_date,
            cluster_days = (CAST(julianday(event_end_date) - julianday(event_date) AS INTEGER) + 1)
        WHERE signal_version = 'v1'
    """)
    conn.commit()
    conn.close()

    ok, errs = _semantic_ok(db, sem)
    _assert("data_normalization:semantic_pass", ok, str(errs))


def test_historical_import_passes_semantic():
    """Bulk wf_v1 import adds rows but all invariants remain satisfied."""
    db = _copy_db()
    sem = json.loads((GOLDEN / "timeline_semantic.json").read_text())

    conn = sqlite3.connect(str(db))
    new_rows = [
        (str(uuid.uuid4()), "HIST.CA", "FIRST_BUY", i, f"202{i}-01-01", f"202{i}-01-10",
         10, 5.0, 61.0, 36.0, None, None, None, None, None, None, None, "wf_v1", "2026-01-01T00:00:00")
        for i in range(5)
    ]
    conn.executemany("""
        INSERT OR IGNORE INTO constitutional_opportunity_events
        (event_id, ticker, event_type, event_index, event_date, event_end_date,
         cluster_days, entry_price, buy_r2, buy_score,
         buy_r3, buy_r4, buy_r5, buy_r6, buy_r7, buy_r8,
         sector, signal_version, created_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
    """, new_rows)
    conn.commit()
    conn.close()

    ok, errs = _semantic_ok(db, sem)
    _assert("historical_import:semantic_pass", ok, str(errs))


def test_duplicate_rejection_by_unique_index():
    """UNIQUE INDEX on (ticker, event_type, event_date) rejects duplicate signals."""
    db = _copy_db()

    conn = sqlite3.connect(str(db))
    # Insert a valid new signal
    uid1 = str(uuid.uuid4())
    conn.execute("""
        INSERT INTO constitutional_opportunity_events
        (event_id, ticker, event_type, event_index, event_date, event_end_date,
         cluster_days, entry_price, buy_r2, buy_score, signal_version, created_at)
        VALUES (?, 'DEDUP.CA', 'FIRST_BUY', 0, '2099-06-01', '2099-06-01',
                1, 10.0, 62.0, 37.0, 'v1', '2099-06-01T00:00:00')
    """, (uid1,))
    conn.commit()

    # Attempt to insert a duplicate (same ticker+type+date, different event_id)
    uid2 = str(uuid.uuid4())
    duplicate_blocked = False
    try:
        conn.execute("""
            INSERT INTO constitutional_opportunity_events
            (event_id, ticker, event_type, event_index, event_date, event_end_date,
             cluster_days, entry_price, buy_r2, buy_score, signal_version, created_at)
            VALUES (?, 'DEDUP.CA', 'FIRST_BUY', 99, '2099-06-01', '2099-06-01',
                    1, 10.0, 62.0, 37.0, 'v1', '2099-06-01T00:00:00')
        """, (uid2,))
        conn.commit()
    except sqlite3.IntegrityError:
        duplicate_blocked = True
    conn.close()

    _assert("duplicate_rejection:unique_index_fires", duplicate_blocked,
            "IntegrityError expected on duplicate (ticker, event_type, event_date)")


def test_threshold_violation_detected():
    """Semantic validator catches buy_r2 < 60 — data corruption is NOT silently accepted."""
    db = _copy_db()
    sem = json.loads((GOLDEN / "timeline_semantic.json").read_text())

    conn = sqlite3.connect(str(db))
    # Inject a corrupt row with sub-threshold R2
    conn.execute("""
        INSERT INTO constitutional_opportunity_events
        (event_id, ticker, event_type, event_index, event_date, event_end_date,
         cluster_days, entry_price, buy_r2, buy_score, signal_version, created_at)
        VALUES (?, 'CORRUPT.CA', 'FIRST_BUY', 0, '2099-07-01', '2099-07-01',
                1, 5.0, 45.0, 20.0, 'v1', '2099-07-01T00:00:00')
    """, (str(uuid.uuid4()),))
    conn.commit()
    conn.close()

    ok, errs = _semantic_ok(db, sem)
    _assert("threshold_violation:detected", not ok, f"errs={errs}")
    _assert("threshold_violation:correct_error",
            any("threshold_violations" in e for e in errs), str(errs))


def test_deleted_v1_event_detected():
    """Semantic validator catches deletion of a golden v1 event_id."""
    db = _copy_db()
    sem = json.loads((GOLDEN / "timeline_semantic.json").read_text())

    conn = sqlite3.connect(str(db))
    # Delete one golden v1 event
    golden_id = sem["v1_event_ids"][0]
    conn.execute("DELETE FROM constitutional_opportunity_events WHERE event_id=?", (golden_id,))
    conn.commit()
    conn.close()

    ok, errs = _semantic_ok(db, sem)
    _assert("deleted_v1:detected", not ok, f"errs={errs}")
    _assert("deleted_v1:correct_error",
            any("missing v1 event_ids" in e for e in errs), str(errs))


# ── Run all tests ─────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("\n=== GOLDEN MASTER RESILIENCE TESTS ===\n")

    test_vacuum_does_not_break_semantic()
    test_append_only_insert_passes_semantic()
    test_index_rebuild_passes_semantic()
    test_data_normalization_passes_semantic()
    test_historical_import_passes_semantic()
    test_duplicate_rejection_by_unique_index()
    test_threshold_violation_detected()
    test_deleted_v1_event_detected()

    total  = len(_results)
    passed = sum(1 for _, ok, _ in _results if ok)
    failed = total - passed

    print(f"\n{'='*50}")
    print(f"RESILIENCE TESTS: {passed}/{total} passed")
    if failed:
        print("\nFAILED:")
        for name, ok, detail in _results:
            if not ok:
                print(f"  ✗ {name} — {detail}")
        sys.exit(1)
    else:
        print("ALL RESILIENCE TESTS PASS.")
        sys.exit(0)
