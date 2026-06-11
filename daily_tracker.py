"""
Daily Tracker
=============
يُتابع كل إشارة نشطة يومياً ويحسب Bottom Quality Score بعد 28 يوم.

التشغيل التلقائي: يُستدعى من main.py بعد _run_scan_workflow().
التشغيل اليدوي:  python daily_tracker.py
"""

import sys
from datetime import date, timedelta

try:
    import yfinance as yf
    import pandas as pd
except ImportError:
    sys.exit("Run: pip install yfinance pandas")

from signal_db import (
    DB_PATH, get_active_signals, get_signals_needing_bq,
    upsert_tracking, upsert_bottom_quality, get_tracking_history,
    init_db,
)

# ── كم يوم نُتابع إشارة قبل أن تُعتبر منتهية
MAX_TRACKING_DAYS = 60
# ── الحد الأدنى من أيام التداول لحساب BQ
MIN_TRADING_DAYS  = 20
# ── عدد أيام التقويم قبل بدء حساب BQ
MIN_CALENDAR_DAYS = 28


# ── Data Fetch ─────────────────────────────────────────────────────────────────

def _fetch_since(symbol: str, signal_date: str) -> pd.DataFrame | None:
    """
    يجلب OHLCV من اليوم التالي لـ signal_date حتى اليوم.
    يُرجع DataFrame مفهرس بالتاريخ، أو None عند الخطأ.
    """
    try:
        yf_sym = symbol if symbol.endswith(".CA") else f"{symbol}.CA"
        start  = (date.fromisoformat(signal_date) + timedelta(days=1)).isoformat()
        end    = (date.today() + timedelta(days=1)).isoformat()

        df = yf.Ticker(yf_sym).history(
            start=start, end=end,
            interval="1d", auto_adjust=False,
        )
        if df.empty:
            return None

        df = df[["High", "Low", "Close", "Volume"]].dropna(subset=["Close"])
        df.index = df.index.tz_localize(None)
        return df.sort_index()

    except Exception as e:
        print(f"  [Tracker] {symbol}: fetch error — {e}")
        return None


def _batch_fetch(symbols_dates: list[tuple]) -> dict:
    """
    يجلب بيانات لمجموعة من (symbol, signal_date).
    يُرجع dict: symbol → DataFrame (أطول نافذة = من أقدم إشارة).
    """
    # نجلب كل سهم مرة واحدة بأطول فترة ممكنة ثم نقطّع لكل إشارة
    from collections import defaultdict
    by_symbol = defaultdict(list)
    for sym, sdate in symbols_dates:
        by_symbol[sym].append(sdate)

    result = {}
    for sym, dates in by_symbol.items():
        earliest = min(dates)
        df = _fetch_since(sym, earliest)
        if df is not None:
            result[sym] = df
    return result


# ── Tracking Update ────────────────────────────────────────────────────────────

def _update_tracking(sig: dict, df: pd.DataFrame, db_path: str):
    """
    يُحدّث جدول tracking بآخر يوم تداول متاح في df.
    """
    entry_price = sig.get("price", 0)
    if not entry_price:
        return

    today_str  = str(date.today())
    signal_date = sig["signal_date"]

    # نافذة من اليوم التالي للإشارة حتى آخر بيانات متاحة
    start = date.fromisoformat(signal_date) + timedelta(days=1)
    window = df[df.index >= pd.Timestamp(start)]
    if window.empty:
        return

    latest       = window.iloc[-1]
    current_price = float(latest["Close"])
    days_since    = len(window)   # أيام تداول فعلية

    mfe = round((float(window["High"].max())  - entry_price) / entry_price, 4)
    mae = round((float(window["Low"].min())   - entry_price) / entry_price, 4)

    upsert_tracking(sig["id"], {
        "track_date":     today_str,
        "days_since":     days_since,
        "current_price":  current_price,
        "current_return": round((current_price - entry_price) / entry_price, 4),
        "mfe":            mfe,
        "mae":            mae,
        "highest_close":  round(float(window["Close"].max()), 4),
        "lowest_close":   round(float(window["Close"].min()), 4),
        "highest_high":   round(float(window["High"].max()),  4),
        "lowest_low":     round(float(window["Low"].min()),   4),
    }, db_path=db_path)


# ── Bottom Quality Score ───────────────────────────────────────────────────────

def _days_to_target(window: pd.DataFrame, entry_price: float, target_pct: float = 0.07) -> int | None:
    """عدد أيام التداول للوصول لـ target_pct% فوق entry_price."""
    target = entry_price * (1 + target_pct)
    for i, (_, row) in enumerate(window.iterrows()):
        if row["High"] >= target:
            return i + 1
    return None


def _compute_bq(sig: dict, df: pd.DataFrame) -> dict | None:
    """
    يحسب Bottom Quality Score (0-100) بعد 20 يوم تداول.

    المكونات:
      bq_gain      (30 pts) — MFE-based: كلما ارتفع السهم أكثر كان الـ bottom أفضل
      bq_drawdown  (25 pts) — MAE-based: كلما قلّ التراجع كان الـ bottom أفضل
      bq_recovery  (20 pts) — سرعة الوصول لـ +7% (أقل أيام = أفضل)
      bq_reversal  (15 pts) — النصف الثاني من الـ 20 يوم > النصف الأول
      bq_volume    (10 pts) — حجم التداول في أيام الصعود > أيام الهبوط
    """
    entry_price = sig.get("price", 0)
    if not entry_price:
        return None

    signal_date  = sig["signal_date"]
    start        = date.fromisoformat(signal_date) + timedelta(days=1)
    window_full  = df[df.index >= pd.Timestamp(start)]

    if len(window_full) < MIN_TRADING_DAYS:
        return None

    window = window_full.iloc[:MIN_TRADING_DAYS]   # أول 20 يوم تداول فقط

    closes  = window["Close"].values
    highs   = window["High"].values
    lows    = window["Low"].values
    volumes = window["Volume"].values if "Volume" in window.columns else None

    mfe_20 = round((max(highs)  - entry_price) / entry_price, 4)
    mae_20 = round((min(lows)   - entry_price) / entry_price, 4)

    r5d  = round((closes[4]  - entry_price) / entry_price, 4) if len(closes) >= 5  else None
    r10d = round((closes[9]  - entry_price) / entry_price, 4) if len(closes) >= 10 else None
    r20d = round((closes[19] - entry_price) / entry_price, 4) if len(closes) >= 20 else None

    # ── 1. Gain Score (30 pts) ────────────────────────────────────────────────
    # MFE: 0%→0, 7%→15, 15%→25, 25%+→30
    if   mfe_20 >= 0.25: g = 30.0
    elif mfe_20 >= 0.15: g = 25.0 + (mfe_20 - 0.15) / 0.10 * 5.0
    elif mfe_20 >= 0.07: g = 15.0 + (mfe_20 - 0.07) / 0.08 * 10.0
    elif mfe_20 >  0.00: g = mfe_20 / 0.07 * 15.0
    else:                g = 0.0

    # ── 2. Drawdown Score (25 pts) ────────────────────────────────────────────
    # MAE: 0%→25, -5%→15, -10%→5, -15%+→0
    abs_mae = abs(mae_20)
    if   abs_mae <= 0.00: d = 25.0
    elif abs_mae <= 0.05: d = 25.0 - abs_mae / 0.05 * 10.0
    elif abs_mae <= 0.10: d = 15.0 - (abs_mae - 0.05) / 0.05 * 10.0
    elif abs_mae <= 0.15: d = 5.0  - (abs_mae - 0.10) / 0.05 * 5.0
    else:                 d = 0.0

    # ── 3. Recovery Speed (20 pts) ────────────────────────────────────────────
    # أيام للوصول لـ +7%: 0 لم يصل→0, ≤5→20, ≤10→15, ≤15→10, ≤20→5
    days7 = _days_to_target(window, entry_price, 0.07)
    if   days7 is None:  r = 0.0
    elif days7 <= 5:     r = 20.0
    elif days7 <= 10:    r = 15.0
    elif days7 <= 15:    r = 10.0
    else:                r = 5.0

    # ── 4. Trend Reversal (15 pts) ────────────────────────────────────────────
    # متوسط النصف الثاني > النصف الأول → علامة انعكاس حقيقية
    half        = MIN_TRADING_DAYS // 2
    first_half  = float(closes[:half].mean())
    second_half = float(closes[half:].mean())
    if first_half > 0:
        reversal_pct = (second_half - first_half) / first_half
    else:
        reversal_pct = 0.0

    if   reversal_pct >= 0.10: rv = 15.0
    elif reversal_pct >= 0.05: rv = 10.0 + (reversal_pct - 0.05) / 0.05 * 5.0
    elif reversal_pct >= 0.00: rv = reversal_pct / 0.05 * 10.0
    else:                      rv = 0.0

    # ── 5. Volume Expansion (10 pts) ──────────────────────────────────────────
    # حجم أيام الصعود / حجم أيام الهبوط (نسبة ≥ 1.5 = كامل النقاط)
    if volumes is not None and len(volumes) >= 2:
        up_days   = [volumes[i] for i in range(1, len(closes)) if closes[i] > closes[i-1]]
        down_days = [volumes[i] for i in range(1, len(closes)) if closes[i] < closes[i-1]]
        up_avg   = sum(up_days)   / max(len(up_days),   1)
        down_avg = sum(down_days) / max(len(down_days), 1)
        vol_ratio = up_avg / max(down_avg, 1)
        if   vol_ratio >= 1.5: v = 10.0
        elif vol_ratio >= 1.0: v = (vol_ratio - 1.0) / 0.5 * 10.0
        else:                  v = 0.0
    else:
        v = 5.0   # قيمة افتراضية عند غياب بيانات الحجم

    bq_score = round(g + d + r + rv + v, 1)

    return {
        "bq_score":    bq_score,
        "bq_gain":     round(g,  2),
        "bq_drawdown": round(d,  2),
        "bq_recovery": round(r,  2),
        "bq_reversal": round(rv, 2),
        "bq_volume":   round(v,  2),
        "mfe_20d":     mfe_20,
        "mae_20d":     mae_20,
        "r5d":         r5d,
        "r10d":        r10d,
        "r20d":        r20d,
        "days_to_7pct": days7,
    }


# ── Main Entry Points ──────────────────────────────────────────────────────────

def run_daily_tracking(db_path: str = DB_PATH, verbose: bool = True) -> int:
    """
    يُحدّث tracking لكل الإشارات النشطة.
    يُستدعى يومياً بعد الـ scan أو بشكل مستقل.
    يُرجع عدد الإشارات التي جرى تحديثها.
    """
    init_db(db_path)
    signals = get_active_signals(max_days=MAX_TRACKING_DAYS, db_path=db_path)
    if not signals:
        if verbose:
            print("[Tracker] No active signals to track.")
        return 0

    pairs = [(s["symbol"], s["signal_date"]) for s in signals]
    if verbose:
        print(f"[Tracker] Fetching data for {len(set(s['symbol'] for s in signals))} symbols ...")

    data_map = _batch_fetch(pairs)
    updated  = 0

    for sig in signals:
        sym = sig["symbol"]
        df  = data_map.get(sym)
        if df is None:
            continue
        _update_tracking(sig, df, db_path=db_path)
        updated += 1

    if verbose:
        print(f"[Tracker] Tracking updated for {updated}/{len(signals)} signals.")
    return updated


def run_bq_scoring(db_path: str = DB_PATH, verbose: bool = True) -> int:
    """
    يحسب BQ Score للإشارات التي مرّ عليها MIN_CALENDAR_DAYS يوماً.
    يُستدعى بعد run_daily_tracking().
    يُرجع عدد الإشارات التي حُسب لها BQ Score.
    """
    signals = get_signals_needing_bq(min_days=MIN_CALENDAR_DAYS, db_path=db_path)
    if not signals:
        if verbose:
            print("[BQ] No signals ready for BQ scoring.")
        return 0

    if verbose:
        print(f"[BQ] Computing BQ scores for {len(signals)} signals ...")

    pairs    = [(s["symbol"], s["signal_date"]) for s in signals]
    data_map = _batch_fetch(pairs)
    scored   = 0

    for sig in signals:
        sym = sig["symbol"]
        df  = data_map.get(sym)
        if df is None:
            if verbose:
                print(f"  [BQ] {sym}: no data")
            continue

        bq = _compute_bq(sig, df)
        if bq is None:
            if verbose:
                print(f"  [BQ] {sym} ({sig['signal_date']}): insufficient trading days")
            continue

        upsert_bottom_quality(sig["id"], bq, db_path=db_path)
        scored += 1

        if verbose:
            bq_str = f"{bq['bq_score']:.1f}"
            r20    = f"{bq['r20d']*100:+.1f}%" if bq.get("r20d") is not None else "N/A"
            mfe    = f"{bq['mfe_20d']*100:.1f}%" if bq.get("mfe_20d") is not None else "N/A"
            print(f"  ✓ {sym:<10} {sig['signal_date']}  BQ={bq_str:<5}  "
                  f"r20d={r20}  MFE={mfe}")

    if verbose:
        print(f"[BQ] Done — scored {scored}/{len(signals)}")
    return scored


def run_all(db_path: str = DB_PATH, verbose: bool = True):
    """يُشغّل tracking + BQ scoring معاً."""
    run_daily_tracking(db_path=db_path, verbose=verbose)
    run_bq_scoring(db_path=db_path, verbose=verbose)


# ── CLI ────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser(description="EGX Research — Daily Tracker")
    p.add_argument("--bq-only",      action="store_true", help="BQ scoring only (no tracking fetch)")
    p.add_argument("--tracking-only", action="store_true", help="Tracking only (no BQ scoring)")
    p.add_argument("--db", default=DB_PATH, help=f"DB path (default: {DB_PATH})")
    args = p.parse_args()

    if args.bq_only:
        run_bq_scoring(db_path=args.db)
    elif args.tracking_only:
        run_daily_tracking(db_path=args.db)
    else:
        run_all(db_path=args.db)
