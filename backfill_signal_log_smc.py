"""
SMC Historical Signal Backfill → signal_log.json
=================================================
Reads all signals from egx_research.db (2021 onwards) that have BQ
computed, and injects them into signal_log.json so the equity curve
and research report show performance from 2021 instead of 2024.

Each entry uses:
  - smc_score    = raw_score from signals table
  - outcome_gain = r20d  (actual confirmed return at exactly 20 trading days — real exit, no assumptions)
  - peak_gain    = mfe_20d  (actual max favorable excursion — how far price moved at best)
  - outcome      = flat/small/medium/large mapped from r20d thresholds
  - outcome_date = signal_date + 28 calendar days (~20 trading days)
  - source       = "smc_historical"

Run once after historical_backtest.py + backfill_research_db.py.
Safe to re-run — skips existing ids.
"""

import json
import sqlite3
from datetime import date, timedelta
from pathlib import Path

from signal_db import DB_PATH, get_conn
from egx_context import is_ramadan, is_cbe_window

SIGNAL_LOG_FILE = "signal_log.json"

def _outcome_from_r20d(r20d: float) -> str:
    """Map actual 20-day return to outcome category — no assumptions, real exit."""
    if   r20d >= 0.20: return "large"
    elif r20d >= 0.08: return "medium"
    elif r20d >= 0.04: return "small"
    else:              return "flat"


def _load_signal_log() -> dict:
    p = Path(SIGNAL_LOG_FILE)
    if p.exists():
        with open(p, encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, list):
            return {"signals": data}
        return data
    return {"signals": []}


def run_backfill(db_path: str = DB_PATH, dry_run: bool = False):
    print("SMC Historical → signal_log.json backfill")
    print("=" * 55)

    # Load existing signal_log
    log_data  = _load_signal_log()
    existing  = log_data.setdefault("signals", [])
    exist_ids = {s["id"] for s in existing if "id" in s}
    print(f"Existing signal_log entries: {len(existing)}")

    # Pull all signals with BQ from DB
    conn = get_conn(db_path)
    rows = conn.execute("""
        SELECT
            s.id, s.symbol, s.signal_date, s.signal_type,
            s.raw_score, s.price,
            b.mfe_20d, b.mae_20d, b.r20d
        FROM signals s
        JOIN bottom_quality b ON b.signal_id = s.id
        ORDER BY s.signal_date
    """).fetchall()
    conn.close()
    print(f"DB signals with BQ: {len(rows)}")

    new_entries = []
    skipped     = 0

    for row in rows:
        sig_id, symbol, sig_date, sig_type, raw_score, price, \
            mfe_20d, mae_20d, r20d = row

        log_id = f"{sig_id}_smc_hist"
        if log_id in exist_ids:
            skipped += 1
            continue

        # Dates
        d            = date.fromisoformat(sig_date)
        outcome_date = (d + timedelta(days=28)).isoformat()

        # Use r20d (actual confirmed return at day 20) — no assumptions
        r20d_val      = float(r20d) if r20d is not None else 0.0
        outcome_price = round(float(price) * (1 + r20d_val), 2)

        # Outcome category — based on actual exit, not peak
        outcome = _outcome_from_r20d(r20d_val)

        # Context flags (historically accurate)
        ctx = {
            "is_ramadan":   is_ramadan(d),
            "cbe_window":   is_cbe_window(d),
            "season":       "normal",
            "volume_vs_adv": None,
        }

        entry = {
            "id":            log_id,
            "symbol":        symbol,
            "signal_date":   sig_date,
            "signal":        sig_type,
            "smc_score":     int(raw_score) if raw_score is not None else 0,
            "pattern_score": 0,
            "price":         float(price),
            "target":        round(float(price) * 1.15, 2),
            "indicators":    {},
            "outcome":       outcome,
            "outcome_date":  outcome_date,
            "outcome_price": outcome_price,
            "outcome_gain":  round(r20d_val, 4),
            "peak_gain":     round(float(mfe_20d), 4),
            "source":        "smc_historical",
            "context":       ctx,
        }
        new_entries.append(entry)
        exist_ids.add(log_id)

    print(f"Already in log (skipped): {skipped}")
    print(f"New entries to add:       {len(new_entries)}")

    if not new_entries:
        print("Nothing to add.")
        return

    # Stats
    by_year = {}
    for e in new_entries:
        yr = e["signal_date"][:4]
        by_year[yr] = by_year.get(yr, 0) + 1
    print("\nNew entries by year:")
    for yr in sorted(by_year):
        print(f"  {yr}: {by_year[yr]}")

    if dry_run:
        print("\nDry run — nothing written.")
        return

    # Merge: keep existing first, then new SMC historical (sorted by date)
    all_signals = existing + new_entries
    all_signals.sort(key=lambda s: s.get("signal_date", ""))
    log_data["signals"] = all_signals

    with open(SIGNAL_LOG_FILE, "w", encoding="utf-8") as f:
        json.dump(log_data, f, ensure_ascii=False, indent=2)

    print(f"\nSaved {len(all_signals)} total entries → {SIGNAL_LOG_FILE}")
    print("Next: run research_report.py or daily scan to regenerate reports")


if __name__ == "__main__":
    import sys
    dry = "--dry-run" in sys.argv
    db  = DB_PATH
    for a in sys.argv[1:]:
        if a.startswith("--db="):
            db = a[5:]
    run_backfill(db_path=db, dry_run=dry)
