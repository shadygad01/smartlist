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

_HERE          = os.path.dirname(os.path.abspath(__file__))
LOCAL_DATA_DIR = os.path.join(_HERE, "historical_data", "historical_data")


# ── Local CSV loader ──────────────────────────────────────────────────────────

def _load_local_ohlcv(symbol: str, start_date: "str | None" = None) -> "pd.DataFrame | None":
    """Load OHLCV from local historical_data/ CSV. Returns None if file not found."""
    csv_path = os.path.join(LOCAL_DATA_DIR, f"{symbol}.csv")
    if not os.path.exists(csv_path):
        return None
    try:
        df = pd.read_csv(csv_path, parse_dates=["Date"], index_col="Date")
        df.index = pd.to_datetime(df.index).tz_localize(None)
        df = df[["Open", "High", "Low", "Close", "Volume"]]
        if start_date:
            df = df[df.index >= pd.Timestamp(start_date)]
        print(f"  [local] {len(df)} bars from {os.path.basename(csv_path)}")
        return df
    except Exception as exc:
        print(f"  [local] Failed to load {csv_path}: {exc}")
        return None


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

            # Try local CSV first; fall back to yfinance
            df_raw = _load_local_ohlcv(symbol, start_date=dl_start)
            if df_raw is None:
                try:
                    df_raw = yf.Ticker(symbol).history(
                        start=dl_start, end=dl_end, auto_adjust=True,
                    )
                    if not df_raw.empty:
                        df_raw.index = pd.to_datetime(df_raw.index).tz_localize(None)
                except Exception as exc:
                    print(f"  ERROR downloading {symbol}: {exc}")
                    total_err += len(sigs)
                    continue

            if df_raw is None or df_raw.empty:
                print(f"  No data returned for {symbol}")
                total_skip += len(sigs)
                continue
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


def backfill_derived_features(db_path: str = DB_PATH):
    """
    يُحدّث الحقول المُشتقّة في جدول signals التي يمكن حسابها بعد التسجيل:
      1. discount_depth = 1 - snap_prem_disc (عمق منطقة الخصم)
      2. sv_hit / hvn_hit → NULL حيث = 0  (تحتاج volume profile غير متاح)
      3. rsi_div / macd_div → NULL حيث = 0 (تحتاج بيانات RSI/MACD تاريخية)
      4. htf_hh / htf_hl   → NULL حيث = 0 (تحتاج بيانات higher timeframe)
      5. price_ok = 1 لجميع الإشارات (كل إشارة مُسجَّلة اجتازت بوابة السعر)
      6. is_ramadan / is_cbe / stock_tier حيث NULL
    """
    from egx_context import is_ramadan, is_cbe_window

    STOCK_QUALITY = {
        "MCQE.CA": 1.15, "RAYA.CA": 1.15, "ORHD.CA": 1.15, "ARCC.CA": 1.15, "OIH.CA": 1.15,
        "ETEL.CA": 1.07, "PHDC.CA": 1.07, "CCAP.CA": 1.07, "EFID.CA": 1.07, "ISPH.CA": 1.07,
        "JUFO.CA": 0.88, "HRHO.CA": 0.88, "EAST.CA": 0.88, "EFIH.CA": 0.88,
    }

    conn = get_conn(db_path)

    # ── 1. discount_depth = 1 - snap_prem_disc ────────────────────────────────
    rows = conn.execute(
        "SELECT id, snap_prem_disc FROM signals "
        "WHERE discount_depth IS NULL AND snap_prem_disc IS NOT NULL"
    ).fetchall()
    if rows:
        with conn:
            for row in rows:
                depth = 1.0 - row[1]
                conn.execute(
                    "UPDATE signals SET discount_depth = ? WHERE id = ?",
                    (depth, row[0])
                )
        print(f"[derived] discount_depth computed for {len(rows)} signals")
    else:
        print("[derived] discount_depth: nothing to update")

    # ── 2-4. Binary flags: NULL only for uncomputed signals (r2_ob IS NULL)  ──
    # IMPORTANT: only touch signals that backfill_smc_scores() hasn't computed yet.
    # Once r2_ob is set by backfill_smc_scores(), sv_hit=0 is a valid computed value
    # (no stopping volume found), NOT a default placeholder — must not overwrite.
    with conn:
        conn.execute("UPDATE signals SET sv_hit  = NULL WHERE sv_hit  = 0 AND r2_ob IS NULL")
        conn.execute("UPDATE signals SET hvn_hit = NULL WHERE hvn_hit = 0 AND r2_ob IS NULL")
        conn.execute("UPDATE signals SET rsi_div = NULL WHERE rsi_div = 0 AND r2_ob IS NULL")
        conn.execute("UPDATE signals SET macd_div= NULL WHERE macd_div= 0 AND r2_ob IS NULL")
        conn.execute("UPDATE signals SET htf_hh  = NULL WHERE htf_hh  = 0 AND r2_ob IS NULL")
        conn.execute("UPDATE signals SET htf_hl  = NULL WHERE htf_hl  = 0 AND r2_ob IS NULL")
    print("[derived] binary flags → NULL (uncomputed signals only) done")

    # ── 5. price_ok = 1 for uncomputed signals (all logged signals passed price gate) ─
    with conn:
        conn.execute("UPDATE signals SET price_ok = 1 WHERE price_ok = 0 AND r2_ob IS NULL")
    print("[derived] price_ok = 1 for uncomputed signals done")

    # ── 6. is_ramadan / is_cbe / stock_tier where NULL ────────────────────────
    rows = conn.execute(
        "SELECT id, symbol, signal_date FROM signals "
        "WHERE is_ramadan IS NULL OR is_cbe IS NULL OR stock_tier IS NULL"
    ).fetchall()
    if rows:
        with conn:
            for row in rows:
                sig_id, symbol, sig_date_str = row[0], row[1], row[2]
                try:
                    d = date.fromisoformat(sig_date_str)
                except (ValueError, TypeError):
                    continue
                is_ram     = 1 if is_ramadan(d) else 0
                is_cbe_val = 1 if is_cbe_window(d) else 0
                tier       = STOCK_QUALITY.get(symbol, 1.0)
                conn.execute(
                    "UPDATE signals SET is_ramadan = ?, is_cbe = ?, stock_tier = ? "
                    "WHERE id = ? AND (is_ramadan IS NULL OR is_cbe IS NULL OR stock_tier IS NULL)",
                    (is_ram, is_cbe_val, tier, sig_id)
                )
        print(f"[derived] is_ramadan / is_cbe / stock_tier filled for {len(rows)} signals")
    else:
        print("[derived] is_ramadan / is_cbe / stock_tier: nothing to update")

    # ── 7. sector where NULL — from main.py SECTORS dict ─────────────────────
    from main import SECTORS
    rows = conn.execute(
        "SELECT id, symbol FROM signals WHERE sector IS NULL"
    ).fetchall()
    if rows:
        with conn:
            for sig_id, symbol in rows:
                sector_val = SECTORS.get(symbol)
                if sector_val:
                    conn.execute(
                        "UPDATE signals SET sector = ? WHERE id = ?",
                        (sector_val, sig_id)
                    )
        print(f"[derived] sector filled for {len(rows)} signals")
    else:
        print("[derived] sector: nothing to update")

    conn.close()


def backfill_gate_derived(db_path: str = DB_PATH):
    """
    يملأ القيم المضمونة رياضياً من منطق الـ gate في main.py دون الحاجة لـ OHLCV:

    1. r3_liquidity = 20  لكل إشارة Buy/Strong Buy/Very Strong Buy/Institutional Buy
       ← مضمون: الـ gate يشترط r3 == W_LIQ (20) لهذه الأنواع
    2. sweep_detected = 1  لنفس الإشارات (r3=20 يعني Sweep & Reverse مؤكد)
    3. equal_lows           من feat_equal_lows_count (نفس منطق sc_liquidity تماماً)

    لا يُعدِّل الإشارات التي سبق حسابها (r2_ob IS NOT NULL).
    """
    # Signal types guaranteed to have r3=20 by the gate (main.py line 1348)
    GATE_TYPES = ("'Buy'", "'Strong Buy'", "'Very Strong Buy'", "'Institutional Buy'")
    gate_in = ", ".join(GATE_TYPES)

    conn = get_conn(db_path)

    # ── 1 & 2. r3=20 و sweep_detected=1 لإشارات الـ gate ──────────────────────
    rows = conn.execute(f"""
        SELECT id FROM signals
        WHERE signal_type IN ({gate_in})
          AND r2_ob IS NULL
          AND (r3_liquidity IS NULL OR sweep_detected = 0)
    """).fetchall()
    if rows:
        with conn:
            conn.execute(f"""
                UPDATE signals
                SET r3_liquidity = 20, sweep_detected = 1
                WHERE signal_type IN ({gate_in})
                  AND r2_ob IS NULL
            """)
        print(f"[gate] r3_liquidity=20 + sweep_detected=1 لـ {len(rows)} إشارة")
    else:
        print("[gate] r3_liquidity / sweep_detected: nothing to update")

    # ── 3. equal_lows من feat_equal_lows_count (نفس منطق sc_liquidity: count >= 3)
    # sc_liquidity: "Equal Lows x{eql_count}" when eql_count >= 3, within 0.5%
    # feat_equal_lows_count: نفس المفهوم من feature_extractor
    # equal_lows = True فقط لما مفيش sweep ومفيش wick — يعني Early Buy فقط
    rows_eq = conn.execute("""
        SELECT id, feat_equal_lows_count
        FROM signals
        WHERE feat_equal_lows_count IS NOT NULL
          AND r2_ob IS NULL
          AND equal_lows = 0
    """).fetchall()
    if rows_eq:
        updates = [(1 if (cnt or 0) >= 3 else 0, sid) for sid, cnt in rows_eq]
        with conn:
            conn.executemany(
                "UPDATE signals SET equal_lows = ? WHERE id = ?",
                updates
            )
        filled = sum(1 for v, _ in updates if v == 1)
        print(f"[gate] equal_lows computed for {len(rows_eq)} signals ({filled} = True)")
    else:
        print("[gate] equal_lows: nothing to update")

    # Summary
    r3_filled  = conn.execute("SELECT COUNT(*) FROM signals WHERE r3_liquidity IS NOT NULL").fetchone()[0]
    swp_filled = conn.execute("SELECT COUNT(*) FROM signals WHERE sweep_detected = 1").fetchone()[0]
    eq_filled  = conn.execute("SELECT COUNT(*) FROM signals WHERE equal_lows = 1").fetchone()[0]
    print(f"[gate] حالة DB: r3_liquidity={r3_filled}/642  sweep=1: {swp_filled}/642  equal_lows=1: {eq_filled}/642")

    conn.close()


def backfill_smc_scores(db_path: str = DB_PATH):
    """
    يحسب r1-r8 والأعلام الثنائية (sv_hit, rsi_div, htf_hh, sweep_detected, ...)
    لكل إشارة تاريخية باستخدام نفس دوال التسجيل في main.py على بيانات OHLCV الفعلية.

    يُعالج فقط الإشارات التي r2_ob IS NULL (الإشارات التاريخية).
    الإشارات الحية (7 إشارات) لديها قيم صحيحة مُسجَّلة من الـ scanner — لا تُعدَّل.
    """
    # lazy import to avoid potential circular issues at module load time
    from main import (
        swings, sc_ob, sc_liquidity, sc_htf, sc_avwap,
        sc_macd, sc_div, sc_demand_zone, sc_price,
        calc_stopping_volume, calc_volume_profile,
        calc_macd, calc_avwap,
        PRICE_GATE_NORMAL, PRICE_GATE_WHITELIST, WHITELIST,
    )

    conn = get_conn(db_path)
    rows = conn.execute("""
        SELECT id, symbol, signal_date, price
        FROM signals
        WHERE r2_ob IS NULL
        ORDER BY symbol, signal_date
    """).fetchall()
    conn.close()

    if not rows:
        print("[smc_backfill] كل الإشارات لديها r2_ob — لا يوجد شيء لحسابه")
        return

    print(f"[smc_backfill] حساب SMC scores لـ {len(rows)} إشارة تاريخية...")

    # Group by symbol
    by_symbol: dict[str, list] = defaultdict(list)
    for row in rows:
        by_symbol[row[1]].append(row)

    total_ok = total_skip = total_err = 0

    for symbol, sigs in by_symbol.items():
        earliest = min(date.fromisoformat(s[2]) for s in sigs)
        # Download enough history: 150 days before earliest signal covers ~110 trading bars
        dl_start = (earliest - timedelta(days=200)).isoformat()
        dl_end   = (TODAY + timedelta(days=1)).isoformat()

        print(f"\n{symbol}: تنزيل {dl_start} → {dl_end}  ({len(sigs)} إشارة)")

        # Try local CSV first; fall back to yfinance
        df_raw = _load_local_ohlcv(symbol, start_date=dl_start)
        if df_raw is None:
            try:
                df_raw = yf.Ticker(symbol).history(
                    start=dl_start, end=dl_end, auto_adjust=True,
                )
                if not df_raw.empty:
                    df_raw.index = pd.to_datetime(df_raw.index).tz_localize(None)
            except Exception as exc:
                print(f"  ERROR تنزيل {symbol}: {exc}")
                total_err += len(sigs)
                continue

        if df_raw is None or df_raw.empty:
            print(f"  لا بيانات لـ {symbol}")
            total_skip += len(sigs)
            continue

        conn = get_conn(db_path)
        for sig_id, sym, sig_date_str, sig_price in sigs:
            sig_ts = pd.Timestamp(sig_date_str)

            # ── Slice: all bars up to and including signal date (same as analyze()) ──
            df_sig = df_raw[df_raw.index <= sig_ts].tail(110)

            if len(df_sig) < 20:
                print(f"  SKIP {sig_id} — فقط {len(df_sig)} بار")
                total_skip += 1
                continue

            try:
                close = df_sig["Close"]
                cur   = float(sig_price) if sig_price else float(close.iloc[-1])

                hi, lo, eq, buy_hi, sell_lo = swings(df_sig)
                av, alo                     = calc_avwap(df_sig)

                # ── Gate: price must be below EQ — same logic as analyze() ──────
                if cur >= eq:
                    r1, l1 = 0, "Premium Zone"
                    r2, l2 = 0, "Locked"
                    r3, l3 = 0, "Locked"
                    r4, l4 = 0, "Locked"
                    r5, l5 = 0, "Locked"
                    r6, l6 = 0, "Locked"
                    r7, l7 = 0, "Locked"
                    r8, l8 = 0, "Locked"
                    sv_result = hvn_result = macd_result = None
                else:
                    r1, l1 = sc_price(cur, lo, hi, eq, buy_hi, sell_lo)
                    r2, l2 = sc_ob(df_sig, cur, eq, lo, buy_hi)
                    r3, l3 = sc_liquidity(df_sig, cur)
                    r4, l4 = sc_htf(df_sig)
                    r5, l5 = sc_avwap(cur, av, alo)
                    macd_result = calc_macd(close)
                    ml          = macd_result[0]
                    r6, l6      = sc_macd(close, _macd=macd_result)
                    r7, l7      = sc_div(close, ml)
                    sv_result   = calc_stopping_volume(df_sig, eq, lo)
                    hvn_result  = calc_volume_profile(df_sig, eq, lo, buy_hi)
                    r8, l8      = sc_demand_zone(df_sig, eq, lo, buy_hi,
                                                  _sv=sv_result, _hvn=hvn_result)

                # ── Binary flags — exact same logic as main.py lines 1483-1496 ──
                rsi_div        = 1 if "RSI div"    in l7                        else 0
                macd_div       = 1 if "MACD div"   in l7                        else 0
                htf_hh         = 1 if ("HH+HL" in l4 or "HH:True" in l4)       else 0
                htf_hl         = 1 if ("HH+HL" in l4 or "HL:True" in l4)       else 0
                sweep_detected = 1 if "Sweep"      in l3                        else 0
                wick_rejection = 1 if "wick"        in l3.lower()               else 0
                equal_lows     = 1 if "Equal Lows" in l3                        else 0
                sv_hit         = 1 if (sv_result  and sv_result[0])             else 0
                hvn_hit        = 1 if (hvn_result and hvn_result[0])            else 0

                PRICE_GATE = PRICE_GATE_WHITELIST if sym in WHITELIST else PRICE_GATE_NORMAL
                price_ok   = 1 if r1 >= PRICE_GATE else 0

                sv_score  = round(float(sv_result[1]),  3) if sv_result  else 0.0
                hvn_score = round(float(hvn_result[1]), 3) if hvn_result else 0.0
                sv_depth  = (
                    round((eq - sv_result[3]) / max(eq - lo, 0.001), 4)
                    if sv_result and sv_result[0] else 0.0
                )

                with conn:
                    conn.execute("""
                        UPDATE signals SET
                            r1_price       = ?,
                            r2_ob          = ?,
                            r3_liquidity   = ?,
                            r4_htf         = ?,
                            r5_avwap       = ?,
                            r6_macd        = ?,
                            r7_div         = ?,
                            r8_demand      = ?,
                            sv_hit         = ?,
                            sv_score       = ?,
                            hvn_hit        = ?,
                            hvn_score      = ?,
                            rsi_div        = ?,
                            macd_div       = ?,
                            htf_hh         = ?,
                            htf_hl         = ?,
                            sweep_detected = ?,
                            wick_rejection = ?,
                            equal_lows     = ?,
                            price_ok       = ?,
                            sv_depth       = ?
                        WHERE id = ?
                    """, (r1, r2, r3, r4, r5, r6, r7, r8,
                          sv_hit, sv_score, hvn_hit, hvn_score,
                          rsi_div, macd_div, htf_hh, htf_hl,
                          sweep_detected, wick_rejection, equal_lows,
                          price_ok, sv_depth,
                          sig_id))

                total_ok += 1
                print(f"  OK  {sig_id[:28]:28s}  "
                      f"r1={r1:2d} r2={r2:2d} r3={r3:2d} r4={r4:2d} "
                      f"r5={r5:2d} r6={r6} r7={r7}  "
                      f"sv={sv_hit} hvn={hvn_hit} sweep={sweep_detected} "
                      f"wick={wick_rejection} eqlo={equal_lows}")

            except Exception as exc:
                print(f"  ERR {sig_id}: {exc}")
                total_err += 1

        conn.close()

    print(f"\n[smc_backfill] تمّ — تحديث={total_ok}  تخطّي={total_skip}  خطأ={total_err}")


def main(db_path: str = DB_PATH, dry_run: bool = False):
    run_backfill(db_path=db_path, dry_run=dry_run)
    if not dry_run:
        backfill_derived_features(db_path=db_path)
        backfill_gate_derived(db_path=db_path)
        backfill_smc_scores(db_path=db_path)
        backfill_binary_flags(db_path=db_path)


def backfill_binary_flags(db_path: str = DB_PATH):
    """
    يحسب البيانات الثنائية (sweep_detected, htf_hh/hl, sv_hit, hvn_hit, rsi_div, ...)
    لكل الإشارات من OHLCV الفعلية — بدون أي شرط على r2_ob.

    الفرق عن backfill_smc_scores():
      - يعالج كل الإشارات بغض النظر عن r2_ob (يشمل الـ 430 تاريخية)
      - يُحدِّث البيانات الثنائية فقط — لا يمس r1-r8 (الصحيحة من signal_history.json)
      - يستخدم CSVs المحلية أولاً
    """
    from main import (
        swings, sc_liquidity, sc_htf, sc_div, sc_price,
        calc_stopping_volume, calc_volume_profile,
        calc_macd, calc_avwap,
        PRICE_GATE_NORMAL, PRICE_GATE_WHITELIST, WHITELIST,
    )

    conn = get_conn(db_path)
    rows = conn.execute("""
        SELECT id, symbol, signal_date, price
        FROM signals
        ORDER BY symbol, signal_date
    """).fetchall()
    conn.close()

    print(f"[binary_flags] حساب binary flags لـ {len(rows)} إشارة من OHLCV فعلية...")

    by_symbol: dict[str, list] = defaultdict(list)
    for row in rows:
        by_symbol[row[1]].append(row)

    total_ok = total_skip = total_err = 0

    for symbol, sigs in by_symbol.items():
        earliest  = min(date.fromisoformat(s[2]) for s in sigs)
        dl_start  = (earliest - timedelta(days=200)).isoformat()
        dl_end    = (TODAY + timedelta(days=1)).isoformat()

        df_raw = _load_local_ohlcv(symbol, start_date=dl_start)
        if df_raw is None:
            try:
                df_raw = yf.Ticker(symbol).history(
                    start=dl_start, end=dl_end, auto_adjust=True,
                )
                if not df_raw.empty:
                    df_raw.index = pd.to_datetime(df_raw.index).tz_localize(None)
            except Exception as exc:
                print(f"  ERROR {symbol}: {exc}")
                total_err += len(sigs)
                continue

        if df_raw is None or df_raw.empty:
            print(f"  لا بيانات لـ {symbol}")
            total_skip += len(sigs)
            continue

        conn = get_conn(db_path)
        for sig_id, sym, sig_date_str, sig_price in sigs:
            sig_ts = pd.Timestamp(sig_date_str)
            df_sig = df_raw[df_raw.index <= sig_ts].tail(110)

            if len(df_sig) < 20:
                total_skip += 1
                continue

            try:
                close = df_sig["Close"]
                cur   = float(sig_price) if sig_price else float(close.iloc[-1])

                hi, lo, eq, buy_hi, sell_lo = swings(df_sig)
                av, alo                     = calc_avwap(df_sig)

                if cur >= eq:
                    sweep_detected = wick_rejection = equal_lows = 0
                    htf_hh = htf_hl = rsi_div = macd_div = 0
                    sv_hit = hvn_hit = 0
                    sv_score = hvn_score = sv_depth = 0.0
                    price_ok = 0
                    discount_depth = 0.0
                else:
                    r3, l3 = sc_liquidity(df_sig, cur)
                    r4, l4 = sc_htf(df_sig)
                    macd_result = calc_macd(close)
                    ml          = macd_result[0]
                    from main import sc_div as _sc_div
                    r7, l7      = _sc_div(close, ml)
                    sv_result   = calc_stopping_volume(df_sig, eq, lo)
                    hvn_result  = calc_volume_profile(df_sig, eq, lo, buy_hi)
                    r1, l1      = sc_price(cur, lo, hi, eq, buy_hi, sell_lo)

                    sweep_detected = 1 if "Sweep"      in l3                        else 0
                    wick_rejection = 1 if "wick"        in l3.lower()               else 0
                    equal_lows     = 1 if "Equal Lows" in l3                        else 0
                    htf_hh         = 1 if ("HH+HL" in l4 or "HH:True" in l4)       else 0
                    htf_hl         = 1 if ("HH+HL" in l4 or "HL:True" in l4)       else 0
                    rsi_div        = 1 if "RSI div"    in l7                        else 0
                    macd_div       = 1 if "MACD div"   in l7                        else 0
                    sv_hit         = 1 if (sv_result  and sv_result[0])             else 0
                    hvn_hit        = 1 if (hvn_result and hvn_result[0])            else 0
                    sv_score       = round(float(sv_result[1]),  3) if sv_result  else 0.0
                    hvn_score      = round(float(hvn_result[1]), 3) if hvn_result else 0.0
                    sv_depth       = (
                        round((eq - sv_result[3]) / max(eq - lo, 0.001), 4)
                        if sv_result and sv_result[0] else 0.0
                    )
                    PRICE_GATE    = PRICE_GATE_WHITELIST if sym in WHITELIST else PRICE_GATE_NORMAL
                    price_ok      = 1 if r1 >= PRICE_GATE else 0
                    discount_depth = round(
                        1.0 - (cur - lo) / max(eq - lo, 0.001), 4
                    )

                with conn:
                    conn.execute("""
                        UPDATE signals SET
                            sweep_detected = ?,
                            wick_rejection = ?,
                            equal_lows     = ?,
                            htf_hh         = ?,
                            htf_hl         = ?,
                            rsi_div        = ?,
                            macd_div       = ?,
                            sv_hit         = ?,
                            sv_score       = ?,
                            hvn_hit        = ?,
                            hvn_score      = ?,
                            sv_depth       = ?,
                            price_ok       = ?,
                            discount_depth = ?
                        WHERE id = ?
                    """, (sweep_detected, wick_rejection, equal_lows,
                          htf_hh, htf_hl, rsi_div, macd_div,
                          sv_hit, sv_score, hvn_hit, hvn_score,
                          sv_depth, price_ok, discount_depth,
                          sig_id))

                total_ok += 1
                if any([sweep_detected, htf_hh, htf_hl, hvn_hit, rsi_div, macd_div]):
                    print(f"  ✓ {sig_id[:32]:32s} "
                          f"sweep={sweep_detected} wick={wick_rejection} "
                          f"htf_hh={htf_hh} htf_hl={htf_hl} "
                          f"hvn={hvn_hit} rsi_div={rsi_div} macd_div={macd_div}")

            except Exception as exc:
                print(f"  ERR {sig_id}: {exc}")
                total_err += 1

        conn.close()
        print(f"  {symbol}: {len(sigs)} إشارة ✓")

    print(f"\n[binary_flags] تمّ — OK={total_ok}  تخطّي={total_skip}  خطأ={total_err}")

    # ملخص بعد التحديث
    conn = get_conn(db_path)
    row = conn.execute("""
        SELECT
            SUM(sweep_detected) as sweeps,
            SUM(htf_hh)         as hh,
            SUM(htf_hl)         as hl,
            SUM(hvn_hit)        as hvn,
            SUM(sv_hit)         as sv,
            SUM(rsi_div)        as rsi,
            SUM(macd_div)       as macd,
            COUNT(*)            as total
        FROM signals
    """).fetchone()
    conn.close()
    print(f"\nDB flags summary (n={row[7]}):")
    print(f"  sweep={row[0]}  htf_hh={row[1]}  htf_hl={row[2]}")
    print(f"  hvn={row[3]}  sv={row[4]}  rsi_div={row[5]}  macd_div={row[6]}")


if __name__ == "__main__":
    import sys as _sys
    # دعم تشغيل الدالة مباشرة: python backfill_research_db.py --flags-only
    if "--flags-only" in _sys.argv:
        db = DB_PATH
        for a in _sys.argv[1:]:
            if a.startswith("--db="):
                db = a[5:]
        backfill_binary_flags(db_path=db)
    else:
        dry = "--dry-run" in _sys.argv
        db  = DB_PATH
        for a in _sys.argv[1:]:
            if a.startswith("--db="):
                db = a[5:]
        main(db_path=db, dry_run=dry)

