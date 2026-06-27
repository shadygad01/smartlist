"""
Architecture Fingerprint Builder — Phase 7 Constitutional Architecture Certification.

Computes SHA256 of all CODE and architectural files that define the constitutional
production system. Writes architecture_fingerprint.json.

Tracked files (code artifacts):
  - constitutional_gate.py          (the decision engine — Contract 1)
  - audit/audit_status.py           (the audit contract — Contract 8)
  - audit/run_consistency_report.py (the certification runner)
  - .github/workflows/*.yml         (all workflow definitions)
  - dashboard.py                    (primary renderer)
  - egx_email.py                    (email renderer)
  - notifications/scan_orchestrator.py (notification renderer)
  - main.py                         (signal detection)
  - universe_snapshot.py            (candidate pool consumer)
  - presentation/presentation_snapshot.py (presentation builder)

Schema tracked:
  - production_decision_snapshot.json (field names — schema integrity)
  - presentation_snapshot.json        (field names — schema integrity)

The fingerprint detects any code change between production runs.
A divergence means architectural drift — regression investigation required.
"""
from __future__ import annotations

import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

BASE = Path(__file__).parent.parent
sys.path.insert(0, str(BASE))

from audit.audit_status import AuditStatus

_CODE_FILES = [
    "constitutional_gate.py",
    "audit/audit_status.py",
    "audit/run_consistency_report.py",
    "dashboard.py",
    "egx_email.py",
    "notifications/scan_orchestrator.py",
    "main.py",
    "universe_snapshot.py",
    "presentation/presentation_snapshot.py",
    "constitutional_timeline_engine.py",
    "constitutional_opportunity_engine.py",
]

_WORKFLOW_GLOB = ".github/workflows/*.yml"

_SCHEMA_SOURCES = [
    "production_decision_snapshot.json",
    "presentation_snapshot.json",
]


def _sha256_file(path: Path) -> str:
    if not path.exists():
        return "MISSING"
    h = hashlib.sha256(path.read_bytes())
    return h.hexdigest()


def _schema_fields(path: Path) -> list[str]:
    """Extract top-level field names from a JSON file for schema tracking."""
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text())
        if isinstance(data, dict):
            return sorted(data.keys())
    except Exception:
        pass
    return []


def main() -> int:
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")

    hashes: dict[str, str] = {}
    missing: list[str] = []

    # ── Code file hashes ──────────────────────────────────────────────────────
    for rel in _CODE_FILES:
        fp = BASE / rel
        digest = _sha256_file(fp)
        hashes[rel] = digest
        if digest == "MISSING":
            missing.append(rel)

    # ── Workflow YAML hashes ──────────────────────────────────────────────────
    workflows = sorted((BASE / ".github" / "workflows").glob("*.yml")) if (BASE / ".github" / "workflows").is_dir() else []
    for wf in workflows:
        rel = str(wf.relative_to(BASE))
        hashes[rel] = _sha256_file(wf)

    # ── Schema fingerprints ───────────────────────────────────────────────────
    schemas: dict[str, list[str]] = {}
    for rel in _SCHEMA_SOURCES:
        fp = BASE / rel
        fields = _schema_fields(fp)
        schemas[rel] = fields

    # ── Composite hash (all code files + workflows, sorted by key) ───────────
    composite_input = json.dumps(
        {k: v for k, v in sorted(hashes.items()) if v != "MISSING"},
        sort_keys=True
    ).encode()
    composite = hashlib.sha256(composite_input).hexdigest()

    fingerprint = {
        "generated_at": now,
        "composite_hash": composite,
        "file_hashes": dict(sorted(hashes.items())),
        "schemas": schemas,
        "missing_files": missing,
        "tracked_file_count": len(hashes),
        "workflow_count": len(workflows),
    }

    out_path = BASE / "architecture_fingerprint.json"
    out_path.write_text(json.dumps(fingerprint, indent=2))

    print("Architecture Fingerprint")
    print(f"  generated_at  : {now}")
    print(f"  composite     : {composite[:16]}...")
    print(f"  tracked files : {len(hashes)}")
    print(f"  workflows     : {len(workflows)}")
    if missing:
        print(f"  MISSING       : {missing}")

    print(f"\nFile hashes:")
    for rel, digest in sorted(hashes.items()):
        flag = " ✗ MISSING" if digest == "MISSING" else ""
        print(f"  {rel:<55} {digest[:12]}...{flag}")

    if missing:
        print(f"\nWARN: {len(missing)} tracked file(s) missing — architecture incomplete")
        print("Architecture fingerprint written (partial).")
        return int(AuditStatus.PASS)  # non-blocking — missing renderers are optional

    print(f"\nArchitecture fingerprint written to architecture_fingerprint.json")
    return int(AuditStatus.PASS)


if __name__ == "__main__":
    sys.exit(main())
