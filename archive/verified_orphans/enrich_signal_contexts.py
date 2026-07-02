"""
Enrich Existing Signals with EGX Context
=========================================
يضيف حقل context لكل الإشارات الموجودة في signal_log.json
باستخدام تاريخ الإشارة — بدون أي تحميل بيانات جديدة.

ثم يُعيد حساب الأوزان المتعلَّمة مع الفصل بين رمضان والأوقات العادية.

Usage:
    python enrich_signal_contexts.py
"""

import json
import os
from collections import Counter
from egx_context import get_signal_context
from pattern_engine import update_weights_from_log

LOG_FILE = "signal_log.json"


BOUNCE_LARGE  = 0.20
BOUNCE_MEDIUM = 0.10
BOUNCE_SMALL  = 0.04


def _gain_to_tier(g):
    if g is None: return None
    g = float(g)
    if g >= BOUNCE_LARGE:  return "large"
    if g >= BOUNCE_MEDIUM: return "medium"
    if g >= BOUNCE_SMALL:  return "small"
    return "flat"


def enrich_contexts():
    if not os.path.exists(LOG_FILE):
        print("❌  signal_log.json not found")
        return 0

    with open(LOG_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

    signals   = data["signals"]
    ctx_added = 0
    peak_added = 0
    tier_updated = 0

    for sig in signals:
        # 1. Context
        if not sig.get("context"):
            sig["context"] = get_signal_context(sig.get("signal_date", ""))
            ctx_added += 1

        # 2. peak_gain — استخدم outcome_gain كأفضل تقدير متاح
        if sig.get("peak_gain") is None and sig.get("outcome_gain") is not None:
            sig["peak_gain"] = sig["outcome_gain"]
            peak_added += 1

        # 3. تحديث تصنيف الإشارات القديمة (win/loss/neutral → large/medium/small/flat)
        if sig.get("outcome") in ("win", "loss", "neutral"):
            new_tier = _gain_to_tier(sig.get("peak_gain"))
            if new_tier:
                sig["outcome"] = new_tier
                tier_updated += 1

    with open(LOG_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    return signals, ctx_added, peak_added, tier_updated


def print_context_stats(signals):
    total   = len(signals)
    TIERS   = ("large", "medium", "small", "flat")
    decided = [s for s in signals if s.get("outcome") in TIERS]

    by_tier = {t: [s for s in decided if s["outcome"] == t] for t in TIERS}
    peaks   = [s["peak_gain"] for s in decided if s.get("peak_gain")]
    avg_p   = sum(peaks)/len(peaks)*100 if peaks else 0

    ramadan = [s for s in decided if s.get("context", {}).get("is_ramadan")]
    normal  = [s for s in decided if not s.get("context", {}).get("is_ramadan")]

    def avg_peak(lst):
        ps = [s.get("peak_gain", 0) or 0 for s in lst]
        return sum(ps)/len(ps)*100 if ps else 0

    print(f"\n{'─'*55}")
    print(f"  📊  Signal Stats ({total} total, {len(decided)} decided)")
    print(f"{'─'*55}")
    print(f"  📈  Bounce tiers:")
    for t in TIERS:
        sigs = by_tier[t]
        ap   = avg_peak(sigs)
        print(f"      {t:<8} : {len(sigs):4d}  avg_peak={ap:5.1f}%")
    print(f"  📊  Overall avg peak : {avg_p:.1f}%")
    print(f"  🌙  Ramadan avg peak : {avg_peak(ramadan):.1f}%  (n={len(ramadan)})")
    print(f"  📅  Normal  avg peak : {avg_peak(normal):.1f}%  (n={len(normal)})")
    print(f"{'─'*55}\n")


if __name__ == "__main__":
    print("=" * 55)
    print("  EGX SIGNAL CONTEXT ENRICHMENT")
    print("=" * 55)

    result = enrich_contexts()
    if isinstance(result, int):
        exit(1)

    signals, ctx_added, peak_added, tier_updated = result

    print(f"\n  ✅  context tags added  : {ctx_added}")
    print(f"  ✅  peak_gain populated : {peak_added}")
    print(f"  ✅  outcome tiers updated: {tier_updated}")

    print_context_stats(signals)

    print("  🔄  Re-learning weights with context-aware data...")
    new_weights = update_weights_from_log()

    if new_weights:
        print("\n  ✅  Weights updated successfully")
        print(f"  📁  Saved to learned_weights.json")
    else:
        print("\n  ⚠️   Not enough decided signals to update weights")

    print("\n  Done ✅")
