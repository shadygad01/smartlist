"""
Historical Signal Backfill
===========================
يملأ signal_log.json ببيانات تاريخية حقيقية من آخر 500 يوم لكل سهم.

المنهجية:
  - لكل سهم: يجيب 500 يوم من Yahoo Finance
  - يرصد كل لحظة كان فيها السعر عند قاع محلي (local low)
  - يستخرج قيم المؤشرات الستة وقتها
  - يحسب النتيجة الفعلية بعد 15 يوم (win / loss / neutral)
  - يسجل الكل في signal_log.json

الفرق عن السجل العادي:
  - النتائج معروفة مسبقاً (تاريخية) → لا انتظار 15 يوم
  - يشمل الإشارات الناجحة والفاشلة على حد سواء → توازن حقيقي
  - يُعطي النظام قاعدة تعلم فورية بدل الانتظار 3 أشهر
"""

import json
import os
import sys
import time
import numpy as np
import pandas as pd
import yfinance as yf
import requests
from datetime import date, timedelta

# ── استيراد المؤشرات من pattern_engine ────────────────────────────────────────
from pattern_engine import (
    _extract, _stoch_rsi, _atr, _rsi_series,
    FORWARD_DAYS
)

MIN_GAIN  = 0.07   # target gain for signal outcome evaluation
STOP_LOSS = 0.06   # stop loss for signal outcome evaluation

LOG_FILE = "signal_log.json"
LOCAL_CSV_DIR = "historical_data/historical_data"

STOCKS = [
    "COMI.CA", "TMGH.CA", "ETEL.CA", "EGAL.CA",
    "EAST.CA", "ABUK.CA", "ORAS.CA", "EFIH.CA",
    "ADIB.CA", "FWRY.CA", "EMFD.CA", "PHDC.CA",
    "ORHD.CA", "EFID.CA", "HRHO.CA", "JUFO.CA",
    "BTFH.CA", "RAYA.CA", "GBCO.CA", "HELI.CA",
    "ARCC.CA", "MCQE.CA", "ORWE.CA", "ISPH.CA",
    "RMDA.CA", "OIH.CA",  "CCAP.CA",
]

HEADERS = {"User-Agent": "Mozilla/5.0"}


# ── تحميل البيانات ────────────────────────────────────────────────────────────

def _download(symbol, period="2y"):
    """يحمّل بيانات OHLCV من Yahoo Finance مع fallback للملفات المحلية."""
    yf_sym = symbol if symbol.endswith(".CA") else f"{symbol}.CA"
    df = pd.DataFrame()

    try:
        ticker = yf.Ticker(yf_sym)
        df = ticker.history(period=period, interval="1d",
                            auto_adjust=False, repair=True)
        if not df.empty and len(df) > 5:
            df = df[["Open","High","Low","Close","Volume"]].copy()
            df.index = df.index.tz_localize(None)
    except Exception:
        pass

    if df.empty:
        try:
            url = (f"https://query1.finance.yahoo.com/v8/finance/chart/{yf_sym}"
                   f"?range={period}&interval=1d&includeAdjustedClose=false")
            r = requests.get(url, headers=HEADERS, timeout=15)
            if r.status_code == 200:
                data = r.json()
                res  = data["chart"]["result"][0]
                ind  = res["indicators"]["quote"][0]
                df   = pd.DataFrame({
                    "Open":   ind["open"],  "High":  ind["high"],
                    "Low":    ind["low"],   "Close": ind["close"],
                    "Volume": ind["volume"],
                }, index=pd.to_datetime(res["timestamp"], unit="s"))
                df = df.dropna(subset=["Close"])
                if not df.empty:
                    df.index = df.index.tz_localize(None)
        except Exception:
            pass

    # Fallback: local CSV (ensures no symbol is skipped due to network failures)
    if df.empty:
        csv_path = os.path.join(LOCAL_CSV_DIR, f"{symbol}.csv")
        if os.path.exists(csv_path):
            try:
                local = pd.read_csv(csv_path, parse_dates=["Date"], index_col="Date")
                local.index = pd.to_datetime(local.index)
                # Normalize column names to standard OHLCV
                col_map = {}
                for c in local.columns:
                    cl = c.lower()
                    if cl == "open":    col_map[c] = "Open"
                    elif cl == "high":  col_map[c] = "High"
                    elif cl == "low":   col_map[c] = "Low"
                    elif cl == "close": col_map[c] = "Close"
                    elif cl == "volume": col_map[c] = "Volume"
                local = local.rename(columns=col_map)
                needed = [c for c in ["Open","High","Low","Close","Volume"] if c in local.columns]
                if "Close" in needed and len(local) > 60:
                    df = local[needed].copy()
                    df.index = df.index.tz_localize(None) if df.index.tz else df.index
                    print(f"  [{symbol}] using local CSV ({len(df)} rows)")
            except Exception:
                pass

    return df


# ── I/O ───────────────────────────────────────────────────────────────────────

def _load():
    if not os.path.exists(LOG_FILE):
        return {"signals": []}
    try:
        with open(LOG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"signals": []}

def _save(data):
    with open(LOG_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# ── رصد الأحداث التاريخية ─────────────────────────────────────────────────────

def _scan_stock_history(symbol, df):
    """
    يمشي على كل يوم في التاريخ ويرصد:
      - لحظات القيعان المحلية (local lows)
      - يحسب النتيجة الفعلية بعد FORWARD_DAYS
      - يستخرج المؤشرات وقتها
    يُرجع: list of signal dicts
    """
    close  = df["Close"].values
    n      = len(close)
    signals = []

    for i in range(50, n - FORWARD_DAYS):
        # شرط القاع المحلي
        if close[i] > min(close[max(0, i-5):i+1]) * 1.002:
            continue

        future   = close[i+1: i+FORWARD_DAYS+1]
        max_f    = float(np.max(future))
        min_f    = float(np.min(future))
        # peak_gain: أقصى ربح ممكن نظرياً (خروج عند القمة المستقبلية — متفائل، للعرض فقط)
        # real_gain: العائد الفعلي close-to-close بعد FORWARD_DAYS — هذا أساس أي تقييم أداء
        peak_gain = (max_f - close[i]) / close[i]
        drawdown  = (close[i] - min_f) / close[i]
        real_gain = (float(close[i + FORWARD_DAYS]) - close[i]) / close[i]

        # تصنيف النتيجة من العائد الفعلي (وليس من قمة المستقبل)
        if real_gain >= MIN_GAIN:
            outcome = "win"
        elif real_gain <= -STOP_LOSS:
            outcome = "loss"
        else:
            outcome = "neutral"

        # استخراج المؤشرات
        cond = _extract(df, i)
        if cond is None:
            continue

        sig_date     = str(df.index[i].date())
        outcome_date = str(df.index[min(i + FORWARD_DAYS, n-1)].date())
        sig_id       = f"{symbol}_{sig_date}_hist"

        signals.append({
            "id":            sig_id,
            "symbol":        symbol,
            "signal_date":   sig_date,
            # ⚠️ كان سابقاً "BUY" if outcome == "win" — تسمية مبنية على المستقبل
            # (look-ahead leakage) جعلت أي تحليل "نسبة نجاح إشارات BUY" دائرياً.
            # الأحداث التاريخية ليست إشارات من الماسح — تُوسم كحدث تاريخي محايد.
            "signal":        "HIST_EVENT",
            "smc_score":     0,      # غير محسوب في الباكتست التاريخي
            "pattern_score": 0,
            "price":         round(float(close[i]), 2),
            "target":        round(float(close[i]) * (1 + MIN_GAIN), 2),
            "indicators":    {k: round(float(v), 4) for k, v in cond.items()},
            "outcome":       outcome,
            "outcome_date":  outcome_date,
            "outcome_price": round(float(close[i + FORWARD_DAYS]), 2),
            "outcome_gain":  round(real_gain, 4),
            "peak_gain":     round(peak_gain, 4),
            "max_drawdown":  round(drawdown, 4),
            "source":        "backfill",
        })

    return signals


# ── Main ──────────────────────────────────────────────────────────────────────

def run_backfill(stocks=None, period="2y", skip_existing=True):
    """
    يشغّل الباكتست على كل الأسهم ويحفظ النتائج في signal_log.json

    skip_existing: لو True، يتخطى الأسهم اللي عندها بيانات تاريخية مسجّلة
    """
    stocks = stocks or STOCKS
    data   = _load()

    # الـ IDs الموجودة مسبقاً
    existing_ids = {s["id"] for s in data["signals"]}

    total_added  = 0
    total_wins   = 0
    total_losses = 0

    print(f"{'='*60}")
    print(f"  HISTORICAL BACKFILL — {len(stocks)} stocks — period={period}")
    print(f"{'='*60}\n")

    for idx, symbol in enumerate(stocks, 1):
        print(f"  [{idx:2d}/{len(stocks)}] {symbol:<12}", end=" ", flush=True)

        # تخطي لو عنده بيانات تاريخية مسبقاً
        if skip_existing:
            has_hist = any(
                s["symbol"] == symbol and s.get("source") == "backfill"
                for s in data["signals"]
            )
            if has_hist:
                print("⏭  skipped (already backfilled)")
                continue

        df = _download(symbol, period=period)
        if df.empty or len(df) < 60:
            print(f"⚠️  no data ({len(df)} bars)")
            continue

        signals = _scan_stock_history(symbol, df)

        # حذف المكررات
        new_sigs = [s for s in signals if s["id"] not in existing_ids]
        for s in new_sigs:
            existing_ids.add(s["id"])

        data["signals"].extend(new_sigs)

        wins    = sum(1 for s in new_sigs if s["outcome"] == "win")
        losses  = sum(1 for s in new_sigs if s["outcome"] == "loss")
        neutral = sum(1 for s in new_sigs if s["outcome"] == "neutral")
        total_added  += len(new_sigs)
        total_wins   += wins
        total_losses += losses

        wr = wins / (wins + losses) * 100 if (wins + losses) > 0 else 0
        print(f"✅  {len(new_sigs):3d} events  "
              f"({wins}W / {losses}L / {neutral}N)  "
              f"WR={wr:.0f}%  bars={len(df)}")

        # حفظ تدريجي بعد كل سهم (لو انقطع الإنترنت في النص)
        _save(data)
        time.sleep(0.5)   # احترام rate limit

    # إحصائيات نهائية
    all_sigs   = data["signals"]
    hist_sigs  = [s for s in all_sigs if s.get("source") == "backfill"]
    live_sigs  = [s for s in all_sigs if s.get("source") != "backfill"]

    h_wins     = sum(1 for s in hist_sigs if s["outcome"] == "win")
    h_losses   = sum(1 for s in hist_sigs if s["outcome"] == "loss")
    h_decided  = h_wins + h_losses
    h_wr       = h_wins / h_decided * 100 if h_decided > 0 else 0

    print(f"\n{'='*60}")
    print(f"  BACKFILL COMPLETE")
    print(f"  Added this run : {total_added} events")
    print(f"  Total hist     : {len(hist_sigs)} events")
    print(f"  Total live     : {len(live_sigs)} events")
    print(f"  Hist Win Rate  : {h_wr:.1f}%  ({h_wins}W / {h_losses}L)")
    print(f"  signal_log.json: {len(all_sigs)} total records")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    period = sys.argv[1] if len(sys.argv) > 1 else "2y"
    run_backfill(period=period)
