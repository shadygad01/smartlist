"""
Extend Long-Term Metrics
========================
Computes forward returns at 90d / 120d / 180d / 252d trading days
for all signals (hist + live) using local OHLCV CSV files.

Adds to hist_signals:  r_90d, mfe_90d, mae_90d ... up to r_252d
Adds to bottom_quality: same columns for live signals
Refreshes v_all_signals VIEW.

Usage:
  python extend_metrics.py           # compute missing rows
  python extend_metrics.py --force   # recompute all
"""

import argparse
import os
import sqlite3

import pandas as pd

DB_PATH = "egx_research.db"
CSV_DIR = "historical_data/historical_data"

WINDOWS = [90, 120, 180, 252]   # trading days

# columns to add per window
WINDOW_COLS = {}
for w in WINDOWS:
    WINDOW_COLS[f"r_{w}d"]   = "REAL"
    WINDOW_COLS[f"mfe_{w}d"] = "REAL"
    WINDOW_COLS[f"mae_{w}d"] = "REAL"

EXTRA_COLS = {
    "peak_return_1y":  "REAL",   # max return achievable within 252d
    "days_to_peak_1y": "INTEGER",
}

ALL_NEW = {**WINDOW_COLS, **EXTRA_COLS}

# ── OHLCV cache ───────────────────────────────────────────────────────────────

_cache: dict[str, pd.DataFrame] = {}


def _load(symbol: str) -> pd.DataFrame | None:
    if symbol in _cache:
        return _cache[symbol]
    path = os.path.join(CSV_DIR, f"{symbol}.csv")
    if not os.path.exists(path):
        return None
    df = pd.read_csv(path, parse_dates=["Date"], index_col="Date")
    df.index = pd.to_datetime(df.index).tz_localize(None)
    df = df.sort_index()
    _cache[symbol] = df
    return df


# ── Forward metric computation ────────────────────────────────────────────────

def _forward_metrics(symbol: str, signal_date: str, entry_price: float) -> dict:
    """
    Compute forward returns from CSV at each window.
    Returns dict of {r_90d, mfe_90d, mae_90d, ...}.
    All values are fractions (0.12 = 12%).
    """
    df = _load(symbol)
    if df is None or not entry_price:
        return {}

    fwd = df[df.index > pd.Timestamp(signal_date)]
    if fwd.empty:
        return {}

    result = {}
    n = len(fwd)

    for w in WINDOWS:
        if n < w:
            continue
        window = fwd.iloc[:w]
        r   = round((float(window["Close"].iloc[-1]) - entry_price) / entry_price, 4)
        mfe = round((float(window["High"].max())      - entry_price) / entry_price, 4)
        mae = round((float(window["Low"].min())       - entry_price) / entry_price, 4)
        result[f"r_{w}d"]   = r
        result[f"mfe_{w}d"] = mfe
        result[f"mae_{w}d"] = mae

    # peak within full 1-year window (up to 252 days)
    cap = fwd.iloc[:min(n, 252)]
    if len(cap) > 0:
        peak_idx = int(cap["High"].values.argmax())
        result["peak_return_1y"]  = round((float(cap["High"].max()) - entry_price) / entry_price, 4)
        result["days_to_peak_1y"] = peak_idx + 1

    return result


# ── Schema migration ──────────────────────────────────────────────────────────

def _migrate(conn: sqlite3.Connection, table: str):
    existing = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
    added = 0
    for col, typ in ALL_NEW.items():
        if col not in existing:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} {typ}")
            added += 1
    if added:
        conn.commit()
        print(f"  [{table}] Added {added} new columns")


# ── VIEW refresh ──────────────────────────────────────────────────────────────

def _refresh_view(conn: sqlite3.Connection):
    """Re-create v_all_signals including all extra columns from both tables."""
    # Dynamically discover columns from each table
    sig_cols  = [r[1] for r in conn.execute("PRAGMA table_info(signals)")]
    bq_cols   = [r[1] for r in conn.execute("PRAGMA table_info(bottom_quality)")]
    hist_cols = [r[1] for r in conn.execute("PRAGMA table_info(hist_signals)")]

    # Core fixed columns (always present)
    CORE_SIG = ["id", "symbol", "signal_date", "price", "raw_score", "adj_score",
                "r1_price", "r2_ob", "r3_liquidity", "r4_htf", "r5_avwap",
                "r6_macd", "r7_div", "r8_demand", "sweep_detected", "wick_rejection",
                "equal_lows", "htf_hh", "htf_hl", "rsi_div", "macd_div",
                "sv_hit", "hvn_hit", "sv_score", "hvn_score", "price_ok"]

    CORE_BQ  = ["r20d", "mfe_20d", "mae_20d"]

    CORE_HIST = ["id", "symbol", "signal_date", "close_price", "raw_score", "adj_score",
                 "r1_price", "r2_ob", "r3_liquidity", "r4_htf", "r5_avwap",
                 "r6_macd", "r7_div", "r8_demand", "sweep_detected", "wick_rejection",
                 "equal_lows", "htf_hh", "htf_hl", "rsi_div", "macd_div",
                 "sv_hit", "hvn_hit", "sv_score", "hvn_score", "price_ok",
                 "r20d", "mfe_20d", "mae_20d"]

    # Extra columns: everything in bq/hist beyond the core
    skip_bq   = set(CORE_BQ) | {"signal_id", "computed_at"}
    skip_hist = set(CORE_HIST) | {"created_at"}

    extra_bq   = [c for c in bq_cols   if c not in skip_bq]
    extra_hist = [c for c in hist_cols  if c not in skip_hist]

    # Union of all extra cols (same order for both sides)
    all_extra = []
    seen = set()
    for c in extra_bq + extra_hist:
        if c not in seen:
            all_extra.append(c)
            seen.add(c)

    # Build SELECT lists
    live_core = """    s.id,
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
    'live' AS source"""

    hist_core = """    -(hs.id)        AS id,
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
    'historical' AS source"""

    def _live_extra(col):
        if col in bq_cols:   return f"b.{col}"
        if col in sig_cols:  return f"s.{col}"
        return f"NULL AS {col}"

    def _hist_extra(col):
        if col in hist_cols: return f"hs.{col}"
        return f"NULL AS {col}"

    live_extra_sql = ",\n    ".join(_live_extra(c) for c in all_extra)
    hist_extra_sql = ",\n    ".join(_hist_extra(c) for c in all_extra)

    view_sql = f"""CREATE VIEW v_all_signals AS

SELECT
{live_core},
    {live_extra_sql}
FROM signals s
JOIN bottom_quality b ON b.signal_id = s.id
WHERE b.r20d IS NOT NULL

UNION ALL

SELECT
{hist_core},
    {hist_extra_sql}
FROM hist_signals hs
WHERE hs.r20d IS NOT NULL
"""
    conn.execute("DROP VIEW IF EXISTS v_all_signals")
    conn.execute(view_sql)
    conn.commit()
    n = conn.execute("SELECT COUNT(*) FROM v_all_signals").fetchone()[0]
    ncols = len(conn.execute("SELECT * FROM v_all_signals LIMIT 1").description)
    print(f"  v_all_signals rebuilt — {n} signals, {ncols} columns")


# ── Backfill hist_signals ─────────────────────────────────────────────────────

def _backfill_hist(conn: sqlite3.Connection, force: bool):
    if force:
        rows = conn.execute(
            "SELECT id, symbol, signal_date, close_price FROM hist_signals WHERE r20d IS NOT NULL"
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT id, symbol, signal_date, close_price FROM hist_signals "
            "WHERE r20d IS NOT NULL AND peak_return_1y IS NULL"
        ).fetchall()

    print(f"  [hist_signals] {len(rows)} rows to process")
    ok = skip = 0
    for row_id, symbol, sig_date, close_price in rows:
        metrics = _forward_metrics(symbol, sig_date, float(close_price or 0))
        if not metrics:
            skip += 1
            continue
        valid = {k: v for k, v in metrics.items() if k in ALL_NEW}
        if not valid:
            skip += 1
            continue
        set_clause = ", ".join(f"{k} = :{k}" for k in valid)
        valid["_id"] = row_id
        conn.execute(f"UPDATE hist_signals SET {set_clause} WHERE id = :_id", valid)
        ok += 1
        if ok % 100 == 0:
            conn.commit()
            print(f"    ... {ok} updated")
    conn.commit()
    print(f"  [hist_signals] done — ok={ok} skip={skip}")


# ── Backfill bottom_quality (live signals) ────────────────────────────────────

def _backfill_live(conn: sqlite3.Connection, force: bool):
    if force:
        rows = conn.execute("""
            SELECT bq.signal_id, s.symbol, s.signal_date,
                   COALESCE(s.price, 0) AS ep
            FROM bottom_quality bq
            JOIN signals s ON s.id = bq.signal_id
            WHERE bq.r20d IS NOT NULL
        """).fetchall()
    else:
        rows = conn.execute("""
            SELECT bq.signal_id, s.symbol, s.signal_date,
                   COALESCE(s.price, 0) AS ep
            FROM bottom_quality bq
            JOIN signals s ON s.id = bq.signal_id
            WHERE bq.r20d IS NOT NULL AND bq.peak_return_1y IS NULL
        """).fetchall()

    print(f"  [bottom_quality] {len(rows)} rows to process")
    ok = skip = 0
    for sig_id, symbol, sig_date, ep in rows:
        metrics = _forward_metrics(symbol, sig_date, float(ep or 0))
        if not metrics:
            skip += 1
            continue
        bq_cols = {r[1] for r in conn.execute("PRAGMA table_info(bottom_quality)")}
        valid = {k: v for k, v in metrics.items() if k in ALL_NEW and k in bq_cols}
        if not valid:
            skip += 1
            continue
        set_clause = ", ".join(f"{k} = :{k}" for k in valid)
        valid["_id"] = sig_id
        conn.execute(
            f"UPDATE bottom_quality SET {set_clause} WHERE signal_id = :_id",
            valid,
        )
        ok += 1
        if ok % 100 == 0:
            conn.commit()
            print(f"    ... {ok} updated")
    conn.commit()
    print(f"  [bottom_quality] done — ok={ok} skip={skip}")


# ── Summary ───────────────────────────────────────────────────────────────────

def _print_summary(conn: sqlite3.Connection):
    print("\n=== Long-term Metrics Summary ===")
    for w in WINDOWS:
        col = f"mfe_{w}d"
        row = conn.execute(f"""
            SELECT COUNT(*), AVG({col}), MAX({col})
            FROM v_all_signals WHERE {col} IS NOT NULL
        """).fetchone()
        if row and row[0]:
            print(f"  {w:3d}d: n={row[0]:4d}  avg_mfe={row[1]*100:5.1f}%  max_mfe={row[2]*100:5.1f}%")

    row = conn.execute(
        "SELECT COUNT(*), AVG(peak_return_1y), MAX(peak_return_1y) "
        "FROM v_all_signals WHERE peak_return_1y IS NOT NULL"
    ).fetchone()
    if row and row[0]:
        print(f"  Peak 1y: n={row[0]:4d}  avg={row[1]*100:5.1f}%  max={row[2]*100:5.1f}%")


# ── Main ──────────────────────────────────────────────────────────────────────

def run(force: bool = False):
    conn = sqlite3.connect(DB_PATH)
    print("\n=== Extend Long-Term Metrics ===")

    _migrate(conn, "hist_signals")
    _migrate(conn, "bottom_quality")

    _backfill_hist(conn, force)
    _backfill_live(conn, force)

    _refresh_view(conn)
    _print_summary(conn)
    conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    run(force=args.force)
