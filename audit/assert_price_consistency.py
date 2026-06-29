"""
CI Price Consistency Assertion — Constitutional Rule: ONE ticker = ONE current price.

Checks that every section within presentation_snapshot.json shows the IDENTICAL
current_price for each ticker. Sections compared:

  - universe_snapshot[]     (all 27 tickers, canonical snapshot source)
  - active[]                (ACTIVE/PREMIUM/UNDER_REVIEW subset, derived from universe_snapshot)
  - near_constitutional[]   (approaching-entry tickers, PriceAuthority-enriched at build time)

All three are written in the same snapshot generation run and MUST agree.

NOTE: universe_snapshot.db is intentionally excluded from this check because it is
a live database updated by market scans. Any scan that runs after the snapshot is
generated will update the DB but NOT the snapshot file, causing expected divergence.
The DB is the canonical live source; the snapshot is the canonical point-in-time source.
The CI assertion concerns only the internal consistency of a single snapshot.

Exits 1 if ANY intra-snapshot mismatch exceeds TOLERANCE_PCT.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

BASE = Path(__file__).parent.parent
sys.path.insert(0, str(BASE))

from audit.audit_status import AuditStatus

TOLERANCE_PCT = 0.01  # prices must match within 0.01% (floating-point rounding only)

SNAPSHOT_PATH = BASE / "presentation_snapshot.json"

failures: list[str] = []
results_table: list[dict] = []


def _load_snapshot() -> dict:
    if not SNAPSHOT_PATH.exists():
        print(f"ERROR: {SNAPSHOT_PATH} not found")
        sys.exit(AuditStatus.FAIL)
    return json.loads(SNAPSHOT_PATH.read_text())


def _pct_diff(a: float, b: float) -> float:
    denom = max(a, b, 0.001)
    return abs(a - b) / denom * 100


snap = _load_snapshot()

# Section: universe_snapshot[] — all tickers
universe = {e["ticker"]: float(e["current_price"])
            for e in snap.get("universe_snapshot", [])
            if e.get("current_price")}

# Section: active[] — ACTIVE/PREMIUM/UNDER_REVIEW (subset of universe_snapshot)
active = {e["ticker"]: float(e["current_price"])
          for e in snap.get("active", [])
          if e.get("current_price")}

# Section: near_constitutional[] — approaching-entry tickers
near = {e["ticker"]: float(e["current_price"])
        for e in snap.get("near_constitutional", [])
        if e.get("current_price")}

all_tickers = sorted(set(universe) | set(active) | set(near))

print(f"Intra-Snapshot Price Consistency Audit — {len(all_tickers)} tickers")
print(f"Snapshot: {snap.get('scan_id', 'unknown')}  generated: {snap.get('generated_at', 'unknown')}")
print(f"\n{'Ticker':12s} {'Universe':10s} {'Active':10s} {'NearEntry':10s} {'Result':10s}")
print("-" * 60)

for ticker in all_tickers:
    u_p = universe.get(ticker)
    a_p = active.get(ticker)
    n_p = near.get(ticker)

    prices = {k: v for k, v in {
        "Universe": u_p, "Active": a_p, "NearEntry": n_p
    }.items() if v is not None}

    if len(prices) < 2:
        status = "SINGLE"
    else:
        vals  = list(prices.values())
        ref   = vals[0]
        diffs = [_pct_diff(ref, v) for v in vals[1:]]
        max_d = max(diffs) if diffs else 0.0
        if max_d > TOLERANCE_PCT:
            status = f"MISMATCH {max_d:.3f}%"
            failures.append(
                f"{ticker}: {', '.join(f'{k}={v:.4f}' for k, v in prices.items())}"
            )
        else:
            status = "PASS"

    results_table.append({"ticker": ticker, "universe": u_p, "active": a_p, "near": n_p, "status": status})
    print(
        f"{ticker:12s} "
        f"{(f'{u_p:.2f}' if u_p else '—'):10s} "
        f"{(f'{a_p:.2f}' if a_p else '—'):10s} "
        f"{(f'{n_p:.2f}' if n_p else '—'):10s} "
        f"{status}"
    )

passed = sum(1 for r in results_table if r["status"] == "PASS")
single = sum(1 for r in results_table if r["status"] == "SINGLE")

print(f"\nTotal: {len(all_tickers)} tickers — {passed} PASS, {single} SINGLE-SECTION, {len(failures)} MISMATCH")

if failures:
    print("\nINTRA-SNAPSHOT PRICE MISMATCH (CONSTITUTIONAL RULE BROKEN):")
    for f in failures:
        print(f"  ✗ {f}")
    print("\nASSERTION FAILED — same snapshot emits different prices for the same ticker.")
    sys.exit(AuditStatus.FAIL)

print("\nASSERTION PASSED — all snapshot sections show identical current prices.")
sys.exit(AuditStatus.PASS)
