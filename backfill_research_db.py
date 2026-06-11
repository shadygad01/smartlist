"""
Backfill egx_research.db from signal_history.json.

Reads all Buy/Strong Buy signals at least 28 calendar days old,
downloads yfinance price data, computes BQ scores, and inserts
into the signals + bottom_quality tables.
"""

import json
import sqlite3
import sys
import os
from datetime import date, timedelta, datetime

import pandas as pd
import yfinance as yf

# ── project imports ──────────────────────────────────────────────────────────
from signal_db import init_db, get_conn, upsert_bottom_quality, DB_PATH
from daily_tracker import _compute_bq, _days_to_target   # noqa: F401  (used inside _compute_bq)

# ── Config ───────────────────────────────────────────────────────────────────
SIGNAL_HISTORY  = "signal_history.json"
MIN_DAYS_OLD    = 28          # signal must be at least this many calendar days old
LOOKBACK_DAYS   = 120         # days of price history to download per symbol
MIN_TRADING_DAYS = 20         # must have at least 20 trading days after entry

TODAY           = date.today()
CUTOFF_DATE     = TODAY - timedelta(days=MIN_DAYS_OLD)


# ── Minimal signal insert (only the fields we have from signal_history) ──────

def _insert_minimal_signal(conn: sqlite3.Connection, sig_id: str, symbol: str,
                            sig_date: str, signal_type: str, raw_score: int,
                            price: float, r1_price: int | None = None):
    """Insert a minimal signals row, or update r1_price if already exists."""
    conn.execute("""
        INSERT INTO signals
          (id, symbol, signal_date, signal_type, raw_score, r1_price, price, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
          r1_price = excluded.r1_price
    """, (sig_id, symbol, sig_date, signal_type, raw_score, r1_price, price,
          datetime.utcnow().isoformat()))


# ── Main backfill ─────────────────────────────────────────────────────────────

def run_backfill(db_path: str = DB_PATH, dry_run: bool = False):
    init_db(db_path)

    with open(SIGNAL_HISTORY, encoding="utf-8") as f:
        history: dict = json.load(f)

    # Collect eligible signals
    eligible = []
    for symbol, entries in history.items():
        if not isinstance(entries, list):
            entries = [entries]
        for entry in entries:
            sig_date = entry.get("date", "")
            signal   = entry.get("signal", "")
            if signal not in ("Buy", "Strong Buy"):
                continue
            try:
                d = date.fromisoformat(sig_date)
            except ValueError:
                continue
            if d > CUTOFF_DATE:
                continue   # too recent — not enough forward data
            eligible.append({
                "id":          f"{symbol}_{sig_date}",
                "symbol":      symbol,
                "signal_date": sig_date,
                "signal_type": signal,
                "raw_score":   int(entry.get("score", 0)),
                "price":       float(entry.get("price", 0)),
                "r1_price":    int(entry.get("r1", 0)) if entry.get("r1") is not None else None,
            })

    print(f"Eligible Buy/Strong Buy signals (≥{MIN_DAYS_OLD}d old): {len(eligible)}")

    # Check which are already in bottom_quality (BQ computed)
    conn = get_conn(db_path)
    existing_bq_ids = {
        r[0] for r in conn.execute(
            "SELECT signal_id FROM bottom_quality"
        ).fetchall()
    }
    conn.close()

    need_bq    = [s for s in eligible if s["id"] not in existing_bq_ids]
    need_r1upd = [s for s in eligible if s["id"] in existing_bq_ids]
    print(f"Already have BQ: {len(existing_bq_ids)}  |  Need BQ computation: {len(need_bq)}")
    print(f"Updating r1_price on {len(need_r1upd)} existing signals ...")

    if dry_run:
        print("Dry run — exiting without writing.")
        return

    # Update r1_price on all existing signals (fast — no yfinance needed)
    if need_r1upd:
        conn = get_conn(db_path)
        with conn:
            for sig in need_r1upd:
                conn.execute(
                    "UPDATE signals SET r1_price = ? WHERE id = ? AND r1_price IS NULL",
                    (sig.get("r1_price"), sig["id"])
                )
        conn.close()
        print(f"  r1_price updated.")

    # Group by symbol to batch yfinance downloads (only for signals missing BQ)
    from collections import defaultdict
    by_symbol: dict[str, list] = defaultdict(list)
    for sig in need_bq:
        by_symbol[sig["symbol"]].append(sig)

    total_ok = 0
    total_skip = 0
    total_err  = 0

    for symbol, sigs in by_symbol.items():
        # Download enough history to cover the oldest signal + LOOKBACK_DAYS
        earliest = min(date.fromisoformat(s["signal_date"]) for s in sigs)
        dl_start = (earliest - timedelta(days=5)).isoformat()   # small buffer
        dl_end   = (TODAY + timedelta(days=1)).isoformat()

        print(f"\n{symbol}: downloading {dl_start} → {dl_end} ({len(sigs)} signals)")

        try:
            ticker = yf.Ticker(symbol)
            df_raw = ticker.history(start=dl_start, end=dl_end, auto_adjust=True)
        except Exception as exc:
            print(f"  ERROR downloading {symbol}: {exc}")
            total_err += len(sigs)
            continue

        if df_raw.empty:
            print(f"  No data returned for {symbol}")
            total_skip += len(sigs)
            continue

        # Normalise index to date
        df_raw.index = pd.to_datetime(df_raw.index).tz_localize(None)

        conn = get_conn(db_path)
        for sig in sigs:
            bq = _compute_bq(sig, df_raw)
            if bq is None:
                print(f"  SKIP {sig['id']} — insufficient forward data")
                total_skip += 1
                continue

            with conn:
                _insert_minimal_signal(
                    conn,
                    sig_id      = sig["id"],
                    symbol      = sig["symbol"],
                    sig_date    = sig["signal_date"],
                    signal_type = sig["signal_type"],
                    raw_score   = sig["raw_score"],
                    price       = sig["price"],
                    r1_price    = sig.get("r1_price"),
                )

            upsert_bottom_quality(sig["id"], bq, db_path=db_path)

            cls = bq.get("classification", "?")
            mfe = bq.get("mfe_20d", 0)
            bqs = bq.get("bq_score", 0)
            print(f"  OK  {sig['id']:30s}  mfe={mfe:+.1%}  bq={bqs:.0f}  [{cls}]")
            total_ok += 1

        conn.close()

    print(f"\n{'─'*60}")
    print(f"Done.  Inserted: {total_ok}  Skipped: {total_skip}  Errors: {total_err}")

    # Quick summary from DB
    conn = get_conn(db_path)
    row = conn.execute("""
        SELECT COUNT(*),
               ROUND(AVG(bq_score),1),
               ROUND(AVG(mfe_20d)*100,1),
               ROUND(AVG(mae_20d)*100,1)
        FROM bottom_quality
    """).fetchone()
    conn.close()
    print(f"DB totals → signals: {row[0]}  avg_bq: {row[1]}  "
          f"avg_mfe: {row[2]}%  avg_mae: {row[3]}%")


if __name__ == "__main__":
    dry = "--dry-run" in sys.argv
    db  = DB_PATH
    for a in sys.argv[1:]:
        if a.startswith("--db="):
            db = a[5:]
    run_backfill(db_path=db, dry_run=dry)
