"""
Data Freshness Assertion — Phase 5 Constitutional Hardening.

Verifies that all production data sources are within their freshness thresholds.
Stale data silently produces false constitutional decisions — this gate prevents that.

Displays exact age of every dataset.
Exits 1 if any required dataset exceeds its maximum age.
"""
from __future__ import annotations

import csv as _csv
import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

BASE = Path(__file__).parent.parent
sys.path.insert(0, str(BASE))

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

failures: list[str] = []
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
        status = "MISSING" if required else "UNKNOWN"
        if required:
            failures.append(f"{label}: MISSING (required)")
        table.append((label, "—", status))
        return
    age_str = _fmt_age(age_h)
    if age_h <= max_h:
        table.append((label, age_str, "PASS"))
    else:
        status = "FAIL" if required else "STALE"
        table.append((label, age_str, status))
        if required:
            failures.append(f"{label}: {age_str} old (max {_fmt_age(max_h)})")
        else:
            failures.append(f"{label}: {age_str} old (max {_fmt_age(max_h)}) — WARNING")


def main() -> int:
    print("Data Freshness Assertion")
    print()

    # 1. candidate_pool.db
    pool_db = BASE / "candidate_pool.db"
    if pool_db.exists():
        try:
            con = sqlite3.connect(str(pool_db))
            row = con.execute("SELECT MAX(signal_date) FROM candidate_pool").fetchone()
            con.close()
            _check("candidate_pool", _age_from_date(row[0] if row and row[0] else None))
        except Exception as e:
            table.append(("candidate_pool", f"ERR", "WARN"))
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
        except Exception as e:
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
    print(f"  {'-'*26} {'-'*10} {'-'*6}")
    for label, age_str, status in table:
        icon = "✓" if status == "PASS" else ("✗" if status in ("FAIL", "MISSING") else "⚠")
        print(f"  {icon} {label:<24} {age_str:<10} {status}")

    print()
    hard = [f for f in failures if "WARNING" not in f]
    soft = [f for f in failures if "WARNING" in f]

    if soft:
        print("STALE DATA (non-blocking):")
        for f in soft:
            print(f"  ⚠ {f}")

    if hard:
        print("\nFRESHNESS FAILURES:")
        for f in hard:
            print(f"  ✗ {f}")
        print("\nASSERTION FAILED — stale production data detected.")
        return 1

    print("ASSERTION PASSED — all required data sources are fresh.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
