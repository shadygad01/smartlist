"""
EGX Historical Backtester
=========================
Replays the exact SMC scoring logic day-by-day on 5 years of OHLCV data,
generating synthetic historical signals and merging them into signal_history.json
so that backfill_research_db.py can compute BQ scores + features for ML training.

Usage:
    python historical_backtest.py            # full run
    python historical_backtest.py --dry-run  # count signals, no file changes
    python historical_backtest.py --start 2022-01-01  # custom start date
"""

import json
import sys
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import yfinance as yf

# ── Import scoring logic from main (pure functions, safe to import) ────────────
import main as _m

STOCKS               = _m.STOCKS
WHITELIST            = _m.WHITELIST
STOCK_QUALITY        = _m.STOCK_QUALITY
PRICE_GATE_NORMAL    = _m.PRICE_GATE_NORMAL
PRICE_GATE_WHITELIST = _m.PRICE_GATE_WHITELIST
W_LIQ                = _m.W_LIQ
CTX_RAMADAN_MULT     = _m.CTX_RAMADAN_MULT
CTX_CBE_MULT         = _m.CTX_CBE_MULT

from main import (
    swings, calc_avwap, calc_macd,
    calc_stopping_volume, calc_volume_profile,
    sc_price, sc_ob, sc_liquidity, sc_htf,
    sc_avwap, sc_macd, sc_div, sc_demand_zone,
    sig_info,
)
from egx_context import is_ramadan, is_cbe_window

# ── Config ─────────────────────────────────────────────────────────────────────
SIGNAL_HISTORY_FILE = "signal_history.json"
MIN_BARS            = 110          # minimum bars before scoring is meaningful
BACKTEST_START      = "2021-06-01" # 5 years of history
BACKTEST_END        = "2026-02-07" # day before live scanner started (2026-02-08)
BUY_SIGNALS         = {"Buy", "Strong Buy", "Very Strong Buy", "Institutional Buy", "Early Buy"}


# ── Core: score one day slice ──────────────────────────────────────────────────

def _score_day(symbol: str, df_slice: pd.DataFrame, sig_date: date):
    """
    Run the full SMC scoring pipeline on df_slice (data up to and including sig_date).
    Returns (signal_str, adj_score, price, r1_score) — same fields as live scanner.
    """
    try:
        cur = float(df_slice["Close"].iloc[-1])
        hi, lo, eq, buy_hi, sell_lo = swings(df_slice)
        av, alo = calc_avwap(df_slice)

        if cur >= eq:
            r1 = r2 = r3 = r4 = r5 = r6 = r7 = r8 = 0
        else:
            r1, _ = sc_price(cur, lo, hi, eq, buy_hi, sell_lo)
            r2, _ = sc_ob(df_slice, cur, eq, lo, buy_hi)
            r3, _ = sc_liquidity(df_slice, cur)
            r4, _ = sc_htf(df_slice)
            r5, _ = sc_avwap(cur, av, alo)
            macd_result = calc_macd(df_slice["Close"])
            ml = macd_result[0]
            r6, _ = sc_macd(df_slice["Close"], _macd=macd_result)
            r7, _ = sc_div(df_slice["Close"], ml)
            sv_result  = calc_stopping_volume(df_slice, eq, lo)
            hvn_result = calc_volume_profile(df_slice, eq, lo, buy_hi)
            r8, _ = sc_demand_zone(df_slice, eq, lo, buy_hi,
                                   _sv=sv_result, _hvn=hvn_result)

        total = min(r1 + r2 + r3 + r4 + r5 + r6 + r7 + r8, 100)

        # Context multipliers (historically accurate via egx_context.py)
        ctx_mult = 1.0
        if is_ramadan(sig_date):
            ctx_mult *= CTX_RAMADAN_MULT
        if is_cbe_window(sig_date):
            ctx_mult *= CTX_CBE_MULT
        stock_mult = STOCK_QUALITY.get(symbol, 1.0)
        score = min(int(round(total * stock_mult * ctx_mult)), 100)

        # Signal gates — identical to analyze() in main.py
        PRICE_GATE        = PRICE_GATE_WHITELIST if symbol in WHITELIST else PRICE_GATE_NORMAL
        _entry_score_gate = 35 if symbol in WHITELIST else 40

        if total < 35:
            return "Skip", score, cur, r1
        if r1 < PRICE_GATE:
            return "Wait", score, cur, r1
        if score < _entry_score_gate:
            return "Wait", score, cur, r1
        if r3 < W_LIQ:
            return "Early Buy", score, cur, r1

        return sig_info(score)[0], score, cur, r1

    except Exception:
        return "Skip", 0, 0.0, 0


# ── Main backtest ──────────────────────────────────────────────────────────────

def run_backtest(
    backtest_start: str = BACKTEST_START,
    backtest_end:   str = BACKTEST_END,
    dry_run: bool = False,
):
    print(f"EGX Historical Backtester")
    print(f"Period : {backtest_start} → {backtest_end}")
    print(f"Stocks : {len(STOCKS)}")
    print(f"Dry run: {dry_run}")
    print("=" * 60)

    # Load existing signal history (live signals stay untouched)
    sig_path = Path(SIGNAL_HISTORY_FILE)
    if sig_path.exists():
        with open(sig_path, encoding="utf-8") as f:
            history: dict = json.load(f)
    else:
        history = {}

    # Normalise to list-of-dicts format
    for sym in list(history):
        if not isinstance(history[sym], list):
            history[sym] = [history[sym]]

    end_dt = date.fromisoformat(backtest_end)
    dl_end = (end_dt + timedelta(days=1)).isoformat()

    total_buy_signals = 0
    total_entries     = 0

    for symbol in STOCKS:
        print(f"\n{symbol}: downloading {backtest_start} → {backtest_end}", flush=True)

        try:
            df_full = yf.Ticker(symbol).history(
                start=backtest_start, end=dl_end, auto_adjust=True,
            )
        except Exception as e:
            print(f"  ERROR downloading: {e}")
            continue

        if df_full.empty or len(df_full) < MIN_BARS:
            print(f"  SKIP — only {len(df_full)} bars available (need {MIN_BARS})")
            continue

        df_full.index = pd.to_datetime(df_full.index).tz_localize(None)
        print(f"  {len(df_full)} bars  "
              f"({df_full.index[0].date()} → {df_full.index[-1].date()})", flush=True)

        existing = history.get(symbol, [])
        if not isinstance(existing, list):
            existing = [existing]
        existing_dates = {e["date"] for e in existing if isinstance(e, dict)}

        new_entries: list[dict] = []
        prev_signal = "Wait"

        for i in range(MIN_BARS - 1, len(df_full)):
            df_slice = df_full.iloc[: i + 1]
            sig_date = df_full.index[i].date()
            date_str = sig_date.isoformat()

            sig, score, price, r1 = _score_day(symbol, df_slice, sig_date)

            is_buy      = sig in BUY_SIGNALS
            prev_is_buy = prev_signal in BUY_SIGNALS

            # ── Record Wait→Buy transition (the entry signal backfill cares about)
            if is_buy and not prev_is_buy:
                if date_str not in existing_dates:
                    new_entries.append({
                        "date":   date_str,
                        "score":  score,
                        "price":  round(price, 2),
                        "r1":     r1,
                        "signal": sig,
                    })
                    existing_dates.add(date_str)
                    total_buy_signals += 1

            # ── Record Buy→Wait transition so backfill resets its state machine
            elif prev_is_buy and not is_buy and sig != "Skip":
                if date_str not in existing_dates:
                    new_entries.append({
                        "date":   date_str,
                        "score":  score,
                        "price":  round(price, 2),
                        "r1":     r1,
                        "signal": sig,
                    })
                    existing_dates.add(date_str)

            if sig != "Skip":
                prev_signal = sig

        buy_count = sum(1 for e in new_entries if e["signal"] in BUY_SIGNALS)
        print(f"  New entries: {len(new_entries)}  (buy signals: {buy_count})", flush=True)
        total_entries += len(new_entries)

        if new_entries and not dry_run:
            merged = sorted(
                existing + new_entries,
                key=lambda e: e.get("date", ""),
            )
            history[symbol] = merged

    print(f"\n{'═' * 60}")
    print(f"Buy signals found : {total_buy_signals}")
    print(f"Total new entries : {total_entries}")

    if dry_run:
        print("Dry run — no files written.")
        return

    with open(sig_path, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)

    print(f"\nSaved → {sig_path}")
    print(f"Next  → python backfill_research_db.py")


# ── CLI ────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    dry   = "--dry-run" in sys.argv
    start = BACKTEST_START
    end   = BACKTEST_END

    for arg in sys.argv[1:]:
        if arg.startswith("--start="):
            start = arg[8:]
        elif arg.startswith("--end="):
            end = arg[6:]

    run_backtest(backtest_start=start, backtest_end=end, dry_run=dry)
