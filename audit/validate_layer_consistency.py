"""
Cross-Layer Consistency Validator
Proves that all presentation layers display identical entry_zone values
for every ticker that has v1 constitutional events.

Checks:
  1. universe_snapshot.db.entry_zone == latest v1 timeline event's entry_price
  2. presentation_snapshot.json universe_snapshot.entry_zone matches DB
  3. presentation_snapshot.json re_accumulation latest event matches universe entry_zone
  4. dashboard.html universe table and active table show consistent values

Exits 0 if all checks pass, 1 on any failure.
"""
from __future__ import annotations

import json
import re
import sqlite3
import sys
from pathlib import Path

BASE   = Path(__file__).parent.parent
GOLDEN = Path(__file__).parent / "golden_master"

PASS = "\033[92mPASS\033[0m"
FAIL = "\033[91mFAIL\033[0m"

failures: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    """Print a PASS/FAIL line and accumulate failures."""
    status = PASS if ok else FAIL
    print(f"  [{status}] {label}" + (f" — {detail}" if detail else ""))
    if not ok:
        failures.append(f"{label}: {detail}")


def scalar(db_path: Path, sql: str, params: tuple = ()):
    """Return first column of first row from db_path, or None if DB absent."""
    if not db_path.exists():
        return None
    conn = sqlite3.connect(str(db_path))
    row = conn.execute(sql, params).fetchone()
    conn.close()
    return row[0] if row else None


# ── 1. Build source-of-truth: latest v1 event per ticker from COE DB ──────────
print("\n=== CROSS-LAYER CONSISTENCY VALIDATION ===\n")
print("SOURCE OF TRUTH: constitutional_opportunity_events.db (latest v1 event per ticker)")

COE_DB  = BASE / "constitutional_opportunity_events.db"
SNAP_DB = BASE / "universe_snapshot.db"
SNAP_JSON = BASE / "presentation_snapshot.json"
DASH_HTML = BASE / "dashboard.html"

if not COE_DB.exists():
    print(f"[{FAIL}] COE DB not found: {COE_DB}")
    sys.exit(1)

conn = sqlite3.connect(str(COE_DB))
conn.row_factory = sqlite3.Row
timeline_v1 = conn.execute("""
    SELECT ticker, event_type, event_date, entry_price
    FROM constitutional_opportunity_events
    WHERE signal_version = 'v1'
    ORDER BY ticker, event_date DESC
""").fetchall()
conn.close()

# Latest event per ticker
latest_v1: dict[str, dict] = {}
for row in timeline_v1:
    t = row["ticker"]
    if t not in latest_v1:
        latest_v1[t] = dict(row)

print(f"  Found {len(latest_v1)} tickers with v1 events\n")

# ── 2. Check universe_snapshot.db against COE truth ───────────────────────────
print("CHECK 1: universe_snapshot.db.entry_zone == latest v1 event entry_price")
if SNAP_DB.exists():
    conn = sqlite3.connect(str(SNAP_DB))
    conn.row_factory = sqlite3.Row
    snap_rows = {r["ticker"]: dict(r) for r in conn.execute("SELECT * FROM universe_snapshot").fetchall()}
    conn.close()

    mismatches = 0
    for ticker, truth in sorted(latest_v1.items()):
        if ticker not in snap_rows:
            check(f"  {ticker} in universe_snapshot", False, "MISSING from DB")
            mismatches += 1
            continue
        snap_ez = snap_rows[ticker].get("entry_zone")
        truth_ep = truth["entry_price"]
        # Allow 0.001 float tolerance
        ok = snap_ez is not None and abs(snap_ez - truth_ep) < 0.001
        check(f"  {ticker} entry_zone", ok,
              f"universe_snapshot={snap_ez} vs coe_latest={truth_ep} ({truth['event_type']} {truth['event_date']})")
        if not ok:
            mismatches += 1

    print(f"  → {len(latest_v1) - mismatches}/{len(latest_v1)} tickers consistent")
else:
    check("universe_snapshot.db exists", False, "FILE_NOT_FOUND")

# ── 3. Check presentation_snapshot.json universe_snapshot section ──────────────
print("\nCHECK 2: presentation_snapshot.json universe_snapshot.entry_zone matches DB")
if SNAP_JSON.exists():
    snap_data = json.loads(SNAP_JSON.read_text())
    ps_universe = {r["ticker"]: r for r in snap_data.get("universe_snapshot", [])}

    for ticker, truth in sorted(latest_v1.items()):
        if ticker not in ps_universe:
            check(f"  {ticker} in PS universe", False, "MISSING")
            continue
        ps_ez = ps_universe[ticker].get("entry_zone")
        truth_ep = truth["entry_price"]
        ok = ps_ez is not None and abs(ps_ez - truth_ep) < 0.001
        check(f"  {ticker} PS.universe_snapshot.entry_zone", ok,
              f"json={ps_ez} vs coe_latest={truth_ep}")
else:
    check("presentation_snapshot.json exists", False, "FILE_NOT_FOUND")

# ── 4. Check presentation_snapshot.json re_accumulation latest event ───────────
print("\nCHECK 3: presentation_snapshot.json re_accumulation latest entry_price matches universe")
if SNAP_JSON.exists():
    re_acc_events = snap_data.get("re_accumulation", [])
    re_acc_by_ticker: dict[str, list] = {}
    for ev in re_acc_events:
        t = ev.get("ticker", "")
        re_acc_by_ticker.setdefault(t, []).append(ev)

    checked = 0
    for ticker, events in sorted(re_acc_by_ticker.items()):
        if ticker not in latest_v1:
            continue
        # Latest event = highest event_date
        latest_ev = max(events, key=lambda e: e.get("event_date", ""))
        ev_ep = latest_ev.get("entry_price")
        truth_ep = latest_v1[ticker]["entry_price"]
        ok = ev_ep is not None and abs(ev_ep - truth_ep) < 0.001
        check(f"  {ticker} re_acc latest vs universe", ok,
              f"event_entry={ev_ep} ({latest_ev.get('event_date')}) vs coe_latest={truth_ep}")
        checked += 1

    if checked == 0:
        print("  (no re_accumulation events to check)")
else:
    check("presentation_snapshot.json for re_acc check", False, "FILE_NOT_FOUND")

# ── 5. Dashboard HTML sanity check — universe table values ────────────────────
print("\nCHECK 4: dashboard.html universe table entry zone values for v1 tickers")
if DASH_HTML.exists():
    html = DASH_HTML.read_text()
    dash_mismatches = 0
    for ticker, truth in sorted(latest_v1.items()):
        truth_ep = truth["entry_price"]
        expected_str = f"{truth_ep:.2f}"
        # Check that the expected entry price appears near the ticker in the HTML
        # We look for the ticker symbol and the expected value within a 600-char window
        ticker_positions = [m.start() for m in re.finditer(re.escape(ticker), html)]
        found_in_window = any(
            expected_str in html[max(0, pos - 50):pos + 600]
            for pos in ticker_positions
        )
        check(f"  {ticker} {expected_str} EGP in dashboard", found_in_window,
              f"Expected '{expected_str}' near {ticker}")
        if not found_in_window:
            dash_mismatches += 1

    print(f"  → {len(latest_v1) - dash_mismatches}/{len(latest_v1)} tickers found with correct values")
else:
    check("dashboard.html exists", False, "FILE_NOT_FOUND")

# ── Summary ───────────────────────────────────────────────────────────────────
print(f"\n{'='*60}")
if failures:
    print(f"RESULT: FAIL — {len(failures)} inconsistencies detected:")
    for f in failures:
        print(f"  ✗ {f}")
    sys.exit(1)
else:
    print("RESULT: ALL LAYERS CONSISTENT — Single source of truth validated.")
    sys.exit(0)
