"""
Outcome Enricher
================
يُحدّث extended_signal_log.json بعد 20 يوم تداول:
  r5d, r10d, r20d  ← العائد بعد 5 / 10 / 20 يوم تداول فعلي
  mfe              ← أقصى ربح غير محقق خلال 20 يوم (High)
  mae              ← أقصى خسارة غير محققة خلال 20 يوم (Low)
  outcome/category ← flat / small / medium / large

التشغيل اليدوي:
    python outcome_enricher.py
"""

import json
import os
import sys
from datetime import date, timedelta

try:
    import yfinance as yf
    import pandas as pd
except ImportError:
    sys.exit("Run: pip install yfinance pandas")

EXTENDED_LOG  = "extended_signal_log.json"
MIN_DAYS_WAIT = 21   # انتظر ما يكفي لإتمام 20 يوم تداول فعلي


# ── حدود التصنيف ─────────────────────────────────────────────────────────────
def _categorize(ret: float) -> str:
    if ret >= 0.20: return "large"
    if ret >= 0.10: return "medium"
    if ret >= 0.04: return "small"
    return "flat"


# ── I/O ───────────────────────────────────────────────────────────────────────

def _load():
    if not os.path.exists(EXTENDED_LOG):
        print(f"[Enrich] File not found: {EXTENDED_LOG}")
        return None
    with open(EXTENDED_LOG, "r", encoding="utf-8") as f:
        return json.load(f)


def _save(data):
    with open(EXTENDED_LOG, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _days_since(signal_date_str: str) -> int:
    """أيام التقويم منذ تاريخ الإشارة."""
    try:
        return (date.today() - date.fromisoformat(signal_date_str)).days
    except Exception:
        return 0


def _fetch_forward(symbol: str, signal_date_str: str) -> pd.DataFrame | None:
    """
    يجلب بيانات OHLCV من اليوم التالي لـ signal_date حتى 40 يوم لاحق.
    يُرجع DataFrame بأيام التداول الفعلية، أو None عند الخطأ.
    """
    try:
        yf_sym = symbol if symbol.endswith(".CA") else f"{symbol}.CA"
        start  = (date.fromisoformat(signal_date_str) + timedelta(days=1)).isoformat()
        end    = (date.fromisoformat(signal_date_str) + timedelta(days=45)).isoformat()

        df = yf.Ticker(yf_sym).history(
            start=start, end=end,
            interval="1d", auto_adjust=False,
        )
        if df.empty:
            return None

        df = df[["High", "Low", "Close"]].dropna(subset=["Close"])
        df.index = df.index.tz_localize(None)
        return df.sort_index()

    except Exception as e:
        print(f"  [Enrich] {symbol}: fetch error — {e}")
        return None


# ── Main ──────────────────────────────────────────────────────────────────────

def enrich_outcomes(verbose: bool = True) -> int:
    """
    يعالج كل الإشارات pending في extended_signal_log.json.
    يُرجع عدد الإشارات المُحدَّثة.
    """
    data = _load()
    if data is None:
        return 0

    pending = [s for s in data["signals"] if s.get("outcome") == "pending"]

    if not pending:
        if verbose:
            print("[Enrich] No pending signals.")
        return 0

    if verbose:
        print(f"[Enrich] {len(pending)} pending signals found...")

    updated = skipped = 0

    for sig in pending:
        symbol      = sig["symbol"]
        signal_date = sig["date"]
        entry_price = sig.get("price_ctx", {}).get("price", 0)

        if entry_price <= 0:
            skipped += 1
            continue

        if _days_since(signal_date) < MIN_DAYS_WAIT:
            skipped += 1
            continue

        df = _fetch_forward(symbol, signal_date)
        if df is None or len(df) < 5:
            skipped += 1
            if verbose:
                print(f"  [skip] {symbol} ({signal_date}): insufficient data")
            continue

        # ── عائد عند 5 / 10 / 20 يوم تداول ──────────────────────────
        def ret_at(n):
            if len(df) >= n:
                return round((df["Close"].iloc[n - 1] - entry_price) / entry_price, 4)
            return None

        r5d  = ret_at(5)
        r10d = ret_at(10)
        r20d = ret_at(20)

        # ── MFE / MAE على نافذة 20 يوم ───────────────────────────────
        window = df.iloc[:min(20, len(df))]
        mfe = round((float(window["High"].max()) - entry_price) / entry_price, 4)
        mae = round((float(window["Low"].min())  - entry_price) / entry_price, 4)

        # ── تصنيف النتيجة (r20d أو r10d أو r5d كاحتياطي) ─────────────
        base_ret = next((x for x in (r20d, r10d, r5d) if x is not None), 0.0)
        category = _categorize(base_ret)
        outcome_date = df.index[min(19, len(df) - 1)].strftime("%Y-%m-%d")

        # ── تحديث السجل ───────────────────────────────────────────────
        sig.update({
            "outcome":      category,
            "outcome_date": outcome_date,
            "r5d":          r5d,
            "r10d":         r10d,
            "r20d":         r20d,
            "mfe":          mfe,
            "mae":          mae,
            "category":     category,
        })

        updated += 1
        if verbose:
            r_str = f"{base_ret * 100:+.1f}%" if base_ret is not None else "N/A"
            print(f"  ✓ {symbol:<10} {signal_date}  {category:<7}  "
                  f"r20d={r_str}  MFE={mfe*100:.1f}%  MAE={mae*100:.1f}%")

    if updated:
        _save(data)

    if verbose:
        print(f"\n[Enrich] Done — updated: {updated}, skipped: {skipped}")

    return updated


if __name__ == "__main__":
    enrich_outcomes(verbose=True)
