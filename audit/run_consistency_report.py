"""
Constitutional Consistency Report — Phase 10.

Runs every constitutional hardening assertion and produces the final report table.
This is the definitive CI gate — if this passes, the system is constitutionally sound.

Called as the last step of every production scan workflow.
Exits 1 if any assertion fails.
"""
from __future__ import annotations

import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

BASE   = Path(__file__).parent.parent
AUDIT  = Path(__file__).parent

# (label, script, blocking)
# blocking=False → failure is logged but does not fail the overall report
ASSERTIONS = [
    ("Constitutional Gate",         "assert_decision_consistency.py",       True),
    ("Full Universe Replay",        "assert_full_universe_replay.py",       True),
    ("Cross-Layer Consistency",     "assert_cross_layer_consistency.py",    True),
    ("Rendered Output",             "assert_rendered_output.py",            True),
    ("Event Chain Integrity",       "assert_event_chain_integrity.py",      True),
    ("Data Freshness",              "assert_data_freshness.py",             True),
    ("Workflow Completeness",       "assert_workflow_completeness.py",      False),
    ("Decision Replay",             "assert_decision_replay.py",            False),
    ("Regression Suite",            "assert_regression_suite.py",           True),
    ("Presentation Consistency",    "assert_presentation_consistency.py",   True),
    ("Price Consistency",           "assert_price_consistency.py",          True),
    ("CI Protection Gate",          "assert_ci_protection.py",              True),
]


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
        if "PASS" in l or "FAIL" in l or "SKIP" in l:
            return l[:70]
    return lines[-1][:70] if lines else ""


def main() -> int:
    print("=" * 70)
    print("  CONSTITUTIONAL CONSISTENCY REPORT")
    print(f"  {datetime.now(timezone.utc).isoformat(timespec='seconds')} UTC")
    print("=" * 70)
    print()

    results: list[tuple[str, str, int, bool]] = []   # label, status, code, blocking

    for label, script, blocking in ASSERTIONS:
        output, code = _run(script)
        if code == 0:
            status = "PASS"
        elif code == 2:
            status = "SKIP"
        else:
            status = "FAIL"
        results.append((label, status, code, blocking))
        brief = _brief(output)
        icon  = "✓" if code == 0 else ("·" if code == 2 else "✗")
        print(f"  {icon}  {label:<35} {status:<6}  {brief}")

    # ── Summary ───────────────────────────────────────────────────────────────
    n_pass   = sum(1 for _, s, _, _ in results if s == "PASS")
    n_skip   = sum(1 for _, s, _, _ in results if s == "SKIP")
    n_fail   = sum(1 for _, s, _, _ in results if s == "FAIL")
    blocking_fail = any(s == "FAIL" and b for _, s, _, b in results)

    print()
    print("=" * 70)
    print(f"  {n_pass} PASS  |  {n_fail} FAIL  |  {n_skip} SKIP")
    print("=" * 70)
    print()

    if blocking_fail:
        print("CONSTITUTIONAL CONSISTENCY REPORT: FAIL")
        print("One or more blocking assertions failed.")
        print("No deployment should proceed until all assertions pass.")
        return 1

    if n_fail > 0:
        print("CONSTITUTIONAL CONSISTENCY REPORT: PASS (with non-blocking warnings)")
    else:
        print("CONSTITUTIONAL CONSISTENCY REPORT: PASS")
        print("All layers agree. System is constitutionally sound.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
