"""
Scan Manifest Assertion — Constitutional Architecture Phase 4.

Validates scan_manifest.json:
  1. File exists and is valid JSON
  2. All required fields present
  3. scan_id matches production_decision_snapshot.json
  4. architecture_version, gate_version are non-empty
  5. All expected artifact hashes are present (not None)
  6. scan_id_consistent flag is True

Exit codes:
  0 = PASS
  1 = FAIL
  3 = SKIPPED (scan_manifest.json not present — CI run before manifest is built)
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

BASE  = Path(__file__).parent.parent
sys.path.insert(0, str(BASE))

from audit.audit_status import AuditStatus

MANIFEST_PATH = BASE / "scan_manifest.json"
PROD_SNAP     = BASE / "production_decision_snapshot.json"

_REQUIRED_TOP = [
    "scan_id", "git_commit", "workflow_run", "workflow_name",
    "architecture_version", "gate_version",
    "started_at", "finished_at",
    "scan_id_consistent", "artifact_hashes",
]

_EXPECTED_ARTIFACT_KEYS = [
    "production_decision_snapshot",
    "presentation_snapshot",
    "constitutional_fingerprint",
    "architecture_fingerprint",
]


def main() -> int:
    if not MANIFEST_PATH.exists():
        print("SKIPPED: scan_manifest.json not found — manifest not yet built for this scan")
        return int(AuditStatus.SKIPPED)

    try:
        manifest = json.loads(MANIFEST_PATH.read_text())
    except Exception as e:
        print(f"FAIL: scan_manifest.json is not valid JSON: {e}")
        return int(AuditStatus.FAIL)

    failures: list[str] = []

    # Required top-level fields
    for field in _REQUIRED_TOP:
        if field not in manifest:
            failures.append(f"missing required field: {field}")
        elif not manifest[field] and manifest[field] != 0 and manifest[field] is not False:
            failures.append(f"empty required field: {field}")

    # Version fields must be non-trivial
    for vfield in ("architecture_version", "gate_version"):
        val = manifest.get(vfield, "")
        if val in ("", "unknown", None):
            failures.append(f"{vfield} is unset/unknown — scan_context not initialised before scan")

    # scan_id_consistent
    if not manifest.get("scan_id_consistent"):
        snap_sid = manifest.get("decision_snapshot_scan_id", "N/A")
        ctx_sid  = manifest.get("scan_id", "N/A")
        failures.append(
            f"scan_id_consistent=False — "
            f"context={ctx_sid!r} vs snapshot={snap_sid!r}"
        )

    # Artifact hashes presence
    artifact_hashes = manifest.get("artifact_hashes", {})
    for key in _EXPECTED_ARTIFACT_KEYS:
        if artifact_hashes.get(key) is None:
            failures.append(f"artifact_hashes.{key} is None (artifact not produced)")

    # Cross-validate scan_id with production_decision_snapshot.json directly
    if PROD_SNAP.exists():
        try:
            snap = json.loads(PROD_SNAP.read_text())
            snap_sid = snap.get("scan_id")
            manifest_sid = manifest.get("scan_id")
            if snap_sid != manifest_sid:
                failures.append(
                    f"scan_id cross-validation failed: "
                    f"manifest={manifest_sid!r}, snapshot={snap_sid!r}"
                )
        except Exception as e:
            failures.append(f"could not read production_decision_snapshot.json: {e}")

    if failures:
        print("FAIL: scan_manifest.json assertion failed")
        for f in failures:
            print(f"  - {f}")
        return int(AuditStatus.FAIL)

    scan_id  = manifest.get("scan_id", "?")
    arch_ver = manifest.get("architecture_version", "?")
    gate_ver = manifest.get("gate_version", "?")
    dur      = manifest.get("duration_seconds", "?")
    print("PASS: scan_manifest.json is valid and consistent")
    print(f"  scan_id           : {scan_id}")
    print(f"  architecture_ver  : {arch_ver}")
    print(f"  gate_version      : {gate_ver}")
    print(f"  duration          : {dur}s")
    print(f"  scan_id_consistent: True")
    return int(AuditStatus.PASS)


if __name__ == "__main__":
    sys.exit(main())
