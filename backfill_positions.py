"""
Backfill open positions from historical data.

Simulates what the daily scanner would have registered since START_DATE
by replaying the SMC scoring day-by-day on each stock.
Registers the FIRST day each stock met: score >= 35 AND r1 >= 18.

Set env var DRY_RUN=true to preview results without saving anything.
"""

import json, os, sys
from datetime import datetime, date, timedelta
import pandas as pd
import pytz

DRY_RUN = os.getenv("DRY_RUN", "false").lower() == "true"

# ── import scoring logic from main ───────────────────────────────────────────
sys.path.insert(0, ".")
from main import (
    STOCKS, NAMES, CAIRO,
    swings, calc_avwap,
    sc_price, sc_ob, sc_liquidity, sc_htf,
    sc_avwap, sc_macd, sc_div, sc_demand_zone,
    calc_macd, add_position, load_open_positions,
    WHITELIST,
)

import yfinance as yf

START_DATE  = date(2026, 1, 1)
SCORE_GATE  = 35
R1_GATE     = 18
BARS_NEEDED = 110          # same window the live scanner uses

CAIRO_TZ = pytz.timezone("Africa/Cairo")


def score_on_day(df_full: pd.DataFrame, as_of: date):
    """Run SMC scoring using data up to (and including) `as_of`."""
    df = df_full[df_full.index.date <= as_of].tail(BARS_NEEDED)
    if len(df) < 20:
        return None, 0, 0

    close = df["Close"].squeeze()   # ensure 1-D Series
    cur   = float(close.iloc[-1])

    hi, lo, eq, buy_hi, sell_lo = swings(close)
    av, alo                     = calc_avwap(df)

    if cur >= eq:
        return cur, 0, 0   # premium zone — no signal

    r1, _ = sc_price(cur, lo, hi, eq, buy_hi, sell_lo)
    r2, _ = sc_ob(df, cur, eq, lo, buy_hi)
    r3, _ = sc_liquidity(df, cur)
    r4, _ = sc_htf(df)
    r5, _ = sc_avwap(cur, av, alo)
    r6, _ = sc_macd(close)
    ml, _, _ = calc_macd(close)
    r7, _ = sc_div(close, ml)
    r8, _ = sc_demand_zone(df, eq, lo, buy_hi)

    total = min(r1 + r2 + r3 + r4 + r5 + r6 + r7 + r8, 100)
    return cur, total, r1


def trading_days_since(start: date) -> list:
    """Return EGX trading days (Sun–Thu) from start to yesterday."""
    days = []
    d = start
    yesterday = date.today() - timedelta(days=1)
    while d <= yesterday:
        if d.weekday() in (6, 0, 1, 2, 3):   # Sun=6, Mon=0, Tue=1, Wed=2, Thu=3
            days.append(d)
        d += timedelta(days=1)
    return days


def fetch_history(symbol: str) -> pd.DataFrame:
    """Download full price history needed for backfill."""
    # Use Ticker.history() to avoid MultiIndex columns from yf.download()
    # Go back to 2025-01-01 to have 110 bars before START_DATE
    start_fetch = (START_DATE - timedelta(days=400)).strftime("%Y-%m-%d")
    try:
        ticker = yf.Ticker(symbol)
        df = ticker.history(start=start_fetch, interval="1d",
                            auto_adjust=False)
        if df.empty:
            return pd.DataFrame()
        df = df[["Open", "High", "Low", "Close", "Volume"]].copy()
        df.index = pd.to_datetime(df.index).tz_localize(None)
        return df
    except Exception as e:
        print(f"  [{symbol}] download error: {e}")
        return pd.DataFrame()


def main():
    positions = load_open_positions()
    trading_days = trading_days_since(START_DATE)
    print(f"Backfilling {len(STOCKS)} stocks over {len(trading_days)} trading days "
          f"({START_DATE} → {trading_days[-1] if trading_days else 'N/A'})\n")

    registered = {}   # symbol → (entry_date, entry_price)

    for symbol in STOCKS:
        if symbol in positions:
            print(f"  {symbol}: already registered — skipping")
            continue

        print(f"  {symbol}: downloading history...", end=" ", flush=True)
        df_full = fetch_history(symbol)
        if df_full.empty:
            print("no data")
            continue
        print(f"{len(df_full)} bars")

        for day in trading_days:
            cur, score, r1 = score_on_day(df_full, day)
            if cur is None:
                continue

            # Apply whitelist relaxed gate (same as live scanner)
            r1_gate = 12 if symbol in WHITELIST else R1_GATE

            if score >= SCORE_GATE and r1 >= r1_gate:
                entry_date = datetime(day.year, day.month, day.day,
                                      9, 30, 0,
                                      tzinfo=CAIRO_TZ).isoformat()
                registered[symbol] = (entry_date, round(cur, 2))
                print(f"    ✅ First signal on {day}: price={cur:.2f}, "
                      f"score={score}, r1={r1}")
                break   # stop at first qualifying day
        else:
            print(f"    — No qualifying day found since {START_DATE}")

    print(f"\n{'[DRY RUN] ' if DRY_RUN else ''}Found {len(registered)} position(s) to register:\n")
    print(f"{'Symbol':<12} {'Entry Date':<14} {'Entry Price':>12}  {'Score':>6}  {'R1':>4}")
    print("-" * 55)

    # Re-run to get score/r1 for display
    for symbol, (entry_date, entry_price) in sorted(registered.items()):
        entry_day = date.fromisoformat(entry_date[:10])
        df_full = fetch_history(symbol)
        _, score, r1 = score_on_day(df_full, entry_day) if not df_full.empty else (0, 0, 0)
        print(f"  {symbol:<12} {entry_date[:10]:<14} {entry_price:>10.2f} EGP  {score:>5}  {r1:>4}")

    if DRY_RUN:
        print("\n⚠️  DRY RUN — nothing was saved. Re-run with DRY_RUN=false to apply.")
    else:
        print("\nSaving positions...")
        for symbol, (entry_date, entry_price) in registered.items():
            add_position(symbol, entry_price, entry_date)
            print(f"  ✅ Saved: {NAMES.get(symbol, symbol)} ({symbol}) @ {entry_price} EGP")
        final = load_open_positions()
        print(f"\nDone. open_positions.json now has {len(final)} position(s).")


if __name__ == "__main__":
    main()
