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


def enrich_contexts():
    if not os.path.exists(LOG_FILE):
        print("❌  signal_log.json not found")
        return 0

    with open(LOG_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

    signals = data["signals"]
    updated = 0

    for sig in signals:
        if sig.get("context"):
            continue  # already tagged

        sig_date = sig.get("signal_date", "")
        ctx = get_signal_context(sig_date)   # بدون volume (غير محفوظ للتاريخي)
        sig["context"] = ctx
        updated += 1

    if updated:
        with open(LOG_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    return signals, updated


def print_context_stats(signals):
    total    = len(signals)
    decided  = [s for s in signals if s.get("outcome") in ("win", "loss")]
    ramadan  = [s for s in decided  if s.get("context", {}).get("is_ramadan")]
    cbe_w    = [s for s in decided  if s.get("context", {}).get("cbe_window")]
    seasons  = Counter(s.get("context", {}).get("season", "?") for s in decided)

    ram_wins    = sum(1 for s in ramadan if s["outcome"] == "win")
    ram_decided = len(ramadan)
    norm_sigs   = [s for s in decided if not s.get("context", {}).get("is_ramadan")]
    norm_wins   = sum(1 for s in norm_sigs if s["outcome"] == "win")

    print(f"\n{'─'*55}")
    print(f"  📊  Context Stats ({total} total, {len(decided)} decided)")
    print(f"{'─'*55}")
    print(f"  🌙  Ramadan signals : {len(ramadan):4d}  "
          f"(WR={ram_wins/ram_decided*100:.1f}%)" if ram_decided else
          f"  🌙  Ramadan signals : {len(ramadan):4d}")
    print(f"  📅  Normal signals  : {len(norm_sigs):4d}  "
          f"(WR={norm_wins/len(norm_sigs)*100:.1f}%)" if norm_sigs else
          f"  📅  Normal signals  : {len(norm_sigs):4d}")
    print(f"  🏦  CBE-window sigs : {len(cbe_w):4d}")
    for season, cnt in sorted(seasons.items()):
        print(f"  📆  {season:<10}        : {cnt:4d}")
    print(f"{'─'*55}\n")


if __name__ == "__main__":
    print("=" * 55)
    print("  EGX SIGNAL CONTEXT ENRICHMENT")
    print("=" * 55)

    result = enrich_contexts()
    if isinstance(result, int):
        exit(1)

    signals, updated = result

    if updated:
        print(f"\n  ✅  Tagged {updated} signals with EGX context")
    else:
        print(f"\n  ℹ️   All signals already have context — skipping tagging")

    print_context_stats(signals)

    print("  🔄  Re-learning weights with context-aware data...")
    new_weights = update_weights_from_log()

    if new_weights:
        print("\n  ✅  Weights updated successfully")
        print(f"  📁  Saved to learned_weights.json")
    else:
        print("\n  ⚠️   Not enough decided signals to update weights")

    print("\n  Done ✅")
