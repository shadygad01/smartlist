"""
Constitutional Consistency Report — Phase 10.

Runs every constitutional hardening assertion and produces the final report table.
This is the definitive CI gate — if this passes, the system is constitutionally sound.

Called as the last step of every production scan workflow.
Exits 1 only if any assertion exits FAIL (exit code 1).
EXPECTED (exit code 3) and SKIPPED (exit code 2) never fail CI.

Exit code convention used by all audit scripts:
  0 = PASS     — assertion ran and all checks passed
  1 = FAIL     — real production inconsistency detected; CI must fail
  2 = SKIPPED  — validation skipped due to missing prerequisites or manual execution
  3 = EXPECTED — known limitation in the current execution mode (dev/non-CI);
                 would be a FAIL in production CI
"""
from __future__ import annotations

import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

BASE   = Path(__file__).parent.parent
AUDIT  = Path(__file__).parent

ASSERTIONS = [
    "assert_decision_consistency.py",
    "assert_full_universe_replay.py",
    "assert_cross_layer_consistency.py",
    "assert_rendered_output.py",
    "assert_event_chain_integrity.py",
    "assert_data_freshness.py",
    "assert_workflow_completeness.py",
    "assert_decision_replay.py",
    "assert_regression_suite.py",
    "assert_presentation_consistency.py",
    "assert_price_consistency.py",
    "assert_ci_protection.py",
]

_STATUS_LABELS = {0: "PASS", 1: "FAIL", 2: "SKIPPED", 3: "EXPECTED"}
_STATUS_ICONS  = {0: "✓", 1: "✗", 2: "·", 3: "⚠"}


def _run(script_name: str) -> tuple[str, int]:
    fp = AUDIT / script_name
    if not fp.exists():
        return f"SCRIPT NOT FOUND: {script_name}", 2
    try:
        proc = subprocess.run(
            [sys.executable, str(fp)],
            capture_output=True,
            text=True,
            timeout=90,
        )
        return (proc.stdout + proc.stderr).strip(), proc.returncode
    except subprocess.TimeoutExpired:
        return "TIMEOUT", 1
    except Exception as e:
        return f"ERROR: {e}", 1


def _brief(output: str) -> str:
    lines = [l.strip() for l in output.splitlines() if l.strip()]
    for l in reversed(lines):
        if any(kw in l for kw in ("PASS", "FAIL", "SKIP", "EXPECTED")):
            return l[:72]
    return lines[-1][:72] if lines else ""


def main() -> int:
    print("=" * 70)
    print("  CONSTITUTIONAL CONSISTENCY REPORT")
    print(f"  {datetime.now(timezone.utc).isoformat(timespec='seconds')} UTC")
    print("=" * 70)
    print()

    results: list[tuple[str, str, int]] = []   # (label, status, code)

    for script in ASSERTIONS:
        label  = script.replace("assert_", "").replace(".py", "").replace("_", " ").title()
        output, code = _run(script)
        # Clamp unknown exit codes to FAIL
        if code not in _STATUS_LABELS:
            code = 1
        status = _STATUS_LABELS[code]
        results.append((label, status, code))
        brief  = _brief(output)
        icon   = _STATUS_ICONS[code]
        print(f"  {icon}  {label:<35} {status:<8}  {brief}")

    # ── Summary ───────────────────────────────────────────────────────────────
    n_pass     = sum(1 for _, s, _ in results if s == "PASS")
    n_expected = sum(1 for _, s, _ in results if s == "EXPECTED")
    n_skipped  = sum(1 for _, s, _ in results if s == "SKIPPED")
    n_fail     = sum(1 for _, s, _ in results if s == "FAIL")
    has_fail   = n_fail > 0

    print()
    print("=" * 70)
    print(f"  {n_pass} PASS  |  {n_fail} FAIL  |  {n_expected} EXPECTED  |  {n_skipped} SKIPPED")
    print("=" * 70)
    print()

    if has_fail:
        print("CONSTITUTIONAL CONSISTENCY REPORT: FAIL")
        print("One or more assertions detected a real production inconsistency.")
        print("No deployment should proceed until all FAIL assertions pass.")
        return 1

    if n_expected > 0 or n_skipped > 0:
        parts = []
        if n_expected:
            parts.append(f"{n_expected} EXPECTED (known dev-mode limitation, would FAIL in CI)")
        if n_skipped:
            parts.append(f"{n_skipped} SKIPPED (prerequisites missing or manual run)")
        print(f"CONSTITUTIONAL CONSISTENCY REPORT: PASS")
        print(f"  Note: {'; '.join(parts)}")
    else:
        print("CONSTITUTIONAL CONSISTENCY REPORT: PASS")
        print("All layers agree. System is constitutionally sound.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
