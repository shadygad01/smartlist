"""
ProductionTransaction — Constitutional Architecture Phase 11.

Enforces explicit commit phases so partial execution is architecturally impossible.

GUARANTEE: Phase N cannot execute until Phase N-1 is marked complete.
           NOTIFY specifically requires DECISION + PERSIST + VALIDATE + COMMIT.
           If any operation in DECISION..COMMIT fails, the transaction aborts
           and NOTIFY is never reached.

Phase order (strictly enforced):
    DECISION  (1) — evaluate gate, fetch live data
    PERSIST   (2) — write all DBs and JSON artifacts + timeline registration
    VALIDATE  (3) — lightweight consistency check before commit
    COMMIT    (4) — mark scan as committed; last chance to abort
    NOTIFY    (5) — send email + Telegram (irreversible — must be last)
    PUBLISH   (6) — deploy dashboard, write fingerprints (best-effort)

Rollback (DECISION..COMMIT only):
    Every operation may supply a rollback callable. On abort, completed
    PERSIST/COMMIT rollbacks are called in LIFO order. NOTIFY and PUBLISH
    are never rolled back (external side effects cannot be recalled).

Usage:
    tx = ProductionTransaction(scan_id)
    html, results, snap = tx.step(Phase.DECISION, "build_report", build_report, ...)
    tx.complete(Phase.DECISION)
    tx.step(Phase.PERSIST, "write_snapshot", write_snapshot, snap, rollback=restore_snap)
    tx.step(Phase.PERSIST, "register_timeline", register_alert_events, changes)
    tx.complete(Phase.PERSIST)
    tx.complete(Phase.VALIDATE)   # inline validation may call tx.step() inside
    tx.complete(Phase.COMMIT)
    tx.step(Phase.NOTIFY, "send_email", send_email, html)   # only reachable here
    tx.step(Phase.NOTIFY, "send_telegram", send_telegram, ...)
    tx.complete(Phase.NOTIFY)
"""
from __future__ import annotations

import traceback
from datetime import datetime, timezone
from enum import IntEnum
from pathlib import Path
from typing import Any, Callable, Optional

BASE = Path(__file__).parent.parent


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


class Phase(IntEnum):
    DECISION = 1
    PERSIST  = 2
    VALIDATE = 3
    COMMIT   = 4
    NOTIFY   = 5
    PUBLISH  = 6


class TransactionAbortedError(RuntimeError):
    """Raised when an operation is attempted on an aborted transaction."""


class PhaseViolationError(RuntimeError):
    """Raised when a phase ordering constraint is violated."""


class ProductionTransaction:
    """
    Enforces phase ordering for all production side effects.

    Core guarantee:
        NOTIFY phase operations cannot execute until DECISION, PERSIST,
        VALIDATE, and COMMIT phases are all marked complete via tx.complete().
        Any unhandled exception in a phase causes immediate abort: subsequent
        tx.step() and tx.complete() calls raise TransactionAbortedError.
    """

    def __init__(self, scan_id: str):
        self._scan_id    = scan_id
        self._completed  : set[Phase] = set()
        self._aborted    : bool       = False
        self._abort_phase: Optional[Phase] = None
        self._abort_op   : str        = ""
        self._rollbacks  : list[tuple[Phase, str, Callable]] = []
        self._log_prefix : str        = f"[Tx:{scan_id[:8]}]"

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _journal(
        self,
        phase: Phase,
        operation: str,
        status: str,
        started_at: str,
        finished_at: Optional[str] = None,
        artifact: str = "",
        error: str = "",
    ) -> None:
        try:
            from production.journal import record
            record(
                scan_id     = self._scan_id,
                phase       = phase.name,
                phase_order = int(phase),
                operation   = operation,
                status      = status,
                started_at  = started_at,
                finished_at = finished_at or _now(),
                artifact    = artifact,
                error       = error,
            )
        except Exception as jex:
            print(f"{self._log_prefix} journal write non-fatal: {jex}")

    def _check_not_aborted(self, context: str) -> None:
        if self._aborted:
            raise TransactionAbortedError(
                f"Transaction aborted at phase={self._abort_phase.name if self._abort_phase else '?'} "
                f"op={self._abort_op!r}; cannot execute {context!r}"
            )

    def _check_phase_order(self, phase: Phase) -> None:
        """
        Enforce: NOTIFY requires DECISION+PERSIST+VALIDATE+COMMIT complete.
        PUBLISH requires NOTIFY complete.
        General rule: phase N requires phase N-1 complete.
        """
        if phase == Phase.NOTIFY:
            required = {Phase.DECISION, Phase.PERSIST, Phase.VALIDATE, Phase.COMMIT}
            missing  = required - self._completed
            if missing:
                names = ", ".join(p.name for p in sorted(missing))
                raise PhaseViolationError(
                    f"NOTIFY phase requires {names} to complete first. "
                    f"If email/telegram fire before timeline registration, "
                    f"call tx.complete(Phase.PERSIST) after register_alert_events()."
                )
        elif phase > Phase.DECISION:
            prev = Phase(int(phase) - 1)
            if prev not in self._completed:
                raise PhaseViolationError(
                    f"Phase {phase.name} requires {prev.name} to complete first."
                )

    def _do_rollback(self) -> None:
        """Call all registered rollbacks in LIFO order for PERSIST/COMMIT phases."""
        for rb_phase, rb_op, rb_fn in reversed(self._rollbacks):
            if rb_phase >= Phase.NOTIFY:
                continue  # never rollback external notifications
            try:
                rb_fn()
                print(f"{self._log_prefix} rollback OK: {rb_phase.name}/{rb_op}")
                self._journal(rb_phase, f"rollback:{rb_op}", "rolled_back", _now())
            except Exception as rbe:
                print(f"{self._log_prefix} rollback FAILED: {rb_phase.name}/{rb_op}: {rbe}")
                self._journal(rb_phase, f"rollback:{rb_op}", "rollback_failed", _now(),
                              error=str(rbe))

    # ── Public API ────────────────────────────────────────────────────────────

    def step(
        self,
        phase:    Phase,
        name:     str,
        fn:       Callable,
        /,
        *args:    Any,
        rollback: Optional[Callable] = None,
        artifact: str = "",
        **kwargs: Any,
    ) -> Any:
        """
        Execute fn(*args, **kwargs) within the given phase.

        - Writes started/success or failed to the execution journal.
        - On success: registers rollback (if provided) for LIFO cleanup on abort.
        - On failure: aborts the transaction, runs rollbacks, re-raises.
        - Returns the function's return value so callers can capture it normally.

        NOTIFY/PUBLISH steps are blocked until all prior phases complete.
        """
        self._check_not_aborted(name)
        self._check_phase_order(phase)

        started = _now()
        print(f"{self._log_prefix} {phase.name}/{name} → starting")
        try:
            result = fn(*args, **kwargs)
            finished = _now()
            self._journal(phase, name, "success", started, finished, artifact=artifact)
            print(f"{self._log_prefix} {phase.name}/{name} ✓")
            if rollback is not None:
                self._rollbacks.append((phase, name, rollback))
            return result

        except Exception as exc:
            finished = _now()
            tb = traceback.format_exc()
            self._journal(phase, name, "failed", started, finished, error=tb[:2000])
            print(f"{self._log_prefix} {phase.name}/{name} ✗  {exc}")

            # Only abort + rollback for phases before NOTIFY
            if phase < Phase.NOTIFY:
                self._aborted    = True
                self._abort_phase = phase
                self._abort_op   = name
                self._do_rollback()

            raise

    def complete(self, phase: Phase) -> None:
        """Mark a phase as fully complete, enabling subsequent phases to proceed."""
        self._check_not_aborted(f"complete({phase.name})")
        self._completed.add(phase)
        print(f"{self._log_prefix} {phase.name} COMPLETE ✓")
        self._journal(phase, f"phase:{phase.name}:complete", "success", _now())

    def abort(self, reason: str = "") -> None:
        """Explicitly abort the transaction (e.g. from inline validation)."""
        if not self._aborted:
            self._aborted     = True
            self._abort_phase = None
            self._abort_op    = reason or "explicit_abort"
            self._do_rollback()
            self._journal(Phase.VALIDATE, "explicit_abort", "aborted", _now(),
                          error=reason)
        raise TransactionAbortedError(reason or "Transaction explicitly aborted")

    @property
    def scan_id(self) -> str:
        return self._scan_id

    @property
    def aborted(self) -> bool:
        return self._aborted

    @property
    def completed_phases(self) -> frozenset[Phase]:
        return frozenset(self._completed)

    def notify_safe(self) -> bool:
        """Return True iff NOTIFY phase is safe to proceed (all required phases complete)."""
        required = {Phase.DECISION, Phase.PERSIST, Phase.VALIDATE, Phase.COMMIT}
        return required.issubset(self._completed) and not self._aborted
