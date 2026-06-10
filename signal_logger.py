"""
Signal Logger & Outcome Tracker
=================================
يحفظ كل إشارة BUY/WATCH وقت توليدها، ثم يتابع نتيجتها الفعلية
بعد 15 يوم تداول.

ملف البيانات: signal_log.json
البنية:
{
  "signals": [
    {
      "id":            "COMI.CA_2024-01-15",
      "symbol":        "COMI.CA",
      "signal_date":   "2024-01-15",
      "signal":        "BUY",
      "smc_score":     72,
      "pattern_score": 65.4,
      "price":         45.30,
      "target":        50.74,
      "indicators": {
        "stoch_rsi": 0.18,
        "p_vs_ma20": 0.85,
        "mom_10d":   -0.08,
        "mom_5d":    -0.04,
        "atr_ratio": 1.35,
        "vol_trend": 0.62
      },
      "outcome":       "pending" | "win" | "loss" | "neutral",
      "outcome_date":  "2024-02-05" | null,
      "outcome_price": 52.10 | null,
      "outcome_gain":  0.149 | null
    }
  ]
}
"""

import json
import os
from datetime import date, timedelta
from egx_context import trading_days_between as _egx_days

LOG_FILE     = "signal_log.json"
FORWARD_DAYS = 60    # أيام التداول قبل إغلاق الإشارة (كان 15 — مدّدناه لاستراتيجية بدون stop loss)

# حدود تصنيف حجم الارتداد (مستوردة من pattern_engine للتوحيد)
BOUNCE_LARGE  = 0.20
BOUNCE_MEDIUM = 0.10
BOUNCE_SMALL  = 0.04


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


# ── Helpers ───────────────────────────────────────────────────────────────────

def _trading_days_since(signal_date_str):
    """عدد أيام التداول الفعلية في EGX (الأحد-الخميس + إجازات) من تاريخ الإشارة."""
    return _egx_days(signal_date_str)


# ── Log a new signal ──────────────────────────────────────────────────────────

def log_signal(symbol, result):
    """
    يُستدعى من _run_scan_workflow بعد كل scan ناجح.
    يحفظ الإشارة فقط لو score >= 35 وكانت BUY أو WATCH.
    لو الإشارة مسجّلة مسبقاً لنفس اليوم، يتجاهلها.
    """
    signal = result.get("signal", "")
    score  = result.get("score", 0)

    if score < 35 or signal not in ("BUY", "WATCH", "Institutional Buy",
                                    "Strong Buy", "Aggressive Buy"):
        return

    today_str = date.today().isoformat()
    sig_id    = f"{symbol}_{today_str}"

    data = _load()
    existing_ids = {s["id"] for s in data["signals"]}
    if sig_id in existing_ids:
        return   # مسجّل مسبقاً

    pattern = result.get("pattern", {})
    indicators = pattern.get("detail", {})

    entry = {
        "id":            sig_id,
        "symbol":        symbol,
        "signal_date":   today_str,
        "signal":        signal,
        "smc_score":     score,
        "pattern_score": pattern.get("pattern_score", 0) if pattern.get("ok") else 0,
        "expected_bounce": pattern.get("expected_bounce", 0) if pattern.get("ok") else 0,
        "price":         result.get("price", 0),
        "target":        result.get("target", 0),
        "indicators":    indicators,
        "context":       result.get("signal_context", {}),
        "peak_gain":     None,   # أقصى ارتداد شُوهد منذ الإشارة (يُحدَّث يومياً)
        "peak_date":     None,
        "peak_price":    None,
        "outcome":       "pending",
        "outcome_date":  None,
        "outcome_gain":  None,   # الغين عند إغلاق الإشارة (بعد 60 يوم)
    }

    data["signals"].append(entry)
    _save(data)
    print(f"  📝 Signal logged: {symbol} {signal} @ {result.get('price')} (score={score})")


# ── Check outcomes ────────────────────────────────────────────────────────────

def check_outcomes(current_prices):
    """
    يُستدعى من monitor كل يوم مع أسعار اليوم الحالية.

    لكل إشارة pending:
      1. يُحدِّث peak_gain لو السعر الحالي أعلى من الـ peak السابق
      2. بعد >= FORWARD_DAYS يُغلق الإشارة بتصنيف حجم الارتداد:
         large / medium / small / flat

    current_prices: dict {symbol: float}
    يُرجع: list of resolved signals (للإبلاغ عنها في Telegram)
    """
    data     = _load()
    resolved = []
    today    = date.today().isoformat()

    for sig in data["signals"]:
        if sig["outcome"] != "pending":
            continue

        symbol = sig["symbol"]
        if symbol not in current_prices:
            continue

        cur_price   = float(current_prices[symbol])
        entry_price = float(sig["price"])
        if entry_price <= 0:
            continue

        cur_gain = (cur_price - entry_price) / entry_price

        # ── تحديث peak_gain (يومياً بغض النظر عن المدة) ────────────────
        prev_peak = sig.get("peak_gain") or -1.0
        if cur_gain > prev_peak:
            sig["peak_gain"]  = round(cur_gain, 4)
            sig["peak_date"]  = today
            sig["peak_price"] = round(cur_price, 2)

        # ── إغلاق الإشارة بعد FORWARD_DAYS ─────────────────────────────
        trading_days = _trading_days_since(sig["signal_date"])
        if trading_days < FORWARD_DAYS:
            continue

        peak = sig.get("peak_gain") or cur_gain

        if peak >= BOUNCE_LARGE:
            outcome = "large"
        elif peak >= BOUNCE_MEDIUM:
            outcome = "medium"
        elif peak >= BOUNCE_SMALL:
            outcome = "small"
        else:
            outcome = "flat"

        sig["outcome"]      = outcome
        sig["outcome_date"] = today
        sig["outcome_gain"] = round(cur_gain, 4)
        resolved.append(dict(sig))

        print(f"  ✅ Outcome: {symbol} → {outcome} "
              f"(peak +{peak*100:.1f}%, now {cur_gain*100:+.1f}% after {trading_days}d)")

    _save(data)
    return resolved


# ── Statistics ────────────────────────────────────────────────────────────────

def get_stats():
    """
    يُرجع إحصائيات السجل الكامل — مفيد للمراجعة الدورية.
    """
    data    = _load()
    signals = data["signals"]
    total   = len(signals)

    if total == 0:
        return {"total": 0, "pending": 0, "win": 0, "loss": 0,
                "neutral": 0, "win_rate": 0, "avg_gain": 0}

    TIERS = ("large", "medium", "small", "flat", "win", "loss", "neutral", "pending")
    by_outcome = {t: [] for t in TIERS}

    for s in signals:
        o = s.get("outcome", "pending")
        if o not in by_outcome:
            o = "pending"
        by_outcome[o].append(s.get("peak_gain") or s.get("outcome_gain") or 0)

    large   = len(by_outcome["large"])
    medium  = len(by_outcome["medium"])
    small_  = len(by_outcome["small"])
    flat    = len(by_outcome["flat"])
    # backward compat
    wins    = len(by_outcome["win"])
    decided = large + medium + small_ + flat + wins + len(by_outcome["loss"])
    bounced = large + medium + wins   # counted as positive outcomes

    bounce_rate = bounced / decided if decided > 0 else 0

    all_peaks = [g for lst in (by_outcome["large"], by_outcome["medium"],
                               by_outcome["small"], by_outcome["win"]) for g in lst if g > 0]
    avg_peak  = sum(all_peaks) / len(all_peaks) if all_peaks else 0

    per_symbol = {}
    for s in signals:
        sym = s["symbol"]
        if sym not in per_symbol:
            per_symbol[sym] = {t: 0 for t in TIERS}
        o = s.get("outcome", "pending")
        if o in per_symbol[sym]:
            per_symbol[sym][o] += 1

    return {
        "total":       total,
        "pending":     len(by_outcome["pending"]),
        "large":       large,
        "medium":      medium,
        "small":       small_,
        "flat":        flat,
        "bounce_rate": round(bounce_rate * 100, 1),
        "avg_peak":    round(avg_peak * 100, 2),
        "per_symbol":  per_symbol,
    }
