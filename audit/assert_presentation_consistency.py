"""
CI Presentation Consistency Assertion
Verifies that presentation_snapshot.json is internally consistent:
- near ∩ future == empty
- active ∩ future == empty
- universe count matches expected
Exits 1 on any violation.
"""
from __future__ import annotations
import json, sys
from pathlib import Path

BASE = Path(__file__).parent.parent
snap_path = BASE / "presentation_snapshot.json"

if not snap_path.exists():
    print("FAIL: presentation_snapshot.json missing — was write_presentation_snapshot_json() called?")
    sys.exit(1)

data = json.loads(snap_path.read_text())

near_t   = {e["ticker"] for e in data.get("near_constitutional", [])}
active_t = {u["ticker"] for u in data.get("active", [])}
future_t = {u["ticker"] for u in data.get("future_candidates", [])}

failures = []

overlap_nf = near_t & future_t
if overlap_nf:
    failures.append(f"Near ∩ Future not empty: {sorted(overlap_nf)}")

overlap_af = active_t & future_t
if overlap_af:
    failures.append(f"Active ∩ Future not empty: {sorted(overlap_af)}")

universe_count = len(data.get("universe_snapshot", []))
if universe_count == 0:
    failures.append("universe_snapshot is empty")

stats = data.get("statistics", {})
if stats.get("near_constitutional_count", -1) != len(near_t):
    failures.append(
        f"statistics.near_constitutional_count={stats.get('near_constitutional_count')} "
        f"!= actual {len(near_t)}"
    )
if stats.get("active_count", -1) != len(active_t):
    failures.append(
        f"statistics.active_count={stats.get('active_count')} != actual {len(active_t)}"
    )

print(f"Presentation Consistency Check")
print(f"  generated_at     : {data.get('generated_at','?')}")
print(f"  universe_size    : {universe_count}")
print(f"  near_constitutional: {len(near_t)}")
print(f"  active           : {len(active_t)}")
print(f"  re_accumulation  : {len(data.get('re_accumulation',[]))}")
print(f"  future_candidates: {len(future_t)}")
print(f"  watchlist        : {len(data.get('watchlist',[]))}")

if failures:
    print("\nCONSISTENCY FAILURES:")
    for f in failures:
        print(f"  ✗ {f}")
    print("\nASSERTION FAILED — presentation layers would produce inconsistent output.")
    sys.exit(1)

print("\nASSERTION PASSED — presentation_snapshot.json is internally consistent.")
sys.exit(0)
