#!/usr/bin/env python3
"""
Price Gate Alpha Audit
======================
Evaluates whether the Price Gate (r1 >= PRICE_GATE) adds, protects, or suppresses alpha.

Tests:
  1. Current Gate vs No Gate — side-by-side
  2. Gate Survivors vs Gate Rejects — which has better outcomes?
  3. Whitelist vs Non-Whitelist — is whitelist thesis validated?
  4. Dynamic Gate Study — 5 gate models ranked by alpha quality

Source of truth: SOURCE_OF_TRUTH.md
Mission: Bottom Quality → Fibonacci Expansion → Long-Term Upside
Primary success metrics: MFE, Peak Return, Expectancy (NOT short-term WR)

DO NOT MODIFY PRODUCTION CODE.
DO NOT MODIFY WEIGHTS.
DO NOT MODIFY THRESHOLDS.
"""

import os, sys, warnings
import numpy as np
import pandas as pd
from pathlib import Path
from collections import defaultdict

warnings.filterwarnings("ignore")

print("[alpha_audit] Importing scanner functions from main.py...")
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
sc_div               = _m.sc_div
calc_stopping_volume = _m.calc_stopping_volume
calc_volume_profile  = _m.calc_volume_profile
sc_demand_zone       = _m.sc_demand_zone

W_PRICE = _m.W_PRICE;  W_OB    = _m.W_OB;   W_LIQ  = _m.W_LIQ
W_HTF   = _m.W_HTF;    W_AVWAP = _m.W_AVWAP; W_MACD = _m.W_MACD
W_DIV   = _m.W_DIV;    W_DZ    = _m.W_DZ

WHITELIST            = set(_m.WHITELIST)
STOCK_QUALITY        = _m.STOCK_QUALITY
PRICE_GATE_NORMAL    = _m.PRICE_GATE_NORMAL
PRICE_GATE_WHITELIST = _m.PRICE_GATE_WHITELIST

LOCAL_DATA_DIR  = Path("historical_data/historical_data")
MIN_WINDOW      = 110
GAP_DAYS        = 20
SCORE_GATE      = 35
MFE_WIN_THR     = 0.07   # 7% = MIN_GAIN; used for WR computation

ALL_SYMBOLS = sorted(f.stem for f in LOCAL_DATA_DIR.glob("*.CA.csv"))


# ── OHLCV Loader ──────────────────────────────────────────────────────────────

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


# ── Forward Return Computation ─────────────────────────────────────────────────

def _forward_returns(full_df: pd.DataFrame, t: int):
    """
    Compute MFE and MAE at 40, 90, 252 trading-day windows.
    Only returns values where enough future data exists.
    Uses actual High/Low (no look-ahead — data after t+1).
    """
    n = len(full_df)
    entry = float(full_df["Close"].iloc[t])
    if entry <= 0:
        return {}

    def _window(days):
        end = min(t + days + 1, n)
        fut = full_df.iloc[t + 1: end]
        if len(fut) < max(5, days // 2):
            return None, None
        highs = fut["High"].values.astype(float)
        lows  = fut["Low"].values.astype(float)
        mfe   = round((float(np.nanmax(highs)) - entry) / entry, 4)
        mae   = round((float(np.nanmin(lows))  - entry) / entry, 4)
        return mfe, mae

    result = {}
    mfe40, mae40 = _window(40)
    if mfe40 is not None:
        result["mfe_40d"] = mfe40
        result["mae_40d"] = mae40

    mfe90, mae90 = _window(90)
    if mfe90 is not None:
        result["mfe_90d"] = mfe90
        result["mae_90d"] = mae90

    mfe252, mae252 = _window(252)
    if mfe252 is not None:
        result["mfe_252d"] = mfe252
        result["mae_252d"] = mae252
        result["peak_1y"]  = mfe252   # same as mfe_252d (≈ 1 trading year)

    return result


# ── Full Scoring Without Price Gate Fast-Fail ─────────────────────────────────

def _score_full(df_slice: pd.DataFrame, symbol: str):
    """Returns (above_eq, r1, total_score) or None on error."""
    if len(df_slice) < 20:
        return None
    try:
        cur = float(df_slice["Close"].iloc[-1])
        if not np.isfinite(cur) or cur <= 0:
            return None
        hi, lo, eq, buy_hi, sell_lo = swings(df_slice)

        if cur >= eq:
            return ("above_eq",)

        r1, _ = sc_price(cur, lo, hi, eq, buy_hi, sell_lo)
        r2, _ = sc_ob(df_slice, cur, eq, lo, buy_hi)
        r3, _ = sc_liquidity(df_slice, cur)
        r4, _ = sc_htf(df_slice)

        av, alo = calc_avwap(df_slice)
        r5, _   = _sc_avwap_fn(cur, av, alo)

        close       = df_slice["Close"]
        macd_result = calc_macd(close)
        ml          = macd_result[0]
        r6, _       = sc_macd(close, _macd=macd_result)
        r7, _       = sc_div(close, ml)

        sv_result  = calc_stopping_volume(df_slice, eq, lo)
        hvn_result = calc_volume_profile(df_slice, eq, lo, buy_hi)
        r8, _      = sc_demand_zone(df_slice, eq, lo, buy_hi,
                                    _sv=sv_result, _hvn=hvn_result)

        total = min(r1 + r2 + r3 + r4 + r5 + r6 + r7 + r8, 100)
        return ("ok", r1, r2, r3, r4, r5, r6, r7, r8, total)
    except Exception:
        return None


# ── Candidate Collection ──────────────────────────────────────────────────────

def collect_candidates():
    """
    Scans all CSVs. Returns list of dicts — one per DZ bar with total_score >= 35.
    No price gate applied. Forward returns computed from CSV data.
    """
    candidates = []

    for i, symbol in enumerate(ALL_SYMBOLS, 1):
        print(f"  [{i:2d}/{len(ALL_SYMBOLS)}] {symbol:<12}", end=" ", flush=True)
        df = _load_ohlcv(symbol)
        n  = len(df)
        if n < MIN_WINDOW:
            print("skipped")
            continue

        count = 0
        for t in range(MIN_WINDOW, n):
            df_slice = df.iloc[:t + 1]
            res = _score_full(df_slice, symbol)
            if res is None or res[0] == "above_eq":
                continue

            _, r1, r2, r3, r4, r5, r6, r7, r8, total = res
            if total < SCORE_GATE:
                continue

            fwd = _forward_returns(df, t)
            if not fwd:
                continue   # too near end of CSV

            stock_mult = STOCK_QUALITY.get(symbol, 1.0)
            adj_score  = min(int(round(total * stock_mult)), 100)

            candidates.append({
                "symbol":     symbol,
                "idx":        t,
                "date":       str(df.index[t].date()),
                "r1":         r1,
                "total":      total,
                "adj_score":  adj_score,
                "in_wl":      symbol in WHITELIST,
                **fwd,
            })
            count += 1

        print(f"{count:4d} candidates")

    return candidates


# ── Statistics Engine ─────────────────────────────────────────────────────────

WIN_THR = MFE_WIN_THR

def _stats(group: list, label: str) -> dict:
    """Compute all required alpha metrics for a group of candidate dicts."""
    n = len(group)
    if n == 0:
        return {"label": label, "n": 0,
                "wr_mfe40": None, "exp_mfe40": None,
                "avg_mfe90": None, "avg_mfe252": None, "avg_peak1y": None,
                "sharpe": None, "avg_mae40": None, "worst_mae40": None}

    mfe40  = [c["mfe_40d"]  for c in group if "mfe_40d"  in c]
    mfe90  = [c["mfe_90d"]  for c in group if "mfe_90d"  in c]
    mfe252 = [c["mfe_252d"] for c in group if "mfe_252d" in c]
    peak1y = [c["peak_1y"]  for c in group if "peak_1y"  in c]
    mae40  = [c["mae_40d"]  for c in group if "mae_40d"  in c]

    wr_mfe40  = round(sum(1 for v in mfe40 if v >= WIN_THR) / len(mfe40) * 100, 1) if mfe40 else None
    exp_mfe40 = round(np.mean(mfe40)  * 100, 2) if mfe40 else None
    avg_mfe90 = round(np.mean(mfe90)  * 100, 2) if mfe90 else None
    avg_mfe252= round(np.mean(mfe252) * 100, 2) if mfe252 else None
    avg_peak1y= round(np.mean(peak1y) * 100, 2) if peak1y else None
    avg_mae40 = round(np.mean(mae40)  * 100, 2) if mae40 else None
    worst_mae40=round(min(mae40)      * 100, 2) if mae40 else None

    sharpe = None
    if mfe40 and len(mfe40) >= 5:
        mu  = np.mean(mfe40)
        sig = np.std(mfe40, ddof=1)
        sharpe = round(mu / sig, 3) if sig > 0 else None

    return {
        "label":       label,
        "n":           n,
        "wr_mfe40":    wr_mfe40,
        "exp_mfe40":   exp_mfe40,
        "avg_mfe90":   avg_mfe90,
        "avg_mfe252":  avg_mfe252,
        "avg_peak1y":  avg_peak1y,
        "sharpe":      sharpe,
        "avg_mae40":   avg_mae40,
        "worst_mae40": worst_mae40,
    }


def _print_stats(s: dict):
    def fmt(v, suffix="%"): return f"{v:+.2f}{suffix}" if v is not None else "  n/a  "
    def fmtwr(v): return f"{v:.1f}%" if v is not None else "  n/a  "
    def fmtsh(v): return f"{v:.3f}" if v is not None else "  n/a  "
    print(f"  {'Label':<28}: {s['label']}")
    print(f"  {'Signals Count':<28}: {s['n']:,}")
    print(f"  {'mfe_40d WR (>= 7%)':<28}: {fmtwr(s['wr_mfe40'])}")
    print(f"  {'mfe_40d Expectancy':<28}: {fmt(s['exp_mfe40'])}")
    print(f"  {'mfe_90d Avg Return':<28}: {fmt(s['avg_mfe90'])}")
    print(f"  {'mfe_252d Avg Return':<28}: {fmt(s['avg_mfe252'])}")
    print(f"  {'Peak_1Y Avg Return':<28}: {fmt(s['avg_peak1y'])}")
    print(f"  {'Sharpe (mfe40/std)':<28}: {fmtsh(s['sharpe'])}")
    print(f"  {'Avg MAE_40d (downside)':<28}: {fmt(s['avg_mae40'])}")
    print(f"  {'Worst MAE_40d':<28}: {fmt(s['worst_mae40'])}")


def _compare_row(a: dict, b: dict, key: str, higher_better=True):
    va, vb = a.get(key), b.get(key)
    if va is None or vb is None:
        return "  n/a"
    delta = vb - va
    sign  = "+" if delta > 0 else ""
    arrow = "▲" if (delta > 0) == higher_better else "▼"
    return f"  {arrow}{sign}{delta:.2f}"


# ── Gate Model Dedup Simulation ────────────────────────────────────────────────

def _apply_gate_with_dedup(candidates: list, gate_fn) -> list:
    """
    Filter candidates through gate_fn, then apply GAP_DAYS dedup per symbol.
    gate_fn(cand) -> bool: True means the candidate passes the gate.
    """
    # Sort by symbol + date (candidates are already appended in date order per symbol)
    by_sym = defaultdict(list)
    for c in candidates:
        by_sym[c["symbol"]].append(c)

    result = []
    for sym_cands in by_sym.values():
        last_idx = -GAP_DAYS - 1
        for c in sym_cands:
            if not gate_fn(c):
                continue
            if c["idx"] - last_idx < GAP_DAYS:
                continue
            last_idx = c["idx"]
            result.append(c)
    return result


# ── Gate Models ───────────────────────────────────────────────────────────────

def _gate_current(c):
    gate = PRICE_GATE_WHITELIST if c["in_wl"] else PRICE_GATE_NORMAL
    return c["r1"] >= gate

def _gate_25pct(c):    return c["r1"] >= 0.25 * W_PRICE

def _gate_50pct(c):    return c["r1"] >= 0.50 * W_PRICE

def _gate_75pct(c):    return c["r1"] >= 0.75 * W_PRICE

def _gate_none(c):     return True


# ── Main Audit ────────────────────────────────────────────────────────────────

def run_audit():
    print(f"\n{'='*65}")
    print(f"  PRICE GATE ALPHA AUDIT")
    print(f"  SOURCE: SOURCE_OF_TRUTH.md — Bottom Quality → Fibonacci → Long-Term Upside")
    print(f"  W_PRICE={W_PRICE:.4f} | PRICE_GATE_NORMAL={PRICE_GATE_NORMAL} | PRICE_GATE_WL={PRICE_GATE_WHITELIST}")
    print(f"  MAX r1 achievable = {W_PRICE:.2f} | Gate NORMAL needs {PRICE_GATE_NORMAL} | Gate WL needs {PRICE_GATE_WHITELIST}")
    print(f"  Gate passes r1 < max? NORMAL={'NO' if W_PRICE < PRICE_GATE_NORMAL else 'YES'} | WL={'NO' if W_PRICE < PRICE_GATE_WHITELIST else 'YES'}")
    print(f"{'='*65}\n")

    # ── Collect all candidates ────────────────────────────────────────────────
    print("Scanning all CSVs (no price gate fast-fail)...\n")
    candidates = collect_candidates()
    total_cands = len(candidates)
    print(f"\nTotal candidates (DZ + score>=35 + fwd data): {total_cands:,}")

    if total_cands == 0:
        print("ERROR: no candidates found")
        return

    # ── TEST 1: Current Gate vs No Gate ──────────────────────────────────────
    print(f"\n{'='*65}")
    print(f"  TEST 1 — CURRENT GATE vs NO GATE")
    print(f"  (raw candidates, no dedup)")
    print(f"{'='*65}")

    # Scenario A: current gate (r1 >= PRICE_GATE)
    scen_a = [c for c in candidates if _gate_current(c)]
    # Scenario B: no gate (all candidates)
    scen_b = candidates

    sa = _stats(scen_a, "Scenario A — Current Gate (r1 >= PRICE_GATE)")
    sb = _stats(scen_b, "Scenario B — No Gate (all DZ + score>=35)")

    print(f"\n{'─'*65}")
    print(f"  SCENARIO A — CURRENT GATE (r1 >= {PRICE_GATE_NORMAL}/{PRICE_GATE_WHITELIST})")
    print(f"{'─'*65}")
    _print_stats(sa)

    print(f"\n{'─'*65}")
    print(f"  SCENARIO B — NO GATE (all {total_cands:,} candidates)")
    print(f"{'─'*65}")
    _print_stats(sb)

    print(f"\n  VERDICT:")
    if sa["n"] == 0:
        print(f"  Current gate admits ZERO signals (r1 max={W_PRICE:.2f} < gate {PRICE_GATE_NORMAL}).")
        print(f"  Gate is not protecting alpha — it is ELIMINATING alpha entirely.")
        print(f"  TEST 1 VERDICT: Current gate = ALPHA DESTROYING (blocks 100% of candidates)")
    else:
        diff_exp = (sb["exp_mfe40"] or 0) - (sa["exp_mfe40"] or 0)
        if diff_exp > 0:
            print(f"  Removing gate adds +{diff_exp:.2f}% expectancy. Gate reduces alpha.")
        elif diff_exp < 0:
            print(f"  Removing gate reduces expectancy by {abs(diff_exp):.2f}%. Gate protects alpha.")
        else:
            print(f"  No material expectancy difference. Gate is neutral.")

    # ── TEST 2: Gate Survivors vs Gate Rejects ────────────────────────────────
    print(f"\n{'='*65}")
    print(f"  TEST 2 — GATE SURVIVORS vs GATE REJECTS")
    print(f"  (raw candidates, no dedup)")
    print(f"{'='*65}")

    group_a = [c for c in candidates if _gate_current(c)]
    group_b = [c for c in candidates if not _gate_current(c)]

    ga = _stats(group_a, f"Group A — Gate Survivors (r1 >= gate) n={len(group_a):,}")
    gb = _stats(group_b, f"Group B — Gate Rejects   (r1 < gate)  n={len(group_b):,}")

    print(f"\n{'─'*65}")
    print(f"  GROUP A — SURVIVORS")
    print(f"{'─'*65}")
    _print_stats(ga)

    print(f"\n{'─'*65}")
    print(f"  GROUP B — REJECTS")
    print(f"{'─'*65}")
    _print_stats(gb)

    print(f"\n  VERDICT:")
    if ga["n"] == 0:
        print(f"  Group A (survivors) = 0 signals. Gate rejects 100% of universe.")
        print(f"  Gate cannot be evaluated as a filter — it is a total blocker.")
        print(f"  Gate Rejects have: exp_mfe40={gb['exp_mfe40']}%, wr_mfe40={gb['wr_mfe40']}%, peak_1y={gb['avg_peak1y']}%")
        print(f"  TEST 2 VERDICT: Gate Rejects = ENTIRE universe. Gate is non-functional.")
    else:
        def better(va, vb, higher_better=True):
            if va is None or vb is None: return "?"
            return "A" if (va > vb) == higher_better else "B"
        winner_exp  = better(ga["exp_mfe40"],  gb["exp_mfe40"])
        winner_peak = better(ga["avg_peak1y"], gb["avg_peak1y"])
        print(f"  Expectancy winner: Group {winner_exp}")
        print(f"  Peak Return winner: Group {winner_peak}")
        if winner_exp == winner_peak == "A":
            print(f"  TEST 2 VERDICT: Gate Rejects = worse than survivors → gate adds alpha")
        elif winner_exp == winner_peak == "B":
            print(f"  TEST 2 VERDICT: Gate Rejects = better than survivors → gate destroys alpha")
        else:
            print(f"  TEST 2 VERDICT: Mixed results — gate is non-alpha-producing by metric")

    # ── TEST 3: Whitelist vs Non-Whitelist ────────────────────────────────────
    print(f"\n{'='*65}")
    print(f"  TEST 3 — WHITELIST vs NON-WHITELIST")
    print(f"  Universe: all DZ + score>=35 candidates (no price gate, no dedup)")
    print(f"  Whitelist: {sorted(WHITELIST)}")
    print(f"{'='*65}")

    wl_cands  = [c for c in candidates if c["in_wl"]]
    nwl_cands = [c for c in candidates if not c["in_wl"]]

    swl  = _stats(wl_cands,  f"Whitelist ({len(wl_cands):,} candidates)")
    snwl = _stats(nwl_cands, f"Non-Whitelist ({len(nwl_cands):,} candidates)")

    print(f"\n{'─'*65}")
    print(f"  WHITELIST SYMBOLS")
    print(f"{'─'*65}")
    _print_stats(swl)

    print(f"\n{'─'*65}")
    print(f"  NON-WHITELIST SYMBOLS")
    print(f"{'─'*65}")
    _print_stats(snwl)

    print(f"\n  PER-SYMBOL BREAKDOWN (Whitelist):")
    wl_syms = sorted(WHITELIST)
    print(f"  {'Symbol':<12} {'N':>5} {'WR%':>7} {'Exp%':>8} {'MFE90%':>8} {'Peak1Y%':>9} {'Sharpe':>7}")
    print(f"  {'-'*62}")
    for sym in wl_syms:
        sc = [c for c in candidates if c["symbol"] == sym]
        if not sc: continue
        s = _stats(sc, sym)
        wr   = f"{s['wr_mfe40']:.1f}" if s['wr_mfe40'] is not None else "n/a"
        exp  = f"{s['exp_mfe40']:.1f}" if s['exp_mfe40'] is not None else "n/a"
        m90  = f"{s['avg_mfe90']:.1f}" if s['avg_mfe90'] is not None else "n/a"
        pk   = f"{s['avg_peak1y']:.1f}" if s['avg_peak1y'] is not None else "n/a"
        sh   = f"{s['sharpe']:.3f}"    if s['sharpe'] is not None else "n/a"
        print(f"  {sym:<12} {s['n']:>5} {wr:>7} {exp:>8} {m90:>8} {pk:>9} {sh:>7}")

    print(f"\n  VERDICT:")
    if swl["n"] > 0 and snwl["n"] > 0:
        exp_diff   = (swl["exp_mfe40"]  or 0) - (snwl["exp_mfe40"]  or 0)
        peak_diff  = (swl["avg_peak1y"] or 0) - (snwl["avg_peak1y"] or 0)
        sharpe_diff= (swl["sharpe"]     or 0) - (snwl["sharpe"]     or 0)
        if exp_diff > 0 and peak_diff > 0:
            print(f"  Whitelist outperforms: +{exp_diff:.2f}% Expectancy, +{peak_diff:.2f}% Peak Return")
            print(f"  TEST 3 VERDICT: Whitelist alpha advantage YES | Exp delta={exp_diff:+.2f}% | Peak delta={peak_diff:+.2f}%")
        elif exp_diff < 0 and peak_diff < 0:
            print(f"  Whitelist underperforms: {exp_diff:.2f}% Expectancy, {peak_diff:.2f}% Peak Return")
            print(f"  TEST 3 VERDICT: Whitelist alpha advantage NO | Exp delta={exp_diff:+.2f}% | Peak delta={peak_diff:+.2f}%")
        else:
            print(f"  Mixed: Exp delta={exp_diff:+.2f}% | Peak delta={peak_diff:+.2f}% | Sharpe delta={sharpe_diff:+.3f}")
            print(f"  TEST 3 VERDICT: Whitelist alpha advantage MIXED — no consistent edge")
    else:
        print(f"  Insufficient data for comparison")

    # ── TEST 4: Dynamic Gate Models ───────────────────────────────────────────
    print(f"\n{'='*65}")
    print(f"  TEST 4 — DYNAMIC GATE STUDY")
    print(f"  All models apply GAP_DAYS={GAP_DAYS} dedup (production-like)")
    print(f"  W_PRICE={W_PRICE:.4f}")
    print(f"{'='*65}")

    gate_25  = 0.25 * W_PRICE
    gate_50  = 0.50 * W_PRICE
    gate_75  = 0.75 * W_PRICE

    models = [
        ("A", f"Current Fixed (r1>={PRICE_GATE_NORMAL}/{PRICE_GATE_WHITELIST})", _gate_current),
        ("B", f"25% W_PRICE (r1>={gate_25:.2f})",                               _gate_25pct),
        ("C", f"50% W_PRICE (r1>={gate_50:.2f})",                               _gate_50pct),
        ("D", f"75% W_PRICE (r1>={gate_75:.2f})",                               _gate_75pct),
        ("E", "No Gate (all DZ+score>=35)",                                      _gate_none),
    ]

    model_stats = []
    print(f"\n  Computing models with dedup (GAP_DAYS={GAP_DAYS})...")
    for mid, mlabel, gate_fn in models:
        filtered = _apply_gate_with_dedup(candidates, gate_fn)
        s = _stats(filtered, f"Model {mid}: {mlabel}")
        s["model_id"] = mid
        s["acceptance_rate"] = round(len(filtered) / total_cands * 100, 1) if total_cands > 0 else 0
        model_stats.append(s)
        print(f"  Model {mid}: {len(filtered):4d} signals  acceptance={s['acceptance_rate']:.1f}%")

    print(f"\n  {'Model':<2}  {'Label':<38} {'N':>5} {'WR%':>6} {'Exp%':>7} {'Sharpe':>7} {'Peak1Y%':>9} {'Acc%':>5}")
    print(f"  {'-'*82}")
    for s in model_stats:
        wr   = f"{s['wr_mfe40']:.1f}"  if s['wr_mfe40']   is not None else "n/a  "
        exp  = f"{s['exp_mfe40']:.2f}" if s['exp_mfe40']   is not None else "n/a   "
        sh   = f"{s['sharpe']:.3f}"    if s['sharpe']      is not None else "n/a   "
        pk   = f"{s['avg_peak1y']:.1f}"if s['avg_peak1y']  is not None else "n/a    "
        acc  = f"{s['acceptance_rate']:.1f}"
        print(f"  {s['model_id']:<2}  {s['label']:<38} {s['n']:>5} {wr:>6} {exp:>7} {sh:>7} {pk:>9} {acc:>5}")

    # Rank by composite: Expectancy (40%) + Peak1Y (40%) + Sharpe (20%)
    def _composite(s):
        e = s["exp_mfe40"]  or 0
        p = s["avg_peak1y"] or 0
        sh= s["sharpe"]     or 0
        return 0.4 * e + 0.4 * p + 0.2 * sh * 10

    ranked = sorted(model_stats, key=_composite, reverse=True)

    print(f"\n  RANKING (composite score = 0.4×Exp + 0.4×Peak1Y + 0.2×Sharpe×10):")
    for rank, s in enumerate(ranked, 1):
        cmp = _composite(s)
        exp = s['exp_mfe40']  if s['exp_mfe40']  is not None else 0
        pk  = s['avg_peak1y'] if s['avg_peak1y'] is not None else 0
        sh  = s['sharpe']     if s['sharpe']     is not None else 0
        print(f"  #{rank}  Model {s['model_id']}  composite={cmp:.2f}  exp={exp:.2f}%  peak1y={pk:.2f}%  sharpe={sh:.3f}  n={s['n']}")

    best_model = ranked[0]["model_id"] if ranked else "?"
    print(f"\n  TEST 4 VERDICT: Best Gate Model = {best_model}")

    # ── Full Detail per Model ─────────────────────────────────────────────────
    print(f"\n{'─'*65}")
    print(f"  DETAILED METRICS PER GATE MODEL")
    print(f"{'─'*65}")
    for s in model_stats:
        print(f"\n  MODEL {s['model_id']}: {s['label']}")
        _print_stats(s)
        print(f"  {'Acceptance Rate':<28}: {s['acceptance_rate']:.1f}%")

    # ── Final Decision ────────────────────────────────────────────────────────
    print(f"\n{'='*65}")
    print(f"  FINAL DECISION")
    print(f"{'='*65}")

    # Evidence summary
    current_n      = next((s["n"] for s in model_stats if s["model_id"] == "A"), 0)
    no_gate_s      = next((s for s in model_stats if s["model_id"] == "E"), {})
    best_s         = ranked[0] if ranked else {}

    print(f"\n  EVIDENCE SUMMARY:")
    print(f"  Current gate (Model A) signals   : {current_n}")
    print(f"  No gate (Model E) signals (dedup): {no_gate_s.get('n', '?')}")
    print(f"  Best model by composite          : Model {best_model}")
    print(f"  Gate Survivors vs Rejects        : Survivors={ga['n']} | Rejects={gb['n']}")
    print(f"  Whitelist vs Non-WL Exp delta    : ", end="")
    if swl["exp_mfe40"] is not None and snwl["exp_mfe40"] is not None:
        print(f"{(swl['exp_mfe40'] - snwl['exp_mfe40']):+.2f}%")
    else:
        print("n/a")

    print(f"\n  DECISION:")
    if current_n == 0 and best_model != "A":
        print(f"  Current gate produces 0 signals.")
        print(f"  Best performing gate model: {best_model}")
        print(f"  Decision: 2. RECALIBRATE CURRENT GATE")
        print(f"  Evidence: W_PRICE={W_PRICE:.2f} < PRICE_GATE_NORMAL={PRICE_GATE_NORMAL}.")
        print(f"  Gate threshold must be <= W_PRICE to admit any signals.")
        best_detail = next((s for s in model_stats if s["model_id"] == best_model), {})
        if best_model == "E":
            print(f"  Model E (no gate) is best — consider: 4. REMOVE GATE COMPLETELY")
        else:
            thr_map = {"B": gate_25, "C": gate_50, "D": gate_75}
            if best_model in thr_map:
                print(f"  Model {best_model} threshold = {thr_map[best_model]:.2f} = {['25%','50%','75%'][list(thr_map.keys()).index(best_model)]} of W_PRICE")
                print(f"  Recalibrate: PRICE_GATE_NORMAL → {thr_map[best_model]:.2f} (evidence-based, not assumed)")
    elif best_model == "A":
        print(f"  Decision: 1. KEEP CURRENT GATE")
    else:
        print(f"  Decision: 2. RECALIBRATE CURRENT GATE to Model {best_model} threshold")

    print(f"\n{'='*65}")
    print(f"  AUDIT COMPLETE — All evidence from repository only")
    print(f"{'='*65}\n")


if __name__ == "__main__":
    run_audit()
