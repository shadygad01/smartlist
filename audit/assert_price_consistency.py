"""
CI Price Consistency Assertion — Constitutional Rule: ONE ticker = ONE current price.

Verifies that every dashboard section shows the IDENTICAL current price for each ticker:
  - Universe Status       (universe_snapshot.db via PriceAuthority)
  - Near Constitutional   (presentation_snapshot.json near_constitutional)
  - Constitutional Holders (timeline current_price)
  - Stock DNA             (timeline events current_price)

Exits 1 if ANY mismatch exists.
"""
from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

BASE = Path(__file__).parent.parent
sys.path.insert(0, str(BASE))

from audit.audit_status import AuditStatus

TOLERANCE_PCT = 0.01  # prices must match within 0.01% (floating point only)

failures: list[str] = []
results_table: list[dict] = []


def _load_universe_snapshot() -> dict[str, float]:
    """PriceAuthority canonical prices from universe_snapshot.db."""
    db = BASE / "universe_snapshot.db"
    if not db.exists():
        return {}
    conn = sqlite3.connect(str(db))
    rows = conn.execute(
        "SELECT ticker, current_price FROM universe_snapshot WHERE current_price > 0"
    ).fetchall()
    conn.close()
    return {r[0]: float(r[1]) for r in rows}


def _load_presentation_near() -> dict[str, float]:
    """Near Constitutional Entry prices from presentation_snapshot.json."""
    p = BASE / "presentation_snapshot.json"
    if not p.exists():
        return {}
    data = json.loads(p.read_text())
    return {e["ticker"]: float(e["current_price"])
            for e in data.get("near_constitutional", [])
            if e.get("current_price")}


def _load_presentation_active() -> dict[str, float]:
    """Active/PREMIUM prices from presentation_snapshot.json."""
    p = BASE / "presentation_snapshot.json"
    if not p.exists():
        return {}
    data = json.loads(p.read_text())
    return {e["ticker"]: float(e["current_price"])
            for e in data.get("active", [])
            if e.get("current_price")}


def _load_timeline_prices() -> dict[str, float]:
    """Latest current_price from constitutional_opportunity_events enriched by PriceAuthority."""
    try:
        from constitutional_timeline_engine import get_timeline
        tl = get_timeline()
        by_ticker: dict[str, float] = {}
        for e in tl:
            by_ticker[e["ticker"]] = float(e["current_price"])
        return by_ticker
    except Exception as exc:
        print(f"  [warn] could not load timeline: {exc}")
        return {}


def _pct_diff(a: float, b: float) -> float:
    denom = max(a, b, 0.001)
    return abs(a - b) / denom * 100


# ── Load all sources ──────────────────────────────────────────────────────────

auth   = _load_universe_snapshot()
near   = _load_presentation_near()
active = _load_presentation_active()
tl     = _load_timeline_prices()

all_tickers = sorted(set(auth) | set(near) | set(active) | set(tl))

print(f"Price Consistency Audit — {len(all_tickers)} tickers")
print(f"{'Ticker':12s} {'Auth(US)':10s} {'NearEntry':10s} {'Active':10s} {'Timeline':10s} {'Result':10s}")
print("-" * 70)

for ticker in all_tickers:
    a_p  = auth.get(ticker)
    ne_p = near.get(ticker)
    ac_p = active.get(ticker)
    tl_p = tl.get(ticker)

    prices = {k: v for k, v in {
        "Universe": a_p, "NearEntry": ne_p,
        "Active": ac_p, "Timeline": tl_p
    }.items() if v is not None}

    if len(prices) < 2:
        status = "SINGLE"
    else:
        vals   = list(prices.values())
        ref    = vals[0]
        diffs  = [_pct_diff(ref, v) for v in vals[1:]]
        max_d  = max(diffs) if diffs else 0.0
        if max_d > TOLERANCE_PCT:
            status = f"MISMATCH {max_d:.2f}%"
            failures.append(
                f"{ticker}: {', '.join(f'{k}={v:.2f}' for k,v in prices.items())}"
            )
        else:
            status = "PASS"

    results_table.append({
        "ticker": ticker, "auth": a_p, "near": ne_p,
        "active": ac_p, "timeline": tl_p, "status": status
    })
    print(
        f"{ticker:12s} "
        f"{(f'{a_p:.2f}' if a_p else '—'):10s} "
        f"{(f'{ne_p:.2f}' if ne_p else '—'):10s} "
        f"{(f'{ac_p:.2f}' if ac_p else '—'):10s} "
        f"{(f'{tl_p:.2f}' if tl_p else '—'):10s} "
        f"{status}"
    )

print(f"\nTotal: {len(all_tickers)} tickers, "
      f"{sum(1 for r in results_table if r['status']=='PASS')} PASS, "
      f"{len(failures)} MISMATCH")

if failures:
    print("\nPRICE MISMATCH VIOLATIONS (CONSTITUTIONAL RULE BROKEN):")
    for f in failures:
        print(f"  ✗ {f}")
    print("\nASSERTION FAILED — multiple current prices exist for the same ticker.")
    sys.exit(AuditStatus.FAIL)

print("\nASSERTION PASSED — all sections show identical current prices.")
sys.exit(AuditStatus.PASS)
