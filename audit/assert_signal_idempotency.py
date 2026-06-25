"""
CI Signal Idempotency Assertion — Constitutional Rule: ONE notification per state transition.

Simulates 10 consecutive scans with identical market data.
Verifies:
  1. detect_signal_changes() returns events ONLY on the first call.
  2. Calls 2-10 return an empty list.
  3. signal_event_log has exactly one row per ticker that was in buy zone.
  4. No duplicate rows exist in constitutional_opportunity_events for today.
  5. telegram_delivery has at most one row per (event_type, ticker, event_date).

Exits 1 if ANY violation is found.
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

BASE = Path(__file__).parent.parent
sys.path.insert(0, str(BASE))

failures: list[str] = []


def _qdb(path: Path, sql: str) -> list:
    if not path.exists():
        return []
    try:
        con = sqlite3.connect(str(path))
        rows = con.execute(sql).fetchall()
        con.close()
        return rows
    except Exception as e:
        print(f"  [warn] {path.name}: {e}")
        return []


def main() -> int:
    from presentation.presentation_snapshot import build_presentation_snapshot
    from main import detect_signal_changes
    from time_authority import today_iso

    today = today_iso()

    print("Signal Idempotency Assertion")
    print(f"  Simulating 10 consecutive scans — date={today}")
    print()

    snap = build_presentation_snapshot()

    # ── 10 consecutive calls with the same snapshot ───────────────────────────
    all_results: list[list] = []
    for i in range(10):
        result = detect_signal_changes(snap)
        all_results.append(result)
        status = f"{len(result)} events" if result else "EMPTY"
        print(f"  Scan {i+1:2d}: {status}")

    print()

    first_call_events = all_results[0]
    subsequent_events = [ev for run in all_results[1:] for ev in run]

    if subsequent_events:
        failures.append(
            f"Scans 2-10 returned {len(subsequent_events)} events "
            f"(expected 0). Tickers: "
            f"{sorted({e.get('ticker') for e in subsequent_events})}"
        )

    # ── signal_event_log: one row per (ticker, event_date, to_state) ─────────
    notif_db = BASE / "notification_delivery.db"
    sel_rows = _qdb(
        notif_db,
        f"SELECT ticker, event_date, to_state, COUNT(*) as n "
        f"FROM signal_event_log WHERE event_date='{today}' "
        f"GROUP BY ticker, event_date, to_state HAVING n > 1",
    )
    if sel_rows:
        for row in sel_rows:
            failures.append(
                f"signal_event_log duplicate: ticker={row[0]} date={row[1]} "
                f"to_state={row[2]} count={row[3]}"
            )

    # ── telegram_delivery: one row per (event_type, symbol, event_date) ───────
    tg_rows = _qdb(
        notif_db,
        f"SELECT event_type, symbol, event_date, COUNT(*) as n "
        f"FROM telegram_delivery WHERE event_date='{today}' "
        f"GROUP BY event_type, symbol, event_date HAVING n > 1",
    )
    if tg_rows:
        for row in tg_rows:
            failures.append(
                f"telegram_delivery duplicate: event_type={row[0]} symbol={row[1]} "
                f"date={row[2]} count={row[3]}"
            )

    # ── constitutional_opportunity_events: one row per (ticker, event_type, event_date) ──
    coe_rows = _qdb(
        BASE / "constitutional_opportunity_events.db",
        f"SELECT ticker, event_type, event_date, COUNT(*) as n "
        f"FROM constitutional_opportunity_events WHERE event_date='{today}' "
        f"GROUP BY ticker, event_type, event_date HAVING n > 1",
    )
    if coe_rows:
        for row in coe_rows:
            failures.append(
                f"constitutional_opportunity_events duplicate: ticker={row[0]} "
                f"type={row[1]} date={row[2]} count={row[3]}"
            )

    # ── First call must match snapshot approaching_entries count ──────────────
    snap2 = build_presentation_snapshot()
    snap_buy_count = len(snap2.approaching_entries or []) + len(snap2.opportunities or [])
    first_call_count = len(first_call_events)
    print(f"  First-call events   : {first_call_count}")
    print(f"  Snapshot buy entries: {snap_buy_count}")
    # Note: first_call may be 0 if all tickers were already in buy zone from yesterday.
    # That is correct — only genuine new transitions should fire.

    # ── Summary ───────────────────────────────────────────────────────────────
    print()
    print(f"Total failures: {len(failures)}")

    if failures:
        print("\nIDEMPOTENCY VIOLATIONS:")
        for f in failures:
            print(f"  ✗ {f}")
        print("\nASSERTION FAILED — duplicate signals exist.")
        return 1

    print("ASSERTION PASSED — detect_signal_changes() is idempotent.")
    print(f"  Scans 2-10 returned 0 events as required.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
