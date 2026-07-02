"""
challenger_scanner.py — Challenger Architecture Orchestrator (3-Layer System).

This module runs the CHALLENGER in parallel with production.
It does NOT modify production signals or the active trading portfolio.
It writes results to challenger_results table in egx_research.db for validation.

ARCHITECTURE:
  Layer 1: Eligibility Engine  → ELIGIBLE / REJECTED (discount-first, non-negotiable)
  Layer 2: Expectancy Engine   → 0–100 score (outcome quality, NOT indicator quality)
  Layer 3: Allocation Engine   → A+/A/B/C/D grade + deployment priority

USAGE:
  python challenger_scanner.py           # run on all 26 stock universe
  python challenger_scanner.py SYMBOL    # run on single symbol (debug)
"""

from __future__ import annotations
import sys
import sqlite3
import json
from datetime import datetime, date
from dataclasses import asdict

import challenger_eligibility_engine as eligibility
import challenger_expectancy_engine  as expectancy
import challenger_allocation_engine  as allocation


# Stock universe — mirror production SYMBOLS list
SYMBOLS = [
    "ABUK.CA", "ADIB.CA", "AMOC.CA", "AMER.CA", "COMI.CA",
    "CIRA.CA", "DCBL.CA", "DISK.CA", "EAST.CA", "EGCH.CA",
    "EGTS.CA", "FWRY.CA", "GTHE.CA", "HELI.CA", "ISPH.CA",
    "MNHD.CA", "MFPC.CA", "NBKK.CA", "OCDI.CA", "ORAS.CA",
    "ORTE.CA", "PHDC.CA", "SAUD.CA", "SKPC.CA", "TALM.CA",
    "TMGH.CA",
]

DB_PATH = "egx_research.db"


def _ensure_challenger_table(conn: sqlite3.Connection) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS challenger_results (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            run_date     TEXT NOT NULL,
            symbol       TEXT NOT NULL,
            eligible     INTEGER NOT NULL,
            reject_reason TEXT,
            exp_score    INTEGER,
            exp_outcome  REAL,
            exp_model    TEXT,
            exp_n_train  INTEGER,
            alloc_grade  TEXT,
            alloc_pct    REAL,
            deploy       INTEGER,
            raw_score    INTEGER,
            r1_price     INTEGER,
            r2_ob        INTEGER,
            r3_liquidity INTEGER,
            r4_htf       INTEGER,
            r5_avwap     INTEGER,
            r6_macd      INTEGER,
            r7_div       INTEGER,
            r8_demand    INTEGER,
            sv_hit       INTEGER,
            hvn_hit      INTEGER,
            contributions TEXT,
            created_at   TEXT DEFAULT (datetime('now'))
        )
    """)
    conn.commit()


def run_challenger_on_signal(
    signal: dict,
    run_date: str = None,
    db_path: str = DB_PATH,
    whitelist: set = None,
) -> dict:
    """
    Run the 3-layer challenger on a single signal dict (as returned by analyze()).

    Returns enriched dict with challenger_* fields added.
    Does NOT write to DB — caller handles persistence.
    """
    if run_date is None:
        run_date = datetime.now().strftime("%Y-%m-%d")
    if whitelist is None:
        whitelist = set()

    sym = signal.get("symbol", "")
    cur = signal.get("price", signal.get("cur", 0.0))
    eq  = signal.get("eq", 0.0)
    lo  = signal.get("lo", 0.0)
    hi  = signal.get("hi", 0.0)
    r1  = signal.get("r1", signal.get("r1_price", 0))
    raw = signal.get("raw_score", 0)

    # ── Layer 1: Eligibility ──────────────────────────────────────────────────
    elig = eligibility.check_eligibility(
        cur=cur, eq=eq, lo=lo, hi=hi,
        r1_price=r1, raw_score=raw,
        is_whitelist=(sym in whitelist),
    )

    result = dict(signal)
    result["challenger_eligible"]     = elig.eligible
    result["challenger_reject_reason"] = None if elig.eligible else elig.reason

    if not elig.eligible:
        result["challenger_score"]       = 0
        result["challenger_grade"]       = "REJECTED"
        result["challenger_deploy"]      = False
        result["challenger_exp_outcome"] = None
        result["challenger_model"]       = None
        return result

    # ── Layer 2: Expectancy ───────────────────────────────────────────────────
    factors = {
        "r2_ob":        signal.get("r2", signal.get("r2_ob", 0)) or 0,
        "r3_liquidity": signal.get("r3", signal.get("r3_liquidity", 0)) or 0,
        "r4_htf":       signal.get("r4", signal.get("r4_htf", 0)) or 0,
        "r5_avwap":     signal.get("r5", signal.get("r5_avwap", 0)) or 0,
        "r6_macd":      signal.get("r6", signal.get("r6_macd", 0)) or 0,
        "r7_div":       signal.get("r7", signal.get("r7_div", 0)) or 0,
        "r8_demand":    signal.get("r8", signal.get("r8_demand", 0)) or 0,
    }

    sv_hit  = bool(signal.get("sv_hit", False))
    hvn_hit = bool(signal.get("hvn_hit", False))
    engine  = expectancy.get_engine(db_path)

    exp_result = engine.compute(
        signal_factors=factors,
        signal_date=run_date,
        sv_hit=sv_hit,
        hvn_hit=hvn_hit,
    )

    # ── Layer 3: Allocation ───────────────────────────────────────────────────
    alloc = allocation.grade(exp_result.score)

    result["challenger_score"]        = exp_result.score
    result["challenger_grade"]        = alloc.grade
    result["challenger_deploy"]       = alloc.deploy
    result["challenger_exp_outcome"]  = exp_result.expected_outcome
    result["challenger_model"]        = exp_result.model_source
    result["challenger_n_train"]      = exp_result.n_train
    result["challenger_confidence"]   = exp_result.confidence
    result["challenger_alloc_pct"]    = alloc.allocation_pct
    result["challenger_contributions"] = exp_result.feature_contributions
    return result


def _log_result(conn: sqlite3.Connection, run_date: str, sym: str, r: dict) -> None:
    conn.execute("""
        INSERT INTO challenger_results
          (run_date, symbol, eligible, reject_reason,
           exp_score, exp_outcome, exp_model, exp_n_train,
           alloc_grade, alloc_pct, deploy,
           raw_score, r1_price, r2_ob, r3_liquidity, r4_htf,
           r5_avwap, r6_macd, r7_div, r8_demand,
           sv_hit, hvn_hit, contributions)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
    """, (
        run_date, sym,
        int(r.get("challenger_eligible", False)),
        r.get("challenger_reject_reason"),
        r.get("challenger_score"),
        r.get("challenger_exp_outcome"),
        r.get("challenger_model"),
        r.get("challenger_n_train"),
        r.get("challenger_grade"),
        r.get("challenger_alloc_pct"),
        int(bool(r.get("challenger_deploy", False))),
        r.get("raw_score"),
        r.get("r1", r.get("r1_price")),
        r.get("r2", r.get("r2_ob")),
        r.get("r3", r.get("r3_liquidity")),
        r.get("r4", r.get("r4_htf")),
        r.get("r5", r.get("r5_avwap")),
        r.get("r6", r.get("r6_macd")),
        r.get("r7", r.get("r7_div")),
        r.get("r8", r.get("r8_demand")),
        int(bool(r.get("sv_hit", False))),
        int(bool(r.get("hvn_hit", False))),
        json.dumps(r.get("challenger_contributions") or {}),
    ))


def run_batch(symbols: list[str] = None, save_to_db: bool = True) -> list[dict]:
    """
    Run challenger on all symbols, fetch their latest signal from signals table,
    and persist results. Returns list of result dicts.
    """
    if symbols is None:
        symbols = SYMBOLS

    run_date = datetime.now().strftime("%Y-%m-%d")
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    _ensure_challenger_table(conn)

    results = []
    for sym in symbols:
        # Fetch latest signal for this symbol
        row = conn.execute("""
            SELECT * FROM signals
            WHERE symbol = ?
            ORDER BY signal_date DESC
            LIMIT 1
        """, (sym,)).fetchone()

        if row is None:
            print(f"[challenger] {sym}: no signal data in DB — skipping")
            continue

        sig = dict(row)
        sig["symbol"]  = sym
        sig["price"]   = sig.get("price")
        # Remap column names (signals table uses r1_price etc.)
        sig["r1"] = sig.get("r1_price", 0)
        sig["r2"] = sig.get("r2_ob", 0)
        sig["r3"] = sig.get("r3_liquidity", 0)
        sig["r4"] = sig.get("r4_htf", 0)
        sig["r5"] = sig.get("r5_avwap", 0)
        sig["r6"] = sig.get("r6_macd", 0)
        sig["r7"] = sig.get("r7_div", 0)
        sig["r8"] = sig.get("r8_demand", 0)
        sig["hi"] = sig.get("sell_lo", sig.get("eq", 0)) * 1.5  # approximate
        sig["lo"] = sig.get("buy_hi", 0) / 3                     # approximate

        r = run_challenger_on_signal(sig, run_date=run_date)

        if save_to_db:
            _log_result(conn, run_date, sym, r)

        status = f"[{r.get('challenger_grade','?')}]" if r.get("challenger_eligible") else "[REJECTED]"
        score  = r.get("challenger_score", 0)
        print(f"[challenger] {sym:12s}: score={score:3d}  {status}")
        results.append(r)

    conn.commit()
    conn.close()
    return results


if __name__ == "__main__":
    if len(sys.argv) > 1:
        sym = sys.argv[1].upper()
        print(f"Running challenger on {sym} (single symbol mode)...")
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT * FROM signals WHERE symbol=? ORDER BY signal_date DESC LIMIT 1", (sym,)
        ).fetchone()
        conn.close()
        if row:
            sig = dict(row)
            sig["symbol"] = sym
            sig["r1"] = sig.get("r1_price", 0)
            for rk in ["r2","r3","r4","r5","r6","r7","r8"]:
                col = {"r2":"r2_ob","r3":"r3_liquidity","r4":"r4_htf","r5":"r5_avwap",
                       "r6":"r6_macd","r7":"r7_div","r8":"r8_demand"}[rk]
                sig[rk] = sig.get(col, 0)
            r = run_challenger_on_signal(sig)
            print(json.dumps({k: v for k, v in r.items() if k.startswith("challenger")}, indent=2))
        else:
            print(f"No signal found for {sym}")
    else:
        print(f"Running challenger batch on {len(SYMBOLS)} symbols...")
        results = run_batch()
        deployable = [r for r in results if r.get("challenger_deploy")]
        print(f"\nDeployable signals: {len(deployable)}/{len(results)}")
        for r in deployable:
            print(f"  {r.get('symbol')}: score={r.get('challenger_score')} grade={r.get('challenger_grade')}")
