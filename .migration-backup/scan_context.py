"""
Scan Context — Constitutional Architecture Phase 3.

Generates and propagates a unique scan_id (UUID4) across the entire pipeline.
Every artifact producer must embed the scan_id so consumers can verify that all
artifacts in a given run were produced by the same scan.

Usage (producers):
    from scan_context import get_scan_context, read_scan_id
    ctx = get_scan_context()   # reads scan_context.json if present, else generates fresh
    data["scan_id"] = ctx["scan_id"]
    data["_lineage"] = build_lineage(producer=__file__, parents=[...])

Usage (CI initialisation — first step in workflow):
    python3 scan_context.py --init   # generates new UUID, writes scan_context.json

Singleton contract: scan_context.json is written ONCE per scan (--init flag).
All subsequent reads return the same UUID.
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

BASE         = Path(__file__).parent
CTX_FILE     = BASE / "scan_context.json"
GATE_FILE    = BASE / "constitutional_gate.py"

# Production code files whose composite hash forms the architecture_version.
# Any change to these files produces a new architecture_version, making
# architectural drift detectable via the scan_manifest and decision snapshot.
_ARCH_FILES = [
    "constitutional_gate.py",
    "main.py",
    "notifications/scan_orchestrator.py",
    "universe_snapshot.py",
    "presentation/presentation_snapshot.py",
    "audit/build_production_decision_snapshot.py",
    "constitutional_timeline_engine.py",
    "production/transaction.py",
    "production/invariants.py",
]


# ── Git helpers ───────────────────────────────────────────────────────────────

def _git_commit() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"], cwd=str(BASE), text=True
        ).strip()
    except Exception:
        return os.environ.get("GITHUB_SHA", "")[:7] or "unknown"


def _file_sha256(path: Path) -> str:
    if not path.exists():
        return "missing"
    return hashlib.sha256(path.read_bytes()).hexdigest()[:16]


# ── Gate version fingerprint ──────────────────────────────────────────────────

def compute_gate_version() -> str:
    """
    Return a short hash that uniquely identifies the constitutional gate logic.
    Changes when thresholds or gate function bodies change.
    """
    if not GATE_FILE.exists():
        return "unknown"
    text = GATE_FILE.read_text()
    import re
    parts = []
    for pattern in [
        r"CONST_R2_MIN\s*=.*",
        r"CONST_SCORE_MIN\s*=.*",
        r"PRICE_TOLERANCE\s*=.*",
        r"def is_constitutional_buy\(.*?(?=\ndef |\Z)",
        r"def evaluate\(.*?(?=\ndef |\Z)",
    ]:
        parts.extend(m.group(0) for m in re.finditer(pattern, text, re.DOTALL))
    if not parts:
        # Pattern match failed — hash the entire file to avoid silent miss
        return hashlib.sha256(text.encode()).hexdigest()[:16]
    relevant = "\n".join(parts)
    return hashlib.sha256(relevant.encode()).hexdigest()[:16]


def compute_architecture_version() -> str:
    """
    Return a short hash of the composite of all core production code files.
    Changes when ANY tracked production file changes. Stored in scan_context
    and embedded in production_decision_snapshot.json so every decision can be
    traced back to the exact code version that produced it.
    """
    digests: list[str] = []
    for rel in _ARCH_FILES:
        fp = BASE / rel
        if fp.exists():
            digests.append(f"{rel}:{hashlib.sha256(fp.read_bytes()).hexdigest()}")
        else:
            digests.append(f"{rel}:MISSING")
    composite = "\n".join(sorted(digests))
    return hashlib.sha256(composite.encode()).hexdigest()[:16]


# ── Context generation ────────────────────────────────────────────────────────

def compute_producer_version(producer_file: str | Path) -> str:
    """Return SHA256[:16] of a specific producer script."""
    fp = Path(producer_file)
    if not fp.exists():
        # Try relative to BASE
        fp = BASE / fp
    return hashlib.sha256(fp.read_bytes()).hexdigest()[:16] if fp.exists() else "unknown"


def generate_scan_context() -> dict[str, Any]:
    """Generate a fresh scan context with a new UUID4. Does NOT write to disk."""
    return {
        "scan_id":              str(uuid.uuid4()),
        "git_commit":           _git_commit(),
        "workflow_run":         os.environ.get("GITHUB_RUN_ID", "local"),
        "workflow_job":         os.environ.get("GITHUB_JOB", "local"),
        "gate_version":         compute_gate_version(),
        "architecture_version": compute_architecture_version(),
        "initiated_at":         datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "gate_file_sha":        _file_sha256(GATE_FILE),
    }


def init_scan_context(force: bool = False) -> dict[str, Any]:
    """
    Generate a new scan context and write to scan_context.json.
    If the file already exists and force=False, returns the existing context.
    """
    if CTX_FILE.exists() and not force:
        return read_scan_context()
    ctx = generate_scan_context()
    CTX_FILE.write_text(json.dumps(ctx, indent=2))
    return ctx


def read_scan_context() -> dict[str, Any]:
    """
    Read scan context from scan_context.json.
    If the file doesn't exist or is malformed, generates an ephemeral context
    (not written to disk). Logs parse failures so they are never silently swallowed.
    """
    if CTX_FILE.exists():
        try:
            return json.loads(CTX_FILE.read_text())
        except Exception as e:
            print(f"[scan_context] WARN: scan_context.json unreadable ({e}); generating ephemeral context")
    return generate_scan_context()


def get_scan_id() -> str:
    """Return the current scan_id. Fast accessor."""
    return read_scan_context().get("scan_id", str(uuid.uuid4()))


# ── Artifact lineage builder ──────────────────────────────────────────────────

def build_lineage(
    producer: str,
    parents: list[str | Path] | None = None,
) -> dict[str, Any]:
    """
    Return a lineage dict to embed in any generated artifact under '_lineage'.

    Args:
        producer: Name of the script producing the artifact (e.g., __file__).
        parents:  List of file paths that are direct inputs to this artifact.
    """
    ctx  = read_scan_context()
    parents = parents or []
    fingerprints: dict[str, str] = {}
    for p in parents:
        path = Path(p)
        fingerprints[path.name] = _file_sha256(path)

    return {
        "scan_id":              ctx.get("scan_id", "unknown"),
        "producer":             Path(producer).name,
        "parent_artifacts":     [Path(p).name for p in parents],
        "generation_timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "git_commit":           ctx.get("git_commit", _git_commit()),
        "gate_version":         ctx.get("gate_version", compute_gate_version()),
        "workflow_run":         ctx.get("workflow_run", "local"),
        "source_fingerprints":  fingerprints,
    }


# ── Entry point — --init flag ─────────────────────────────────────────────────

if __name__ == "__main__":
    if "--init" in sys.argv or "init" in sys.argv:
        force = "--force" in sys.argv
        ctx   = init_scan_context(force=force)
        print(f"Scan context initialised:")
        print(f"  scan_id     : {ctx['scan_id']}")
        print(f"  git_commit  : {ctx['git_commit']}")
        print(f"  gate_version: {ctx['gate_version']}")
        print(f"  workflow_run: {ctx['workflow_run']}")
        print(f"  initiated_at: {ctx['initiated_at']}")
    else:
        ctx = read_scan_context()
        print(json.dumps(ctx, indent=2))
