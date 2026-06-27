"""
Scan Manifest Builder — Constitutional Architecture Phase 4.

Generates scan_manifest.json: one immutable record per scan capturing
all artifact hashes, version vectors, and timing. Every artifact produced
in a scan must reference this manifest's scan_id.

Called after all artifacts are produced (decision snapshot, presentation
snapshot, fingerprints, dashboard, email, telegram).

Fields:
  scan_id, git_commit, workflow_run, workflow_name
  architecture_version, gate_version
  started_at, finished_at, duration
  artifact hashes: candidate_pool, timeline, decision_snapshot,
    presentation_snapshot, dashboard, constitutional_fingerprint,
    architecture_fingerprint
  optional: email_hash, telegram_hash
"""
from __future__ import annotations

import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

BASE        = Path(__file__).parent.parent
OUTPUT_PATH = BASE / "scan_manifest.json"
sys.path.insert(0, str(BASE))

from scan_context import read_scan_context


def _sha256(path: Path) -> str | None:
    if not path.exists():
        return None
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


def _sha256_db(path: Path) -> str | None:
    """Hash a SQLite db file as binary blob."""
    return _sha256(path)


def build_scan_manifest() -> dict:
    ctx           = read_scan_context()
    scan_id       = ctx.get("scan_id", "unknown")
    git_commit    = ctx.get("git_commit", "unknown")
    workflow_run  = ctx.get("workflow_run", "local")
    workflow_job  = ctx.get("workflow_job", "local")
    arch_ver      = ctx.get("architecture_version", "unknown")
    gate_ver      = ctx.get("gate_version", "unknown")
    started_at    = ctx.get("initiated_at", "unknown")

    finished_at = datetime.now(timezone.utc).isoformat(timespec="seconds")

    # Parse duration
    duration_s: float | None = None
    try:
        from datetime import datetime as _dt
        s = _dt.fromisoformat(started_at.replace("Z", "+00:00"))
        e = _dt.fromisoformat(finished_at)
        duration_s = round((e - s).total_seconds(), 1)
    except Exception:
        pass

    # Artifact hashes
    prod_snap_path  = BASE / "production_decision_snapshot.json"
    pres_snap_path  = BASE / "presentation_snapshot.json"
    dash_path       = BASE / "dashboard.html"
    pool_db_path    = BASE / "candidate_pool.db"
    timeline_db     = BASE / "constitutional_opportunity_events.db"
    const_fp_path   = BASE / "constitutional_fingerprint.json"
    arch_fp_path    = BASE / "architecture_fingerprint.json"

    # Extract scan_id from decision snapshot to verify consistency
    snap_scan_id: str | None = None
    try:
        snap = json.loads(prod_snap_path.read_text())
        snap_scan_id = snap.get("scan_id")
    except Exception:
        pass

    manifest = {
        "scan_id":                      scan_id,
        "git_commit":                   git_commit,
        "workflow_run":                 workflow_run,
        "workflow_name":                workflow_job,
        "architecture_version":         arch_ver,
        "gate_version":                 gate_ver,
        "started_at":                   started_at,
        "finished_at":                  finished_at,
        "duration_seconds":             duration_s,
        "decision_snapshot_scan_id":    snap_scan_id,
        "scan_id_consistent":           snap_scan_id == scan_id,
        "artifact_hashes": {
            "candidate_pool_db":            _sha256_db(pool_db_path),
            "timeline_db":                  _sha256_db(timeline_db),
            "production_decision_snapshot": _sha256(prod_snap_path),
            "presentation_snapshot":        _sha256(pres_snap_path),
            "dashboard":                    _sha256(dash_path),
            "constitutional_fingerprint":   _sha256(const_fp_path),
            "architecture_fingerprint":     _sha256(arch_fp_path),
        },
    }

    OUTPUT_PATH.write_text(json.dumps(manifest, indent=2))

    print("scan_manifest.json written")
    print(f"  scan_id           : {scan_id}")
    print(f"  git_commit        : {git_commit}")
    print(f"  workflow_run      : {workflow_run}")
    print(f"  arch_version      : {arch_ver}")
    print(f"  gate_version      : {gate_ver}")
    print(f"  started_at        : {started_at}")
    print(f"  finished_at       : {finished_at}")
    print(f"  duration          : {duration_s}s")
    print(f"  scan_id_consistent: {manifest['scan_id_consistent']}")
    for name, h in manifest["artifact_hashes"].items():
        tag = "MISSING" if h is None else h[:16] + "..."
        print(f"  {name:<38} {tag}")

    return manifest


if __name__ == "__main__":
    build_scan_manifest()
