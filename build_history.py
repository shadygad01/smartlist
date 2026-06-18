#!/usr/bin/env python3
"""
build_history.py — One-time backfill of signal_history.json
Fetches ~120 days of historical price data via yfinance and computes a
simplified SMC-proxy score for each stock on each trading day.
Run once: python build_history.py
"""

import json
import os
from datetime import date, timedelta

try:
    import yfinance as yf
    import pandas as pd
    import numpy as np
except ImportError:
    raise SystemExit("Run: pip install yfinance pandas numpy")

BASE = os.path.dirname(os.path.abspath(__file__))

STOCKS = [
    'TMGH.CA', 'EMFD.CA', 'PHDC.CA', 'ORHD.CA', 'HELI.CA',
    'EAST.CA', 'ABUK.CA', 'ORAS.CA', 'EFID.CA', 'HRHO.CA',
    'JUFO.CA', 'ARCC.CA', 'ORWE.CA', 'CCAP.CA',
    'MCQE.CA', 'ISPH.CA', 'RMDA.CA',
    'FWRY.CA', 'EFIH.CA', 'RAYA.CA', 'BTFH.CA',
    'COMI.CA', 'EGAL.CA', 'ADIB.CA',
    'ETEL.CA', 'GBCO.CA', 'OIH.CA',
]

DAYS_BACK = 120


def rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0).rolling(period).mean()
    loss = (-delta.clip(upper=0)).rolling(period).mean()
    rs = gain / loss.replace(0, float('nan'))
    return 100 - 100 / (1 + rs)


def score_series(close: pd.Series, volume: pd.Series) -> pd.Series:
    """
    Simplified 0-100 SMC-proxy score using:
      - RSI(14)          → 0-40 pts
      - Price vs MA20    → 0-30 pts
      - Volume trend     → 0-30 pts
    """
    r = rsi(close)

    ma20 = close.rolling(20).mean()
    price_vs_ma = ((close - ma20) / ma20 * 100).clip(-20, 20)
    ma_score = ((price_vs_ma + 20) / 40 * 30)  # 0-30

    vol_ma10 = volume.rolling(10).mean()
    vol_trend = ((volume / vol_ma10.replace(0, float('nan'))) - 1).clip(-1, 1)
    vol_score = ((vol_trend + 1) / 2 * 30)  # 0-30

    # RSI → rsi_score: peaks around RSI=65 (ideal momentum), 0 below 30 or above 85
    rsi_score = pd.Series(0.0, index=r.index)
    mask = (r >= 30) & (r <= 85)
    rsi_score[mask] = (
        40 * np.exp(-0.5 * ((r[mask] - 62) / 18) ** 2)
    )

    total = (rsi_score + ma_score + vol_score).clip(0, 100).round().astype('Int64')
    return total


def signal_from_score(s: int) -> str:
    if s >= 65:
        return 'Strong Buy'
    if s >= 35:
        return 'Wait'
    return 'Skip'


def r1_from_score(s: int) -> int:
    # r1 proxy: roughly price-position component (~30% of score)
    return min(30, int(s * 0.30))


def main():
    end   = date.today()
    start = end - timedelta(days=DAYS_BACK + 30)   # extra buffer for rolling windows

    hist_path = os.path.join(BASE, 'signal_history.json')
    history: dict = {}
    if os.path.exists(hist_path):
        with open(hist_path, encoding='utf-8') as f:
            history = json.load(f)

    for ticker in STOCKS:
        print(f"  {ticker} … ", end='', flush=True)
        try:
            df = yf.download(ticker, start=str(start), end=str(end + timedelta(1)),
                             auto_adjust=True, progress=False)
            if df.empty or 'Close' not in df.columns:
                print("no data")
                continue

            close  = df['Close'].squeeze()
            volume = df['Volume'].squeeze() if 'Volume' in df.columns else pd.Series(1, index=df.index)

            scores = score_series(close, volume)

            records = history.setdefault(ticker, [])
            existing_dates = {r['date'] for r in records}

            added = 0
            for dt, row in df.iterrows():
                d_str = dt.strftime('%Y-%m-%d')
                if d_str < str(start + timedelta(days=30)):
                    continue       # skip warm-up period
                s = int(scores.get(dt, 0) or 0)
                p = float(close.get(dt) or 0)
                entry = {
                    'date':   d_str,
                    'score':  s,
                    'price':  round(p, 2),
                    'r1':     r1_from_score(s),
                    'signal': signal_from_score(s),
                }
                if d_str in existing_dates:
                    for i, r in enumerate(records):
                        if r['date'] == d_str:
                            records[i] = entry
                            break
                else:
                    records.append(entry)
                    existing_dates.add(d_str)
                    added += 1

            records.sort(key=lambda x: x['date'])
            print(f"{added} new days, {len(records)} total")

        except Exception as e:
            print(f"error — {e}")

    with open(hist_path, 'w', encoding='utf-8') as f:
        json.dump(history, f, ensure_ascii=False, separators=(',', ':'))

    all_dates = sorted({e['date'] for v in history.values() for e in v})
    print(f"\n✅  signal_history.json written")
    print(f"   Stocks : {len(history)}")
    print(f"   Dates  : {all_dates[0] if all_dates else '—'} → {all_dates[-1] if all_dates else '—'} ({len(all_dates)} days)")


if __name__ == '__main__':
    main()
