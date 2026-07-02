"""
Stale Unnotified Events Assertion — Constitutional Architecture Guard.

Verifies that no CONST_BUY transitions from previous trading days remain
permanently unnotified (notified_email=0 AND notified_tg=0).

A stale unnotified event means a FIRST_BUY or RE_ACCUMULATION signal was
detected and recorded in signal_event_log, but send_change_alert() was never
called or failed silently. The retry mechanism in detect_signal_changes()
handles same-day retries, but cannot recover events from previous days if the
ticker has since exited the buy zone.

This assertion is the CI-level visibility gate — it fails if any such orphaned
events exist, forcing investigation.

Exits 0 (PASS) if no stale events exist.
Exits 1 (FAIL) if stale unnotified events are found.
"""
from __future__ import annotations

import sys
from pathlib import Path

BASE = Path(__file__).parent.parent
sys.path.insert(0, str(BASE))

from audit.audit_status import AuditStatus


def main() -> int:
    print("Stale Unnotified Events Assertion")
    print("  Checking for CONST_BUY transitions from previous days with no notification sent...")
    print()

    try:
        from notifications.signal_state_store import get_stale_unnotified
        from time_authority import today_iso
    except Exception as e:
        print(f"  [ERROR] Cannot import dependencies: {e}")
        return AuditStatus.FAIL

    today = today_iso()
    stale = get_stale_unnotified(today)

    if not stale:
        print("  ✓ No stale unnotified events found.")
        print()
        print("ASSERTION PASSED — all recorded CONST_BUY transitions were notified.")
        return AuditStatus.PASS

    print(f"  ✗ Found {len(stale)} stale unnotified event(s):")
    for s in stale:
        print(f"      ticker={s['ticker']}  date={s['event_date']}  transition={s['from_state']}→CONSTITUTIONAL_BUY")
    print()
    print("  These events were recorded in signal_event_log but send_change_alert()")
    print("  was never called or failed. They cannot be auto-retried (ticker may")
    print("  have left buy zone). Investigate the scan logs for those dates.")
    print()
    print("ASSERTION FAILED — stale unnotified FIRST_BUY events exist.")
    return AuditStatus.FAIL


if __name__ == "__main__":
    sys.exit(main())
