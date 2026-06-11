"""
patch_smc_scores.py — One-time patch to populate smc_score for existing backfill signals.

The original backfill stored smc_score=0 for every signal. This script:
  1. Downloads historical price data for each stock (once per stock).
  2. For every signal in signal_log.json with smc_score=0, slices the df
     up to the signal date and calls compute_smc_score().
  3. Writes the updated smc_score back to signal_log.json.
  4. Recomputes STOCK_QUALITY tiers from the new scores.

Run once:
    python3 patch_smc_scores.py
"""

import json
import time
from collections import defaultdict

import pandas as pd

from backfill_signal_log import _download, LOG_FILE, _save, _load
from main import compute_smc_score, _compute_stock_tiers, STOCKS


def _build_date_index(df: pd.DataFrame) -> dict:
    """Map date string → integer position in df."""
    return {str(ts.date()): i for i, ts in enumerate(df.index)}


def patch_smc_scores():
    data = _load()
    signals = data["signals"]

    # Group by symbol — only process signals with smc_score == 0
    by_sym: dict[str, list] = defaultdict(list)
    for idx, s in enumerate(signals):
        if s.get("smc_score", 0) == 0:
            by_sym[s["symbol"]].append((idx, s))

    total_updated = 0
    total_skipped = 0

    print(f"{'='*60}")
    print(f"  SMC SCORE PATCH — {len(by_sym)} stocks to process")
    print(f"{'='*60}\n")

    for sym_idx, (symbol, sig_list) in enumerate(sorted(by_sym.items()), 1):
        print(f"  [{sym_idx:2d}/{len(by_sym)}] {symbol:<12}", end=" ", flush=True)

        df = _download(symbol, period="2y")
        if df.empty or len(df) < 60:
            print(f"⚠️  no data — skipped {len(sig_list)} signals")
            total_skipped += len(sig_list)
            continue

        date_to_pos = _build_date_index(df)
        updated = 0

        for list_idx, sig in sig_list:
            sig_date = sig.get("signal_date", "")
            pos = date_to_pos.get(sig_date)
            if pos is None or pos < 50:
                total_skipped += 1
                continue

            df_slice = df.iloc[: pos + 1]
            try:
                smc_total, _, _ = compute_smc_score(df_slice, symbol)
            except Exception:
                smc_total = 0

            signals[list_idx]["smc_score"] = smc_total
            updated += 1

        total_updated += updated
        print(f"✅  {updated} signals updated")
        _save(data)
        time.sleep(0.3)

    _save(data)

    print(f"\n{'='*60}")
    print(f"  PATCH COMPLETE")
    print(f"  Updated : {total_updated} signals")
    print(f"  Skipped : {total_skipped} signals")
    print(f"{'='*60}\n")

    # Show new tier distribution
    real_smc = [s for s in signals if s.get("smc_score", 0) > 0]
    print(f"  Signals with real smc_score > 0 : {len(real_smc)}")
    if real_smc:
        scores = [s["smc_score"] for s in real_smc]
        print(f"  Score range  : {min(scores)} → {max(scores)}  avg={sum(scores)/len(scores):.1f}")

    print("\n  Computing new STOCK_QUALITY tiers from real scores...")
    tiers = _compute_stock_tiers()
    tier_labels = {1.15: "⭐ Tier A", 1.07: "✅ Tier B", 1.00: "  Tier C", 0.88: "⚠️ Tier D"}
    for sym in sorted(tiers):
        mult = tiers[sym]
        lbl  = tier_labels.get(mult, f"×{mult}")
        print(f"    {sym:<12}  {lbl}  ×{mult}")

    print("\n  Done ✅")
    print("  Restart the app to load the updated STOCK_QUALITY tiers.\n")


if __name__ == "__main__":
    patch_smc_scores()
