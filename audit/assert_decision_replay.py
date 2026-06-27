"""
Decision Replay Assertion — Phase 7 Constitutional Hardening.

Selects 5 tickers deterministically and replays the constitutional decision from the
authoritative production source (universe_snapshot.db) to verify reproducibility.

Three replay checks:
  1. GATE REPLAY: apply is_constitutional_buy(db_r2, db_score, db_cp, db_ep) for 5 tickers.
     Result must exactly match production_decision_snapshot.eligible.
     This guarantees the gate function is deterministic and the snapshot was built correctly.

  2. POOL CONSISTENCY (soft): if pool data is fresh (signal_date within 5 days),
     verify pool R2/score matches universe_snapshot within tolerance.
     Stale pool → skip (universe_snapshot used egx_research fallback instead).

  3. PRICE CHECK (soft): verify latest CSV price is within 5% of universe_snapshot price.

Exits 1 on Gate Replay failure only. Pool/price checks produce warnings.
"""
from __future__ import annotations

import csv as _csv
import hashlib
import json
import sqlite3
import sys
from datetime import date as _date, datetime, timezone
from pathlib import Path

BASE = Path(__file__).parent.parent
sys.path.insert(0, str(BASE))

from constitutional_gate import is_constitutional_buy

PROD_SNAP = BASE / "production_decision_snapshot.json"
UNI_DB    = BASE / "universe_snapshot.db"
POOL_DB   = BASE / "candidate_pool.db"
HIST_DIR  = BASE / "historical_data" / "historical_data"

POOL_STALE_DAYS  = 5      # same threshold as universe_snapshot.py staleness guard
PRICE_DRIFT_WARN = 0.05   # 5% — CSV vs universe price
RS_MISMATCH_WARN = 0.02   # 2% — pool R2/score vs universe R2/score (soft)

failures: list[str] = []
warnings: list[str] = []


def _pick_5(decisions: list[dict]) -> list[str]:
    """Deterministically select 5 tickers: at least 1 eligible (if any), rest by hash."""
    if len(decisions) <= 5:
        return [d["ticker"] for d in decisions]
    sorted_d = sorted(decisions, key=lambda d: d["ticker"])
    seed     = hashlib.md5(",".join(d["ticker"] for d in sorted_d).encode()).hexdigest()
    base_idx = int(seed[:8], 16)
    n        = len(sorted_d)
    selected: list[str] = []
    seen:     set[str]  = set()
    for d in sorted_d:
        if d["eligible"] and d["ticker"] not in seen:
            selected.append(d["ticker"])
            seen.add(d["ticker"])
            break
    for i in range(n):
        if len(selected) >= 5:
            break
        t = sorted_d[(base_idx + i * 7) % n]["ticker"]
        if t not in seen:
            selected.append(t)
            seen.add(t)
    return selected[:5]


def _pool_entry(ticker: str) -> dict | None:
    if not POOL_DB.exists():
        return None
    try:
        con = sqlite3.connect(str(POOL_DB))
        con.row_factory = sqlite3.Row
        row = con.execute(
            "SELECT * FROM candidate_pool WHERE ticker=? ORDER BY signal_date DESC LIMIT 1",
            (ticker,)
        ).fetchone()
        con.close()
        return dict(row) if row else None
    except Exception:
        return None


def _pool_is_fresh(entry: dict) -> bool:
    sig_date = entry.get("signal_date", "")
    if not sig_date:
        return False
    try:
        age = (_date.today() - _date.fromisoformat(sig_date)).days
        return age <= POOL_STALE_DAYS
    except Exception:
        return False


def _csv_price(ticker: str) -> tuple[float | None, str]:
    cp = HIST_DIR / f"{ticker}.csv"
    if not cp.exists():
        return None, ""
    try:
        with open(cp, newline="") as f:
            rows = list(_csv.DictReader(f))
        if not rows:
            return None, ""
        last  = rows[-1]
        close = float(last.get("Close") or last.get("close") or 0)
        return (close if close > 0 else None), last.get("Date", "")
    except Exception:
        return None, ""


def main() -> int:
    if not PROD_SNAP.exists():
        print("SKIPPED: production_decision_snapshot.json not found — run build_production_decision_snapshot.py first")
        return 2

    prod      = json.loads(PROD_SNAP.read_text())
    decisions = prod.get("decisions", [])
    prod_by_t = {d["ticker"]: d for d in decisions}

    # Load universe_snapshot.db — authoritative source for replay inputs
    uni_by_t: dict[str, dict] = {}
    if UNI_DB.exists():
        con = sqlite3.connect(str(UNI_DB))
        con.row_factory = sqlite3.Row
        uni_by_t = {r["ticker"]: dict(r)
                    for r in con.execute("SELECT * FROM universe_snapshot").fetchall()}
        con.close()

    selected = _pick_5(decisions)

    print("Decision Replay Assertion")
    print(f"  universe: {len(decisions)} tickers  eligible: {prod.get('eligible_count', 0)}")
    print(f"  replaying: {selected}")
    print()

    for ticker in selected:
        prod_d = prod_by_t.get(ticker)
        if not prod_d:
            warnings.append(f"{ticker}: not in production_decision_snapshot")
            continue

        prod_elig = prod_d["eligible"]

        # ── 1. GATE REPLAY from universe_snapshot.db ───────────────────────────
        if ticker in uni_by_t:
            u = uni_by_t[ticker]
            db_r2    = float(u.get("candidate_r2") or 0)
            db_score = float(u.get("expected_reward_score") or 0)
            db_cp    = float(u.get("current_price") or 0)
            db_ep    = float(u.get("constitutional_entry_price") or 0)
            replay   = is_constitutional_buy(db_r2, db_score, db_cp, db_ep)

            if replay != prod_elig:
                failures.append(
                    f"{ticker}: GATE REPLAY MISMATCH — "
                    f"is_constitutional_buy({db_r2:.1f},{db_score:.1f},{db_cp:.4f},{db_ep:.4f})={replay} "
                    f"but production_decision_snapshot.eligible={prod_elig}"
                )
                gate_icon = "✗"
            else:
                gate_icon = "✓"
        else:
            warnings.append(f"{ticker}: not in universe_snapshot.db — gate replay skipped")
            db_r2 = db_score = db_cp = db_ep = 0.0
            gate_icon = "⚠"

        # ── 2. POOL CONSISTENCY (soft) ────────────────────────────────────────
        pool = _pool_entry(ticker)
        pool_icon = "·"
        if pool and _pool_is_fresh(pool):
            pool_r2    = float(pool.get("candidate_r2") or 0)
            pool_score = float(pool.get("expected_reward_score") or 0)
            if db_r2 > 0 and abs(pool_r2 - db_r2) / max(db_r2, 1.0) > RS_MISMATCH_WARN:
                warnings.append(f"{ticker}: pool R2={pool_r2:.2f} vs universe R2={db_r2:.2f} (fresh pool, date={pool.get('signal_date')})")
                pool_icon = "⚠"
            elif db_score > 0 and abs(pool_score - db_score) / max(db_score, 1.0) > RS_MISMATCH_WARN:
                warnings.append(f"{ticker}: pool score={pool_score:.2f} vs universe score={db_score:.2f}")
                pool_icon = "⚠"
            else:
                pool_icon = "✓"
        elif pool:
            pool_icon = "·"  # stale pool — skip comparison

        # ── 3. PRICE CHECK (soft) ─────────────────────────────────────────────
        csv_cp, csv_date = _csv_price(ticker)
        price_icon = "·"
        if csv_cp and db_cp > 0:
            drift = abs(csv_cp - db_cp) / db_cp
            if drift > PRICE_DRIFT_WARN:
                warnings.append(
                    f"{ticker}: price drift {drift*100:.1f}% — "
                    f"CSV={csv_cp:.4f}({csv_date}) vs universe={db_cp:.4f}"
                )
                price_icon = "⚠"
            else:
                price_icon = "✓"

        print(
            f"  gate={gate_icon} pool={pool_icon} price={price_icon}  {ticker:<10}  "
            f"r2={db_r2:.1f}  score={db_score:.1f}  ep={db_ep:.4f}  "
            f"cp={db_cp:.4f}  eligible={prod_elig}"
        )

    print()
    if warnings:
        print("REPLAY WARNINGS (non-blocking):")
        for w in warnings:
            print(f"  ⚠ {w}")

    if failures:
        print("\nREPLAY FAILURES:")
        for f in failures:
            print(f"  ✗ {f}")
        print("\nASSERTION FAILED — gate replay differs from production.")
        return 1

    print("ASSERTION PASSED — all gate replays match production.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
