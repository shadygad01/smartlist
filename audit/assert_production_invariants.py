"""
Production Invariant Assertion — Constitutional Architecture Phase 11 (Phase 6).

Verifies all six production invariants that make Partial Execution detectable.

INV-01: email sent → signal_state_current has CONSTITUTIONAL_BUY for eligible tickers
INV-02: Telegram sent → constitutional_opportunity_events.db has v1 event for eligible tickers
INV-03: v1 timeline event for today → production_decision_snapshot has eligible=True
INV-04: production snapshot fresh relative to presentation snapshot (<10 min delta)
INV-05: NOTIFY journal rows → all PERSIST journal rows succeeded
INV-06: signal_state=CONSTITUTIONAL_BUY → v1 timeline event exists

Any FAIL means the pipeline executed partially — some side effect completed
while a dependent side effect did not.

Exits 0 (PASS), 1 (FAIL), 2 (SKIPPED if prerequisites missing).
"""
from __future__ import annotations

import sys
from pathlib import Path

BASE = Path(__file__).parent.parent
sys.path.insert(0, str(BASE))

from audit.audit_status import AuditStatus
from production.invariants import assert_production_invariants


def main() -> int:
    print("Production Invariant Assertion")
    print("  Checking all 6 production invariants for Partial Execution violations...")
    print()

    all_pass, failures = assert_production_invariants(verbose=True)

    print()
    if all_pass:
        print("ASSERTION PASSED — no Partial Execution invariant violations detected.")
        return AuditStatus.PASS
    else:
        print(f"\nASSERTION FAILED — {len(failures)} Partial Execution invariant(s) violated:")
        for f in failures:
            print(f"  ✗ {f}")
        return AuditStatus.FAIL


if __name__ == "__main__":
    sys.exit(main())
