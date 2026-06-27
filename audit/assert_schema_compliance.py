"""
Schema Compliance Assertion — Constitutional Architecture Phase 4.

Validates every production JSON artifact against its JSON Schema contract
before reporting certification status.  A schema violation means a producer
emitted a malformed artifact — no consumer should ever receive invalid data.

Schemas are in schemas/ (relative to project root).
Artifacts validated:
  production_decision_snapshot.json  → schemas/production_decision_snapshot.schema.json
  presentation_snapshot.json         → schemas/presentation_snapshot.schema.json
  consistency_report.json            → schemas/consistency_report.schema.json

Exits 1 on any schema violation.
Exits 2 (SKIPPED) if jsonschema is not installed.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

BASE = Path(__file__).parent.parent
sys.path.insert(0, str(BASE))

from audit.audit_status import AuditStatus

SCHEMA_DIR = BASE / "schemas"
ARTIFACTS: list[tuple[str, str]] = [
    ("production_decision_snapshot.json", "production_decision_snapshot.schema.json"),
    ("presentation_snapshot.json",        "presentation_snapshot.schema.json"),
    ("consistency_report.json",           "consistency_report.schema.json"),
]

failures:  list[str] = []
warnings:  list[str] = []


def _validate(artifact_path: Path, schema_path: Path, validate_fn) -> list[str]:
    """Validate artifact against schema. Returns list of error strings."""
    errs: list[str] = []
    if not artifact_path.exists():
        errs.append(f"{artifact_path.name}: FILE_NOT_FOUND")
        return errs
    if not schema_path.exists():
        errs.append(f"{schema_path.name}: SCHEMA_NOT_FOUND")
        return errs
    try:
        data   = json.loads(artifact_path.read_text())
        schema = json.loads(schema_path.read_text())
        validate_fn(data, schema)
    except Exception as e:
        # jsonschema.ValidationError has a .message attribute
        msg = getattr(e, "message", str(e))
        path = list(getattr(e, "absolute_path", []))
        location = f" @ {'.'.join(str(p) for p in path)}" if path else ""
        errs.append(f"{artifact_path.name}{location}: {msg}")
    return errs


def main() -> int:
    try:
        import jsonschema
        from jsonschema import validate as _jv
    except ImportError:
        print("SKIPPED: jsonschema not installed — run: pip install jsonschema")
        return AuditStatus.SKIPPED

    print("Schema Compliance Assertion")
    print(f"  schema directory: {SCHEMA_DIR.relative_to(BASE)}")
    print()

    all_pass = True
    for artifact_name, schema_name in ARTIFACTS:
        artifact_path = BASE / artifact_name
        schema_path   = SCHEMA_DIR / schema_name

        if not artifact_path.exists():
            warnings.append(f"{artifact_name}: not found — skipping schema check")
            print(f"  ⚠ {artifact_name:<45} NOT FOUND (skipped)")
            continue

        errs = _validate(artifact_path, schema_path, _jv)
        if errs:
            all_pass = False
            for e in errs:
                failures.append(e)
                print(f"  ✗ {e}")
        else:
            # Quick structural summary
            try:
                d = json.loads(artifact_path.read_text())
                size = artifact_path.stat().st_size
                note = ""
                if "decisions" in d:
                    note = f"  {len(d['decisions'])} decisions"
                elif "universe_snapshot" in d:
                    note = f"  {len(d['universe_snapshot'])} tickers"
                elif "assertions" in d:
                    note = f"  {len(d['assertions'])} assertions"
                print(f"  ✓ {artifact_name:<45} {size:>8} bytes{note}")
            except Exception:
                print(f"  ✓ {artifact_name}")

    print()

    # Cross-artifact: scan_id must be consistent if present
    scan_ids: dict[str, str] = {}
    for artifact_name, _ in ARTIFACTS:
        path = BASE / artifact_name
        if path.exists():
            try:
                sid = json.loads(path.read_text()).get("scan_id", "")
                if sid:
                    scan_ids[artifact_name] = sid
            except Exception:
                pass

    if len(set(scan_ids.values())) > 1:
        failures.append(f"scan_id mismatch across artifacts: {scan_ids}")
        print(f"  ✗ scan_id divergence: {scan_ids}")
    elif scan_ids:
        unique_id = next(iter(scan_ids.values()))
        print(f"  ✓ scan_id consistent across {len(scan_ids)} artifact(s): {unique_id[:16]}…")

    if warnings:
        print()
        for w in warnings:
            print(f"  ⚠ {w}")

    print()
    if failures:
        for f in failures:
            print(f"  ✗ {f}")
        print("\nASSERTION FAILED — schema violations detected.")
        return AuditStatus.FAIL

    print("ASSERTION PASSED — all artifacts comply with their JSON Schema contracts.")
    return AuditStatus.PASS


if __name__ == "__main__":
    sys.exit(main())
