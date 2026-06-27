"""
Cross-Layer Consistency Assertion — Phase 2 Constitutional Hardening.

Compares production_decision_snapshot.json against every presentation layer:
  - universe_snapshot.db (input data parity — same R2/score/price fed to gate)
  - presentation_snapshot.json (output signal parity — gate results agree)
  - Dashboard implicit signals (re-derived from presentation universe via gate)

Every field that feeds the gate must be identical across all layers.
Every eligibility result must agree.

Exits 1 on any mismatch.
"""
from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

BASE = Path(__file__).parent.parent
sys.path.insert(0, str(BASE))

from constitutional_gate import is_constitutional_buy
from audit.audit_status import AuditStatus

PROD_SNAP = BASE / "production_decision_snapshot.json"
PRES_SNAP = BASE / "presentation_snapshot.json"
UNI_DB    = BASE / "universe_snapshot.db"

R2_TOL    = 0.001   # floating-point rounding only
SCORE_TOL = 0.001
PRICE_TOL = 0.001   # 0.1% — intraday drift may move price between snapshot writes

failures: list[str] = []
warnings: list[str] = []


def _near(a: float, b: float, tol: float) -> bool:
    base = max(abs(a), abs(b), 1.0)
    return abs(a - b) / base <= tol


def main() -> int:
    if not PROD_SNAP.exists():
        print("SKIPPED: production_decision_snapshot.json not found — run build_production_decision_snapshot.py first")
        return AuditStatus.SKIPPED

    prod      = json.loads(PROD_SNAP.read_text())
    prod_by_t = {d["ticker"]: d for d in prod.get("decisions", [])}
    prod_elig = {t for t, d in prod_by_t.items() if d["eligible"]}

    print("Cross-Layer Consistency Assertion")
    print(f"  production_decision_snapshot: {len(prod_by_t)} tickers  eligible={len(prod_elig)}")
    print(f"  generated_at: {prod.get('generated_at', '?')}")
    print()

    # ── 1. universe_snapshot.db — input parity ─────────────────────────────────
    if UNI_DB.exists():
        con = sqlite3.connect(str(UNI_DB))
        con.row_factory = sqlite3.Row
        uni = {r["ticker"]: dict(r)
               for r in con.execute("SELECT * FROM universe_snapshot").fetchall()}
        con.close()

        for ticker, d in prod_by_t.items():
            if ticker not in uni:
                failures.append(f"[DB] {ticker}: in production_snapshot but missing from universe_snapshot.db")
                continue
            u = uni[ticker]
            db_r2    = float(u.get("candidate_r2") or 0)
            db_score = float(u.get("expected_reward_score") or 0)
            db_ep    = float(u.get("constitutional_entry_price") or 0)
            db_cp    = float(u.get("current_price") or 0)

            if not _near(db_r2, d["constitutional_r2"], R2_TOL):
                failures.append(f"[DB] {ticker}: R2  DB={db_r2}  snapshot={d['constitutional_r2']}")
            if not _near(db_score, d["constitutional_score"], SCORE_TOL):
                failures.append(f"[DB] {ticker}: score  DB={db_score}  snapshot={d['constitutional_score']}")
            if db_ep > 0 and d["constitutional_entry_price"] > 0:
                if not _near(db_ep, d["constitutional_entry_price"], PRICE_TOL):
                    failures.append(f"[DB] {ticker}: entry_price  DB={db_ep}  snapshot={d['constitutional_entry_price']}")
            if db_cp > 0 and d["current_price"] > 0:
                if not _near(db_cp, d["current_price"], PRICE_TOL):
                    warnings.append(f"[DB] {ticker}: current_price drift DB={db_cp} snap={d['current_price']} (intraday OK)")

            # Re-derive gate from DB values and compare
            db_gate = is_constitutional_buy(db_r2, db_score, db_cp, db_ep)
            if db_gate != d["eligible"]:
                failures.append(
                    f"[DB-GATE] {ticker}: gate from DB({db_r2:.1f},{db_score:.1f},{db_cp:.4f},{db_ep:.4f})={db_gate} "
                    f"but production_decision_snapshot.eligible={d['eligible']}"
                )

        print(f"  Layer 1 — universe_snapshot.db: {len(uni)} tickers validated")
    else:
        warnings.append("universe_snapshot.db not found — DB input parity skipped")

    # ── 2. presentation_snapshot.json — output parity ─────────────────────────
    if PRES_SNAP.exists():
        pres     = json.loads(PRES_SNAP.read_text())
        pres_uni = {r["ticker"]: r for r in pres.get("universe_snapshot", [])}

        for ticker, d in prod_by_t.items():
            if ticker not in pres_uni:
                warnings.append(f"[PRES] {ticker}: not in presentation_snapshot.universe_snapshot")
                continue
            p = pres_uni[ticker]
            pres_r2    = float(p.get("candidate_r2") or 0)
            pres_score = float(p.get("expected_reward_score") or 0)
            pres_ep    = float(p.get("constitutional_entry_price") or 0)
            pres_cp    = float(p.get("current_price") or 0)

            if not _near(pres_r2, d["constitutional_r2"], R2_TOL):
                failures.append(f"[PRES] {ticker}: R2 pres={pres_r2} prod={d['constitutional_r2']}")
            if not _near(pres_score, d["constitutional_score"], SCORE_TOL):
                failures.append(f"[PRES] {ticker}: score pres={pres_score} prod={d['constitutional_score']}")
            if pres_ep > 0 and d["constitutional_entry_price"] > 0:
                if not _near(pres_ep, d["constitutional_entry_price"], PRICE_TOL):
                    failures.append(f"[PRES] {ticker}: entry_price pres={pres_ep} prod={d['constitutional_entry_price']}")

            # Re-derive gate from presentation values
            pres_gate = is_constitutional_buy(pres_r2, pres_score, pres_cp, pres_ep)
            if pres_gate != d["eligible"]:
                failures.append(
                    f"[PRES-GATE] {ticker}: ELIGIBILITY DIVERGENCE — "
                    f"presentation gate={pres_gate} vs production={d['eligible']}"
                )

        # Dashboard implicit: tickers the dashboard _s_buy_signals() would show
        dash_elig: set[str] = set()
        for row in pres.get("universe_snapshot", []):
            t  = row.get("ticker", "")
            if t and is_constitutional_buy(
                float(row.get("candidate_r2") or 0),
                float(row.get("expected_reward_score") or 0),
                float(row.get("current_price") or 0),
                float(row.get("constitutional_entry_price") or 0),
            ):
                dash_elig.add(t)

        mismatch = dash_elig ^ prod_elig
        for t in mismatch:
            if t in dash_elig:
                failures.append(f"[DASH] {t}: dashboard gate=True but production_decision_snapshot.eligible=False")
            else:
                failures.append(f"[DASH] {t}: production.eligible=True but dashboard gate=False")

        # today_events must be eligible
        try:
            from time_authority import today_cairo
            _today = today_cairo().isoformat()
        except Exception:
            from datetime import date as _d
            _today = _d.today().isoformat()

        today_evs = [e for e in pres.get("new_events_today", []) if e.get("event_date") == _today]
        for ev in today_evs:
            t = ev["ticker"]
            if t in prod_by_t and not prod_by_t[t]["eligible"]:
                failures.append(f"[TODAY] {t}: in new_events_today but production_decision_snapshot.eligible=False")

        print(f"  Layer 2 — presentation_snapshot.json: {len(pres_uni)} tickers  "
              f"dash_eligible={len(dash_elig)}  prod_eligible={len(prod_elig)}")
        print(f"  Layer 3 — Dashboard implicit signals: {len(mismatch)} mismatch(es)")
    else:
        warnings.append("presentation_snapshot.json not found — output parity skipped")

    # ── Report ─────────────────────────────────────────────────────────────────
    if warnings:
        print("\nWARNINGS:")
        for w in warnings:
            print(f"  ⚠ {w}")
    if failures:
        print("\nCROSS-LAYER FAILURES:")
        for f in failures:
            print(f"  ✗ {f}")
        print("\nASSERTION FAILED — presentation layers produce inconsistent decisions.")
        return AuditStatus.FAIL

    print("\nASSERTION PASSED — all layers agree on constitutional decisions.")
    return AuditStatus.PASS


if __name__ == "__main__":
    sys.exit(main())
