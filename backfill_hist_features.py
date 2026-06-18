"""
Backfill Features for Historical Signals
==========================================
Computes snap_*, feat_*, bq_score, is_ramadan, sector for all 412 hist_signals.
Uses exact same engines as live scanner — no approximations.

Usage:
  python backfill_hist_features.py            # compute missing rows
  python backfill_hist_features.py --force    # recompute all rows
"""

import argparse
import os
import sqlite3
from datetime import date, timedelta

import numpy as np
import pandas as pd

from feature_extractor import compute_entry_features, FEAT_COLS_SCHEMA, SNAP_RECOMPUTE
from egx_context import is_ramadan as _is_ramadan
from main import SECTORS

DB_PATH   = "egx_research.db"
CSV_DIR   = "historical_data/historical_data"
MIN_TRADING_DAYS = 20   # same as daily_tracker


# ── New columns to add to hist_signals ───────────────────────────────────────

SNAP_COLS = {c: "REAL" for c in SNAP_RECOMPUTE}   # 13 snap_* cols

FEAT_COLS = FEAT_COLS_SCHEMA                        # 19 feat_* cols

BQ_COLS = {
    "bq_score":           "REAL",
    "bq_gain":            "REAL",
    "bq_drawdown":        "REAL",
    "bq_recovery":        "REAL",
    "bq_reversal":        "REAL",
    "bq_volume":          "REAL",
    "r1d":                "REAL",
    "r3d":                "REAL",
    "r5d":                "REAL",
    "r10d":               "REAL",
    "days_to_7pct":       "INTEGER",
    "r40d":               "REAL",
    "r60d":               "REAL",
    "mfe_40d":            "REAL",
    "mae_40d":            "REAL",
    "mfe_60d":            "REAL",
    "mae_60d":            "REAL",
    "days_to_peak":       "INTEGER",
    "days_to_trough":     "INTEGER",
    "classification":     "TEXT",
    "time_to_recovery":   "INTEGER",
    "drawdown_duration":  "INTEGER",
}

CTX_COLS = {
    "is_ramadan": "INTEGER",
    "sector":     "TEXT",
}

ALL_NEW_COLS = {**SNAP_COLS, **FEAT_COLS, **BQ_COLS, **CTX_COLS}


# ── Schema migration ──────────────────────────────────────────────────────────

def _migrate_schema(conn: sqlite3.Connection):
    existing = {row[1] for row in conn.execute("PRAGMA table_info(hist_signals)")}
    added = 0
    for col, typ in ALL_NEW_COLS.items():
        if col not in existing:
            conn.execute(f"ALTER TABLE hist_signals ADD COLUMN {col} {typ}")
            added += 1
    if added:
        conn.commit()
        print(f"  Added {added} new columns to hist_signals")
    else:
        print("  Schema already up to date")


# ── OHLCV loader ──────────────────────────────────────────────────────────────

_ohlcv_cache: dict[str, pd.DataFrame] = {}


def _load_ohlcv(symbol: str) -> pd.DataFrame | None:
    if symbol in _ohlcv_cache:
        return _ohlcv_cache[symbol]

    csv_path = os.path.join(CSV_DIR, f"{symbol}.csv")
    if not os.path.exists(csv_path):
        print(f"  [WARN] CSV not found: {csv_path}")
        return None

    try:
        df = pd.read_csv(csv_path, parse_dates=["Date"], index_col="Date")
        df.index = pd.to_datetime(df.index).tz_localize(None)
        df = df.sort_index()
        _ohlcv_cache[symbol] = df
        return df
    except Exception as e:
        print(f"  [ERROR] Loading {csv_path}: {e}")
        return None


# ── BQ computation (identical logic to daily_tracker._compute_bq) ─────────────

def _days_to_target(window: pd.DataFrame, entry_price: float, target_pct: float = 0.07) -> int | None:
    target = entry_price * (1 + target_pct)
    for i, (_, row) in enumerate(window.iterrows()):
        if row["High"] >= target:
            return i + 1
    return None


def _compute_bq(sig: dict, df: pd.DataFrame) -> dict | None:
    """
    Compute Bottom Quality Score using forward OHLCV.
    Identical logic to daily_tracker._compute_bq.
    """
    entry_price = float(sig.get("close_price", 0) or 0)
    if not entry_price:
        return None

    signal_date  = sig["signal_date"]
    start        = date.fromisoformat(signal_date) + timedelta(days=1)
    window_full  = df[df.index >= pd.Timestamp(start)]

    if len(window_full) < MIN_TRADING_DAYS:
        return None

    window  = window_full.iloc[:MIN_TRADING_DAYS]
    closes  = window["Close"].values
    highs   = window["High"].values
    lows    = window["Low"].values
    volumes = window["Volume"].values if "Volume" in window.columns else None

    mfe_20 = round((max(highs)  - entry_price) / entry_price, 4)
    mae_20 = round((min(lows)   - entry_price) / entry_price, 4)

    r1d  = round((closes[0]  - entry_price) / entry_price, 4) if len(closes) >= 1  else None
    r3d  = round((closes[2]  - entry_price) / entry_price, 4) if len(closes) >= 3  else None
    r5d  = round((closes[4]  - entry_price) / entry_price, 4) if len(closes) >= 5  else None
    r10d = round((closes[9]  - entry_price) / entry_price, 4) if len(closes) >= 10 else None

    r40d = mfe_40d = mae_40d = None
    if len(window_full) >= 40:
        w40     = window_full.iloc[:40]
        r40d    = round((float(w40["Close"].iloc[-1]) - entry_price) / entry_price, 4)
        mfe_40d = round((float(w40["High"].max()) - entry_price) / entry_price, 4)
        mae_40d = round((float(w40["Low"].min())  - entry_price) / entry_price, 4)

    r60d = mfe_60d = mae_60d = None
    if len(window_full) >= 60:
        w60     = window_full.iloc[:60]
        r60d    = round((float(w60["Close"].iloc[-1]) - entry_price) / entry_price, 4)
        mfe_60d = round((float(w60["High"].max()) - entry_price) / entry_price, 4)
        mae_60d = round((float(w60["Low"].min())  - entry_price) / entry_price, 4)

    all_highs      = window_full["High"].values
    all_lows       = window_full["Low"].values
    days_to_peak   = int(all_highs.argmax()) + 1
    days_to_trough = int(all_lows.argmin())  + 1

    trough_idx = int(all_lows.argmin())
    time_to_recovery = None
    for i in range(trough_idx, len(window_full)):
        if float(window_full["Close"].iloc[i]) >= entry_price:
            time_to_recovery = i + 1
            break

    drawdown_duration = 0
    for i in range(len(window_full)):
        if float(window_full["Close"].iloc[i]) < entry_price:
            drawdown_duration += 1
        else:
            break

    if   mfe_20 >= 0.20: classification = "Huge Winner"
    elif mfe_20 >= 0.08: classification = "Winner"
    elif mae_20 <= -0.15: classification = "Major Loser"
    elif mfe_20 >= 0.03 and mae_20 > -0.08: classification = "Neutral"
    else: classification = "Loser"

    # bq_gain (30 pts)
    if   mfe_20 >= 0.25: g = 30.0
    elif mfe_20 >= 0.15: g = 25.0 + (mfe_20 - 0.15) / 0.10 * 5.0
    elif mfe_20 >= 0.07: g = 15.0 + (mfe_20 - 0.07) / 0.08 * 10.0
    elif mfe_20 >  0.00: g = mfe_20 / 0.07 * 15.0
    else:                g = 0.0

    # bq_drawdown (25 pts)
    abs_mae = abs(mae_20)
    if   abs_mae <= 0.00: d = 25.0
    elif abs_mae <= 0.05: d = 25.0 - abs_mae / 0.05 * 10.0
    elif abs_mae <= 0.10: d = 15.0 - (abs_mae - 0.05) / 0.05 * 10.0
    elif abs_mae <= 0.15: d = 5.0  - (abs_mae - 0.10) / 0.05 * 5.0
    else:                 d = 0.0

    # bq_recovery (20 pts)
    days7 = _days_to_target(window, entry_price, 0.07)
    if   days7 is None: r = 0.0
    elif days7 <= 5:    r = 20.0
    elif days7 <= 10:   r = 15.0
    elif days7 <= 15:   r = 10.0
    else:               r = 5.0

    # bq_reversal (15 pts)
    half        = MIN_TRADING_DAYS // 2
    first_half  = float(closes[:half].mean())
    second_half = float(closes[half:].mean())
    reversal_pct = (second_half - first_half) / first_half if first_half > 0 else 0.0
    if   reversal_pct >= 0.10: rv = 15.0
    elif reversal_pct >= 0.05: rv = 10.0 + (reversal_pct - 0.05) / 0.05 * 5.0
    elif reversal_pct >= 0.00: rv = reversal_pct / 0.05 * 10.0
    else:                      rv = 0.0

    # bq_volume (10 pts)
    if volumes is not None and len(volumes) >= 2:
        up_days   = [volumes[i] for i in range(1, len(closes)) if closes[i] > closes[i-1]]
        down_days = [volumes[i] for i in range(1, len(closes)) if closes[i] < closes[i-1]]
        up_avg    = sum(up_days)   / max(len(up_days),   1)
        down_avg  = sum(down_days) / max(len(down_days), 1)
        vol_ratio = up_avg / max(down_avg, 1)
        if   vol_ratio >= 1.5: v = 10.0
        elif vol_ratio >= 1.0: v = (vol_ratio - 1.0) / 0.5 * 10.0
        else:                  v = 0.0
    else:
        v = 5.0

    return {
        "bq_score":           round(g + d + r + rv + v, 1),
        "bq_gain":            round(g,  2),
        "bq_drawdown":        round(d,  2),
        "bq_recovery":        round(r,  2),
        "bq_reversal":        round(rv, 2),
        "bq_volume":          round(v,  2),
        "r1d":                r1d,
        "r3d":                r3d,
        "r5d":                r5d,
        "r10d":               r10d,
        "days_to_7pct":       days7,
        "r40d":               r40d,
        "r60d":               r60d,
        "mfe_40d":            mfe_40d,
        "mae_40d":            mae_40d,
        "mfe_60d":            mfe_60d,
        "mae_60d":            mae_60d,
        "days_to_peak":       days_to_peak,
        "days_to_trough":     days_to_trough,
        "classification":     classification,
        "time_to_recovery":   time_to_recovery,
        "drawdown_duration":  drawdown_duration,
    }


# ── VIEW refresh ──────────────────────────────────────────────────────────────

# snap_* present in both tables (hist missing snap_bos_dist)
_SNAP_COMMON    = [c for c in SNAP_RECOMPUTE]   # 13 cols
_SNAP_LIVE_ONLY = ["snap_bos_dist"]             # live signals table only
_FEAT_LIST      = list(FEAT_COLS_SCHEMA.keys())  # 19 cols
_BQ_LIST        = list(BQ_COLS.keys())           # 22 cols
_CTX_LIST       = list(CTX_COLS.keys())          # 2 cols


def _refresh_view(conn: sqlite3.Connection):
    """Recreate v_all_signals: live feat_*/snap_* from signals, hist from hist_signals."""
    conn.execute("DROP VIEW IF EXISTS v_all_signals")

    live_bq   = ",\n    ".join(f"b.{c}"    for c in _BQ_LIST)
    live_snap = ",\n    ".join(f"s.{c}"    for c in _SNAP_COMMON)
    live_only = ",\n    ".join(f"s.{c}"    for c in _SNAP_LIVE_ONLY)
    live_feat = ",\n    ".join(f"s.{c}"    for c in _FEAT_LIST)
    live_ctx  = ",\n    ".join(f"s.{c}"    for c in _CTX_LIST)

    hist_bq   = ",\n    ".join(f"hs.{c}"   for c in _BQ_LIST)
    hist_snap = ",\n    ".join(f"hs.{c}"   for c in _SNAP_COMMON)
    hist_only = ",\n    ".join(f"NULL AS {c}" for c in _SNAP_LIVE_ONLY)
    hist_feat = ",\n    ".join(f"hs.{c}"   for c in _FEAT_LIST)
    hist_ctx  = ",\n    ".join(f"hs.{c}"   for c in _CTX_LIST)

    view_sql = f"""CREATE VIEW v_all_signals AS

SELECT
    s.id,
    s.symbol,
    s.signal_date,
    COALESCE(s.price, 0)          AS close_price,
    s.raw_score,
    COALESCE(s.adj_score, s.raw_score) AS adj_score,
    COALESCE(s.r1_price, 0)       AS r1_price,
    COALESCE(s.r2_ob, 0)          AS r2_ob,
    COALESCE(s.r3_liquidity, 0)   AS r3_liquidity,
    COALESCE(s.r4_htf, 0)         AS r4_htf,
    COALESCE(s.r5_avwap, 0)       AS r5_avwap,
    COALESCE(s.r6_macd, 0)        AS r6_macd,
    COALESCE(s.r7_div, 0)         AS r7_div,
    COALESCE(s.r8_demand, 0)      AS r8_demand,
    COALESCE(s.sweep_detected, 0) AS sweep_detected,
    COALESCE(s.wick_rejection, 0) AS wick_rejection,
    COALESCE(s.equal_lows, 0)     AS equal_lows,
    COALESCE(s.htf_hh, 0)         AS htf_hh,
    COALESCE(s.htf_hl, 0)         AS htf_hl,
    COALESCE(s.rsi_div, 0)        AS rsi_div,
    COALESCE(s.macd_div, 0)       AS macd_div,
    COALESCE(s.sv_hit, 0)         AS sv_hit,
    COALESCE(s.hvn_hit, 0)        AS hvn_hit,
    COALESCE(s.sv_score, 0)       AS sv_score,
    COALESCE(s.hvn_score, 0)      AS hvn_score,
    COALESCE(s.price_ok, 1)       AS price_ok,
    b.r20d,
    b.mfe_20d,
    b.mae_20d,
    'live' AS source,
    {live_bq},
    {live_snap},
    {live_only},
    {live_feat},
    {live_ctx}
FROM signals s
JOIN bottom_quality b ON b.signal_id = s.id
WHERE b.r20d IS NOT NULL

UNION ALL

SELECT
    -(hs.id)        AS id,
    hs.symbol,
    hs.signal_date,
    hs.close_price,
    hs.raw_score,
    hs.adj_score,
    hs.r1_price,
    hs.r2_ob,
    hs.r3_liquidity,
    hs.r4_htf,
    hs.r5_avwap,
    hs.r6_macd,
    hs.r7_div,
    hs.r8_demand,
    hs.sweep_detected,
    hs.wick_rejection,
    hs.equal_lows,
    hs.htf_hh,
    hs.htf_hl,
    hs.rsi_div,
    hs.macd_div,
    hs.sv_hit,
    hs.hvn_hit,
    hs.sv_score,
    hs.hvn_score,
    hs.price_ok,
    hs.r20d,
    hs.mfe_20d,
    hs.mae_20d,
    'historical' AS source,
    {hist_bq},
    {hist_snap},
    {hist_only},
    {hist_feat},
    {hist_ctx}
FROM hist_signals hs
WHERE hs.r20d IS NOT NULL
"""
    conn.execute(view_sql)
    conn.commit()
    print("  Refreshed v_all_signals VIEW with all feature columns")


# ── Main backfill loop ────────────────────────────────────────────────────────

def run(force: bool = False):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    print("\n=== Backfill Hist Features ===")
    _migrate_schema(conn)

    # Fetch rows to process
    if force:
        rows = conn.execute("SELECT * FROM hist_signals WHERE r20d IS NOT NULL").fetchall()
        print(f"  Force mode: processing all {len(rows)} hist_signals")
    else:
        rows = conn.execute(
            "SELECT * FROM hist_signals WHERE r20d IS NOT NULL AND bq_score IS NULL"
        ).fetchall()
        print(f"  Processing {len(rows)} hist_signals missing features")

    if not rows:
        print("  Nothing to do.")
        _refresh_view(conn)
        conn.close()
        return

    ok = skip = err = 0
    for row in rows:
        sig      = dict(row)
        symbol   = sig["symbol"]
        sig_date = sig["signal_date"]

        df = _load_ohlcv(symbol)
        if df is None:
            skip += 1
            continue

        # ── snap_* and feat_* (no look-ahead: uses pre = df[df.index <= sig_ts])
        feat_sig = {
            "signal_date": sig_date,
            "price":       float(sig["close_price"] or 0),
        }
        try:
            features = compute_entry_features(feat_sig, df)
        except Exception as e:
            print(f"  [ERROR] {symbol} {sig_date} features: {e}")
            err += 1
            continue

        # ── bq_score (forward-looking, but using historical future data — no bias)
        try:
            bq = _compute_bq(sig, df)
        except Exception as e:
            print(f"  [ERROR] {symbol} {sig_date} bq: {e}")
            bq = None

        # ── context
        try:
            sig_d = date.fromisoformat(sig_date)
            is_ram = int(_is_ramadan(sig_d))
        except Exception:
            is_ram = 0
        sector = SECTORS.get(symbol, "")

        # ── merge all into one UPDATE dict
        update = {}
        update.update(features)
        if bq:
            update.update(bq)
        update["is_ramadan"] = is_ram
        update["sector"]     = sector

        # Only update columns that exist in our new schema
        valid_cols = set(ALL_NEW_COLS.keys())
        update = {k: v for k, v in update.items() if k in valid_cols}

        if not update:
            skip += 1
            continue

        set_clause = ", ".join(f"{k} = :{k}" for k in update)
        update["_id"] = sig["id"]
        try:
            conn.execute(
                f"UPDATE hist_signals SET {set_clause} WHERE id = :_id",
                update,
            )
            ok += 1
        except Exception as e:
            print(f"  [ERROR] {symbol} {sig_date} UPDATE: {e}")
            err += 1

        if ok % 50 == 0 and ok > 0:
            conn.commit()
            print(f"  ... {ok} rows updated")

    conn.commit()
    print(f"\n  Done — updated: {ok} | skipped: {skip} | errors: {err}")

    # Validate a sample
    sample = conn.execute(
        "SELECT symbol, signal_date, bq_score, feat_dist_swing_low, snap_atr, sector "
        "FROM hist_signals WHERE bq_score IS NOT NULL LIMIT 3"
    ).fetchall()
    if sample:
        print("\n  Sample (3 rows):")
        for r in sample:
            print(f"    {dict(r)}")

    _refresh_view(conn)
    conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true", help="Recompute all rows")
    args = parser.parse_args()
    run(force=args.force)
