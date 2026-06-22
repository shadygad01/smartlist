"""
CI Protection Gate — Phase 13.
Fails immediately if any constitutional invariant is violated.
Called from GitHub Actions before deployment.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

BASE = Path(__file__).parent.parent

failures  = []
warnings  = []

# ── 1. presentation_snapshot.json ─────────────────────────────────────────────
snap_path = BASE / "presentation_snapshot.json"
if not snap_path.exists():
    failures.append("presentation_snapshot.json missing")
    print("\n".join(failures)); sys.exit(1)

snap = json.loads(snap_path.read_text())

near_t   = {e["ticker"] for e in snap.get("near_constitutional", [])}
active_t = {u["ticker"] for u in snap.get("active", [])}
future_t = {u["ticker"] for u in snap.get("future_candidates", [])}
uni_t    = {u["ticker"] for u in snap.get("universe_snapshot", [])}

# Mutual exclusivity
if near_t & future_t:
    failures.append(f"FAIL: Near ∩ Future not empty: {sorted(near_t & future_t)}")
if active_t & future_t:
    failures.append(f"FAIL: Active ∩ Future not empty: {sorted(active_t & future_t)}")

# Universe completeness
if len(uni_t) == 0:
    failures.append("FAIL: universe_snapshot empty in presentation_snapshot.json")
elif len(uni_t) < 20:
    warnings.append(f"WARN: universe_snapshot only {len(uni_t)} tickers (expected ~27)")

# Duplicate tickers in near / active / future
for label, lst in [
    ("near_constitutional", snap.get("near_constitutional", [])),
    ("active", snap.get("active", [])),
    ("future_candidates", snap.get("future_candidates", [])),
]:
    tickers = [e.get("ticker") for e in lst]
    dupes   = [t for t in set(tickers) if tickers.count(t) > 1]
    if dupes:
        failures.append(f"FAIL: Duplicate tickers in {label}: {dupes}")

# Statistics consistency
stats = snap.get("statistics", {})
if stats.get("near_constitutional_count", -1) != len(near_t):
    failures.append(
        f"FAIL: stats.near_constitutional_count={stats.get('near_constitutional_count')} "
        f"!= actual {len(near_t)}"
    )
if stats.get("active_count", -1) != len(active_t):
    failures.append(
        f"FAIL: stats.active_count={stats.get('active_count')} != actual {len(active_t)}"
    )

# Price staleness: presentation_snapshot generated_at should not be >26h old
gen_at = snap.get("generated_at", "")
if gen_at:
    try:
        from datetime import datetime, timezone, timedelta
        _CAIRO_TZ = timezone(timedelta(hours=2))
        dt = datetime.fromisoformat(gen_at)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=_CAIRO_TZ)
        age_h = (datetime.now(_CAIRO_TZ) - dt).total_seconds() / 3600
        if age_h > 26:
            failures.append(f"FAIL: presentation_snapshot.json is {age_h:.1f}h old (>26h)")
    except Exception:
        pass

# ── 2. heartbeat.json freshness ───────────────────────────────────────────────
hb_path = BASE / "heartbeat.json"
if hb_path.exists():
    try:
        hb = json.loads(hb_path.read_text())
        if hb.get("last_validation_passed") is False:
            failures.append("FAIL: heartbeat.last_validation_passed=False")
    except Exception:
        pass

# ── Report ─────────────────────────────────────────────────────────────────────
print(f"CI Protection Gate")
print(f"  near_constitutional : {len(near_t)}")
print(f"  active              : {len(active_t)}")
print(f"  future_candidates   : {len(future_t)}")
print(f"  universe            : {len(uni_t)}")
print(f"  generated_at        : {gen_at}")

if warnings:
    print("\nWARNINGS:")
    for w in warnings:
        print(f"  ⚠ {w}")

if failures:
    print("\nFAILURES:")
    for f in failures:
        print(f"  ✗ {f}")
    print("\nCI GATE FAILED — do not deploy.")
    sys.exit(1)

print("\nCI GATE PASSED — all invariants satisfied.")
sys.exit(0)
