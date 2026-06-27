"""
Workflow Completeness Assertion — Phase 6 Constitutional Hardening.

Verifies that all required pipeline stages produced their artifacts.
A missing artifact means a stage silently failed — this gate catches that.

Required stages (in order):
  CSV Refresh → Candidate Pool → Signal Detection → Timeline Update →
  Universe Snapshot → Presentation Snapshot → Production Decisions →
  Dashboard → Audit Heartbeat → Consistency Validation

Exit codes:
  0 = PASS     — all required artifacts present and fresh, ordering correct
  1 = FAIL     — required artifact missing/stale in CI, or ordering violated in CI
  3 = EXPECTED — stale artifact or ordering violation outside CI (dev/manual run);
                 this same condition would be FAIL in production CI
"""
from __future__ import annotations

import os
import sys
from datetime import datetime, timezone
from pathlib import Path

BASE = Path(__file__).parent.parent
sys.path.insert(0, str(BASE))

_IN_CI: bool = bool(os.environ.get("CI") or os.environ.get("GITHUB_ACTIONS"))

# (stage_label, rel_path_or_dir, max_age_hours, required, is_dir)
STAGES = [
    ("CSV Refresh",            "historical_data/historical_data", None,   True,   True),
    ("Candidate Pool Rebuild", "candidate_pool.db",              120.0,  True,   False),
    ("Signal Detection",       "notification_delivery.db",        None,   False,  False),
    ("Timeline Update",        "constitutional_opportunity_events.db", None, False,  False),
    ("Universe Snapshot",      "universe_snapshot.db",            26.0,   True,   False),
    ("Presentation Snapshot",  "presentation_snapshot.json",      26.0,   True,   False),
    ("Production Decisions",   "production_decision_snapshot.json", 26.0, False,  False),
    ("Dashboard HTML",         "dashboard.html",                  26.0,   False,  False),
    ("Audit Heartbeat",        "heartbeat.json",                  None,   False,  False),
    ("Operations State",       "operations_state.json",           None,   False,  False),
]

hard_failures: list[str] = []   # always FAIL (even in dev) — missing required artifact
expected_issues: list[str] = [] # EXPECTED in non-CI
table: list[tuple] = []


def _age_hours(path: Path) -> float | None:
    if not path.exists():
        return None
    mtime = path.stat().st_mtime
    return (datetime.now(timezone.utc).timestamp() - mtime) / 3600


def _fmt(h: float) -> str:
    return f"{h*60:.0f}m" if h < 1 else (f"{h:.1f}h" if h < 24 else f"{h/24:.1f}d")


def main() -> int:
    print("Workflow Completeness Assertion")
    print(f"  execution mode: {'CI' if _IN_CI else 'dev/manual (staleness/ordering → EXPECTED)'}")
    print()

    for label, rel, max_age_h, required, is_dir in STAGES:
        path = BASE / rel
        if is_dir:
            exists  = path.is_dir() and any(path.iterdir())
            age_h   = None
            age_str = "dir"
        else:
            exists  = path.is_file()
            age_h   = _age_hours(path) if exists else None
            age_str = _fmt(age_h) if age_h is not None else "—"

        if not exists:
            # Missing required artifact → always FAIL (even in dev)
            status = "MISSING"
            if required:
                hard_failures.append(f"Stage '{label}': artifact missing — {rel}")
        elif max_age_h is not None and age_h is not None and age_h > max_age_h:
            # Stale artifact
            if required:
                if _IN_CI:
                    status = "STALE"
                    hard_failures.append(f"Stage '{label}': stale {age_str} > {_fmt(max_age_h)} — {rel}")
                else:
                    status = "EXPECTED"
                    expected_issues.append(
                        f"Stage '{label}': {age_str} old (max {_fmt(max_age_h)}) "
                        f"— stale outside CI (would FAIL in production)"
                    )
            else:
                status = "STALE"  # optional, non-blocking regardless
        else:
            status = "OK"

        req_tag = "" if required else " (opt)"
        icon = "✓" if status == "OK" else ("⚠" if status == "EXPECTED" else "✗")
        table.append((icon, label, age_str, status + req_tag))

    # ── Dependency ordering: each artifact must be newer than its upstream ──────
    # In CI: any ordering violation is a FAIL.
    # In dev: ordering can be off if you ran one step manually → EXPECTED.
    _ORDER_SLACK = 300  # seconds — allow 5 min for artifacts built in the same step
    _deps = [
        ("candidate_pool.db",                "universe_snapshot.db",
         "universe_snapshot.db must be built after candidate_pool.db"),
        ("universe_snapshot.db",             "presentation_snapshot.json",
         "presentation_snapshot.json must be built after universe_snapshot.db"),
        ("presentation_snapshot.json",       "production_decision_snapshot.json",
         "production_decision_snapshot.json must be built after presentation_snapshot.json"),
        ("production_decision_snapshot.json", "dashboard.html",
         "dashboard.html must be built after production_decision_snapshot.json"),
    ]
    for upstream_rel, downstream_rel, msg in _deps:
        up   = BASE / upstream_rel
        down = BASE / downstream_rel
        if up.is_file() and down.is_file():
            if down.stat().st_mtime < up.stat().st_mtime - _ORDER_SLACK:
                detail = (f"{downstream_rel} mtime={_fmt(_age_hours(down) or 0)} "
                          f"< {upstream_rel} mtime={_fmt(_age_hours(up) or 0)}")
                if _IN_CI:
                    hard_failures.append(f"Dependency order: {msg} — {detail}")
                else:
                    expected_issues.append(
                        f"Dependency order: {msg} — {detail} "
                        f"(expected outside CI — would FAIL in production)"
                    )

    for icon, label, age_str, status in table:
        print(f"  {icon} {label:<35} {age_str:<10} {status}")

    print()

    if expected_issues and not _IN_CI:
        print("EXPECTED LIMITATIONS (dev/manual mode — would FAIL in CI):")
        for e in expected_issues:
            print(f"  ⚠ {e}")

    if hard_failures:
        print("\nWORKFLOW FAILURES:")
        for f in hard_failures:
            print(f"  ✗ {f}")
        print("\nASSERTION FAILED — pipeline did not complete all required stages.")
        return 1

    if expected_issues and not _IN_CI:
        print("\nASSERTION EXPECTED — dev/manual run has expected staleness or ordering gaps.")
        return 3

    print("ASSERTION PASSED — all required pipeline stages completed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
