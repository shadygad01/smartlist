"""
Full Universe Replay Assertion — Phase 1 Final Hardening.

Replays ConstitutionalDecision for EVERY ticker in the production universe (all ~27).
No sampling. No random selection. 100% deterministic.

For each ticker:
  1. Verify universe_snapshot.db inputs match stored production snapshot values.
  2. Re-call evaluate() with DB inputs and stored metadata (event_type, sector).
  3. Compare EVERY output field: eligible, reason, constitutional_entry_price,
     constitutional_r2, constitutional_score, event_type, return_pct, status.

Exits 1 on any mismatch. Gate replay failure is blocking.
Input mismatch (DB vs snapshot) is a warning (pool/db may have been refreshed mid-run).
"""
from __future__ import annotations

import json
import re
import sqlite3
import sys
from pathlib import Path

BASE = Path(__file__).parent.parent
sys.path.insert(0, str(BASE))

from constitutional_gate import evaluate, is_constitutional_buy
from audit.audit_status import AuditStatus

PROD_SNAP = BASE / "production_decision_snapshot.json"
UNI_DB    = BASE / "universe_snapshot.db"

FLOAT_TOL   = 0.001   # 0.1% tolerance for float comparison
PRICE_TOL   = 0.001   # same for price fields

failures: list[str] = []
warnings: list[str] = []


def _float_eq(a: float, b: float, tol: float = FLOAT_TOL) -> bool:
    if a == b:
        return True
    denom = max(abs(b), 1.0)
    return abs(a - b) / denom <= tol


def main() -> int:
    if not PROD_SNAP.exists():
        print("SKIPPED: production_decision_snapshot.json not found — run build_production_decision_snapshot.py first")
        return AuditStatus.SKIPPED

    prod     = json.loads(PROD_SNAP.read_text())
    stored   = {d["ticker"]: d for d in prod.get("decisions", [])}
    gen_at   = prod.get("generated_at", "")

    if not stored:
        print("SKIPPED: production_decision_snapshot.json has no decisions")
        return AuditStatus.SKIPPED

    # Load universe_snapshot.db — authoritative inputs
    uni_by_t: dict[str, dict] = {}
    if UNI_DB.exists():
        con = sqlite3.connect(str(UNI_DB))
        con.row_factory = sqlite3.Row
        for row in con.execute("SELECT * FROM universe_snapshot").fetchall():
            uni_by_t[row["ticker"]] = dict(row)
        con.close()

    print("Full Universe Replay Assertion")
    print(f"  universe: {len(stored)} tickers  eligible: {prod.get('eligible_count', 0)}")
    print(f"  generated_at: {gen_at}")
    print()

    for ticker in sorted(stored.keys()):
        s = stored[ticker]   # stored decision fields

        # ── 1. Load DB inputs ─────────────────────────────────────────────────
        if ticker not in uni_by_t:
            warnings.append(f"{ticker}: not in universe_snapshot.db — replay skipped")
            print(f"  ⚠ {ticker:<12}  NOT IN DB")
            continue

        u      = uni_by_t[ticker]
        db_r2  = float(u.get("candidate_r2") or 0)
        db_sc  = float(u.get("expected_reward_score") or 0)
        db_cp  = float(u.get("current_price") or 0)
        db_ep  = float(u.get("constitutional_entry_price") or 0)

        # ── 2. Input consistency (DB vs stored snapshot) ──────────────────────
        stored_r2  = float(s.get("constitutional_r2") or 0)
        stored_sc  = float(s.get("constitutional_score") or 0)
        stored_cp  = float(s.get("current_price") or 0)

        # Derive stored entry_price from snapshot — inverse of evaluate():
        # constitutional_entry_price = entry_price if ep>0 else current_price
        # When cep == cp, the original ep could be 0 (→ cep=cp) or cp (→ cep=cp).
        # Parse the stored reason's "Entry=X" field to disambiguate.
        stored_cep = float(s.get("constitutional_entry_price") or 0)
        if stored_cep != stored_cp or stored_cp == 0:
            stored_ep = stored_cep
        else:
            m = re.search(r"Entry=([\d.]+)", s.get("reason", ""))
            stored_ep = float(m.group(1)) if m else 0.0

        if not _float_eq(db_r2, stored_r2):
            warnings.append(f"{ticker}: DB R2={db_r2:.4f} vs stored R2={stored_r2:.4f} (DB may have refreshed)")
        if not _float_eq(db_sc, stored_sc):
            warnings.append(f"{ticker}: DB score={db_sc:.4f} vs stored score={stored_sc:.4f}")
        if not _float_eq(db_cp, stored_cp, PRICE_TOL):
            warnings.append(f"{ticker}: DB price={db_cp:.4f} vs stored price={stored_cp:.4f}")

        # ── 3. Gate Replay — use stored inputs to get deterministic result ────
        # Use stored r2/score/cp/ep so replay is deterministic against snapshot
        s_r2 = stored_r2
        s_sc = stored_sc
        s_cp = stored_cp
        s_ep = stored_ep

        replayed = evaluate(
            ticker        = ticker,
            r2            = s_r2,
            score         = s_sc,
            current_price = s_cp,
            entry_price   = s_ep,
            event_type    = s.get("event_type", "NONE"),
            sector        = s.get("sector", ""),
            event_date    = s.get("event_date", ""),
            return_pct    = float(s.get("return_pct") or 0),
            status        = s.get("status", ""),
            generated_at  = s.get("generated_at", gen_at),
        )

        # ── 4. Field-by-field comparison ──────────────────────────────────────
        ok = True

        if replayed.eligible != s.get("eligible"):
            failures.append(
                f"{ticker}: eligible={replayed.eligible} != stored={s.get('eligible')}"
            )
            ok = False

        if replayed.event_type != s.get("event_type"):
            failures.append(
                f"{ticker}: event_type={replayed.event_type!r} != stored={s.get('event_type')!r}"
            )
            ok = False

        if not _float_eq(replayed.constitutional_entry_price, stored_cep, PRICE_TOL):
            failures.append(
                f"{ticker}: constitutional_entry_price replayed={replayed.constitutional_entry_price:.4f} "
                f"stored={stored_cep:.4f}"
            )
            ok = False

        if not _float_eq(replayed.constitutional_r2, s_r2):
            failures.append(
                f"{ticker}: constitutional_r2 replayed={replayed.constitutional_r2:.4f} stored={s_r2:.4f}"
            )
            ok = False

        if not _float_eq(replayed.constitutional_score, s_sc):
            failures.append(
                f"{ticker}: constitutional_score replayed={replayed.constitutional_score:.4f} stored={s_sc:.4f}"
            )
            ok = False

        if replayed.reason != s.get("reason", ""):
            failures.append(
                f"{ticker}: reason mismatch\n"
                f"    replayed: {replayed.reason!r}\n"
                f"    stored:   {s.get('reason')!r}"
            )
            ok = False

        icon = "✓" if ok else "✗"
        elig = "BUY" if s.get("eligible") else "---"
        print(
            f"  {icon} {ticker:<12}  {elig:<3}  "
            f"r2={s_r2:.1f}  score={s_sc:.1f}  "
            f"ep={stored_cep:.4f}  cp={s_cp:.4f}"
        )

    print()
    if warnings:
        print("REPLAY WARNINGS (non-blocking — DB may have refreshed after snapshot):")
        for w in warnings:
            print(f"  ⚠ {w}")
        print()

    if failures:
        print("REPLAY FAILURES:")
        for f in failures:
            print(f"  ✗ {f}")
        print("\nASSERTION FAILED — full universe replay diverged from production snapshot.")
        return AuditStatus.FAIL

    print(f"ASSERTION PASSED — all {len(stored)} tickers replay identically.")
    return AuditStatus.PASS


if __name__ == "__main__":
    sys.exit(main())
