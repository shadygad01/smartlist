"""
Recompute entry_score for all open positions using real historical data.
Runs score_on_day() on each position's entry date and updates open_positions.json.
"""

import json, sys
from datetime import date

sys.path.insert(0, ".")
from main import NAMES, load_open_positions, save_open_positions
from backfill_positions import fetch_history, score_on_day

def main():
    positions = load_open_positions()
    open_pos = {s: p for s, p in positions.items() if p.get("status") == "open"}

    print(f"Rescoring {len(open_pos)} open position(s)...\n")
    print(f"{'Symbol':<12} {'Entry Date':<12} {'Old Score':>9} {'New Score':>9}")
    print("-" * 48)

    updated = 0
    for symbol, pos in open_pos.items():
        entry_day = date.fromisoformat(pos["entry_date"][:10])
        df = fetch_history(symbol)
        if df.empty:
            print(f"  {symbol:<12} — no data, skipping")
            continue

        _, score, _ = score_on_day(df, entry_day)
        old_score = pos.get("entry_score", 0)
        positions[symbol]["entry_score"] = score
        print(f"  {symbol:<12} {str(entry_day):<12} {old_score:>9} {score:>9}")
        updated += 1

    save_open_positions()
    print(f"\nDone. Updated entry_score for {updated} position(s).")

if __name__ == "__main__":
    main()
