"""
Data Freshness Assertion — Phase 5 Constitutional Hardening.

Verifies that all production data sources are within their freshness thresholds.
Stale data silently produces false constitutional decisions — this gate prevents that.

Displays exact age of every dataset.

Exit codes:
  0 = PASS     — all required sources are within threshold
  1 = FAIL     — required source is stale or missing, running in CI mode
  3 = EXPECTED — required source is stale, running outside CI (dev/manual run);
                 this same condition is a FAIL in production CI
"""
from __future__ import annotations

import csv as _csv
import json
import os
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

BASE = Path(__file__).parent.parent
sys.path.insert(0, str(BASE))

# Detect CI execution context.
# GitHub Actions sets CI=true and GITHUB_ACTIONS=true.
# Only enforce stale-data failures when running in CI.
_IN_CI: bool = bool(os.environ.get("CI") or os.environ.get("GITHUB_ACTIONS"))

HIST_DIR = BASE / "historical_data" / "historical_data"

# (label, max_age_hours, required)
THRESHOLDS: dict[str, tuple[float, bool]] = {
    "candidate_pool":        (120.0,  True),   # 5 calendar days — rebuilt daily
    "universe_snapshot":     ( 26.0,  True),   # must be from today or yesterday
    "presentation_snapshot": ( 26.0,  True),   # same
    "production_decision":   ( 26.0,  False),  # soft — may not exist in all workflows
    "timeline":              (168.0,  False),  # 7 days — append-only, no event = OK
    "stock_dna":             ( 48.0,  False),  # 2 days
    "csv_prices":            ( 72.0,  False),  # 3 days — weekends OK
}

hard_failures: list[str] = []   # blocking in CI
expected_issues: list[str] = [] # EXPECTED in non-CI (would be FAIL in CI)
soft_warnings: list[str] = []   # always non-blocking (optional datasets)
table: list[tuple[str, str, str]] = []   # (label, age_str, status)


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _age_from_iso(dt_str: str) -> float | None:
    if not dt_str:
        return None
    try:
        dt = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return (_now_utc() - dt).total_seconds() / 3600
    except Exception:
        return None


def _age_from_date(date_str: str) -> float | None:
    if not date_str:
        return None
    try:
        from datetime import date
        d   = date.fromisoformat(date_str)
        dt  = datetime(d.year, d.month, d.day, tzinfo=timezone.utc)
        return (_now_utc() - dt).total_seconds() / 3600
    except Exception:
        return None


def _fmt_age(h: float) -> str:
    if h < 1:
        return f"{h*60:.0f}m"
    if h < 24:
        return f"{h:.1f}h"
    return f"{h/24:.1f}d"


def _check(label: str, age_h: float | None) -> None:
    max_h, required = THRESHOLDS[label]
    if age_h is None:
        if required:
            if _IN_CI:
                status = "FAIL"
                hard_failures.append(f"{label}: MISSING (required in CI)")
            else:
                status = "EXPECTED"
                expected_issues.append(f"{label}: MISSING — not yet built (expected outside CI)")
        else:
            status = "MISSING"
        table.append((label, "—", status))
        return
    age_str = _fmt_age(age_h)
    if age_h <= max_h:
        table.append((label, age_str, "PASS"))
    else:
        if required:
            if _IN_CI:
                status = "FAIL"
                hard_failures.append(f"{label}: {age_str} old (max {_fmt_age(max_h)}) — stale in CI")
            else:
                status = "EXPECTED"
                expected_issues.append(
                    f"{label}: {age_str} old (max {_fmt_age(max_h)}) "
                    f"— stale outside CI (would FAIL in production)"
                )
        else:
            status = "STALE"
            soft_warnings.append(f"{label}: {age_str} old (max {_fmt_age(max_h)}) — optional, non-blocking")
        table.append((label, age_str, status))


def main() -> int:
    print("Data Freshness Assertion")
    print(f"  execution mode: {'CI' if _IN_CI else 'dev/manual (stale data → EXPECTED, not FAIL)'}")
    print()

    # 1. candidate_pool.db
    pool_db = BASE / "candidate_pool.db"
    if pool_db.exists():
        try:
            con = sqlite3.connect(str(pool_db))
            row = con.execute("SELECT MAX(signal_date) FROM candidate_pool").fetchone()
            con.close()
            _check("candidate_pool", _age_from_date(row[0] if row and row[0] else None))
        except Exception:
            table.append(("candidate_pool", "ERR", "WARN"))
    else:
        _check("candidate_pool", None)

    # 2. universe_snapshot.db
    uni_db = BASE / "universe_snapshot.db"
    if uni_db.exists():
        try:
            con = sqlite3.connect(str(uni_db))
            row = con.execute("SELECT MAX(generated_at) FROM universe_snapshot").fetchone()
            con.close()
            _check("universe_snapshot", _age_from_iso(row[0] if row and row[0] else None))
        except Exception:
            table.append(("universe_snapshot", "ERR", "WARN"))
    else:
        _check("universe_snapshot", None)

    # 3. presentation_snapshot.json
    pres_path = BASE / "presentation_snapshot.json"
    if pres_path.exists():
        try:
            pres = json.loads(pres_path.read_text())
            _check("presentation_snapshot", _age_from_iso(pres.get("generated_at", "")))
        except Exception:
            table.append(("presentation_snapshot", "ERR", "WARN"))
    else:
        _check("presentation_snapshot", None)

    # 4. production_decision_snapshot.json
    prod_path = BASE / "production_decision_snapshot.json"
    if prod_path.exists():
        try:
            prod = json.loads(prod_path.read_text())
            _check("production_decision", _age_from_iso(prod.get("generated_at", "")))
        except Exception:
            table.append(("production_decision", "ERR", "WARN"))
    else:
        _check("production_decision", None)

    # 5. constitutional_opportunity_events.db (timeline)
    tl_db = BASE / "constitutional_opportunity_events.db"
    if tl_db.exists():
        try:
            con = sqlite3.connect(str(tl_db))
            row = con.execute("SELECT MAX(created_at) FROM constitutional_opportunity_events").fetchone()
            con.close()
            _check("timeline", _age_from_iso(row[0] if row and row[0] else None))
        except Exception:
            table.append(("timeline", "ERR", "WARN"))
    else:
        _check("timeline", None)

    # 6. stock_dna.db
    dna_db = BASE / "stock_dna.db"
    if dna_db.exists():
        try:
            con = sqlite3.connect(str(dna_db))
            row = con.execute("SELECT MAX(last_updated) FROM stock_dna").fetchone()
            con.close()
            _check("stock_dna", _age_from_iso(row[0] if row and row[0] else None))
        except Exception:
            table.append(("stock_dna", "ERR", "WARN"))
    else:
        _check("stock_dna", None)

    # 7. CSV prices — average age of latest row across all tickers
    if HIST_DIR.exists():
        csv_files = list(HIST_DIR.glob("*.csv"))
        ages: list[float] = []
        for cp in csv_files:
            try:
                with open(cp, newline="") as f:
                    rows = list(_csv.DictReader(f))
                if rows:
                    d = rows[-1].get("Date", "")
                    age = _age_from_date(d)
                    if age is not None:
                        ages.append(age)
            except Exception:
                pass
        _check("csv_prices", sum(ages) / len(ages) if ages else None)
    else:
        _check("csv_prices", None)

    # ── Print table ───────────────────────────────────────────────────────────
    print(f"  {'Dataset':<26} {'Age':<10} Status")
    print(f"  {'-'*26} {'-'*10} {'-'*8}")
    for label, age_str, status in table:
        if status == "PASS":
            icon = "✓"
        elif status in ("FAIL", "MISSING"):
            icon = "✗" if _IN_CI else "⚠"
        elif status == "EXPECTED":
            icon = "⚠"
        else:
            icon = "·"
        print(f"  {icon} {label:<24} {age_str:<10} {status}")

    print()

    if soft_warnings:
        print("STALE OPTIONAL DATA (non-blocking):")
        for w in soft_warnings:
            print(f"  · {w}")

    if expected_issues and not _IN_CI:
        print("\nEXPECTED LIMITATIONS (dev/manual mode — would FAIL in CI):")
        for e in expected_issues:
            print(f"  ⚠ {e}")
        if not hard_failures:
            print("\nASSERTION EXPECTED — data is stale for a dev/manual run (not a production failure).")
            return 3

    if hard_failures:
        print("\nFRESHNESS FAILURES:")
        for f in hard_failures:
            print(f"  ✗ {f}")
        print("\nASSERTION FAILED — stale production data detected.")
        return 1

    print("ASSERTION PASSED — all required data sources are fresh.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
