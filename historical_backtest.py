#!/usr/bin/env python3
"""
EGX Historical Backtest Engine
================================
Replays the full SMC scanner logic on 5+ years of OHLCV data for all 29 stocks.

Design:
  - NO look-ahead bias: each signal date only uses data available up to that date
  - Signal dedup: minimum GAP_DAYS (20) trading days between signals per stock
  - Same scoring functions as live scanner (imported directly from main.py)
  - Same gates: raw_score >= 35 AND r1 >= PRICE_GATE AND cur < eq

Expected output: 1,500-4,000 signals (vs 639 in live DB)
Stored in: egx_research.db -> table hist_signals (with r20d/mfe/mae inline)

CLI:
  python historical_backtest.py            # full rebuild
  python historical_backtest.py --append   # only add missing signals
  python historical_backtest.py --symbol COMI.CA  # single stock
"""

import os, sys, json, sqlite3, time, argparse
import numpy as np
import pandas as pd
from pathlib import Path
from datetime import datetime, date

# ── Load scanner functions from main.py ───────────────────────────────────
print("[hist_backtest] Importing scanner functions from main.py...")
import main as _m

swings               = _m.swings
calc_avwap           = _m.calc_avwap
sc_price             = _m.sc_price
sc_ob                = _m.sc_ob
sc_liquidity         = _m.sc_liquidity
sc_htf               = _m.sc_htf
_sc_avwap_fn         = _m.sc_avwap
calc_macd            = _m.calc_macd
sc_macd              = _m.sc_macd
_calc_rsi            = _m._calc_rsi
sc_div               = _m.sc_div
calc_stopping_volume = _m.calc_stopping_volume
calc_volume_profile  = _m.calc_volume_profile
sc_demand_zone       = _m.sc_demand_zone

W_PRICE = _m.W_PRICE;  W_OB    = _m.W_OB;   W_LIQ  = _m.W_LIQ
W_HTF   = _m.W_HTF;    W_AVWAP = _m.W_AVWAP; W_MACD = _m.W_MACD
W_DIV   = _m.W_DIV;    W_DZ    = _m.W_DZ

WHITELIST         = set(_m.WHITELIST)
STOCK_QUALITY     = _m.STOCK_QUALITY
PRICE_GATE_NORMAL = _m.PRICE_GATE_NORMAL
PRICE_GATE_WL     = _m.PRICE_GATE_WHITELIST

# ── Config ────────────────────────────────────────────────────────────────
LOCAL_DATA_DIR = Path("historical_data/historical_data")
DB_PATH        = "egx_research.db"
MIN_WINDOW     = 110     # minimum rows before scanning starts
GAP_DAYS       = 20      # minimum trading days between signals per stock
SCORE_GATE     = 35      # Skip gate — same as live scanner
TODAY          = date.today().isoformat()

ALL_SYMBOLS = sorted(f.stem for f in LOCAL_DATA_DIR.glob("*.CA.csv"))


# ── DB Setup ──────────────────────────────────────────────────────────────

def _init_db(db_path: str, rebuild: bool = False):
    conn = sqlite3.connect(db_path)
    if rebuild:
        conn.execute("DROP TABLE IF EXISTS hist_signals")
        print("  [db] Dropped hist_signals (rebuild mode)")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS hist_signals (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol           TEXT    NOT NULL,
            signal_date      TEXT    NOT NULL,
            close_price      REAL,
            raw_score        INTEGER,
            adj_score        INTEGER,
            r1_price         INTEGER DEFAULT 0,
            r2_ob            INTEGER DEFAULT 0,
            r3_liquidity     INTEGER DEFAULT 0,
            r4_htf           INTEGER DEFAULT 0,
            r5_avwap         INTEGER DEFAULT 0,
            r6_macd          INTEGER DEFAULT 0,
            r7_div           INTEGER DEFAULT 0,
            r8_demand        INTEGER DEFAULT 0,
            sweep_detected   INTEGER DEFAULT 0,
            wick_rejection   INTEGER DEFAULT 0,
            equal_lows       INTEGER DEFAULT 0,
            htf_hh           INTEGER DEFAULT 0,
            htf_hl           INTEGER DEFAULT 0,
            rsi_div          INTEGER DEFAULT 0,
            macd_div         INTEGER DEFAULT 0,
            sv_hit           INTEGER DEFAULT 0,
            hvn_hit          INTEGER DEFAULT 0,
            sv_score         REAL    DEFAULT 0,
            hvn_score        REAL    DEFAULT 0,
            price_ok         INTEGER DEFAULT 1,
            r20d             REAL,
            mfe_20d          REAL,
            mae_20d          REAL,
            created_at       TEXT    DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(symbol, signal_date)
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_hs_sym  ON hist_signals(symbol)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_hs_date ON hist_signals(signal_date)")
    conn.commit()
    conn.close()


def _already_scanned(db_path: str, symbol: str) -> set:
    conn = sqlite3.connect(db_path)
    rows = conn.execute(
        "SELECT signal_date FROM hist_signals WHERE symbol = ?", (symbol,)
    ).fetchall()
    conn.close()
    return {r[0] for r in rows}


def _insert_signals(db_path: str, rows: list):
    if not rows:
        return
    conn = sqlite3.connect(db_path)
    conn.executemany("""
        INSERT OR IGNORE INTO hist_signals (
            symbol, signal_date, close_price,
            raw_score, adj_score,
            r1_price, r2_ob, r3_liquidity, r4_htf, r5_avwap,
            r6_macd, r7_div, r8_demand,
            sweep_detected, wick_rejection, equal_lows,
            htf_hh, htf_hl, rsi_div, macd_div,
            sv_hit, hvn_hit, sv_score, hvn_score, price_ok,
            r20d, mfe_20d, mae_20d
        ) VALUES (
            :symbol, :signal_date, :close_price,
            :raw_score, :adj_score,
            :r1_price, :r2_ob, :r3_liquidity, :r4_htf, :r5_avwap,
            :r6_macd, :r7_div, :r8_demand,
            :sweep_detected, :wick_rejection, :equal_lows,
            :htf_hh, :htf_hl, :rsi_div, :macd_div,
            :sv_hit, :hvn_hit, :sv_score, :hvn_score, :price_ok,
            :r20d, :mfe_20d, :mae_20d
        )
    """, rows)
    conn.commit()
    conn.close()


# ── OHLCV Loader ──────────────────────────────────────────────────────────

def _load_ohlcv(symbol: str) -> pd.DataFrame:
    path = LOCAL_DATA_DIR / f"{symbol}.csv"
    if not path.exists():
        return pd.DataFrame()
    df = pd.read_csv(path, parse_dates=["Date"], index_col="Date")
    df.index = pd.DatetimeIndex(df.index).tz_localize(None)
    df = df.sort_index()
    for c in ["Open", "High", "Low", "Close", "Volume"]:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    return df.dropna(subset=["Close", "High", "Low"])


# ── Signal Scoring ────────────────────────────────────────────────────────

def _score_day(df_slice: pd.DataFrame, symbol: str) -> dict | None:
    """
    Run full SMC scoring on df_slice (all data up to and including signal date).
    Returns None if not qualifying. No look-ahead bias — df_slice must not include
    any row after the signal date.
    """
    if len(df_slice) < 20:
        return None
    try:
        cur = float(df_slice["Close"].iloc[-1])
        if not np.isfinite(cur) or cur <= 0:
            return None

        hi, lo, eq, buy_hi, sell_lo = swings(df_slice)

        # Gate 0: discount zone
        if cur >= eq:
            return None

        # r1 fast-fail before expensive components
        r1, l1 = sc_price(cur, lo, hi, eq, buy_hi, sell_lo)
        price_gate = PRICE_GATE_WL if symbol in WHITELIST else PRICE_GATE_NORMAL
        if r1 < price_gate:
            return None

        r2, l2 = sc_ob(df_slice, cur, eq, lo, buy_hi)
        r3, l3 = sc_liquidity(df_slice, cur)
        r4, l4 = sc_htf(df_slice)

        av, alo = calc_avwap(df_slice)
        r5, l5  = _sc_avwap_fn(cur, av, alo)

        close       = df_slice["Close"]
        macd_result = calc_macd(close)
        ml          = macd_result[0]
        r6, l6      = sc_macd(close, _macd=macd_result)
        r7, l7      = sc_div(close, ml)

        sv_result  = calc_stopping_volume(df_slice, eq, lo)
        hvn_result = calc_volume_profile(df_slice, eq, lo, buy_hi)
        r8, l8     = sc_demand_zone(df_slice, eq, lo, buy_hi,
                                    _sv=sv_result, _hvn=hvn_result)

        raw_score = min(r1 + r2 + r3 + r4 + r5 + r6 + r7 + r8, 100)
        if raw_score < SCORE_GATE:
            return None

        stock_mult = STOCK_QUALITY.get(symbol, 1.0)
        adj_score  = min(int(round(raw_score * stock_mult)), 100)

        return {
            "raw_score": raw_score,
            "adj_score": adj_score,
            "r1_price":    r1, "r2_ob":      r2,
            "r3_liquidity":r3, "r4_htf":     r4,
            "r5_avwap":    r5, "r6_macd":    r6,
            "r7_div":      r7, "r8_demand":  r8,
            "close_price": cur,
            "sweep_detected": int("Sweep & Reverse" in l3),
            "wick_rejection":  int("ejection wick" in l3 or "wick" in l3.lower() and "No" not in l3),
            "equal_lows":      int("Equal Lows" in l3),
            "htf_hh": int("HH+HL structure confirmed" in l4),
            "htf_hl": int("HH+HL structure confirmed" in l4 or "Partial structure (HH:" in l4),
            "rsi_div":  int("RSI div" in l7 or "RSI Div" in l7),
            "macd_div": int("MACD div" in l7 or "MACD Div" in l7),
            "sv_hit":   int(bool(sv_result[0])  if sv_result  else False),
            "hvn_hit":  int(bool(hvn_result[0]) if hvn_result else False),
            "sv_score":  round(float(sv_result[1]),  3) if sv_result  else 0.0,
            "hvn_score": round(float(hvn_result[1]), 3) if hvn_result else 0.0,
            "price_ok":  1,
        }
    except Exception:
        return None


# ── Forward Returns ────────────────────────────────────────────────────────

def _outcomes(full_df: pd.DataFrame, t: int, horizon: int = 20) -> tuple:
    """r20d, mfe_20d, mae_20d — all measured from day t+1 onwards (no look-ahead)."""
    entry = float(full_df["Close"].iloc[t])
    end   = min(t + horizon + 1, len(full_df))
    fut   = full_df.iloc[t + 1: end]

    if len(fut) < 5:
        return None, None, None

    closes = fut["Close"].values.astype(float)
    highs  = fut["High"].values.astype(float)  if "High" in fut.columns else closes
    lows   = fut["Low"].values.astype(float)   if "Low"  in fut.columns else closes

    r20d = round((float(fut["Close"].iloc[-1]) - entry) / entry, 4)
    mfe  = round((float(np.nanmax(highs)) - entry) / entry, 4)
    mae  = round((float(np.nanmin(lows))  - entry) / entry, 4)
    return r20d, mfe, mae


# ── Per-Stock Scan ────────────────────────────────────────────────────────

def _scan_symbol(symbol: str, skip_dates: set, verbose: bool = True) -> list:
    df = _load_ohlcv(symbol)
    if df.empty or len(df) < MIN_WINDOW:
        if verbose:
            print(f"  {symbol:<12}    0 signals  (insufficient data: {len(df)} rows)")
        return []

    signals  = []
    n        = len(df)
    last_sig = -GAP_DAYS - 1   # allow signal from first eligible day

    for t in range(MIN_WINDOW, n):
        # Dedup: enforce minimum gap between signals
        if t - last_sig < GAP_DAYS:
            continue

        signal_date = df.index[t].strftime("%Y-%m-%d")
        if signal_date in skip_dates:
            last_sig = t
            continue

        # All data up to (and including) day t — no look-ahead
        df_slice = df.iloc[: t + 1]

        scores = _score_day(df_slice, symbol)
        if scores is None:
            continue

        r20d, mfe, mae = _outcomes(df, t, horizon=20)
        if r20d is None:
            continue          # not enough future data (near end of history)

        row = {
            "symbol":      symbol,
            "signal_date": signal_date,
            **scores,
            "r20d":    r20d,
            "mfe_20d": mfe,
            "mae_20d": mae,
        }
        signals.append(row)
        last_sig = t

    if verbose:
        print(f"  {symbol:<12} {len(signals):>4} signals")
    return signals


# ── Metrics ───────────────────────────────────────────────────────────────

def _metrics(rows: list) -> dict:
    r20ds = [r["r20d"]    for r in rows if r.get("r20d")    is not None]
    mfes  = [r["mfe_20d"] for r in rows if r.get("mfe_20d") is not None]
    maes  = [r["mae_20d"] for r in rows if r.get("mae_20d") is not None]
    if not r20ds:
        return {}
    wins   = sum(1 for v in r20ds if v >= 0.07)
    gains  = [v for v in r20ds if v > 0]
    losses = [v for v in r20ds if v < 0]
    pf     = round(sum(gains) / max(abs(sum(losses)), 1e-9), 3)
    return {
        "n":      len(r20ds),
        "mean":   round(float(np.mean(r20ds)), 4),
        "median": round(float(np.median(r20ds)), 4),
        "wr":     round(wins / len(r20ds), 4),
        "pf":     pf,
        "mfe":    round(float(np.mean(mfes)), 4) if mfes else 0,
        "mae":    round(float(np.mean(maes)), 4) if maes else 0,
        "std":    round(float(np.std(r20ds)), 4),
    }


def _flag_metrics(rows: list, flag: str) -> dict:
    yes = [r for r in rows if r.get(flag) == 1 and r.get("r20d") is not None]
    no  = [r for r in rows if r.get(flag) == 0 and r.get("r20d") is not None]
    return {"flag": flag, "yes": _metrics(yes), "no": _metrics(no)}


# ── Load from DB ──────────────────────────────────────────────────────────

def _load_hist_signals(db_path: str) -> list:
    cols = [
        "id", "symbol", "signal_date", "close_price",
        "raw_score", "adj_score",
        "r1_price", "r2_ob", "r3_liquidity", "r4_htf",
        "r5_avwap", "r6_macd", "r7_div", "r8_demand",
        "sweep_detected", "wick_rejection", "equal_lows",
        "htf_hh", "htf_hl", "rsi_div", "macd_div",
        "sv_hit", "hvn_hit", "sv_score", "hvn_score", "price_ok",
        "r20d", "mfe_20d", "mae_20d",
    ]
    conn = sqlite3.connect(db_path)
    try:
        rows = conn.execute(
            f"SELECT {', '.join(cols)} FROM hist_signals WHERE r20d IS NOT NULL"
        ).fetchall()
    except Exception:
        rows = []
    conn.close()
    return [dict(zip(cols, r)) for r in rows]


# ── HTML Report ───────────────────────────────────────────────────────────

def _fmt(v):
    return f"{v*100:+.2f}%" if v is not None else "—"


def _flag_row(label, fm):
    y, n = fm["yes"], fm["no"]
    if not y or not n:
        return ""
    diff = y.get("mean", 0) - n.get("mean", 0)
    color = "#155724" if diff > 0.005 else "#721c24" if diff < -0.005 else "#666"
    arrow = "▲" if diff > 0.005 else "▼" if diff < -0.005 else "~"
    return (f"<tr>"
            f"<td style='padding:8px 12px;font-size:13px;'>{label}</td>"
            f"<td style='padding:8px 12px;text-align:center;font-size:13px;font-weight:700;'>{y.get('n',0)}</td>"
            f"<td style='padding:8px 12px;text-align:center;font-size:13px;font-weight:700;'>{_fmt(y.get('mean'))}</td>"
            f"<td style='padding:8px 12px;text-align:center;font-size:13px;'>{n.get('n',0)}</td>"
            f"<td style='padding:8px 12px;text-align:center;font-size:13px;'>{_fmt(n.get('mean'))}</td>"
            f"<td style='padding:8px 12px;text-align:center;font-size:13px;font-weight:700;color:{color};'>{arrow} {_fmt(diff)}</td>"
            f"<td style='padding:8px 12px;text-align:center;font-size:12px;'>{y.get('pf',0):.2f}</td>"
            f"</tr>")


def _sym_row(i, sym, m):
    c = "#155724" if m.get("mean", 0) > 0.05 else "#856404" if m.get("mean", 0) > 0 else "#721c24"
    bg = "background:#f9f9f9;" if i % 2 else ""
    return (f"<tr style='{bg}'>"
            f"<td style='padding:7px 10px;font-size:12px;font-weight:600;'>{sym}</td>"
            f"<td style='padding:7px 10px;text-align:center;font-size:12px;'>{m.get('n',0)}</td>"
            f"<td style='padding:7px 10px;text-align:center;font-size:12px;font-weight:700;color:{c};'>{_fmt(m.get('mean'))}</td>"
            f"<td style='padding:7px 10px;text-align:center;font-size:12px;'>{_fmt(m.get('mfe'))}</td>"
            f"<td style='padding:7px 10px;text-align:center;font-size:12px;'>{m.get('wr',0)*100:.0f}%</td>"
            f"<td style='padding:7px 10px;text-align:center;font-size:12px;'>{m.get('pf',0):.2f}</td>"
            f"</tr>")


def build_html(all_rows, base_live, flag_analysis, sym_perf, elapsed, n_new):
    base = _metrics(all_rows)
    n    = base.get("n", 0)
    hc   = "#155724" if base.get("mean", 0) > 0.04 else "#856404" if base.get("mean", 0) > 0 else "#721c24"

    kpis = ""
    for label, val, color in [
        ("Total Signals",  f"{n:,}",                                "#1a3c5e"),
        ("Avg Return",     f"{base.get('mean',0)*100:+.2f}%",       hc),
        ("MFE (20d)",      f"{base.get('mfe',0)*100:.1f}%",         "#155724"),
        ("Win Rate (≥7%)", f"{base.get('wr',0)*100:.1f}%",          hc),
        ("Profit Factor",  f"{base.get('pf',0):.2f}",               "#155724" if base.get("pf",0)>2 else "#856404"),
        ("vs Live Signals",f"{n:,} vs {base_live.get('n',639)}",    "#333"),
    ]:
        kpis += (f"<div style='flex:1;min-width:110px;text-align:center;padding:10px 6px;"
                 f"background:#f7faff;border-radius:7px;margin:4px;'>"
                 f"<div style='font-size:10px;color:#888;text-transform:uppercase;letter-spacing:.8px;margin-bottom:4px;'>{label}</div>"
                 f"<div style='font-size:19px;font-weight:700;color:{color};'>{val}</div>"
                 f"</div>")

    comp_rows = ""
    for metric, lv, hv in [
        ("N Signals",     str(base_live.get("n", 639)),                  f"{n:,}"),
        ("Avg Return",    f"{base_live.get('mean',0)*100:.2f}%",          f"{base.get('mean',0)*100:.2f}%"),
        ("MFE (20d)",     f"{base_live.get('mfe',0)*100:.1f}%",          f"{base.get('mfe',0)*100:.1f}%"),
        ("Win Rate (≥7%)",f"{base_live.get('wr',0)*100:.1f}%",           f"{base.get('wr',0)*100:.1f}%"),
        ("Profit Factor", f"{base_live.get('pf',0):.2f}",                f"{base.get('pf',0):.2f}"),
        ("MAE (20d)",     f"{base_live.get('mae',0)*100:.1f}%",          f"{base.get('mae',0)*100:.1f}%"),
    ]:
        comp_rows += (f"<tr><td style='padding:8px 12px;font-size:13px;'>{metric}</td>"
                      f"<td style='padding:8px 12px;text-align:center;font-size:13px;'>{lv}</td>"
                      f"<td style='padding:8px 12px;text-align:center;font-size:13px;font-weight:700;'>{hv}</td></tr>")

    flag_rows = "".join(_flag_row(fm["flag"].replace("_", " ").title(), fm) for fm in flag_analysis)
    sym_sorted = sorted(sym_perf.items(), key=lambda x: x[1].get("mean", 0), reverse=True)
    sym_rows   = "".join(_sym_row(i, sym, m) for i, (sym, m) in enumerate(sym_sorted))

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>EGX Historical Backtest — {TODAY}</title>
  <style>
    *{{box-sizing:border-box;margin:0;padding:0;}}
    body{{font-family:'Segoe UI',Arial,sans-serif;background:#f0f2f5;color:#222;padding:0;}}
    .header{{background:linear-gradient(135deg,#1a3c5e,#2a6496);color:#fff;padding:22px 28px;}}
    .header h1{{font-size:1.4em;margin:0 0 4px;}}
    .header .sub{{font-size:.82em;opacity:.75;}}
    .container{{max-width:1000px;margin:22px auto;padding:0 14px;}}
    .card{{background:#fff;border-radius:10px;box-shadow:0 2px 12px rgba(0,0,0,.08);
           padding:22px 24px;margin-bottom:20px;}}
    .card h2{{font-size:15px;font-weight:700;color:#1a3c5e;margin-bottom:14px;border-bottom:2px solid #e8f0fe;padding-bottom:8px;}}
    table{{width:100%;border-collapse:collapse;}}
    th{{background:#1a3c5e;color:#fff;padding:10px 12px;text-align:left;font-size:12px;}}
    th.r{{text-align:center;}}
    tr:hover{{background:#f5f8ff;}}
    .note{{margin-top:10px;font-size:11px;color:#888;line-height:1.5;}}
    .footer{{text-align:center;color:#aaa;font-size:11px;padding:20px 0 30px;}}
  </style>
</head>
<body>
<div class="header">
  <h1>🏛️ EGX Historical Backtest Engine</h1>
  <div class="sub">Full SMC scanner replay · 5+ years OHLCV · 29 stocks · {n:,} signals · {TODAY} · {elapsed:.0f}s runtime</div>
</div>
<div class="container">

<div class="card">
  <h2>📊 Baseline Performance — {n:,} Historical Signals</h2>
  <div style="display:flex;flex-wrap:wrap;gap:4px;">{kpis}</div>
  <div class="note">
    Method: rolling scan of all {len(ALL_SYMBOLS)} stocks × full OHLCV history | Gate: raw_score≥35 + price_ok + discount_zone |
    Dedup: {GAP_DAYS} trading-day minimum between signals per stock | Forward return: 20 trading days from signal close
  </div>
</div>

<div class="card">
  <h2>🔄 Live DB vs Historical Backtest — Consistency Check</h2>
  <table>
    <tr><th>Metric</th><th class="r">Live DB ({base_live.get("n",639)} signals)</th><th class="r">Historical ({n:,} signals)</th></tr>
    {comp_rows}
  </table>
  <div class="note">
    ✅ If historical ≈ live DB → signals are statistically consistent, patterns are real.<br>
    ⚠️ Large divergence → live signals may be biased (timing, market cycle, selection).
  </div>
</div>

<div class="card">
  <h2>🚩 Binary Flag Analysis — Statistical Power from {n:,} Signals</h2>
  <table>
    <tr>
      <th>Flag</th>
      <th class="r">n (YES)</th><th class="r">Return (YES)</th>
      <th class="r">n (NO)</th><th class="r">Return (NO)</th>
      <th class="r">Δ Return</th><th class="r">PF (YES)</th>
    </tr>
    {flag_rows}
  </table>
  <div class="note">
    ▲ = flag adds return vs baseline | ▼ = flag hurts | ~ = negligible difference.<br>
    Findings consistent across both live DB (639) AND historical ({n:,}) are actionable.
  </div>
</div>

<div class="card">
  <h2>📈 Performance by Symbol — All Historical Signals</h2>
  <table>
    <tr>
      <th>Symbol</th><th class="r">Signals</th><th class="r">Avg Return</th>
      <th class="r">MFE</th><th class="r">Win Rate</th><th class="r">PF</th>
    </tr>
    {sym_rows}
  </table>
</div>

</div>
<div class="footer">EGX Historical Backtest Engine v1.0 · {n_new} new signals added this run · {TODAY}</div>
</body>
</html>"""


# ── Main ──────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--append",  action="store_true", help="Skip already-scanned dates")
    parser.add_argument("--symbol",  default=None,        help="Scan single symbol only")
    parser.add_argument("--no-html", action="store_true", help="Skip HTML report")
    args = parser.parse_args()

    rebuild = not args.append
    symbols = [args.symbol] if args.symbol else ALL_SYMBOLS

    t0 = time.time()
    print(f"\n[hist_backtest] EGX Historical Backtest Engine")
    print(f"  Mode:    {'rebuild' if rebuild else 'append'}")
    print(f"  Stocks:  {len(symbols)}")
    print(f"  Gate:    raw_score≥{SCORE_GATE}, price_ok, discount_zone")
    print(f"  Dedup:   {GAP_DAYS} trading days\n")

    _init_db(DB_PATH, rebuild=rebuild)

    total_new = 0
    for sym in symbols:
        skip = _already_scanned(DB_PATH, sym) if args.append else set()
        rows = _scan_symbol(sym, skip_dates=skip, verbose=True)
        _insert_signals(DB_PATH, rows)
        total_new += len(rows)

    elapsed = time.time() - t0
    print(f"\n[hist_backtest] Scan done in {elapsed:.1f}s — {total_new} new signals added")

    all_rows = _load_hist_signals(DB_PATH)
    base     = _metrics(all_rows)
    print(f"  DB total: {base.get('n',0):,} | avg={base.get('mean',0)*100:.2f}% "
          f"| MFE={base.get('mfe',0)*100:.1f}% | PF={base.get('pf',0):.2f} "
          f"| WR={base.get('wr',0)*100:.1f}%")

    # Live signals for comparison
    try:
        conn = sqlite3.connect(DB_PATH)
        live_rows = conn.execute("""
            SELECT b.r20d, b.mfe_20d, b.mae_20d
            FROM signals s JOIN bottom_quality b ON b.signal_id = s.id
            WHERE b.r20d IS NOT NULL
        """).fetchall()
        conn.close()
        live_list = [{"r20d": r[0], "mfe_20d": r[1], "mae_20d": r[2]} for r in live_rows]
        live_base = _metrics(live_list)
    except Exception:
        live_base = {"n": 639, "mean": 0.046, "mfe": 0.131, "wr": 0.454, "pf": 2.49, "mae": -0.071}

    flags = ["sweep_detected", "wick_rejection", "equal_lows",
             "htf_hh", "htf_hl", "rsi_div", "macd_div", "sv_hit", "hvn_hit"]
    flag_analysis = [_flag_metrics(all_rows, f) for f in flags]

    print(f"\n  Binary Flag Analysis ({base.get('n',0):,} historical signals):")
    print(f"  {'Flag':<20} {'n(YES)':>7} {'ret(YES)':>9} {'n(NO)':>7} {'ret(NO)':>9} {'Δ':>8}")
    for fm in flag_analysis:
        y, n_ = fm["yes"], fm["no"]
        if y and n_:
            diff = y.get("mean", 0) - n_.get("mean", 0)
            print(f"  {fm['flag']:<20} {y.get('n',0):>7} {y.get('mean',0)*100:>+8.2f}%"
                  f" {n_.get('n',0):>7} {n_.get('mean',0)*100:>+8.2f}% {diff*100:>+7.2f}%")

    sym_perf = {}
    for sym in sorted(set(r["symbol"] for r in all_rows)):
        sym_perf[sym] = _metrics([r for r in all_rows if r["symbol"] == sym])

    out = {
        "generated_at":   TODAY,
        "engine_version": "1.0",
        "n_signals":      base.get("n", 0),
        "n_new_this_run": total_new,
        "elapsed_s":      round(elapsed, 1),
        "baseline":       base,
        "live_baseline":  live_base,
        "flag_analysis":  flag_analysis,
        "symbol_perf":    {k: v for k, v in sorted(sym_perf.items(),
                           key=lambda x: x[1].get("mean", 0), reverse=True)},
    }
    with open("historical_backtest_results.json", "w") as f:
        json.dump(out, f, indent=2, ensure_ascii=False)
    print(f"\n  JSON → historical_backtest_results.json")

    if not args.no_html:
        html  = build_html(all_rows, live_base, flag_analysis, sym_perf, elapsed, total_new)
        fname = f"historical_backtest_report_{TODAY}.html"
        with open(fname, "w", encoding="utf-8") as f:
            f.write(html)
        print(f"  HTML → {fname}")

    print(f"\n[hist_backtest] Done.\n")
    return out


if __name__ == "__main__":
    main()
