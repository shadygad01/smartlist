"""
Scan ID Consistency Assertion — Constitutional Architecture Phase 3.

Verifies that a single scan_id propagated unchanged through every production
artifact in the current run. If any artifact was produced by a different scan
(stale artifact, partial re-run, cache poisoning), this fails.

Artifacts checked:
  production_decision_snapshot.json  (primary — must have scan_id)
  presentation_snapshot.json         (secondary)
  scan_context.json                  (authoritative source of truth)

Exits 1 if:
  - production_decision_snapshot.json has no scan_id
  - Any two checked artifacts disagree on scan_id
  - scan_id format is clearly invalid (empty string)

Exits 2 (SKIPPED) if scan_context.json does not exist (pre-Phase 3 run).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

BASE = Path(__file__).parent.parent
sys.path.insert(0, str(BASE))

from audit.audit_status import AuditStatus

PROD_SNAP  = BASE / "production_decision_snapshot.json"
PRES_SNAP  = BASE / "presentation_snapshot.json"
CTX_FILE   = BASE / "scan_context.json"

failures: list[str] = []
warnings: list[str] = []


def _load_scan_id(path: Path, key: str = "scan_id") -> str | None:
    if not path.exists():
        return None
    try:
        d = json.loads(path.read_text())
        return d.get(key) or None
    except Exception:
        return None


def main() -> int:
    if not CTX_FILE.exists():
        print("SKIPPED: scan_context.json not found — this run predates Phase 3 scan UUID propagation")
        print("         Run 'python3 scan_context.py --init' at the start of each workflow.")
        return AuditStatus.SKIPPED

    ctx_id   = _load_scan_id(CTX_FILE)
    prod_id  = _load_scan_id(PROD_SNAP)
    pres_id  = _load_scan_id(PRES_SNAP)

    print("Scan ID Consistency Assertion")
    print(f"  scan_context.json              : {ctx_id or 'MISSING'}")
    print(f"  production_decision_snapshot   : {prod_id or 'MISSING'}")
    print(f"  presentation_snapshot          : {pres_id or 'MISSING (pre-Phase 3)'}")
    print()

    # Primary: production_decision_snapshot MUST have scan_id
    if not prod_id:
        failures.append("production_decision_snapshot.json missing scan_id — rebuild required")
    elif prod_id != ctx_id:
        failures.append(
            f"production_decision_snapshot scan_id={prod_id!r} "
            f"!= scan_context scan_id={ctx_id!r} — stale artifact"
        )
    else:
        print(f"  ✓ production_decision_snapshot.json  scan_id matches context")

    # Secondary: presentation_snapshot (may be absent in older runs)
    if pres_id is None:
        warnings.append("presentation_snapshot.json has no scan_id — predates Phase 3")
        print(f"  ⚠ presentation_snapshot.json         no scan_id (pre-Phase 3 artifact)")
    elif pres_id != ctx_id:
        failures.append(
            f"presentation_snapshot.json scan_id={pres_id!r} "
            f"!= scan_context scan_id={ctx_id!r} — stale artifact"
        )
    else:
        print(f"  ✓ presentation_snapshot.json         scan_id matches context")

    # Per-decision scan_id consistency
    if PROD_SNAP.exists() and prod_id:
        try:
            d     = json.loads(PROD_SNAP.read_text())
            snap_id = d.get("scan_id", "")
            mismatched = [
                dec["ticker"]
                for dec in d.get("decisions", [])
                if dec.get("scan_id", "") != snap_id
            ]
            if mismatched:
                failures.append(
                    f"Decisions with scan_id != snapshot scan_id: {sorted(mismatched)}"
                )
                print(f"  ✗ Per-decision scan_id mismatch: {sorted(mismatched)}")
            else:
                print(f"  ✓ All {len(d.get('decisions', []))} decision records carry matching scan_id")
        except Exception as e:
            warnings.append(f"Could not verify per-decision scan_id: {e}")

    print()
    if warnings:
        for w in warnings:
            print(f"  ⚠ {w}")
        print()

    if failures:
        for f in failures:
            print(f"  ✗ {f}")
        print("\nASSERTION FAILED — scan_id inconsistency detected.")
        return AuditStatus.FAIL

    print("ASSERTION PASSED — scan_id propagated consistently across all artifacts.")
    return AuditStatus.PASS


if __name__ == "__main__":
    sys.exit(main())
