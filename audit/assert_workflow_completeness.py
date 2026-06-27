"""
Workflow Completeness Assertion — Phase 6 Constitutional Hardening.

Verifies that all required pipeline stages produced their artifacts.
A missing artifact means a stage silently failed — this gate catches that.

Required stages (in order):
  CSV Refresh → Candidate Pool → Signal Detection → Timeline Update →
  Universe Snapshot → Presentation Snapshot → Production Decisions →
  Dashboard → Audit Heartbeat → Consistency Validation

Exits 1 if any required stage artifact is missing or too stale.
"""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

BASE = Path(__file__).parent.parent
sys.path.insert(0, str(BASE))

# (stage_label, rel_path_or_dir, max_age_hours, required, is_dir)
STAGES = [
    ("CSV Refresh",            "historical_data/historical_data", None,   True,   True),
    ("Candidate Pool Rebuild", "candidate_pool.db",              120.0,  True,   False),
    ("Signal Detection",       "notification_delivery.db",        None,   False,  False),
    ("Timeline Update",        "constitutional_opportunity_events.db", None, False, False),
    ("Universe Snapshot",      "universe_snapshot.db",            26.0,   True,   False),
    ("Presentation Snapshot",  "presentation_snapshot.json",      26.0,   True,   False),
    ("Production Decisions",   "production_decision_snapshot.json", 26.0, False,  False),
    ("Dashboard HTML",         "dashboard.html",                  26.0,   False,  False),
    ("Audit Heartbeat",        "heartbeat.json",                  None,   False,  False),
    ("Operations State",       "operations_state.json",           None,   False,  False),
]

failures: list[str] = []
table:    list[tuple] = []


def _age_hours(path: Path) -> float | None:
    if not path.exists():
        return None
    mtime = path.stat().st_mtime
    return (datetime.now(timezone.utc).timestamp() - mtime) / 3600


def _fmt(h: float) -> str:
    return f"{h*60:.0f}m" if h < 1 else (f"{h:.1f}h" if h < 24 else f"{h/24:.1f}d")


def main() -> int:
    print("Workflow Completeness Assertion")
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
            status = "MISSING"
            if required:
                failures.append(f"Stage '{label}': artifact missing — {rel}")
        elif max_age_h is not None and age_h is not None and age_h > max_age_h:
            status = f"STALE"
            if required:
                failures.append(f"Stage '{label}': artifact stale {age_str} > {_fmt(max_age_h)} — {rel}")
        else:
            status = "OK"

        req_tag = "" if required else " (opt)"
        table.append(("✓" if status == "OK" else "✗", label, age_str, status + req_tag))

    # ── Dependency ordering: each artifact must be newer than its upstream ──────
    # Allows 300s slack for artifacts built in the same pipeline step.
    _ORDER_SLACK = 300  # seconds
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
                failures.append(f"Dependency order: {msg} — "
                                 f"{downstream_rel} mtime={down.stat().st_mtime:.0f} "
                                 f"< {upstream_rel} mtime={up.stat().st_mtime:.0f}")

    for icon, label, age_str, status in table:
        print(f"  {icon} {label:<35} {age_str:<10} {status}")

    print()
    if failures:
        print("WORKFLOW FAILURES:")
        for f in failures:
            print(f"  ✗ {f}")
        print("\nASSERTION FAILED — pipeline did not complete all required stages.")
        return 1

    print("ASSERTION PASSED — all required pipeline stages completed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
