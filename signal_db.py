"""
Signal Database — SQLite
========================
قاعدة البيانات المركزية للنظام البحثي.
لا تمس منطق الماسح — تستقبل نتائجه وتحفظها.

الملف: egx_research.db
الجداول:
  signals        ← الإشارة الكاملة بكل متغيراتها
  tracking       ← متابعة سعرية يومية لكل إشارة
  bottom_quality ← تقييم جودة الـ Bottom بعد 20 يوم
  report_log     ← سجل التقارير المُرسَلة
"""

import sqlite3
import os
from datetime import date, datetime, timedelta

DB_PATH = "egx_research.db"

# الأوزان الحالية للماسح (للمقارنة في اقتراحات التعديل)
CURRENT_WEIGHTS = {
    "r1_price":    30,
    "r2_ob":       10,
    "r3_liquidity": 20,
    "r4_htf":      10,
    "r5_avwap":     8,
    "r6_macd":      4,
    "r7_div":       3,
    "r8_demand":   15,
}
WEIGHT_LABELS = {
    "r1_price":    "W_PRICE",
    "r2_ob":       "W_OB",
    "r3_liquidity":"W_LIQ",
    "r4_htf":      "W_HTF",
    "r5_avwap":    "W_AVWAP",
    "r6_macd":     "W_MACD",
    "r7_div":      "W_DIV",
    "r8_demand":   "W_DZ",
}


# ── Connection ─────────────────────────────────────────────────────────────────

def get_conn(db_path: str = DB_PATH) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


# ── Schema ─────────────────────────────────────────────────────────────────────

def _migrate_schema(conn: sqlite3.Connection):
    """يضيف الأعمدة الجديدة للجداول القائمة بدون فقدان البيانات."""
    existing = {r[1] for r in conn.execute("PRAGMA table_info(signals)").fetchall()}
    new_cols = {
        "sv_hit":        "INTEGER DEFAULT 0",
        "sv_score":      "REAL",
        "sv_price":      "REAL",
        "hvn_hit":       "INTEGER DEFAULT 0",
        "hvn_score":     "REAL",
        "hvn_price":     "REAL",
        "macd_val":      "REAL",
        "vol_spike":     "REAL",
        "rsi_val":       "REAL",
        "macd_hist":     "REAL",
        "macd_signal":   "REAL",
        "rsi_div":       "INTEGER DEFAULT 0",
        "macd_div":      "INTEGER DEFAULT 0",
        "ob_quality":    "REAL",
        "ob_dist":       "REAL",
        "htf_hh":        "INTEGER DEFAULT 0",
        "htf_hl":        "INTEGER DEFAULT 0",
        "avwap_gap":     "REAL",
        "sweep_detected":"INTEGER DEFAULT 0",
        "wick_rejection":"INTEGER DEFAULT 0",
        "equal_lows":    "INTEGER DEFAULT 0",
        "ctx_mult":      "REAL",
        "stock_mult":    "REAL",
        "price_gate":    "INTEGER",
        "price_ok":      "INTEGER DEFAULT 0",
        "sv_depth":      "REAL",
    }
    for col, defn in new_cols.items():
        if col not in existing:
            conn.execute(f"ALTER TABLE signals ADD COLUMN {col} {defn}")

    # Migrate signals — snapshot engine columns (Phase 3)
    snap_cols = {
        "snap_atr":         "REAL",
        "snap_wick_ratio":  "REAL",
        "snap_compression": "REAL",
        "snap_consol_len":  "INTEGER",
        "snap_bos":         "INTEGER DEFAULT 0",
        "snap_bos_dist":    "REAL",
        "snap_choch":       "INTEGER DEFAULT 0",
        "snap_pivot_str":   "REAL",
        "snap_num_touches": "INTEGER",
        "snap_sweep_size":  "REAL",
        "snap_vol_exp":     "REAL",
        "snap_reclaim_spd": "REAL",
        "snap_dist_lo":     "REAL",
        "snap_prem_disc":   "REAL",
    }
    for col, defn in snap_cols.items():
        if col not in existing:
            conn.execute(f"ALTER TABLE signals ADD COLUMN {col} {defn}")


    # Migrate bottom_quality table
    bq_existing = {r[1] for r in conn.execute("PRAGMA table_info(bottom_quality)").fetchall()}
    bq_new_cols = {
        "r1d":          "REAL",
        "r3d":          "REAL",
        "r40d":         "REAL",
        "r60d":         "REAL",
        "mfe_40d":      "REAL",
        "mfe_60d":      "REAL",
        "mae_40d":      "REAL",
        "mae_60d":      "REAL",
        "days_to_peak":   "INTEGER",
        "days_to_trough": "INTEGER",
        "classification": "TEXT",
    }
    for col, defn in bq_new_cols.items():
        if col not in bq_existing:
            conn.execute(f"ALTER TABLE bottom_quality ADD COLUMN {col} {defn}")


def init_db(db_path: str = DB_PATH):
    """ينشئ الجداول إن لم تكن موجودة."""
    conn = get_conn(db_path)
    with conn:
        conn.executescript("""

        CREATE TABLE IF NOT EXISTS signals (
            id              TEXT PRIMARY KEY,
            symbol          TEXT NOT NULL,
            signal_date     TEXT NOT NULL,
            signal_type     TEXT,

            raw_score       INTEGER,
            adj_score       INTEGER,

            r1_price        INTEGER,
            r2_ob           INTEGER,
            r3_liquidity    INTEGER,
            r4_htf          INTEGER,
            r5_avwap        INTEGER,
            r6_macd         INTEGER,
            r7_div          INTEGER,
            r8_demand       INTEGER,

            price           REAL,
            target          REAL,
            eq              REAL,
            buy_hi          REAL,
            sell_lo         REAL,
            avwap           REAL,
            avwap_lower     REAL,
            discount_depth  REAL,

            pattern_score   REAL,
            pattern_eff     REAL,
            pattern_wr      REAL,
            pattern_gain    REAL,
            pattern_n       INTEGER,

            ind_stoch_rsi   REAL,
            ind_p_vs_ma20   REAL,
            ind_mom_10d     REAL,
            ind_mom_5d      REAL,
            ind_atr_ratio   REAL,
            ind_vol_trend   REAL,

            is_ramadan      INTEGER,
            is_cbe          INTEGER,
            stock_tier      REAL,
            sector          TEXT,

            market_regime   TEXT,
            egx30_trend     TEXT,

            zone1           REAL,
            zone2           REAL,
            zone3           REAL,
            avg_entry       REAL,

            desc_price      TEXT,
            desc_liquidity  TEXT,
            desc_demand     TEXT,
            desc_ob         TEXT,
            desc_htf        TEXT,

            sv_hit          INTEGER,
            sv_score        REAL,
            sv_price        REAL,
            hvn_hit         INTEGER,
            hvn_score       REAL,
            hvn_price       REAL,
            macd_val        REAL,
            vol_spike       REAL,

            rsi_val         REAL,
            macd_hist       REAL,
            macd_signal     REAL,
            rsi_div         INTEGER DEFAULT 0,
            macd_div        INTEGER DEFAULT 0,
            ob_quality      REAL,
            ob_dist         REAL,
            htf_hh          INTEGER DEFAULT 0,
            htf_hl          INTEGER DEFAULT 0,
            avwap_gap       REAL,
            sweep_detected  INTEGER DEFAULT 0,
            wick_rejection  INTEGER DEFAULT 0,
            equal_lows      INTEGER DEFAULT 0,
            ctx_mult        REAL,
            stock_mult      REAL,
            price_gate      INTEGER,
            price_ok        INTEGER DEFAULT 0,
            sv_depth        REAL,

            created_at      TEXT
        );

        CREATE INDEX IF NOT EXISTS idx_sig_date   ON signals(signal_date);
        CREATE INDEX IF NOT EXISTS idx_sig_symbol ON signals(symbol);

        CREATE TABLE IF NOT EXISTS tracking (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            signal_id       TEXT    NOT NULL,
            track_date      TEXT    NOT NULL,
            days_since      INTEGER,
            current_price   REAL,
            current_return  REAL,
            mfe             REAL,
            mae             REAL,
            highest_close   REAL,
            lowest_close    REAL,
            highest_high    REAL,
            lowest_low      REAL,
            UNIQUE(signal_id, track_date),
            FOREIGN KEY(signal_id) REFERENCES signals(id)
        );

        CREATE INDEX IF NOT EXISTS idx_trk_signal ON tracking(signal_id);

        CREATE TABLE IF NOT EXISTS bottom_quality (
            signal_id       TEXT PRIMARY KEY,
            bq_score        REAL,
            bq_gain         REAL,
            bq_drawdown     REAL,
            bq_recovery     REAL,
            bq_reversal     REAL,
            bq_volume       REAL,
            mfe_20d         REAL,
            mae_20d         REAL,
            r1d             REAL,
            r3d             REAL,
            r5d             REAL,
            r10d            REAL,
            r20d            REAL,
            days_to_7pct    INTEGER,
            r40d            REAL,
            r60d            REAL,
            mfe_40d         REAL,
            mfe_60d         REAL,
            mae_40d         REAL,
            mae_60d         REAL,
            days_to_peak    INTEGER,
            days_to_trough  INTEGER,
            classification  TEXT,
            computed_at     TEXT,
            FOREIGN KEY(signal_id) REFERENCES signals(id)
        );

        CREATE TABLE IF NOT EXISTS report_log (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            report_type     TEXT,
            sent_at         TEXT,
            signals_covered INTEGER
        );

        """)
    # executescript() does an implicit COMMIT, so _migrate_schema runs
    # outside that transaction — each ALTER TABLE commits independently (correct).
    _migrate_schema(conn)
    conn.close()


# ── Helpers ────────────────────────────────────────────────────────────────────

def _parse_rows(rows: list) -> dict:
    """استخراج r1-r8 وأوصافها من rows list اللي يُرجعها analyze()."""
    key_map = {
        "Price Position":      ("r1_price",    "desc_price"),
        "Order Block Quality": ("r2_ob",        "desc_ob"),
        "Liquidity Context":   ("r3_liquidity", "desc_liquidity"),
        "Higher Timeframe":    ("r4_htf",        "desc_htf"),
        "Anchored VWAP":       ("r5_avwap",      None),
        "MACD vs Zero":        ("r6_macd",       None),
        "Divergence":          ("r7_div",         None),
        "Demand Zone (SV+VP)": ("r8_demand",     "desc_demand"),
    }
    out = {}
    for row in rows:
        name, score, _mx, desc = row
        if name in key_map:
            sk, dk = key_map[name]
            out[sk] = score
            if dk:
                out[dk] = str(desc)[:300]
    return out


def _discount_depth(price: float, eq: float, buy_hi: float) -> float:
    """نسبة عمق السعر في Discount Zone: 0=عند EQ, 1=عند Swing Low."""
    try:
        lo = eq - (eq - buy_hi) / 0.70
        d  = eq - lo
        return round(max(0.0, min(1.0, (eq - price) / d)), 4) if d > 0 else 0.0
    except Exception:
        return 0.0


def _market_context(results: dict) -> tuple:
    """
    يحسب market_regime و egx30_trend من نتائج الـ scan الحالي
    بدون أي تحميل بيانات إضافي.
    """
    htf_vals, disc_count, total = [], 0, 0
    for r in results.values():
        if not r.get("ok"):
            continue
        total += 1
        for row in r.get("rows", []):
            if row[0] == "Higher Timeframe":
                htf_vals.append(row[1])
        if r.get("price", 0) < r.get("eq", 9999):
            disc_count += 1

    avg_htf = sum(htf_vals) / len(htf_vals) if htf_vals else 0
    egx30_trend = "uptrend" if avg_htf >= 7 else ("sideways" if avg_htf >= 4 else "downtrend")

    if total > 0:
        pct = disc_count / total
        market_regime = "bearish" if pct >= 0.60 else ("neutral" if pct >= 0.35 else "bullish")
    else:
        market_regime = "unknown"

    return market_regime, egx30_trend


# ── Write Operations ───────────────────────────────────────────────────────────

def log_signals(results: dict, sectors: dict, stock_quality: dict,
                is_ramadan: bool, is_cbe: bool,
                db_path: str = DB_PATH) -> int:
    """
    يُسجّل إشارات اليوم في قاعدة البيانات.
    يُستدعى مرة واحدة في نهاية _run_scan_workflow().
    يُرجع عدد الإشارات الجديدة.
    """
    init_db(db_path)
    today  = str(date.today())
    mr, et = _market_context(results)

    conn  = get_conn(db_path)
    added = 0

    with conn:
        for symbol, r in results.items():
            if not r.get("ok"):
                continue

            raw = r.get("raw_score", r.get("score", 0))
            if raw < 35:
                continue

            sig_id = f"{symbol}_{today}"
            if conn.execute("SELECT 1 FROM signals WHERE id=?", (sig_id,)).fetchone():
                continue

            price  = float(r.get("price",   0) or 0)
            eq     = float(r.get("eq",      0) or 0)
            buy_hi = float(r.get("buy_hi",  0) or 0)

            p   = _parse_rows(r.get("rows", []))
            pat = r.get("pattern") or {}
            ind = pat.get("detail", {})
            ez  = r.get("entry_zones")

            conn.execute("""
                INSERT OR IGNORE INTO signals (
                    id, symbol, signal_date, signal_type,
                    raw_score, adj_score,
                    r1_price, r2_ob, r3_liquidity, r4_htf,
                    r5_avwap, r6_macd, r7_div, r8_demand,
                    price, target, eq, buy_hi, sell_lo,
                    avwap, avwap_lower, discount_depth,
                    pattern_score, pattern_eff, pattern_wr,
                    pattern_gain, pattern_n,
                    ind_stoch_rsi, ind_p_vs_ma20, ind_mom_10d,
                    ind_mom_5d, ind_atr_ratio, ind_vol_trend,
                    is_ramadan, is_cbe, stock_tier, sector,
                    market_regime, egx30_trend,
                    zone1, zone2, zone3, avg_entry,
                    desc_price, desc_liquidity, desc_demand,
                    desc_ob, desc_htf,
                    sv_hit, sv_score, sv_price,
                    hvn_hit, hvn_score, hvn_price,
                    macd_val, vol_spike,
                    rsi_val, macd_hist, macd_signal,
                    rsi_div, macd_div,
                    ob_quality, ob_dist,
                    htf_hh, htf_hl, avwap_gap,
                    sweep_detected, wick_rejection, equal_lows,
                    ctx_mult, stock_mult, price_gate, price_ok, sv_depth,
                    snap_atr, snap_wick_ratio, snap_compression, snap_consol_len,
                    snap_bos, snap_bos_dist, snap_choch, snap_pivot_str,
                    snap_num_touches, snap_sweep_size, snap_vol_exp,
                    snap_reclaim_spd, snap_dist_lo, snap_prem_disc,
                    created_at
                ) VALUES (
                    :id, :symbol, :signal_date, :signal_type,
                    :raw_score, :adj_score,
                    :r1, :r2, :r3, :r4, :r5, :r6, :r7, :r8,
                    :price, :target, :eq, :buy_hi, :sell_lo,
                    :avwap, :avwap_lower, :disc_depth,
                    :ps, :pe, :pwr, :pg, :pn,
                    :i_sr, :i_ma20, :i_m10, :i_m5, :i_atr, :i_vt,
                    :ram, :cbe, :tier, :sector,
                    :mr, :et,
                    :z1, :z2, :z3, :ze,
                    :dp, :dl, :dd, :dob, :dhtf,
                    :sv_hit, :sv_score, :sv_price,
                    :hvn_hit, :hvn_score, :hvn_price,
                    :macd_val, :vol_spike,
                    :rsi_val, :macd_hist, :macd_signal,
                    :rsi_div, :macd_div,
                    :ob_quality, :ob_dist,
                    :htf_hh, :htf_hl, :avwap_gap,
                    :sweep_detected, :wick_rejection, :equal_lows,
                    :ctx_mult, :stock_mult, :price_gate, :price_ok, :sv_depth,
                    :snap_atr, :snap_wick_ratio, :snap_compression, :snap_consol_len,
                    :snap_bos, :snap_bos_dist, :snap_choch, :snap_pivot_str,
                    :snap_num_touches, :snap_sweep_size, :snap_vol_exp,
                    :snap_reclaim_spd, :snap_dist_lo, :snap_prem_disc,
                    :now
                )
            """, {
                "id": sig_id, "symbol": symbol,
                "signal_date": today, "signal_type": r.get("signal", ""),
                "raw_score": raw, "adj_score": r.get("score", 0),
                "r1": p.get("r1_price"),    "r2": p.get("r2_ob"),
                "r3": p.get("r3_liquidity"),"r4": p.get("r4_htf"),
                "r5": p.get("r5_avwap"),    "r6": p.get("r6_macd"),
                "r7": p.get("r7_div"),      "r8": p.get("r8_demand"),
                "price": price,
                "target": float(r.get("target", 0) or 0),
                "eq": eq, "buy_hi": buy_hi,
                "sell_lo": float(r.get("sell_lo", 0) or 0),
                "avwap": float(r.get("avwap", 0) or 0),
                "avwap_lower": float(r.get("avwap_l", 0) or 0),
                "disc_depth": _discount_depth(price, eq, buy_hi),
                "ps": pat.get("pattern_score", 0),
                "pe": pat.get("effective_score", 0),
                "pwr": pat.get("win_rate", 0),
                "pg": pat.get("avg_gain", 0),
                "pn": pat.get("similar_count", 0),
                "i_sr":  ind.get("stoch_rsi"),
                "i_ma20":ind.get("p_vs_ma20"),
                "i_m10": ind.get("mom_10d"),
                "i_m5":  ind.get("mom_5d"),
                "i_atr": ind.get("atr_ratio"),
                "i_vt":  ind.get("vol_trend"),
                "ram": int(is_ramadan), "cbe": int(is_cbe),
                "tier": stock_quality.get(symbol, 1.0),
                "sector": sectors.get(symbol, ""),
                "mr": mr, "et": et,
                "z1": ez["z1"]["center"] if ez else None,
                "z2": ez["z2"]["center"] if ez else None,
                "z3": ez["z3"]["center"] if ez else None,
                "ze": ez["avg_entry"]    if ez else None,
                "dp":   p.get("desc_price"),
                "dl":   p.get("desc_liquidity"),
                "dd":   p.get("desc_demand"),
                "dob":  p.get("desc_ob"),
                "dhtf": p.get("desc_htf"),
                "sv_hit":        int(r.get("sv_hit",  False) or False),
                "sv_score":      r.get("sv_score", 0.0),
                "sv_price":      r.get("sv_price"),
                "hvn_hit":       int(r.get("hvn_hit", False) or False),
                "hvn_score":     r.get("hvn_score", 0.0),
                "hvn_price":     r.get("hvn_price"),
                "macd_val":      r.get("macd_val"),
                "vol_spike":     r.get("vol_spike"),
                "rsi_val":       r.get("rsi_val"),
                "macd_hist":     r.get("macd_hist"),
                "macd_signal":   r.get("macd_signal"),
                "rsi_div":       int(bool(r.get("rsi_div",       False))),
                "macd_div":      int(bool(r.get("macd_div",      False))),
                "ob_quality":    r.get("ob_quality"),
                "ob_dist":       r.get("ob_dist"),
                "htf_hh":        int(bool(r.get("htf_hh",        False))),
                "htf_hl":        int(bool(r.get("htf_hl",        False))),
                "avwap_gap":     r.get("avwap_gap"),
                "sweep_detected":int(bool(r.get("sweep_detected",False))),
                "wick_rejection":int(bool(r.get("wick_rejection",False))),
                "equal_lows":    int(bool(r.get("equal_lows",    False))),
                "ctx_mult":      r.get("ctx_mult"),
                "stock_mult":    r.get("stock_mult"),
                "price_gate":    r.get("price_gate"),
                "price_ok":      int(bool(r.get("price_ok",      False))),
                "sv_depth":      r.get("sv_depth"),
                "snap_atr":         r.get("snap_atr"),
                "snap_wick_ratio":  r.get("snap_wick_ratio"),
                "snap_compression": r.get("snap_compression"),
                "snap_consol_len":  r.get("snap_consol_len"),
                "snap_bos":         int(bool(r.get("snap_bos", 0))),
                "snap_bos_dist":    r.get("snap_bos_dist"),
                "snap_choch":       int(bool(r.get("snap_choch", 0))),
                "snap_pivot_str":   r.get("snap_pivot_str"),
                "snap_num_touches": r.get("snap_num_touches"),
                "snap_sweep_size":  r.get("snap_sweep_size"),
                "snap_vol_exp":     r.get("snap_vol_exp"),
                "snap_reclaim_spd": r.get("snap_reclaim_spd"),
                "snap_dist_lo":     r.get("snap_dist_lo"),
                "snap_prem_disc":   r.get("snap_prem_disc"),
                "now":           datetime.now().isoformat(),
            })
            added += 1

    conn.close()
    if added:
        print(f"  [DB] +{added} signal(s) → {db_path}")
    return added


def upsert_tracking(signal_id: str, data: dict, db_path: str = DB_PATH):
    conn = get_conn(db_path)
    with conn:
        conn.execute("""
            INSERT OR REPLACE INTO tracking
            (signal_id, track_date, days_since, current_price, current_return,
             mfe, mae, highest_close, lowest_close, highest_high, lowest_low)
            VALUES (:sid, :dt, :days, :cp, :ret,
                    :mfe, :mae, :hc, :lc, :hh, :ll)
        """, {
            "sid": signal_id, "dt": data["track_date"],
            "days": data.get("days_since"),
            "cp":  data.get("current_price"),
            "ret": data.get("current_return"),
            "mfe": data.get("mfe"), "mae": data.get("mae"),
            "hc":  data.get("highest_close"), "lc": data.get("lowest_close"),
            "hh":  data.get("highest_high"),  "ll": data.get("lowest_low"),
        })
    conn.close()


def upsert_bottom_quality(signal_id: str, bq: dict, db_path: str = DB_PATH):
    conn = get_conn(db_path)
    with conn:
        conn.execute("""
            INSERT INTO bottom_quality
            (signal_id, bq_score, bq_gain, bq_drawdown, bq_recovery,
             bq_reversal, bq_volume, mfe_20d, mae_20d,
             r1d, r3d, r5d, r10d, r20d, days_to_7pct,
             r40d, r60d, mfe_40d, mfe_60d, mae_40d, mae_60d,
             days_to_peak, days_to_trough, classification, computed_at)
            VALUES
            (:sid, :bq, :g, :d, :r, :rv, :v,
             :mfe, :mae,
             :r1, :r3, :r5, :r10, :r20, :days,
             :r40, :r60, :mfe40, :mfe60, :mae40, :mae60,
             :dtp, :dtt, :cls, :now)
            ON CONFLICT(signal_id) DO UPDATE SET
              bq_score      = excluded.bq_score,
              bq_gain       = excluded.bq_gain,
              bq_drawdown   = excluded.bq_drawdown,
              bq_recovery   = excluded.bq_recovery,
              bq_reversal   = excluded.bq_reversal,
              bq_volume     = excluded.bq_volume,
              mfe_20d       = excluded.mfe_20d,
              mae_20d       = excluded.mae_20d,
              r1d           = excluded.r1d,
              r3d           = excluded.r3d,
              r5d           = excluded.r5d,
              r10d          = excluded.r10d,
              r20d          = excluded.r20d,
              days_to_7pct  = excluded.days_to_7pct,
              r40d          = COALESCE(excluded.r40d,    r40d),
              r60d          = COALESCE(excluded.r60d,    r60d),
              mfe_40d       = COALESCE(excluded.mfe_40d, mfe_40d),
              mfe_60d       = COALESCE(excluded.mfe_60d, mfe_60d),
              mae_40d       = COALESCE(excluded.mae_40d, mae_40d),
              mae_60d       = COALESCE(excluded.mae_60d, mae_60d),
              days_to_peak   = excluded.days_to_peak,
              days_to_trough = excluded.days_to_trough,
              classification = excluded.classification,
              computed_at   = excluded.computed_at
        """, {
            "sid": signal_id,
            "bq":  bq.get("bq_score"),    "g":   bq.get("bq_gain"),
            "d":   bq.get("bq_drawdown"), "r":   bq.get("bq_recovery"),
            "rv":  bq.get("bq_reversal"), "v":   bq.get("bq_volume"),
            "mfe": bq.get("mfe_20d"),     "mae": bq.get("mae_20d"),
            "r1":  bq.get("r1d"),         "r3":  bq.get("r3d"),
            "r5":  bq.get("r5d"),         "r10": bq.get("r10d"),
            "r20": bq.get("r20d"),
            "days": bq.get("days_to_7pct"),
            "r40":  bq.get("r40d"),       "r60":  bq.get("r60d"),
            "mfe40": bq.get("mfe_40d"),   "mfe60": bq.get("mfe_60d"),
            "mae40": bq.get("mae_40d"),   "mae60": bq.get("mae_60d"),
            "dtp":  bq.get("days_to_peak"),
            "dtt":  bq.get("days_to_trough"),
            "cls":  bq.get("classification"),
            "now":  datetime.now().isoformat(),
        })
    conn.close()


def log_report_sent(report_type: str, n_signals: int, db_path: str = DB_PATH):
    conn = get_conn(db_path)
    with conn:
        conn.execute(
            "INSERT INTO report_log (report_type, sent_at, signals_covered) VALUES (?,?,?)",
            (report_type, datetime.now().isoformat(), n_signals),
        )
    conn.close()


# ── Read Operations ────────────────────────────────────────────────────────────

def get_active_signals(max_days: int = 60, db_path: str = DB_PATH) -> list:
    """إشارات تحتاج متابعة يومية (أقل من max_days يوماً)."""
    init_db(db_path)
    cutoff = (date.today() - timedelta(days=max_days)).isoformat()
    conn = get_conn(db_path)
    rows = conn.execute(
        "SELECT * FROM signals WHERE signal_date >= ? ORDER BY signal_date",
        (cutoff,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_signals_needing_bq(min_days: int = 28, db_path: str = DB_PATH) -> list:
    """إشارات مرّ عليها min_days يوماً ولم يُحسَب لها BQ Score بعد."""
    init_db(db_path)
    cutoff = (date.today() - timedelta(days=min_days)).isoformat()
    conn   = get_conn(db_path)
    rows   = conn.execute("""
        SELECT s.*
        FROM signals s
        LEFT JOIN bottom_quality b ON s.id = b.signal_id
        WHERE s.signal_date <= :cutoff
          AND b.signal_id IS NULL
        ORDER BY s.signal_date
    """, {"cutoff": cutoff}).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_mature_signals(db_path: str = DB_PATH) -> list:
    """إشارات محسومة (مع BQ Score) — للتحليل والـ ML."""
    init_db(db_path)
    conn = get_conn(db_path)
    rows = conn.execute("""
        SELECT s.*, b.bq_score, b.bq_gain, b.bq_drawdown,
               b.bq_recovery, b.bq_reversal, b.bq_volume,
               b.mfe_20d, b.mae_20d,
               b.r1d, b.r3d, b.r5d, b.r10d, b.r20d, b.days_to_7pct,
               b.r40d, b.r60d, b.mfe_40d, b.mfe_60d, b.mae_40d, b.mae_60d,
               b.days_to_peak, b.days_to_trough, b.classification
        FROM signals s
        JOIN bottom_quality b ON s.id = b.signal_id
        ORDER BY s.signal_date
    """).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_signals_for_bq_update(db_path: str = DB_PATH) -> list:
    """
    إشارات لديها BQ لكن تحتاج تحديث للمقاييس الموسّعة (r40d أو r60d).
    تُستدعى من run_bq_scoring() بعد الحسابات الأولية.
    """
    init_db(db_path)
    cutoff_40d = (date.today() - timedelta(days=56)).isoformat()
    cutoff_60d = (date.today() - timedelta(days=84)).isoformat()
    conn = get_conn(db_path)
    rows = conn.execute("""
        SELECT s.*
        FROM signals s
        JOIN bottom_quality b ON s.id = b.signal_id
        WHERE (b.r40d IS NULL AND s.signal_date <= :c40)
           OR (b.r60d IS NULL AND s.signal_date <= :c60)
        ORDER BY s.signal_date
    """, {"c40": cutoff_40d, "c60": cutoff_60d}).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_tracking_history(signal_id: str, db_path: str = DB_PATH) -> list:
    conn = get_conn(db_path)
    rows = conn.execute(
        "SELECT * FROM tracking WHERE signal_id=? ORDER BY track_date",
        (signal_id,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_last_report_date(report_type: str, db_path: str = DB_PATH) -> str | None:
    init_db(db_path)
    conn = get_conn(db_path)
    row  = conn.execute(
        "SELECT MAX(sent_at) FROM report_log WHERE report_type=?",
        (report_type,)
    ).fetchone()
    conn.close()
    return row[0] if row and row[0] else None


def get_stats(db_path: str = DB_PATH) -> dict:
    init_db(db_path)
    conn = get_conn(db_path)
    stats = {
        "total_signals":    conn.execute("SELECT COUNT(*) FROM signals").fetchone()[0],
        "with_bq":          conn.execute("SELECT COUNT(*) FROM bottom_quality").fetchone()[0],
        "tracking_records": conn.execute("SELECT COUNT(*) FROM tracking").fetchone()[0],
        "first_date":       conn.execute("SELECT MIN(signal_date) FROM signals").fetchone()[0],
        "last_date":        conn.execute("SELECT MAX(signal_date) FROM signals").fetchone()[0],
    }
    conn.close()
    return stats
