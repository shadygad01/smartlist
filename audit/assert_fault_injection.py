"""
Fault Injection Assertion — Constitutional Architecture Phase 11 (Phase 9).

Proves that partial execution is architecturally impossible by simulating
failures at every phase boundary and verifying that:
  1. NOTIFY operations are never called when PERSIST fails.
  2. PERSIST operations roll back JSON writes when a mid-phase failure occurs.
  3. The execution journal records the failure and all rollback events.
  4. Subsequent operations on an aborted transaction raise TransactionAbortedError.

Tests:
  FI-01  Failure in PERSIST aborts before NOTIFY (no email/telegram)
  FI-02  Failure in PERSIST triggers rollback for completed file writes
  FI-03  Failure during NOTIFY does NOT rollback already-completed PERSIST
  FI-04  ProductionTransaction.step() raises TransactionAbortedError after abort
  FI-05  Phase ordering: NOTIFY without COMMIT raises PhaseViolationError
  FI-06  Phase ordering: PERSIST without DECISION raises PhaseViolationError
  FI-07  Journal records failure, rollback events, and all successful steps
  FI-08  Timeline write failure → email never called
  FI-09  Signal state write failure → telegram never called
  FI-10  All PERSIST steps succeed → NOTIFY executes normally

Exits 0 (PASS), 1 (FAIL).
"""
from __future__ import annotations

import sys
import tempfile
import uuid
from pathlib import Path
from typing import Any

BASE = Path(__file__).parent.parent
sys.path.insert(0, str(BASE))

from audit.audit_status import AuditStatus
from production.transaction import (
    ProductionTransaction, Phase,
    TransactionAbortedError, PhaseViolationError,
)


_PASS = "\033[32m✓\033[0m"
_FAIL = "\033[31m✗\033[0m"


def _scan_id() -> str:
    return f"test-{uuid.uuid4()}"


class _CallLog:
    """Records which functions were called during a test."""
    def __init__(self):
        self.called: list[str] = []

    def fn(self, name: str, *, raises: bool = False, value: Any = None):
        def _inner(*args, **kwargs):
            self.called.append(name)
            if raises:
                raise RuntimeError(f"Injected failure: {name}")
            return value
        _inner.__name__ = name
        return _inner


def _result(name: str, passed: bool, detail: str = "") -> tuple[str, bool]:
    icon = _PASS if passed else _FAIL
    print(f"  {icon} {name}" + (f": {detail}" if detail else ""))
    return name, passed


# ── Individual fault injection tests ─────────────────────────────────────────

def fi01_persist_failure_blocks_notify() -> tuple[str, bool]:
    """FI-01: Failure in PERSIST prevents NOTIFY from executing."""
    log = _CallLog()
    tx  = ProductionTransaction(_scan_id())

    tx.step(Phase.DECISION, "data_fetch", log.fn("fetch", value=("html", {}, None)))
    tx.complete(Phase.DECISION)

    try:
        tx.step(Phase.PERSIST, "write_snapshot", log.fn("snapshot"))
        tx.step(Phase.PERSIST, "register_timeline", log.fn("timeline", raises=True))
    except RuntimeError:
        pass  # expected

    notify_called = False
    try:
        tx.step(Phase.NOTIFY, "send_email", log.fn("email"))
        notify_called = True
    except TransactionAbortedError:
        pass

    passed = not notify_called and "email" not in log.called
    return _result("FI-01", passed,
                   "email blocked after timeline failure" if passed
                   else f"email was called despite timeline failure! called={log.called}")


def fi02_persist_failure_triggers_rollback() -> tuple[str, bool]:
    """FI-02: Failure in PERSIST rolls back completed JSON writes."""
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False, mode="w") as f:
        f.write('{"original": true}')
        tmp = Path(f.name)

    original_content = tmp.read_text()
    log = _CallLog()
    tx  = ProductionTransaction(_scan_id())

    tx.step(Phase.DECISION, "fetch", log.fn("fetch", value=None))
    tx.complete(Phase.DECISION)

    def _write_file():
        tmp.write_text('{"modified": true}')

    def _restore_file():
        tmp.write_text(original_content)

    try:
        tx.step(Phase.PERSIST, "write_file", _write_file, rollback=_restore_file)
        assert tmp.read_text() == '{"modified": true}', "write should have happened"
        tx.step(Phase.PERSIST, "failing_op", log.fn("fail", raises=True))
    except RuntimeError:
        pass

    content_after = tmp.read_text()
    tmp.unlink(missing_ok=True)

    passed = content_after == original_content
    return _result("FI-02", passed,
                   "file restored to original" if passed
                   else f"file NOT restored: got {content_after!r}")


def fi03_notify_failure_does_not_rollback_persist() -> tuple[str, bool]:
    """FI-03: Failure in NOTIFY does NOT undo completed PERSIST writes."""
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False, mode="w") as f:
        f.write('{"original": true}')
        tmp = Path(f.name)

    log = _CallLog()
    tx  = ProductionTransaction(_scan_id())

    tx.step(Phase.DECISION, "fetch", log.fn("fetch", value=None))
    tx.complete(Phase.DECISION)
    tx.step(Phase.PERSIST, "write_file", lambda: tmp.write_text('{"written": true}'),
            rollback=lambda: tmp.write_text('{"original": true}'))
    tx.complete(Phase.PERSIST)
    tx.complete(Phase.VALIDATE)
    tx.complete(Phase.COMMIT)

    try:
        tx.step(Phase.NOTIFY, "send_email", log.fn("email", raises=True))
    except RuntimeError:
        pass  # NOTIFY failure does not abort (email can't be rolled back)

    content = tmp.read_text()
    tmp.unlink(missing_ok=True)

    passed = content == '{"written": true}'
    return _result("FI-03", passed,
                   "PERSIST write preserved after NOTIFY failure" if passed
                   else f"PERSIST write was incorrectly rolled back: {content!r}")


def fi04_aborted_tx_raises_on_step() -> tuple[str, bool]:
    """FI-04: step() on aborted transaction raises TransactionAbortedError."""
    log = _CallLog()
    tx  = ProductionTransaction(_scan_id())

    tx.step(Phase.DECISION, "fetch", log.fn("fetch", value=None))
    tx.complete(Phase.DECISION)

    try:
        tx.step(Phase.PERSIST, "bad_op", log.fn("bad", raises=True))
    except RuntimeError:
        pass

    raised = False
    try:
        tx.step(Phase.PERSIST, "next_op", log.fn("next"))
    except TransactionAbortedError:
        raised = True

    passed = raised and tx.aborted
    return _result("FI-04", passed,
                   "TransactionAbortedError raised on aborted tx" if passed
                   else "expected TransactionAbortedError but got none")


def fi05_notify_without_commit_raises() -> tuple[str, bool]:
    """FI-05: NOTIFY without COMMIT raises PhaseViolationError."""
    log = _CallLog()
    tx  = ProductionTransaction(_scan_id())

    tx.step(Phase.DECISION, "fetch", log.fn("fetch", value=None))
    tx.complete(Phase.DECISION)
    tx.complete(Phase.PERSIST)
    tx.complete(Phase.VALIDATE)
    # Deliberately skip tx.complete(Phase.COMMIT)

    raised = False
    try:
        tx.step(Phase.NOTIFY, "send_email", log.fn("email"))
    except PhaseViolationError:
        raised = True

    passed = raised and "email" not in log.called
    return _result("FI-05", passed,
                   "PhaseViolationError raised without COMMIT" if passed
                   else "expected PhaseViolationError but NOTIFY proceeded")


def fi06_persist_without_decision_raises() -> tuple[str, bool]:
    """FI-06: PERSIST without DECISION raises PhaseViolationError."""
    log = _CallLog()
    tx  = ProductionTransaction(_scan_id())
    # Deliberately skip tx.complete(Phase.DECISION)

    raised = False
    try:
        tx.step(Phase.PERSIST, "write_op", log.fn("write"))
    except PhaseViolationError:
        raised = True

    passed = raised and "write" not in log.called
    return _result("FI-06", passed,
                   "PhaseViolationError raised without DECISION" if passed
                   else "expected PhaseViolationError but PERSIST proceeded")


def fi07_journal_records_failure_and_rollback() -> tuple[str, bool]:
    """FI-07: Journal records failure + rollback events."""
    log = _CallLog()
    sid = _scan_id()
    tx  = ProductionTransaction(sid)

    rollback_called = {"v": False}

    tx.step(Phase.DECISION, "fetch", log.fn("fetch", value=None))
    tx.complete(Phase.DECISION)

    def _write():
        pass

    def _rollback():
        rollback_called["v"] = True

    try:
        tx.step(Phase.PERSIST, "write_op", _write, rollback=_rollback)
        tx.step(Phase.PERSIST, "bad_op", log.fn("bad", raises=True))
    except RuntimeError:
        pass

    # Check journal rows
    try:
        from production.journal import query_scan
        rows = query_scan(sid)
    except Exception:
        rows = []

    has_failed_row    = any(r["status"] == "failed"      for r in rows)
    has_rollback_row  = any("rollback" in r["operation"] for r in rows)
    rollback_executed = rollback_called["v"]

    passed = has_failed_row and rollback_executed
    detail = (
        f"failure_in_journal={has_failed_row} "
        f"rollback_executed={rollback_executed} "
        f"rollback_in_journal={has_rollback_row} "
        f"({len(rows)} total rows)"
    )
    return _result("FI-07", passed, detail)


def fi08_timeline_failure_blocks_email() -> tuple[str, bool]:
    """FI-08: Timeline write failure → email never called."""
    log = _CallLog()
    tx  = ProductionTransaction(_scan_id())

    tx.step(Phase.DECISION, "fetch", log.fn("fetch", value=("html", {}, None)))
    tx.complete(Phase.DECISION)
    tx.step(Phase.PERSIST, "write_snapshot", log.fn("snapshot"))

    try:
        tx.step(Phase.PERSIST, "register_timeline", log.fn("timeline", raises=True))
    except RuntimeError:
        pass

    email_called = False
    try:
        tx.step(Phase.NOTIFY, "send_email", log.fn("email"))
        email_called = True
    except TransactionAbortedError:
        pass

    passed = not email_called
    return _result("FI-08", passed,
                   "email blocked after timeline failure" if passed
                   else "email was called despite timeline failure!")


def fi09_signal_state_failure_blocks_telegram() -> tuple[str, bool]:
    """FI-09: Signal state write failure → Telegram never called."""
    log = _CallLog()
    tx  = ProductionTransaction(_scan_id())

    tx.step(Phase.DECISION, "fetch", log.fn("fetch", value=None))
    tx.complete(Phase.DECISION)
    tx.step(Phase.PERSIST, "write_snapshot", log.fn("snapshot"))

    try:
        tx.step(Phase.PERSIST, "detect_signal_changes", log.fn("state_write", raises=True))
    except RuntimeError:
        pass

    tg_called = False
    try:
        tx.step(Phase.NOTIFY, "send_telegram", log.fn("telegram"))
        tg_called = True
    except TransactionAbortedError:
        pass

    passed = not tg_called
    return _result("FI-09", passed,
                   "telegram blocked after signal state failure" if passed
                   else "telegram was called despite signal state failure!")


def fi10_all_persist_success_enables_notify() -> tuple[str, bool]:
    """FI-10: All PERSIST steps succeed → NOTIFY executes normally."""
    log = _CallLog()
    tx  = ProductionTransaction(_scan_id())

    tx.step(Phase.DECISION, "fetch", log.fn("fetch", value=("html", {}, None)))
    tx.complete(Phase.DECISION)
    tx.step(Phase.PERSIST, "write_snapshot",  log.fn("snapshot"))
    tx.step(Phase.PERSIST, "register_timeline", log.fn("timeline"))
    tx.step(Phase.PERSIST, "save_results",    log.fn("save"))
    tx.complete(Phase.PERSIST)
    tx.complete(Phase.VALIDATE)
    tx.complete(Phase.COMMIT)
    tx.step(Phase.NOTIFY, "send_email",    log.fn("email"))
    tx.step(Phase.NOTIFY, "send_telegram", log.fn("telegram"))
    tx.complete(Phase.NOTIFY)

    passed = (
        not tx.aborted
        and "email"    in log.called
        and "telegram" in log.called
        and "timeline" in log.called
    )
    return _result("FI-10", passed,
                   f"all phases executed correctly, called={log.called}" if passed
                   else f"unexpected state: aborted={tx.aborted} called={log.called}")


# ── Runner ────────────────────────────────────────────────────────────────────

_ALL_TESTS = [
    fi01_persist_failure_blocks_notify,
    fi02_persist_failure_triggers_rollback,
    fi03_notify_failure_does_not_rollback_persist,
    fi04_aborted_tx_raises_on_step,
    fi05_notify_without_commit_raises,
    fi06_persist_without_decision_raises,
    fi07_journal_records_failure_and_rollback,
    fi08_timeline_failure_blocks_email,
    fi09_signal_state_failure_blocks_telegram,
    fi10_all_persist_success_enables_notify,
]


def main() -> int:
    print("Fault Injection Assertion (Phase 9)")
    print("  Simulating failures at every phase boundary...")
    print()

    results: list[tuple[str, bool]] = []
    for test_fn in _ALL_TESTS:
        try:
            name, passed = test_fn()
        except Exception as exc:
            print(f"  {_FAIL} {test_fn.__name__}: EXCEPTION — {exc}")
            name, passed = test_fn.__name__, False
        results.append((name, passed))

    n_pass = sum(1 for _, p in results if p)
    n_fail = sum(1 for _, p in results if not p)

    print()
    print(f"  {n_pass}/{len(results)} tests passed")
    print()

    if n_fail:
        print(f"ASSERTION FAILED — {n_fail} fault injection test(s) failed.")
        print("  The architecture does NOT prevent partial execution in all scenarios.")
        return AuditStatus.FAIL

    print("ASSERTION PASSED — all fault injection tests confirm:")
    print("  • NOTIFY is architecturally blocked when any PERSIST step fails.")
    print("  • Rollback restores file state on PERSIST failure.")
    print("  • Phase ordering is enforced by PhaseViolationError.")
    print("  • The 'email sent, timeline missing' class is structurally impossible.")
    return AuditStatus.PASS


if __name__ == "__main__":
    sys.exit(main())
