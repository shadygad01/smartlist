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
FORWARD_DAYS = 15    # عدد أيام التداول للحكم على النتيجة
MIN_GAIN     = 0.07  # +7% = win
STOP_LOSS    = 0.06  # -6% = loss


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
        "price":         result.get("price", 0),
        "target":        result.get("target", 0),
        "indicators":    indicators,
        "context":       result.get("signal_context", {}),
        "outcome":       "pending",
        "outcome_date":  None,
        "outcome_price": None,
        "outcome_gain":  None,
    }

    data["signals"].append(entry)
    _save(data)
    print(f"  📝 Signal logged: {symbol} {signal} @ {result.get('price')} (score={score})")


# ── Check outcomes ────────────────────────────────────────────────────────────

def check_outcomes(current_prices):
    """
    يُستدعى من monitor كل يوم مع أسعار اليوم الحالية.
    يفحص الإشارات pending اللي مضى عليها >= FORWARD_DAYS يوم تداول
    ويسجل النتيجة.

    current_prices: dict {symbol: float}
    يُرجع: list of resolved signals (للإبلاغ عنها في Telegram)
    """
    data     = _load()
    resolved = []

    for sig in data["signals"]:
        if sig["outcome"] != "pending":
            continue

        trading_days = _trading_days_since(sig["signal_date"])
        if trading_days < FORWARD_DAYS:
            continue

        symbol = sig["symbol"]
        if symbol not in current_prices:
            continue

        cur_price  = float(current_prices[symbol])
        entry_price = float(sig["price"])
        if entry_price <= 0:
            continue

        gain = (cur_price - entry_price) / entry_price

        if gain >= MIN_GAIN:
            outcome = "win"
        elif gain <= -STOP_LOSS:
            outcome = "loss"
        else:
            outcome = "neutral"

        sig["outcome"]       = outcome
        sig["outcome_date"]  = date.today().isoformat()
        sig["outcome_price"] = round(cur_price, 2)
        sig["outcome_gain"]  = round(gain, 4)
        resolved.append(dict(sig))

        print(f"  ✅ Outcome recorded: {symbol} → {outcome} "
              f"({gain*100:+.1f}% after {trading_days} trading days)")

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

    by_outcome = {"win": [], "loss": [], "neutral": [], "pending": []}
    for s in signals:
        by_outcome[s["outcome"]].append(s.get("outcome_gain") or 0)

    wins    = len(by_outcome["win"])
    losses  = len(by_outcome["loss"])
    decided = wins + losses

    win_rate = wins / decided if decided > 0 else 0

    all_gains = [g for g in by_outcome["win"] + by_outcome["loss"] + by_outcome["neutral"] if g != 0]
    avg_gain  = sum(all_gains) / len(all_gains) if all_gains else 0

    # Per-symbol stats
    per_symbol = {}
    for s in signals:
        sym = s["symbol"]
        if sym not in per_symbol:
            per_symbol[sym] = {"win": 0, "loss": 0, "neutral": 0, "pending": 0}
        per_symbol[sym][s["outcome"]] += 1

    return {
        "total":      total,
        "pending":    len(by_outcome["pending"]),
        "win":        wins,
        "loss":       losses,
        "neutral":    len(by_outcome["neutral"]),
        "win_rate":   round(win_rate * 100, 1),
        "avg_gain":   round(avg_gain * 100, 2),
        "per_symbol": per_symbol,
    }
