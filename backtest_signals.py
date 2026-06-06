"""
Build full signal history for all stocks from real historical data.

For every trading day since START_DATE, runs the SMC scorer on each stock
and records every day the buy signal was active (score >= 35, r1 >= gate).
Saves results to signal_history.json — at least 20 signals per stock where
the data allows.

Each entry:
  { "date": "2026-01-05", "price": 37.10, "score": 67, "r1": 25 }
"""

import json, os, sys
from datetime import date, timedelta

sys.path.insert(0, ".")
from main import STOCKS, NAMES, WHITELIST
from backfill_positions import fetch_history, score_on_day, trading_days_since

START_DATE         = date(2026, 1, 1)
SCORE_GATE         = 35
R1_GATE            = 18
SIGNAL_HISTORY_FILE = "signal_history.json"


def save_signal_history(data: dict):
    with open(SIGNAL_HISTORY_FILE, "w") as f:
        json.dump(data, f, indent=2)
    print(f"Saved {SIGNAL_HISTORY_FILE}")


def main():
    trading_days = trading_days_since(START_DATE)
    if not trading_days:
        print("No trading days found.")
        return

    print(f"Building signal history: {len(STOCKS)} stocks × {len(trading_days)} days "
          f"({START_DATE} → {trading_days[-1]})\n")

    history = {}

    for symbol in STOCKS:
        print(f"  {symbol}: fetching...", end=" ", flush=True)
        df_full = fetch_history(symbol)
        if df_full.empty:
            print("no data — skipped")
            history[symbol] = []
            continue
        print(f"{len(df_full)} bars → scanning...", end=" ", flush=True)

        r1_gate = 12 if symbol in WHITELIST else R1_GATE
        signals = []

        for day in trading_days:
            cur, score, r1 = score_on_day(df_full, day)
            if cur is None:
                continue                    # insufficient history
            if score == 0:
                continue                    # premium zone — no signal
            if score >= SCORE_GATE and r1 >= r1_gate:
                signals.append({
                    "date":  str(day),
                    "price": round(cur, 2),
                    "score": score,
                    "r1":    r1,
                })

        history[symbol] = signals
        print(f"{len(signals)} signal(s)")

    save_signal_history(history)

    # Summary table
    print(f"\n{'Symbol':<12} {'Name':<32} {'Signals':>7}  {'Latest':>12}  {'Avg Score':>9}")
    print("─" * 78)
    for symbol in STOCKS:
        sigs = history.get(symbol, [])
        count     = len(sigs)
        latest    = sigs[-1]["date"] if sigs else "—"
        avg_score = round(sum(s["score"] for s in sigs) / count, 1) if count else 0
        print(f"  {symbol:<12} {NAMES.get(symbol, symbol):<32} {count:>7}  {latest:>12}  {avg_score:>9}")

    total = sum(len(v) for v in history.values())
    print(f"\nTotal signals recorded: {total}")


if __name__ == "__main__":
    main()
