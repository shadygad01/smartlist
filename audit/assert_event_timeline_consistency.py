"""
Event Timeline Consistency Assertion — Constitutional Architecture Hardening.

constitutional_opportunity_events.db is the single source of truth for buy
signals. event_timeline.db is a separate, independently-persisted display feed
(the dashboard's "EVENT TIMELINE" widget) fed by a distinct write path
(log_buy_signal() in continuous_scan(), plus the reconciliation sync in
presentation_snapshot.py). Because these are two independent stores, they can
silently diverge — exactly what happened before: event_timeline.db was frozen
on the code branch instead of persisted via the data branch, so the dashboard's
Event Timeline widget kept showing stale buy signals days after new ones had
fired and been correctly notified.

This assertion verifies, for every v1 constitutional event in the trailing
window, that a matching BUY_SIGNAL row exists in event_timeline.db for the
same ticker+date — i.e. "buy signals match signals in EVENT TIMELINE".

Exits 1 on any missing BUY_SIGNAL row.
"""
from __future__ import annotations

import sqlite3
import sys
from datetime import date, timedelta
from pathlib import Path

BASE = Path(__file__).parent.parent
sys.path.insert(0, str(BASE))

from audit.audit_status import AuditStatus

TIMELINE_DB       = BASE / "constitutional_opportunity_events.db"
EVENT_TIMELINE_DB = BASE / "event_timeline.db"

WINDOW_DAYS = 60

failures: list[str] = []


def main() -> int:
    try:
        from time_authority import today_cairo
        today = today_cairo().isoformat()
    except Exception:
        today = date.today().isoformat()

    print(f"Event Timeline Consistency Assertion  date={today}  window={WINDOW_DAYS}d")
    print()

    if not TIMELINE_DB.exists():
        print("  INFO: constitutional_opportunity_events.db not found — nothing to validate")
        print("\nASSERTION PASSED — no constitutional events to check.")
        return AuditStatus.PASS

    cutoff = (date.fromisoformat(today) - timedelta(days=WINDOW_DAYS)).isoformat()

    con = sqlite3.connect(str(TIMELINE_DB))
    con.row_factory = sqlite3.Row
    try:
        buy_events = con.execute(
            "SELECT ticker, event_date FROM constitutional_opportunity_events "
            "WHERE event_date >= ? AND (signal_version='v1' OR signal_version IS NULL) "
            "ORDER BY event_date ASC, ticker ASC",
            (cutoff,),
        ).fetchall()
    finally:
        con.close()

    if not buy_events:
        print(f"  INFO: no v1 constitutional events in the last {WINDOW_DAYS}d — nothing to validate")
        print("\nASSERTION PASSED — no constitutional events to check.")
        return AuditStatus.PASS

    print(f"  Constitutional v1 events in window: {len(buy_events)}")

    if not EVENT_TIMELINE_DB.exists():
        for ev in buy_events:
            failures.append(f"{ev['ticker']} ({ev['event_date']}): event_timeline.db not found")
    else:
        et_con = sqlite3.connect(str(EVENT_TIMELINE_DB))
        try:
            et_rows = et_con.execute(
                "SELECT ticker, timestamp FROM event_timeline WHERE event_type='BUY_SIGNAL'"
            ).fetchall()
        finally:
            et_con.close()
        logged = {(t, (ts or "")[:10]) for t, ts in et_rows}

        for ev in buy_events:
            key = (ev["ticker"], ev["event_date"])
            if key not in logged:
                failures.append(
                    f"{ev['ticker']}: constitutional event on {ev['event_date']} has NO matching "
                    f"BUY_SIGNAL row in event_timeline.db (dashboard Event Timeline is stale)"
                )

    print()
    if failures:
        print("EVENT TIMELINE INCONSISTENCIES:")
        for f in failures:
            print(f"  ✗ {f}")
        print("\nASSERTION FAILED — event_timeline.db is out of sync with constitutional_opportunity_events.db.")
        print("Fix: event_timeline_engine.sync_buy_signals_from_constitutional_timeline() should have")
        print("caught this — check it ran and that event_timeline.db is being persisted (ci/data_files.txt).")
        return AuditStatus.FAIL

    print(f"ASSERTION PASSED — all {len(buy_events)} constitutional event(s) have matching BUY_SIGNAL entries.")
    return AuditStatus.PASS


if __name__ == "__main__":
    sys.exit(main())
