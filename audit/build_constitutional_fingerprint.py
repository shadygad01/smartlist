"""
Constitutional Fingerprint — Phase 3 Final Hardening.

Generates constitutional_fingerprint.json: SHA256 hashes and key counts
for all authoritative artifacts. Run after every scan.

Fingerprint fields:
  scan_timestamp           — ISO-8601 UTC when fingerprint was built
  commit_sha               — git HEAD SHA
  universe_size            — number of tickers in universe_snapshot.db
  eligible_count           — BUY-eligible tickers in production snapshot
  re_accum_count           — RE_ACCUMULATION tickers
  near_count               — near-constitutional tickers (presentation_snapshot)
  timeline_event_count     — total v1 events in constitutional_opportunity_events.db
  production_decision_sha256
  presentation_snapshot_sha256
  universe_snapshot_sha256
  dashboard_sha256
  candidate_pool_sha256    (if present)
  signal_history_sha256    (if present)

Used by: downstream validation to detect unauthorized mutations of authoritative files.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

BASE   = Path(__file__).parent.parent
OUTPUT = BASE / "constitutional_fingerprint.json"


def _sha256(path: Path) -> str | None:
    if not path.exists():
        return None
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


def _git_sha() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"], text=True, cwd=str(BASE)
        ).strip()
    except Exception:
        return "unknown"


def _universe_size() -> int:
    db = BASE / "universe_snapshot.db"
    if not db.exists():
        return 0
    try:
        con = sqlite3.connect(str(db))
        n = con.execute("SELECT COUNT(*) FROM universe_snapshot").fetchone()[0]
        con.close()
        return n
    except Exception:
        return 0


def _timeline_event_count() -> int:
    db = BASE / "constitutional_opportunity_events.db"
    if not db.exists():
        return 0
    try:
        con = sqlite3.connect(str(db))
        n = con.execute(
            "SELECT COUNT(*) FROM constitutional_opportunity_events "
            "WHERE signal_version='v1' OR signal_version IS NULL"
        ).fetchone()[0]
        con.close()
        return n
    except Exception:
        return 0


def _near_count() -> int:
    pres = BASE / "presentation_snapshot.json"
    if not pres.exists():
        return 0
    try:
        d = json.loads(pres.read_text())
        return len(d.get("near_constitutional", []))
    except Exception:
        return 0


def build_constitutional_fingerprint() -> dict:
    prod_path  = BASE / "production_decision_snapshot.json"
    pres_path  = BASE / "presentation_snapshot.json"
    uni_path   = BASE / "universe_snapshot.db"
    dash_path  = BASE / "dashboard.html"
    pool_path  = BASE / "candidate_pool.db"
    hist_path  = BASE / "signal_history.json"

    eligible_count = 0
    re_accum_count = 0
    if prod_path.exists():
        try:
            prod = json.loads(prod_path.read_text())
            eligible_count = prod.get("eligible_count", 0)
            re_accum_count = sum(
                1 for d in prod.get("decisions", [])
                if d.get("event_type") == "RE_ACCUMULATION"
            )
        except Exception:
            pass

    fp = {
        "scan_timestamp":               datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "commit_sha":                   _git_sha(),
        "universe_size":                _universe_size(),
        "eligible_count":               eligible_count,
        "re_accum_count":               re_accum_count,
        "near_count":                   _near_count(),
        "timeline_event_count":         _timeline_event_count(),
        "production_decision_sha256":   _sha256(prod_path),
        "presentation_snapshot_sha256": _sha256(pres_path),
        "universe_snapshot_sha256":     _sha256(uni_path),
        "dashboard_sha256":             _sha256(dash_path),
        "candidate_pool_sha256":        _sha256(pool_path),
        "signal_history_sha256":        _sha256(hist_path),
    }

    OUTPUT.write_text(json.dumps(fp, indent=2))

    print("Constitutional Fingerprint")
    print(f"  commit:        {fp['commit_sha']}")
    print(f"  universe_size: {fp['universe_size']}")
    print(f"  eligible:      {fp['eligible_count']}")
    print(f"  re_accum:      {fp['re_accum_count']}")
    print(f"  near:          {fp['near_count']}")
    print(f"  tl_events:     {fp['timeline_event_count']}")
    print(f"  prod_snap:     {fp['production_decision_sha256'] or 'MISSING'}")
    print(f"  pres_snap:     {fp['presentation_snapshot_sha256'] or 'MISSING'}")
    print(f"  dashboard:     {fp['dashboard_sha256'] or 'MISSING'}")
    print(f"  Written: {OUTPUT}")
    return fp


if __name__ == "__main__":
    build_constitutional_fingerprint()
