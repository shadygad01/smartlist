"""
Constitutional Production Certification — Phase 2 Architecture Certification.

Runs every constitutional hardening assertion and produces the final certification report.
This is the definitive CI gate — if this passes, the system is constitutionally sound.

Called as the last step of every production scan workflow.

CI strict mode (Phase 3): when _IN_CI=True, EXPECTED and SKIPPED are both treated as FAIL.
  Rationale: production CI must never ship with skipped validations or known limitations.

Dev mode (Phase 4): EXPECTED and SKIPPED are shown with their reason but do not fail CI.

Exit codes:
  0 = PASS     — all assertions passed (CI: FAIL=0; dev: FAIL=0, EXPECTED/SKIPPED allowed)
  1 = FAIL     — one or more assertions failed (or EXPECTED/SKIPPED in CI strict mode)
"""
from __future__ import annotations

import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

BASE  = Path(__file__).parent.parent
AUDIT = Path(__file__).parent
sys.path.insert(0, str(BASE))

from audit.audit_status import AuditStatus, is_ci

_IN_CI = is_ci()

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
    # Phase 11 — Partial Execution Hardening
    "assert_production_invariants.py",
    "assert_no_direct_notify_calls.py",
    "assert_fault_injection.py",
    "assert_scan_id_consistency.py",
    "assert_schema_compliance.py",
    "assert_e2e_constitutional_audit.py",
]

_STATUS_LABELS = {
    AuditStatus.PASS:     "PASS",
    AuditStatus.FAIL:     "FAIL",
    AuditStatus.SKIPPED:  "SKIPPED",
    AuditStatus.EXPECTED: "EXPECTED",
}
_STATUS_ICONS = {
    AuditStatus.PASS:     "✓",
    AuditStatus.FAIL:     "✗",
    AuditStatus.SKIPPED:  "·",
    AuditStatus.EXPECTED: "⚠",
}


def _run(script_name: str) -> tuple[str, AuditStatus]:
    fp = AUDIT / script_name
    if not fp.exists():
        return f"SCRIPT NOT FOUND: {script_name}", AuditStatus.FAIL
    try:
        proc = subprocess.run(
            [sys.executable, str(fp)],
            capture_output=True,
            text=True,
            timeout=90,
        )
        raw_code = proc.returncode
        try:
            status = AuditStatus(raw_code)
        except ValueError:
            status = AuditStatus.FAIL  # unknown exit code → treat as FAIL
        return (proc.stdout + proc.stderr).strip(), status
    except subprocess.TimeoutExpired:
        return "TIMEOUT", AuditStatus.FAIL
    except Exception as e:
        return f"ERROR: {e}", AuditStatus.FAIL


def _brief(output: str) -> str:
    lines = [ln.strip() for ln in output.splitlines() if ln.strip()]
    for ln in reversed(lines):
        if any(kw in ln for kw in ("PASS", "FAIL", "SKIP", "EXPECTED")):
            return ln[:72]
    return lines[-1][:72] if lines else ""


def _reason(output: str, status: AuditStatus) -> str:
    """Extract the human-readable reason from SKIPPED or EXPECTED output."""
    if status not in (AuditStatus.SKIPPED, AuditStatus.EXPECTED):
        return ""
    lines = [ln.strip() for ln in output.splitlines() if ln.strip()]
    # Prefer lines starting with SKIPPED: / EXPECTED / ⚠ / assertion message
    for ln in lines:
        for prefix in ("SKIPPED:", "ASSERTION EXPECTED", "ASSERTION SKIPPED",
                       "⚠", "EXPECTED LIMITATIONS"):
            if ln.startswith(prefix):
                return ln[:100]
    return lines[0][:100] if lines else ""


def _write_report_json(
    now: str,
    results: list[tuple[str, AuditStatus, str]],
    mode: str,
    verdict: str,
) -> None:
    import json as _json
    report = {
        "generated_at": now,
        "mode": mode,
        "verdict": verdict,
        "assertions": [
            {
                "label": label,
                "status": _STATUS_LABELS[status],
                "status_code": int(status),
                "brief": _brief(output),
            }
            for label, status, output in results
        ],
        "summary": {
            "pass":     sum(1 for _, s, _ in results if s == AuditStatus.PASS),
            "fail":     sum(1 for _, s, _ in results if s == AuditStatus.FAIL),
            "expected": sum(1 for _, s, _ in results if s == AuditStatus.EXPECTED),
            "skipped":  sum(1 for _, s, _ in results if s == AuditStatus.SKIPPED),
        },
    }
    out = BASE / "consistency_report.json"
    out.write_text(_json.dumps(report, indent=2))


def main() -> int:
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    mode = "CI/strict" if _IN_CI else "dev/manual"

    print("=" * 72)
    print("  CONSTITUTIONAL PRODUCTION CERTIFICATION")
    print(f"  {now} UTC")
    print(f"  mode: {mode}")
    if _IN_CI:
        print("  CI strict mode: EXPECTED and SKIPPED are treated as FAIL")
    print("=" * 72)
    print()

    results: list[tuple[str, AuditStatus, str]] = []  # (label, status, output)

    for script in ASSERTIONS:
        label  = script.replace("assert_", "").replace(".py", "").replace("_", " ").title()
        output, status = _run(script)
        results.append((label, status, output))
        brief  = _brief(output)
        icon   = _STATUS_ICONS[status]
        status_label = _STATUS_LABELS[status]
        print(f"  {icon}  {label:<35} {status_label:<8}  {brief}")

    # ── Totals (raw, before CI promotion) ────────────────────────────────────
    n_pass     = sum(1 for _, s, _ in results if s == AuditStatus.PASS)
    n_fail     = sum(1 for _, s, _ in results if s == AuditStatus.FAIL)
    n_expected = sum(1 for _, s, _ in results if s == AuditStatus.EXPECTED)
    n_skipped  = sum(1 for _, s, _ in results if s == AuditStatus.SKIPPED)

    print()
    print("=" * 72)
    print(f"  {n_pass} PASS  |  {n_fail} FAIL  |  {n_expected} EXPECTED  |  {n_skipped} SKIPPED")
    print("=" * 72)
    print()

    # ── Phase 3: CI strict promotion ─────────────────────────────────────────
    # In CI, EXPECTED and SKIPPED are promoted to FAIL.
    ci_promoted = []
    if _IN_CI:
        for label, status, output in results:
            if status in (AuditStatus.EXPECTED, AuditStatus.SKIPPED):
                ci_promoted.append((label, _STATUS_LABELS[status], _brief(output)))

    has_real_fail = n_fail > 0
    has_ci_promoted = bool(ci_promoted)

    # ── Phase 4: Dev-mode detail for EXPECTED / SKIPPED ──────────────────────
    if not _IN_CI and (n_expected > 0 or n_skipped > 0):
        print("DEV/MANUAL MODE — non-blocking conditions:")
        for label, status, output in results:
            if status in (AuditStatus.EXPECTED, AuditStatus.SKIPPED):
                reason = _reason(output, status)
                status_label = _STATUS_LABELS[status]
                print(f"  {_STATUS_ICONS[status]} [{status_label}] {label}: {reason}")
        print()

    # ── CI strict mode report ────────────────────────────────────────────────
    if has_ci_promoted:
        print("CI STRICT MODE — promoted to FAIL (not acceptable in production):")
        for label, orig_status, brief in ci_promoted:
            print(f"  ✗ [{orig_status}→FAIL] {label}: {brief}")
        print()

    # ── Final verdict ────────────────────────────────────────────────────────
    if has_real_fail or has_ci_promoted:
        print("CONSTITUTIONAL PRODUCTION CERTIFICATION: FAIL")
        if has_real_fail:
            print("  One or more assertions detected a real production inconsistency.")
        if has_ci_promoted:
            print("  EXPECTED/SKIPPED assertions are not permitted in production CI.")
        print("  No deployment should proceed until all FAIL assertions pass.")
        _write_report_json(now, results, mode, "FAIL")
        return int(AuditStatus.FAIL)

    if n_expected > 0 or n_skipped > 0:
        # Dev mode only (CI case already returned above)
        parts = []
        if n_expected:
            parts.append(f"{n_expected} EXPECTED (dev-mode limitation)")
        if n_skipped:
            parts.append(f"{n_skipped} SKIPPED (prerequisites missing)")
        print("CONSTITUTIONAL PRODUCTION CERTIFICATION: PASS")
        print(f"  Note ({mode}): {'; '.join(parts)}")
        print("  These would be FAIL in production CI.")
    else:
        print("CONSTITUTIONAL PRODUCTION CERTIFICATION: PASS")
        print("  All layers agree. System is constitutionally certified.")

    _write_report_json(now, results, mode, "PASS")
    return int(AuditStatus.PASS)


if __name__ == "__main__":
    sys.exit(main())
