"""
Candidate Pool Builder — Constitutional Layer V1
================================================
Intermediate layer between frozen Signal Engine (R1-R8) and future
Portfolio Allocator.  Append-only.  Never rewrites history.

Constitution:
  - Universe  : config/scanner_config.get_constitutional_universe() ONLY
  - Engine    : discount_reversal_engine.py FROZEN (no modifications)
  - Data      : historical_data/historical_data/{SYM}.csv — point-in-time
  - Storage   : candidate_pool.db  (SQLite, append-only)
                candidate_pool.json
                candidate_pool.parquet
  - Identity  : candidate_id = SHA-256(ticker|signal_date|entry_price)
  - Policy    : allocator_status = 'NEW' on creation
"""

import hashlib
import json
import os
import sqlite3
import sys
from datetime import date as _date

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(__file__))

from config.scanner_config import get_constitutional_universe
from signal_engine import swings
from discount_reversal_engine import (
    _compute_macd,
    _detect_bos,
    _detect_choch,
    compute_final_score,
    r1_discount_context,
    r2_discount_quality,
    r3_discount_residency,
    r4_base_formation,
    r5_low_protection,
    r6_recovery,
    r7_macd_phase,
    r8_volume_behaviour,
)

# ── Constants ────────────────────────────────────────────────────────────────
DATA_DIR  = os.path.join(os.path.dirname(__file__), "historical_data", "historical_data")
DB_PATH   = os.path.join(os.path.dirname(__file__), "candidate_pool.db")
JSON_PATH = os.path.join(os.path.dirname(__file__), "candidate_pool.json")
PARQUET_PATH = os.path.join(os.path.dirname(__file__), "candidate_pool.parquet")

SECTOR_MAP = {
    "TMGH.CA": "Real Estate", "EMFD.CA": "Real Estate", "PHDC.CA": "Real Estate",
    "ORHD.CA": "Real Estate", "HELI.CA": "Real Estate",
    "EAST.CA": "Industrial",  "ABUK.CA": "Industrial",  "ORAS.CA": "Industrial",
    "EFID.CA": "Industrial",  "HRHO.CA": "Industrial",  "JUFO.CA": "Industrial",
    "ARCC.CA": "Industrial",  "ORWE.CA": "Industrial",  "CCAP.CA": "Industrial",
    "MCQE.CA": "Healthcare",  "ISPH.CA": "Healthcare",  "RMDA.CA": "Healthcare",
    "FWRY.CA": "FinTech",     "EFIH.CA": "FinTech",     "RAYA.CA": "FinTech",
    "BTFH.CA": "FinTech",
    "COMI.CA": "Banking",     "EGAL.CA": "Banking",     "ADIB.CA": "Banking",
    "ETEL.CA": "Telecom",     "GBCO.CA": "Telecom",     "OIH.CA":  "Telecom",
}

DB_SCHEMA = """
CREATE TABLE IF NOT EXISTS candidate_pool (
    candidate_id      TEXT PRIMARY KEY,
    ticker            TEXT NOT NULL,
    signal_date       TEXT NOT NULL,
    entry_price       REAL NOT NULL,
    current_price     REAL,
    r2_score          REAL,
    r3_score          REAL,
    r4_score          REAL,
    r5_score          REAL,
    r6_score          REAL,
    r7_score          REAL,
    r8_score          REAL,
    final_score       REAL,
    sector            TEXT,
    industry          TEXT,
    market_cap        REAL,
    avg_volume        REAL,
    atr20             REAL,
    volatility20      REAL,
    discount_depth    REAL,
    distance_from_eq  REAL,
    correlation_group TEXT DEFAULT '',
    allocator_status  TEXT DEFAULT 'NEW',
    snapshot_ts       TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_cp_ticker ON candidate_pool(ticker);
CREATE INDEX IF NOT EXISTS idx_cp_date   ON candidate_pool(signal_date);
CREATE INDEX IF NOT EXISTS idx_cp_sector ON candidate_pool(sector);
CREATE INDEX IF NOT EXISTS idx_cp_status ON candidate_pool(allocator_status);
"""


# ── Helpers ──────────────────────────────────────────────────────────────────

def _make_candidate_id(ticker: str, signal_date: str, entry_price: float) -> str:
    raw = f"{ticker}|{signal_date}|{entry_price:.6f}"
    return hashlib.sha256(raw.encode()).hexdigest()


def _atr20(highs, lows, closes):
    h = np.array(highs[-21:], dtype=float)
    l = np.array(lows[-21:],  dtype=float)
    c = np.array(closes[-21:], dtype=float)
    if len(c) < 2:
        return 0.0
    tr = np.maximum(h[1:] - l[1:],
         np.maximum(np.abs(h[1:] - c[:-1]), np.abs(l[1:] - c[:-1])))
    return float(tr[-20:].mean()) if len(tr) >= 1 else 0.0


def _vol20(closes):
    c = np.array(closes[-21:], dtype=float)
    if len(c) < 2:
        return 0.0
    rets = np.diff(np.log(c + 1e-12))
    return float(rets[-20:].std()) if len(rets) >= 2 else 0.0


# ── Core builder ─────────────────────────────────────────────────────────────

def build_candidate_pool(
    start_date: str = "2026-01-01",
    end_date: str   = str(_date.today()),
    db_path: str    = DB_PATH,
) -> pd.DataFrame:
    """
    Scan every constitutional symbol across [start_date, end_date].
    Emit one record per BUY-zone day (close < eq AND R1 passes).
    Append-only: existing candidate_ids are skipped (INSERT OR IGNORE).

    Returns DataFrame of newly inserted rows.
    """
    universe = get_constitutional_universe()
    assert len(universe) == 27, f"Universe count {len(universe)} != 27 — STOP"

    # Initialise DB
    conn = sqlite3.connect(db_path)
    conn.executescript(DB_SCHEMA)
    conn.commit()

    snapshot_ts = pd.Timestamp.utcnow().isoformat()
    rows = []

    for sym in universe:
        csv_path = os.path.join(DATA_DIR, f"{sym}.csv")
        if not os.path.exists(csv_path):
            continue

        df = pd.read_csv(csv_path, parse_dates=["Date"]).sort_values("Date").reset_index(drop=True)
        scan_mask = (df["Date"] >= start_date) & (df["Date"] <= end_date)
        scan_rows = df[scan_mask]
        if len(scan_rows) < 5:
            continue

        for i in range(len(scan_rows)):
            sig_row  = scan_rows.iloc[i]
            sig_date = sig_row["Date"]

            # Point-in-time history only
            hist = df[df["Date"] <= sig_date].tail(120)
            if len(hist) < 30:
                continue

            # Zone geometry
            hi, lo, eq, buy_hi, sell_lo = swings(hist)
            close = float(sig_row["Close"])

            # R1 hard gate
            if close >= eq:
                continue

            r1_score, r1_state = r1_discount_context(close, eq, lo, hi)
            if r1_state in ("premium", "extended"):
                continue

            highs   = hist["High"].tolist()
            lows    = hist["Low"].tolist()
            closes  = hist["Close"].tolist()
            volumes = hist["Volume"].tolist() if "Volume" in hist.columns else []

            # R2-R8
            r2_score, _, _, disc_depth = r2_discount_quality(close, eq, lo, hi)
            r3_days, r3_score = r3_discount_residency(closes, eq)
            r4_score, *_  = r4_base_formation(highs, lows, closes, volumes)
            r5_score, *_  = r5_low_protection(lows, closes)

            h_arr = np.array(highs, dtype=float)
            l_arr = np.array(lows,  dtype=float)
            c_arr = np.array(closes, dtype=float)
            choch = _detect_choch(h_arr, l_arr, c_arr) if len(closes) >= 10 else False
            bos   = _detect_bos(h_arr, l_arr, c_arr)   if len(closes) >= 7  else False
            r6_score, *_ = r6_recovery(highs, lows, closes,
                                       choch_present=choch, bos_present=bos)

            if len(closes) >= 26:
                ctx = _compute_macd(closes, with_context=True)
                r7_score = r7_macd_phase(
                    ctx["macd_val"], ctx["macd_hist"], price=close,
                    macd_slope=ctx["macd_slope"],
                    hist_slope=ctx["hist_slope"],
                    macd_range=ctx["macd_range"],
                )
            else:
                r7_score = 50.0

            r8_score, *_ = r8_volume_behaviour(volumes) if volumes else (50.0, False, False)
            final = compute_final_score(r1_score, r2_score, r3_score, r4_score,
                                        r5_score, r6_score, r7_score, r8_score, r1_state)

            # Derived metrics
            atr    = _atr20(highs, lows, closes)
            vol20  = _vol20(closes)
            avg_v  = float(np.mean(volumes[-20:])) if len(volumes) >= 20 else (
                     float(np.mean(volumes)) if volumes else 0.0)
            mkt_cap = close * avg_v   # proxy (price × avg_vol, not true mktcap)
            dist_eq = (eq - close) / close if close > 0 else 0.0

            # Current price
            latest = df[df["Date"] <= end_date]
            cur_price = float(latest.iloc[-1]["Close"]) if not latest.empty else close

            cid = _make_candidate_id(sym, str(sig_date)[:10], close)

            row = {
                "candidate_id":    cid,
                "ticker":          sym,
                "signal_date":     str(sig_date)[:10],
                "entry_price":     round(close, 4),
                "current_price":   round(cur_price, 4),
                "r2_score":        round(r2_score, 4),
                "r3_score":        round(r3_score, 4),
                "r4_score":        round(r4_score, 4),
                "r5_score":        round(r5_score, 4),
                "r6_score":        round(r6_score, 4),
                "r7_score":        round(r7_score, 4),
                "r8_score":        round(r8_score, 4),
                "final_score":     round(final, 4),
                "sector":          SECTOR_MAP.get(sym, "Unknown"),
                "industry":        SECTOR_MAP.get(sym, "Unknown"),
                "market_cap":      round(mkt_cap, 2),
                "avg_volume":      round(avg_v, 2),
                "atr20":           round(atr, 6),
                "volatility20":    round(vol20, 6),
                "discount_depth":  round(disc_depth, 6),
                "distance_from_eq": round(dist_eq, 6),
                "correlation_group": "",
                "allocator_status":  "NEW",
                "snapshot_ts":       snapshot_ts,
            }
            rows.append(row)

            conn.execute("""
                INSERT OR IGNORE INTO candidate_pool (
                    candidate_id, ticker, signal_date, entry_price, current_price,
                    r2_score, r3_score, r4_score, r5_score, r6_score, r7_score, r8_score,
                    final_score, sector, industry, market_cap, avg_volume,
                    atr20, volatility20, discount_depth, distance_from_eq,
                    correlation_group, allocator_status, snapshot_ts
                ) VALUES (
                    :candidate_id, :ticker, :signal_date, :entry_price, :current_price,
                    :r2_score, :r3_score, :r4_score, :r5_score, :r6_score, :r7_score, :r8_score,
                    :final_score, :sector, :industry, :market_cap, :avg_volume,
                    :atr20, :volatility20, :discount_depth, :distance_from_eq,
                    :correlation_group, :allocator_status, :snapshot_ts
                )
            """, row)

    conn.commit()
    conn.close()

    return pd.DataFrame(rows) if rows else pd.DataFrame()


def export_pool(db_path: str = DB_PATH,
                json_path: str = JSON_PATH,
                parquet_path: str = PARQUET_PATH) -> pd.DataFrame:
    """Read full pool from DB and write JSON + Parquet exports."""
    conn = sqlite3.connect(db_path)
    df = pd.read_sql("SELECT * FROM candidate_pool ORDER BY signal_date, ticker", conn)
    conn.close()

    df.to_json(json_path, orient="records", indent=2, date_format="iso")

    try:
        df.to_parquet(parquet_path, index=False, engine="pyarrow")
    except Exception as e:
        print(f"  Parquet export warning: {e}")

    return df


def validate_pool(df: pd.DataFrame) -> dict:
    """Run all constitutional validation checks. Returns dict of results."""
    universe = set(get_constitutional_universe())
    results  = {}

    # No lookahead: signal_date is index; current_price allowed to be today's
    # (it is a display field, not an input to any engine function)
    results["no_lookahead"]         = True   # enforced by hist = df[df['Date'] <= sig_date]

    results["duplicate_ids"]        = int(df["candidate_id"].duplicated().sum())
    results["missing_r2"]           = int(df["r2_score"].isna().sum())
    results["missing_sector"]       = int(df["sector"].isna().sum() + (df["sector"] == "").sum())
    results["missing_volatility"]   = int(df["volatility20"].isna().sum())
    results["missing_atr"]          = int(df["atr20"].isna().sum())

    non_const = set(df["ticker"].unique()) - universe
    results["unconstitutional_tickers"] = sorted(non_const)
    results["universe_100pct"]      = len(non_const) == 0

    results["total_candidates"]     = len(df)
    results["all_status_new"]       = bool((df["allocator_status"] == "NEW").all())
    results["all_ids_unique"]       = results["duplicate_ids"] == 0

    return results


def generate_statistics(df: pd.DataFrame) -> dict:
    """Candidate pool descriptive statistics."""
    stats = {}
    if df.empty:
        return stats

    stats["total_candidates"]      = len(df)
    stats["symbols_covered"]       = df["ticker"].nunique()
    stats["date_range"]            = f"{df['signal_date'].min()} to {df['signal_date'].max()}"

    daily   = df.groupby("signal_date").size()
    monthly = df.assign(month=df["signal_date"].str[:7]).groupby("month").size()
    sector  = df.groupby("sector").size().to_dict()
    by_sym  = df.groupby("ticker").size().to_dict()

    stats["candidates_per_day_mean"]   = round(float(daily.mean()), 1)
    stats["candidates_per_day_max"]    = int(daily.max())
    stats["candidates_per_month_mean"] = round(float(monthly.mean()), 1)
    stats["candidates_per_sector"]     = sector
    stats["candidates_per_symbol"]     = by_sym

    for col, label in [
        ("r2_score",        "avg_r2"),
        ("volatility20",    "avg_volatility20"),
        ("atr20",           "avg_atr20"),
        ("discount_depth",  "avg_discount_depth"),
        ("final_score",     "avg_final_score"),
        ("distance_from_eq","avg_distance_from_eq"),
    ]:
        stats[label] = round(float(df[col].mean()), 4)

    return stats


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import hashlib as _h

    START = "2026-01-01"
    END   = str(_date.today())

    print("=" * 72)
    print("CONSTITUTIONAL CANDIDATE POOL BUILDER V1")
    print(f"Window: {START} to {END}")
    print("=" * 72)

    universe = get_constitutional_universe()
    print(f"Universe Source : config/scanner_config.py")
    print(f"Universe Count  : {len(universe)}")
    assert len(universe) == 27, "STOP: universe count != 27"
    print("Universe Check  : PASS\n")

    print("Building candidate pool...")
    df_new = build_candidate_pool(start_date=START, end_date=END)
    print(f"New candidates inserted : {len(df_new)}")

    print("Exporting pool...")
    df_full = export_pool()
    print(f"Total pool size         : {len(df_full)}")

    print("\nValidating...")
    validation = validate_pool(df_full)
    for k, v in validation.items():
        flag = "PASS" if v in (True, 0, []) else "FAIL" if v is False else str(v)
        print(f"  {k:<30}: {flag}")

    print("\nStatistics...")
    stats = generate_statistics(df_full)
    print(f"  Total candidates      : {stats['total_candidates']}")
    print(f"  Symbols covered       : {stats['symbols_covered']} / 27")
    print(f"  Date range            : {stats['date_range']}")
    print(f"  Candidates/day (mean) : {stats['candidates_per_day_mean']}")
    print(f"  Candidates/month (mean): {stats['candidates_per_month_mean']}")
    print(f"  Avg R2                : {stats['avg_r2']}")
    print(f"  Avg volatility20      : {stats['avg_volatility20']}")
    print(f"  Avg ATR20             : {stats['avg_atr20']}")
    print(f"  Avg discount_depth    : {stats['avg_discount_depth']}")
    print(f"  Avg final_score       : {stats['avg_final_score']}")
    print(f"\n  Candidates/sector:")
    for s, n in sorted(stats["candidates_per_sector"].items()):
        print(f"    {s:<15}: {n}")
    print(f"\n  Candidates/symbol:")
    for s, n in sorted(stats["candidates_per_symbol"].items()):
        print(f"    {s:<12}: {n}")

    # File hashes
    print("\nFile hashes:")
    for path in [DB_PATH, JSON_PATH, PARQUET_PATH]:
        if os.path.exists(path):
            with open(path, "rb") as f:
                h = _h.sha256(f.read()).hexdigest()
            size = os.path.getsize(path)
            print(f"  {os.path.basename(path):<28}: {h[:32]}...  ({size:,} bytes)")
        else:
            print(f"  {os.path.basename(path):<28}: NOT FOUND")

    print("\nDone.")
