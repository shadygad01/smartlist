"""
Backfill egx_research.db from signal_history.json.

Reads all Buy/Strong Buy signals at least 28 calendar days old,
downloads yfinance price data, computes BQ scores, and inserts
into the signals + bottom_quality tables.

Phase 1 upgrade: also computes feat_* and snap_* features from
400-day OHLCV history for every signal (requires pre-signal data).
"""

import json
import sqlite3
import sys
import os
from collections import defaultdict
from datetime import date, timedelta, datetime

import pandas as pd
import yfinance as yf

# ── project imports ──────────────────────────────────────────────────────────
from signal_db import (
    init_db, get_conn, upsert_bottom_quality,
    upsert_signal_features, DB_PATH,
)
from daily_tracker import _compute_bq, _days_to_target   # noqa: F401
from feature_extractor import compute_entry_features

# ── Config ───────────────────────────────────────────────────────────────────
SIGNAL_HISTORY   = "signal_history.json"
MIN_DAYS_OLD     = 28          # signal must be at least this many calendar days old
LOOKBACK_DAYS    = 400         # calendar days of history to download (covers 252-bar features)
MIN_TRADING_DAYS = 20          # must have at least 20 trading days after entry
EGX30_TICKER     = "^EGX30"   # Yahoo Finance ticker for EGX30 index

TODAY        = date.today()
CUTOFF_DATE  = TODAY - timedelta(days=MIN_DAYS_OLD)


# ── EGX30 download ─────────────────────────────────────────────────────────────

def _download_egx30(earliest: date) -> "pd.DataFrame | None":
    """Downloads EGX30 OHLCV history starting LOOKBACK_DAYS before earliest signal."""
    try:
        dl_start = (earliest - timedelta(days=LOOKBACK_DAYS)).isoformat()
        dl_end   = (TODAY + timedelta(days=1)).isoformat()
        df = yf.Ticker(EGX30_TICKER).history(
            start=dl_start, end=dl_end, auto_adjust=True,
        )
        if df.empty:
            print(f"  [EGX30] No data for {EGX30_TICKER}")
            return None
        df.index = pd.to_datetime(df.index).tz_localize(None)
        print(f"  [EGX30] Downloaded {len(df)} bars for {EGX30_TICKER}")
        return df
    except Exception as exc:
        print(f"  [EGX30] Download failed: {exc}")
        return None


# ── Minimal signal insert ─────────────────────────────────────────────────────

def _insert_minimal_signal(conn: sqlite3.Connection, sig_id: str, symbol: str,
                            sig_date: str, signal_type: str, raw_score: int,
                            price: float, r1_price: "int | None" = None,
                            r2_ob: "int | None" = None,
                            r3_liquidity: "int | None" = None,
                            r4_htf: "int | None" = None,
                            r5_avwap: "int | None" = None,
                            r6_macd: "int | None" = None,
                            r7_div: "int | None" = None,
                            r8_demand: "int | None" = None):
    """Insert a minimal signals row, or update r-scores if already exists."""
    conn.execute("""
        INSERT INTO signals
          (id, symbol, signal_date, signal_type, raw_score,
           r1_price, r2_ob, r3_liquidity, r4_htf,
           r5_avwap, r6_macd, r7_div, r8_demand,
           price, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
          r1_price    = excluded.r1_price,
          r2_ob       = COALESCE(excluded.r2_ob,       signals.r2_ob),
          r3_liquidity= COALESCE(excluded.r3_liquidity, signals.r3_liquidity),
          r4_htf      = COALESCE(excluded.r4_htf,      signals.r4_htf),
          r5_avwap    = COALESCE(excluded.r5_avwap,    signals.r5_avwap),
          r6_macd     = COALESCE(excluded.r6_macd,     signals.r6_macd),
          r7_div      = COALESCE(excluded.r7_div,      signals.r7_div),
          r8_demand   = COALESCE(excluded.r8_demand,   signals.r8_demand)
    """, (sig_id, symbol, sig_date, signal_type, raw_score,
          r1_price, r2_ob, r3_liquidity, r4_htf,
          r5_avwap, r6_macd, r7_div, r8_demand,
          price, datetime.utcnow().isoformat()))


# ── Main backfill ─────────────────────────────────────────────────────────────

def run_backfill(db_path: str = DB_PATH, dry_run: bool = False):
    init_db(db_path)

    with open(SIGNAL_HISTORY, encoding="utf-8") as f:
        history: dict = json.load(f)

    # Collect eligible signals — only first Buy/Strong Buy/Early Buy after Wait
    BUY_SIGNALS = {"Buy", "Strong Buy", "Very Strong Buy", "Institutional Buy", "Early Buy"}
    eligible = []
    for symbol, entries in history.items():
        if not isinstance(entries, list):
            entries = [entries]
        entries_sorted = sorted(entries, key=lambda e: e.get("date", ""))

        prev_signal = "Wait"
        for entry in entries_sorted:
            sig_date = entry.get("date", "")
            signal   = entry.get("signal", "")
            is_buy      = signal in BUY_SIGNALS
            prev_is_buy = prev_signal in BUY_SIGNALS

            if is_buy and not prev_is_buy:
                try:
                    d = date.fromisoformat(sig_date)
                except ValueError:
                    prev_signal = signal
                    continue
                if d <= CUTOFF_DATE:
                    def _ri(key):
                        v = entry.get(key)
                        return int(v) if v is not None else None
                    eligible.append({
                        "id":           f"{symbol}_{sig_date}",
                        "symbol":       symbol,
                        "signal_date":  sig_date,
                        "signal_type":  signal,
                        "raw_score":    int(entry.get("score", 0)),
                        "price":        float(entry.get("price", 0)),
                        "r1_price":     _ri("r1"),
                        "r2_ob":        _ri("r2"),
                        "r3_liquidity": _ri("r3"),
                        "r4_htf":       _ri("r4"),
                        "r5_avwap":     _ri("r5"),
                        "r6_macd":      _ri("r6"),
                        "r7_div":       _ri("r7"),
                        "r8_demand":    _ri("r8"),
                    })

            prev_signal = signal

    print(f"Entry signals (first Buy after Wait, ≥{MIN_DAYS_OLD}d old): {len(eligible)}")

    conn = get_conn(db_path)
    existing_bq_ids = {
        r[0] for r in conn.execute("SELECT signal_id FROM bottom_quality").fetchall()
    }
    # Signals that already have features computed
    existing_feat_ids = {
        r[0] for r in conn.execute(
            "SELECT id FROM signals WHERE feat_dist_swing_low IS NOT NULL"
        ).fetchall()
    }
    conn.close()

    need_bq    = [s for s in eligible if s["id"] not in existing_bq_ids]
    need_r1upd = [s for s in eligible if s["id"] in existing_bq_ids]
    need_feat  = [s for s in eligible if s["id"] not in existing_feat_ids]

    print(f"Already have BQ: {len(existing_bq_ids)}  |  Need BQ: {len(need_bq)}")
    print(f"Missing features: {len(need_feat)}")
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
        print("  r1_price updated.")

    # All signals that need downloading (BQ or features)
    to_download = {s["id"]: s for s in need_bq + need_feat}
    if not to_download:
        print("Nothing to download.")
    else:
        # Download EGX30 once (for relative strength feature)
        all_dates = [date.fromisoformat(s["signal_date"]) for s in to_download.values()]
        earliest_all = min(all_dates)
        egx30_df = _download_egx30(earliest_all)

        # Group by symbol
        by_symbol: dict[str, list] = defaultdict(list)
        for sig in to_download.values():
            by_symbol[sig["symbol"]].append(sig)

        total_ok = total_skip = total_feat = total_err = 0

        for symbol, sigs in by_symbol.items():
            earliest = min(date.fromisoformat(s["signal_date"]) for s in sigs)
            dl_start = (earliest - timedelta(days=LOOKBACK_DAYS)).isoformat()
            dl_end   = (TODAY + timedelta(days=1)).isoformat()

            print(f"\n{symbol}: downloading {dl_start} → {dl_end} ({len(sigs)} signals)")

            try:
                df_raw = yf.Ticker(symbol).history(
                    start=dl_start, end=dl_end, auto_adjust=True,
                )
            except Exception as exc:
                print(f"  ERROR downloading {symbol}: {exc}")
                total_err += len(sigs)
                continue

            if df_raw.empty:
                print(f"  No data returned for {symbol}")
                total_skip += len(sigs)
                continue

            df_raw.index = pd.to_datetime(df_raw.index).tz_localize(None)
            need_bq_ids  = {s["id"] for s in need_bq}
            need_feat_ids = {s["id"] for s in need_feat}

            conn = get_conn(db_path)
            for sig in sigs:
                # ── BQ computation ──────────────────────────────────────────
                if sig["id"] in need_bq_ids:
                    bq = _compute_bq(sig, df_raw)
                    if bq is None:
                        print(f"  SKIP {sig['id']} — insufficient forward data")
                        total_skip += 1
                    else:
                        with conn:
                            _insert_minimal_signal(
                                conn,
                                sig_id       = sig["id"],
                                symbol       = sig["symbol"],
                                sig_date     = sig["signal_date"],
                                signal_type  = sig["signal_type"],
                                raw_score    = sig["raw_score"],
                                price        = sig["price"],
                                r1_price     = sig.get("r1_price"),
                                r2_ob        = sig.get("r2_ob"),
                                r3_liquidity = sig.get("r3_liquidity"),
                                r4_htf       = sig.get("r4_htf"),
                                r5_avwap     = sig.get("r5_avwap"),
                                r6_macd      = sig.get("r6_macd"),
                                r7_div       = sig.get("r7_div"),
                                r8_demand    = sig.get("r8_demand"),
                            )
                        upsert_bottom_quality(sig["id"], bq, db_path=db_path)
                        cls = bq.get("classification", "?")
                        mfe = bq.get("mfe_20d", 0)
                        bqs = bq.get("bq_score", 0)
                        print(f"  BQ  {sig['id']:30s}  mfe={mfe:+.1%}  bq={bqs:.0f}  [{cls}]")
                        total_ok += 1

                # ── Feature extraction ──────────────────────────────────────
                if sig["id"] in need_feat_ids:
                    try:
                        features = compute_entry_features(sig, df_raw, egx30_df)
                        if features:
                            upsert_signal_features(sig["id"], features, db_path=db_path)
                            total_feat += 1
                            print(f"  FEAT {sig['id'][:30]:30s}  "
                                  f"({len([v for v in features.values() if v is not None])} cols)")
                    except Exception as fe:
                        print(f"  feat_err {sig['id']}: {fe}")

            conn.close()

        print(f"\n{'─'*60}")
        print(f"BQ: Inserted={total_ok}  Skipped={total_skip}  Errors={total_err}")
        print(f"Features: Filled={total_feat}")

    # Quick summary from DB
    conn = get_conn(db_path)
    row = conn.execute("""
        SELECT COUNT(*),
               ROUND(AVG(bq_score),1),
               ROUND(AVG(mfe_20d)*100,1),
               ROUND(AVG(mae_20d)*100,1)
        FROM bottom_quality
    """).fetchone()
    feat_row = conn.execute(
        "SELECT COUNT(*) FROM signals WHERE feat_dist_swing_low IS NOT NULL"
    ).fetchone()
    conn.close()
    print(f"\nDB totals → bq_signals: {row[0]}  avg_bq: {row[1]}  "
          f"avg_mfe: {row[2]}%  avg_mae: {row[3]}%")
    print(f"Signals with features: {feat_row[0]}")


if __name__ == "__main__":
    dry = "--dry-run" in sys.argv
    db  = DB_PATH
    for a in sys.argv[1:]:
        if a.startswith("--db="):
            db = a[5:]
    run_backfill(db_path=db, dry_run=dry)
