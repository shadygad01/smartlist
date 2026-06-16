#!/usr/bin/env python3
"""
Post-Gate Classification Quality Audit — 6 Tests
==================================================
Audits the complete classification distribution after the Price Gate
architectural fix. Uses current production logic from main.py verbatim.

DO NOT MODIFY — audit/analysis only. No code changes.
"""

import os, sys, warnings
import numpy as np
import pandas as pd
from pathlib import Path
from collections import defaultdict
from datetime import date, timedelta

warnings.filterwarnings("ignore")

print("[audit] Importing from main.py (production logic)...")
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
PRICE_GATE_FRAC_N    = _m.PRICE_GATE_FRAC_NORMAL
PRICE_GATE_FRAC_WL   = _m.PRICE_GATE_FRAC_WHITELIST

LOCAL_DATA_DIR = Path("historical_data/historical_data")
MIN_WINDOW     = 110
GAP_DAYS       = 20
SCORE_GATE     = 35
MFE_WIN_THR    = 0.07

ALL_SYMBOLS = sorted(f.stem for f in LOCAL_DATA_DIR.glob("*.CA.csv"))

# Classification ordering for monotonicity check
CLASS_ORDER = ["Wait", "Early Buy", "Buy", "Strong Buy", "Very Strong Buy", "Institutional Buy"]
CLASS_IDX   = {c: i for i, c in enumerate(CLASS_ORDER)}


def _load_ohlcv(symbol):
    path = LOCAL_DATA_DIR / f"{symbol}.csv"
    if not path.exists():
        return pd.DataFrame()
    df = pd.read_csv(path, parse_dates=["Date"], index_col="Date")
    df.index = pd.DatetimeIndex(df.index).tz_localize(None)
    df = df.sort_index()
    for c in ["Open","High","Low","Close","Volume"]:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    return df.dropna(subset=["Close","High","Low"])


def _fwd(full_df, t, days):
    n = len(full_df)
    entry = float(full_df["Close"].iloc[t])
    if entry <= 0:
        return None, None
    end = min(t + days + 1, n)
    fut = full_df.iloc[t + 1: end]
    if len(fut) < max(5, days // 2):
        return None, None
    mfe = round((float(np.nanmax(fut["High"].values)) - entry) / entry, 4)
    mae = round((float(np.nanmin(fut["Low"].values))  - entry) / entry, 4)
    return mfe, mae


def _classify(symbol, r1, r2, r3, r4, r5, r6, r7, r8):
    """Exact classification logic from main.py lines 722-795."""
    total = min(r1+r2+r3+r4+r5+r6+r7+r8, 100)
    if total < SCORE_GATE:
        return "Skip", total, 0

    PRICE_GATE     = PRICE_GATE_WHITELIST if symbol in WHITELIST else PRICE_GATE_NORMAL
    price_ok       = (r1 >= PRICE_GATE)
    stock_mult     = STOCK_QUALITY.get(symbol, 1.0)
    adj_score      = min(int(round(total * stock_mult)), 100)
    _entry_gate    = 35 if symbol in WHITELIST else 40

    if not price_ok:
        return "Wait", total, adj_score
    if adj_score < _entry_gate:
        return "Wait", total, adj_score

    liq_ok = (r3 >= W_LIQ)
    if not liq_ok:
        return "Early Buy", total, adj_score

    # sig_info
    if adj_score >= 85: return "Institutional Buy", total, adj_score
    if adj_score >= 70: return "Very Strong Buy",   total, adj_score
    if adj_score >= 55: return "Strong Buy",        total, adj_score
    return "Buy", total, adj_score


def collect_signals():
    """
    Collect all post-gate signals with classification and outcomes.
    Applies production dedup (GAP_DAYS=20).
    """
    records = []
    print(f"\n  Scanning {len(ALL_SYMBOLS)} symbols...\n")

    for i, symbol in enumerate(ALL_SYMBOLS, 1):
        df = _load_ohlcv(symbol)
        n  = len(df)
        if n < MIN_WINDOW:
            print(f"  [{i:2d}/{len(ALL_SYMBOLS)}] {symbol:<12} skipped")
            continue

        last_sig = -GAP_DAYS - 1
        count    = 0

        for t in range(MIN_WINDOW, n):
            df_slice = df.iloc[:t + 1]
            try:
                cur = float(df_slice["Close"].iloc[-1])
                if not np.isfinite(cur) or cur <= 0:
                    continue
                hi, lo, eq, buy_hi, sell_lo = swings(df_slice)
                if cur >= eq:
                    continue

                r1, _ = sc_price(cur, lo, hi, eq, buy_hi, sell_lo)
                r2, _ = sc_ob(df_slice, cur, eq, lo, buy_hi)
                r3, _ = sc_liquidity(df_slice, cur)
                r4, _ = sc_htf(df_slice)
                av, alo = calc_avwap(df_slice)
                r5, _  = _sc_avwap_fn(cur, av, alo)
                close       = df_slice["Close"]
                macd_result = calc_macd(close)
                r6, _ = sc_macd(close, _macd=macd_result)
                r7, _ = sc_div(close, macd_result[0])
                sv_result  = calc_stopping_volume(df_slice, eq, lo)
                hvn_result = calc_volume_profile(df_slice, eq, lo, buy_hi)
                r8, _ = sc_demand_zone(df_slice, eq, lo, buy_hi,
                                       _sv=sv_result, _hvn=hvn_result)
            except Exception:
                continue

            cls, raw_score, adj_score = _classify(symbol, r1, r2, r3, r4, r5, r6, r7, r8)

            if cls in ("Skip", "Wait"):
                continue   # only track buy-eligible (deduped)

            if t - last_sig < GAP_DAYS:
                continue
            last_sig = t

            # Forward returns
            mfe40,  mae40  = _fwd(df, t, 40)
            mfe252, mae252 = _fwd(df, t, 252)
            if mfe40 is None:
                continue

            sig_date = str(df.index[t].date())
            records.append({
                "symbol":    symbol,
                "date":      sig_date,
                "idx":       t,
                "in_wl":     symbol in WHITELIST,
                "class":     cls,
                "raw_score": raw_score,
                "adj_score": adj_score,
                "r1":        r1, "r2": r2, "r3": r3,
                "r4":        r4, "r5": r5, "r6": r6,
                "r7":        r7, "r8": r8,
                "mfe_40d":   mfe40,  "mae_40d":  mae40,
                "mfe_252d":  mfe252, "mae_252d": mae252,
            })
            count += 1

        print(f"  [{i:2d}/{len(ALL_SYMBOLS)}] {symbol:<12}  {count:3d} signals")

    return records


def _group_stats(group, label):
    if not group:
        return {"label": label, "n": 0}
    mfe40  = [r["mfe_40d"]  for r in group]
    mfe252 = [r["mfe_252d"] for r in group if r["mfe_252d"] is not None]
    mae40  = [r["mae_40d"]  for r in group]
    raw    = [r["raw_score"] for r in group]
    adj    = [r["adj_score"] for r in group]

    wr     = sum(1 for v in mfe40 if v >= MFE_WIN_THR) / len(mfe40) * 100
    exp    = np.mean(mfe40) * 100
    pk1y   = np.mean(mfe252) * 100 if mfe252 else None
    sh     = np.mean(mfe40) / np.std(mfe40, ddof=1) if len(mfe40) >= 3 else None
    avg_mae= np.mean(mae40) * 100

    return {
        "label":    label,
        "n":        len(group),
        "wr":       round(wr,  1),
        "exp":      round(exp, 2),
        "pk1y":     round(pk1y, 2) if pk1y is not None else None,
        "sharpe":   round(sh,  3) if sh is not None else None,
        "avg_raw":  round(np.mean(raw), 1),
        "avg_adj":  round(np.mean(adj), 1),
        "avg_mae":  round(avg_mae, 2),
    }


def _pct(v, suffix="%"):
    return f"{v:+.2f}{suffix}" if v is not None else "  n/a "
def _fmt(v, decimals=1):
    return f"{v:.{decimals}f}" if v is not None else " n/a"


def run_audit():
    print(f"\n{'='*70}")
    print(f"  POST-GATE CLASSIFICATION AUDIT")
    print(f"  Production gate: NORMAL={PRICE_GATE_NORMAL:.3f} ({PRICE_GATE_FRAC_N*100:.0f}%×W_PRICE)")
    print(f"                   WL={PRICE_GATE_WHITELIST:.3f} ({PRICE_GATE_FRAC_WL*100:.0f}%×W_PRICE)")
    print(f"  W_PRICE={W_PRICE:.4f} | W_LIQ={W_LIQ:.4f} | SCORE_GATE={SCORE_GATE}")
    print(f"{'='*70}")

    records = collect_signals()
    total   = len(records)

    if total == 0:
        print("ERROR: No signals collected.")
        return

    df_all = pd.DataFrame(records)
    df_all["date_dt"] = pd.to_datetime(df_all["date"])
    cutoff_12m = pd.Timestamp.today() - pd.DateOffset(months=12)

    print(f"\n  Total signals collected: {total}")

    # ── WAIT signals (no dedup — raw count for distribution reference) ─────
    # We also collect Wait signals separately for Test 1 distribution
    # by re-running without the dedup filter (count only, no fwd returns needed)
    wait_count = 0
    skip_count = 0
    for symbol in ALL_SYMBOLS:
        df = _load_ohlcv(symbol)
        n  = len(df)
        if n < MIN_WINDOW:
            continue
        for t in range(MIN_WINDOW, n):
            df_slice = df.iloc[:t + 1]
            try:
                cur = float(df_slice["Close"].iloc[-1])
                if not np.isfinite(cur) or cur <= 0: continue
                hi, lo, eq, buy_hi, sell_lo = swings(df_slice)
                if cur >= eq: continue
                r1, _ = sc_price(cur, lo, hi, eq, buy_hi, sell_lo)
                r2, _ = sc_ob(df_slice, cur, eq, lo, buy_hi)
                r3, _ = sc_liquidity(df_slice, cur)
                r4, _ = sc_htf(df_slice)
                av, alo = calc_avwap(df_slice)
                r5, _  = _sc_avwap_fn(cur, av, alo)
                close  = df_slice["Close"]
                macd_result = calc_macd(close)
                r6, _ = sc_macd(close, _macd=macd_result)
                r7, _ = sc_div(close, macd_result[0])
                sv  = calc_stopping_volume(df_slice, eq, lo)
                hvn = calc_volume_profile(df_slice, eq, lo, buy_hi)
                r8, _ = sc_demand_zone(df_slice, eq, lo, buy_hi, _sv=sv, _hvn=hvn)
            except:
                continue
            cls, _, _ = _classify(symbol, r1, r2, r3, r4, r5, r6, r7, r8)
            if cls == "Skip": skip_count += 1
            elif cls == "Wait": wait_count += 1
    dz_bars = 13373  # from previous audit

    # ── TEST 1: Full Historical Distribution ──────────────────────────────────
    print(f"\n{'='*70}")
    print(f"  TEST 1 — FULL HISTORICAL CLASSIFICATION DISTRIBUTION")
    print(f"  (deduped buy-family only; WAIT/SKIP counts = raw DZ bars)")
    print(f"{'='*70}")

    classes = ["Early Buy", "Buy", "Strong Buy", "Very Strong Buy", "Institutional Buy"]
    class_groups = {c: [r for r in records if r["class"] == c] for c in classes}

    buy_total = total
    grand_total_dz = dz_bars
    wait_pct  = wait_count / grand_total_dz * 100
    skip_pct  = skip_count / grand_total_dz * 100
    buy_pct   = buy_total  / grand_total_dz * 100

    print(f"\n  {'Class':<20} {'Count':>7} {'%DZ':>7} {'AvgRaw':>8} {'AvgAdj':>8} {'WR%':>6} {'Exp%':>7} {'Sharpe':>7} {'Peak1Y%':>9}")
    print(f"  {'-'*80}")
    print(f"  {'SKIP (score<35)':<20} {skip_count:>7,} {skip_count/grand_total_dz*100:>6.1f}% {'n/a':>8} {'n/a':>8} {'n/a':>6} {'n/a':>7} {'n/a':>7} {'n/a':>9}")
    print(f"  {'WAIT':<20} {wait_count:>7,} {wait_pct:>6.1f}% {'n/a':>8} {'n/a':>8} {'n/a':>6} {'n/a':>7} {'n/a':>7} {'n/a':>9}")

    for cls in classes:
        g = class_groups[cls]
        s = _group_stats(g, cls)
        pct = len(g) / grand_total_dz * 100
        raw = f"{s['avg_raw']:.1f}" if g else "n/a"
        adj = f"{s['avg_adj']:.1f}" if g else "n/a"
        wr  = f"{s['wr']:.1f}" if g else "n/a"
        exp = f"{s['exp']:.2f}" if g else "n/a"
        sh  = f"{s['sharpe']:.3f}" if g and s['sharpe'] is not None else "n/a"
        pk  = f"{s['pk1y']:.1f}" if g and s['pk1y'] is not None else "n/a"
        n   = len(g)
        print(f"  {cls:<20} {n:>7,} {pct:>6.1f}% {raw:>8} {adj:>8} {wr:>6} {exp:>7} {sh:>7} {pk:>9}")

    # Buy family totals
    buy_s = _group_stats(records, "ALL BUY-FAMILY")
    print(f"  {'-'*80}")
    print(f"  {'TOTAL BUY-FAMILY':<20} {buy_total:>7,} {buy_pct:>6.1f}% {buy_s['avg_raw']:>8.1f} {buy_s['avg_adj']:>8.1f} {buy_s['wr']:>6.1f} {buy_s['exp']:>7.2f} {_fmt(buy_s['sharpe'],3):>7} {_fmt(buy_s['pk1y'],1):>9}")

    # ── TEST 2: Last 12 Months ──────────────────────────────────────────────
    print(f"\n{'='*70}")
    print(f"  TEST 2 — LAST 12 MONTHS vs FULL HISTORY")
    print(f"  Cutoff: {cutoff_12m.date()}")
    print(f"{'='*70}")

    rec_12m  = [r for r in records if pd.Timestamp(r["date"]) >= cutoff_12m]
    rec_hist = [r for r in records if pd.Timestamp(r["date"]) <  cutoff_12m]

    print(f"\n  Last 12m signals: {len(rec_12m)}  |  Prior history: {len(rec_hist)}")

    print(f"\n  {'Class':<20} {'Hist N':>7} {'Hist%':>7} {'12m N':>7} {'12m%':>7} {'Drift':>8}")
    print(f"  {'-'*60}")
    for cls in classes:
        h_n = sum(1 for r in rec_hist if r["class"] == cls)
        m_n = sum(1 for r in rec_12m  if r["class"] == cls)
        h_pct = h_n / max(len(rec_hist), 1) * 100
        m_pct = m_n / max(len(rec_12m),  1) * 100
        drift = m_pct - h_pct
        drift_str = f"{drift:+.1f}pp"
        flag = " ⚠️" if abs(drift) > 10 else ""
        print(f"  {cls:<20} {h_n:>7} {h_pct:>6.1f}% {m_n:>7} {m_pct:>6.1f}% {drift_str:>8}{flag}")

    # Per-class quality comparison
    print(f"\n  QUALITY SHIFT (12m vs full history):")
    print(f"  {'Class':<20} {'H-WR':>7} {'12-WR':>7} {'H-Exp':>8} {'12-Exp':>8} {'H-Pk1Y':>9} {'12-Pk1Y':>9}")
    print(f"  {'-'*70}")
    for cls in classes:
        hg = [r for r in rec_hist if r["class"] == cls]
        mg = [r for r in rec_12m  if r["class"] == cls]
        hs = _group_stats(hg, cls)
        ms = _group_stats(mg, cls)
        hwr  = f"{hs['wr']:.1f}" if hg else "n/a"
        mwr  = f"{ms['wr']:.1f}" if mg else "n/a"
        hexp = f"{hs['exp']:.1f}" if hg else "n/a"
        mexp = f"{ms['exp']:.1f}" if mg else "n/a"
        hpk  = f"{hs['pk1y']:.0f}" if hg and hs['pk1y'] is not None else "n/a"
        mpk  = f"{ms['pk1y']:.0f}" if mg and ms['pk1y'] is not None else "n/a"
        print(f"  {cls:<20} {hwr:>7} {mwr:>7} {hexp:>8} {mexp:>8} {hpk:>9} {mpk:>9}")

    # Drift assessment
    if rec_12m:
        h_avg_adj = np.mean([r["adj_score"] for r in rec_hist]) if rec_hist else 0
        m_avg_adj = np.mean([r["adj_score"] for r in rec_12m])
        drift = m_avg_adj - h_avg_adj
        print(f"\n  Avg adj_score drift: {drift:+.2f} ({'↑ improving' if drift > 1 else '↓ degrading' if drift < -1 else '→ stable'})")
        if abs(drift) > 5:
            print(f"  ⚠️  DRIFT DETECTED: classification score shifted {drift:+.2f} points in last 12m")
        else:
            print(f"  ✅  NO MATERIAL DRIFT detected in last 12 months")

    # ── TEST 3: Class Quality Monotonicity ────────────────────────────────────
    print(f"\n{'='*70}")
    print(f"  TEST 3 — CLASS QUALITY MONOTONICITY")
    print(f"  Expected: Wait < Early Buy < Buy < Strong Buy < Very Strong Buy < Institutional Buy")
    print(f"{'='*70}")

    mono_order = ["Early Buy", "Buy", "Strong Buy", "Very Strong Buy", "Institutional Buy"]
    mono_stats = []
    for cls in mono_order:
        g = class_groups[cls]
        s = _group_stats(g, cls)
        mono_stats.append(s)

    print(f"\n  {'Class':<22} {'N':>5} {'WR%':>7} {'Exp%':>8} {'Sharpe':>8} {'Peak1Y%':>9} {'MAE40%':>8}")
    print(f"  {'-'*70}")
    for s in mono_stats:
        wr  = f"{s['wr']:.1f}"  if s['n'] > 0 else " n/a"
        exp = f"{s['exp']:.2f}" if s['n'] > 0 else " n/a"
        sh  = f"{s['sharpe']:.3f}" if s['n'] > 0 and s['sharpe'] else " n/a"
        pk  = f"{s['pk1y']:.1f}" if s['n'] > 0 and s['pk1y'] is not None else " n/a"
        mae = f"{s['avg_mae']:.2f}" if s['n'] > 0 else " n/a"
        print(f"  {s['label']:<22} {s['n']:>5} {wr:>7} {exp:>8} {sh:>8} {pk:>9} {mae:>8}")

    # Check monotonicity for each metric
    print(f"\n  MONOTONICITY CHECK:")
    metrics = [("WR%", "wr"), ("Exp%", "exp"), ("Sharpe", "sharpe"), ("Peak_1Y", "pk1y")]
    for mname, mkey in metrics:
        vals = [s[mkey] for s in mono_stats if s['n'] > 0 and s[mkey] is not None]
        classes_with_vals = [mono_stats[i]['label'] for i in range(len(mono_stats))
                             if mono_stats[i]['n'] > 0 and mono_stats[i][mkey] is not None]
        inversions = []
        for j in range(len(vals) - 1):
            if vals[j] > vals[j + 1]:
                inversions.append(f"{classes_with_vals[j]} > {classes_with_vals[j+1]}")
        if not inversions:
            print(f"  {mname:<12}: ✅ MONOTONIC")
        else:
            print(f"  {mname:<12}: ⚠️  INVERSIONS: {', '.join(inversions)}")

    # ── TEST 4: Score Threshold Audit ─────────────────────────────────────────
    print(f"\n{'='*70}")
    print(f"  TEST 4 — SCORE THRESHOLD AUDIT")
    print(f"{'='*70}")

    print(f"\n  DEFINED THRESHOLDS (from main.py sig_info):")
    print(f"  {'Class':<22} {'Min Score':>10} {'Max Score':>10}")
    print(f"  {'-'*46}")
    thresholds = [
        ("Wait",             "< entry_gate", "—"),
        ("Early Buy",        "≥ entry_gate", "—"),
        ("Buy",              "35",  "54"),
        ("Strong Buy",       "55",  "69"),
        ("Very Strong Buy",  "70",  "84"),
        ("Institutional Buy","85",  "100"),
    ]
    for cls, lo, hi in thresholds:
        print(f"  {cls:<22} {lo:>10} {hi:>10}")

    print(f"\n  OBSERVED adj_score DISTRIBUTION PER CLASS:")
    print(f"  {'Class':<22} {'N':>5} {'Min':>6} {'Max':>6} {'Avg':>6} {'Median':>8} {'Overlap':>8}")
    print(f"  {'-'*65}")
    all_cls = classes
    prev_max = None
    for cls in all_cls:
        g = class_groups[cls]
        if not g:
            print(f"  {cls:<22} {'0':>5} {'n/a':>6} {'n/a':>6} {'n/a':>6} {'n/a':>8} {'n/a':>8}")
            prev_max = None
            continue
        scores = [r["adj_score"] for r in g]
        mn, mx = min(scores), max(scores)
        avg = np.mean(scores)
        med = np.median(scores)
        overlap = ""
        if prev_max is not None and mn <= prev_max:
            overlap = f"⚠️ overlaps"
        print(f"  {cls:<22} {len(g):>5} {mn:>6} {mx:>6} {avg:>6.1f} {med:>8.1f} {overlap:>8}")
        prev_max = mx

    # Entry score gates
    wl_entry  = 35
    norm_entry = 40
    adj_scores_buy = [r["adj_score"] for r in records if r["class"] not in ("Skip", "Wait")]
    print(f"\n  Entry score gate: WHITELIST >= {wl_entry} | NORMAL >= {norm_entry}")
    print(f"  Adj score range across all buy-family: {min(adj_scores_buy)} – {max(adj_scores_buy)}")
    print(f"  Adj score mean:   {np.mean(adj_scores_buy):.1f}")
    print(f"  Adj score median: {np.median(adj_scores_buy):.1f}")

    # ── TEST 5: Alpha Concentration ───────────────────────────────────────────
    print(f"\n{'='*70}")
    print(f"  TEST 5 — ALPHA CONCENTRATION")
    print(f"  Top 10% signals by mfe_252d (Peak_1Y outcome)")
    print(f"{'='*70}")

    sigs_with_pk = [r for r in records if r["mfe_252d"] is not None]
    if sigs_with_pk:
        n10 = max(1, len(sigs_with_pk) // 10)
        top10 = sorted(sigs_with_pk, key=lambda r: r["mfe_252d"], reverse=True)[:n10]
        bot10 = sorted(sigs_with_pk, key=lambda r: r["mfe_252d"])[:n10]

        top_dist  = defaultdict(int)
        bot_dist  = defaultdict(int)
        for r in top10: top_dist[r["class"]] += 1
        for r in bot10: bot_dist[r["class"]] += 1

        print(f"\n  Top {n10} signals (top 10% by Peak_1Y):")
        print(f"  Avg Peak_1Y in top 10%: +{np.mean([r['mfe_252d'] for r in top10])*100:.1f}%")
        print(f"\n  {'Class':<22} {'Top 10%':>8} {'Top %':>7} {'Bot 10%':>8} {'Bot %':>7} {'Routing':>10}")
        print(f"  {'-'*65}")
        all_dist = defaultdict(int)
        for r in records: all_dist[r["class"]] += 1
        for cls in classes:
            t_n = top_dist.get(cls, 0)
            b_n = bot_dist.get(cls, 0)
            all_n = all_dist.get(cls, 1)
            t_pct = t_n / n10 * 100
            b_pct = b_n / n10 * 100
            base_pct = all_n / total * 100
            # Routing: is top-10% share > base share (over-represented)?
            routing = "✅ over" if t_pct > base_pct + 5 else ("⚠️ under" if t_pct < base_pct - 5 else "→ neutral")
            print(f"  {cls:<22} {t_n:>8} {t_pct:>6.1f}% {b_n:>8} {b_pct:>6.1f}% {routing:>10}")

        print(f"\n  Top 10 individual signals (highest Peak_1Y):")
        print(f"  {'Symbol':<12} {'Date':<12} {'Class':<20} {'AdjScore':>9} {'Peak1Y%':>9}")
        print(f"  {'-'*65}")
        for r in top10[:10]:
            pk = f"+{r['mfe_252d']*100:.1f}%"
            print(f"  {r['symbol']:<12} {r['date']:<12} {r['class']:<20} {r['adj_score']:>9} {pk:>9}")

        # Is classification routing best opportunities upward?
        top_cls_list = [r["class"] for r in top10]
        top_avg_idx  = np.mean([CLASS_IDX.get(c, 0) for c in top_cls_list])
        all_avg_idx  = np.mean([CLASS_IDX.get(r["class"], 0) for r in records])
        print(f"\n  Avg class rank of top 10%:  {top_avg_idx:.2f}  (0=Wait, 5=Institutional)")
        print(f"  Avg class rank of all:      {all_avg_idx:.2f}")
        if top_avg_idx > all_avg_idx + 0.3:
            print(f"  ✅ Classification routes top opportunities to HIGHER classes")
        elif top_avg_idx < all_avg_idx - 0.3:
            print(f"  ⚠️  ROUTING FAILURE: top opportunities concentrated in LOWER classes")
        else:
            print(f"  → Classification is neutral on alpha routing (no clear signal)")

    # ── TEST 6: Classification Failure Analysis ────────────────────────────────
    print(f"\n{'='*70}")
    print(f"  TEST 6 — CLASSIFICATION FAILURE ANALYSIS")
    print(f"  Best 20 and Worst 20 signals per class by mfe_252d")
    print(f"{'='*70}")

    for cls in classes:
        g = class_groups[cls]
        if len(g) < 5:
            print(f"\n  {cls}: insufficient data ({len(g)} signals)")
            continue

        with_pk = [r for r in g if r["mfe_252d"] is not None]
        if not with_pk:
            print(f"\n  {cls}: no 252d outcomes available")
            continue

        best20  = sorted(with_pk, key=lambda r: r["mfe_252d"], reverse=True)[:min(20, len(with_pk))]
        worst20 = sorted(with_pk, key=lambda r: r["mfe_252d"])[:min(20, len(with_pk))]

        b_avg_raw = np.mean([r["raw_score"] for r in best20])
        w_avg_raw = np.mean([r["raw_score"] for r in worst20])
        b_avg_adj = np.mean([r["adj_score"] for r in best20])
        w_avg_adj = np.mean([r["adj_score"] for r in worst20])
        b_avg_r1  = np.mean([r["r1"] for r in best20])
        w_avg_r1  = np.mean([r["r1"] for r in worst20])
        b_avg_r3  = np.mean([r["r3"] for r in best20])
        w_avg_r3  = np.mean([r["r3"] for r in worst20])
        b_avg_r8  = np.mean([r["r8"] for r in best20])
        w_avg_r8  = np.mean([r["r8"] for r in worst20])
        b_avg_mfe = np.mean([r["mfe_252d"] for r in best20]) * 100
        w_avg_mfe = np.mean([r["mfe_252d"] for r in worst20]) * 100
        b_avg_mfe40 = np.mean([r["mfe_40d"] for r in best20]) * 100
        w_avg_mfe40 = np.mean([r["mfe_40d"] for r in worst20]) * 100

        print(f"\n  {cls} ({len(g)} total | {len(with_pk)} with 252d data):")
        print(f"  {'Metric':<22} {'Best 20':>10} {'Worst 20':>10} {'Delta':>10}")
        print(f"  {'-'*55}")
        print(f"  {'avg raw_score':<22} {b_avg_raw:>10.1f} {w_avg_raw:>10.1f} {b_avg_raw-w_avg_raw:>+10.1f}")
        print(f"  {'avg adj_score':<22} {b_avg_adj:>10.1f} {w_avg_adj:>10.1f} {b_avg_adj-w_avg_adj:>+10.1f}")
        print(f"  {'avg r1 (price)':<22} {b_avg_r1:>10.2f} {w_avg_r1:>10.2f} {b_avg_r1-w_avg_r1:>+10.2f}")
        print(f"  {'avg r3 (liq)':<22}  {b_avg_r3:>10.2f} {w_avg_r3:>10.2f} {b_avg_r3-w_avg_r3:>+10.2f}")
        print(f"  {'avg r8 (demand)':<22} {b_avg_r8:>10.2f} {w_avg_r8:>10.2f} {b_avg_r8-w_avg_r8:>+10.2f}")
        print(f"  {'avg mfe_40d':<22} {b_avg_mfe40:>10.1f}% {w_avg_mfe40:>10.1f}% {b_avg_mfe40-w_avg_mfe40:>+10.1f}pp")
        print(f"  {'avg peak_1y':<22} {b_avg_mfe:>10.1f}% {w_avg_mfe:>10.1f}% {b_avg_mfe-w_avg_mfe:>+10.1f}pp")

        # Identify discriminating factors
        gaps = [
            ("r1_price",  b_avg_r1  - w_avg_r1),
            ("r3_liq",    b_avg_r3  - w_avg_r3),
            ("r8_demand", b_avg_r8  - w_avg_r8),
            ("raw_score", b_avg_raw - w_avg_raw),
        ]
        top_gap = max(gaps, key=lambda x: abs(x[1]))
        print(f"  → Strongest discriminator: {top_gap[0]} (gap={top_gap[1]:+.2f})")

    # ── FINAL VERDICT ──────────────────────────────────────────────────────────
    print(f"\n{'='*70}")
    print(f"  FINAL VERDICT")
    print(f"{'='*70}")

    # 1. Hierarchy working?
    n_by_cls = {c: len(class_groups[c]) for c in classes}
    print(f"\n  1. CLASSIFICATION HIERARCHY:")
    print(f"     Class distribution (deduped signals):")
    for cls in classes:
        n = n_by_cls[cls]
        pct = n / total * 100 if total > 0 else 0
        print(f"     {cls:<22}: {n:>4} ({pct:.1f}%)")

    # 2. Score thresholds calibrated?
    # Check if any class has avg adj_score near a boundary
    print(f"\n  2. SCORE THRESHOLD CALIBRATION:")
    boundary_issues = []
    for cls in classes:
        g = class_groups[cls]
        if not g:
            continue
        scores = [r["adj_score"] for r in g]
        avg = np.mean(scores)
        # Check if near a threshold (within 3 points)
        thrs = [35, 55, 70, 85]
        for thr in thrs:
            if abs(avg - thr) <= 3:
                boundary_issues.append(f"{cls} avg_adj={avg:.1f} ≈ boundary {thr}")
    if boundary_issues:
        for bi in boundary_issues:
            print(f"     ⚠️  {bi}")
    else:
        print(f"     ✅ No class has avg adj_score near a class boundary (within 3 pts)")

    # 3. Alpha increases with class?
    print(f"\n  3. ALPHA MONOTONICITY:")
    mono_vals = [(c, _group_stats(class_groups[c], c)) for c in classes if class_groups[c]]
    mono_exp   = all(mono_vals[i][1]["exp"]  <= mono_vals[i+1][1]["exp"]
                     for i in range(len(mono_vals)-1) if mono_vals[i][1]["n"]>0 and mono_vals[i+1][1]["n"]>0)
    mono_pk    = all(mono_vals[i][1]["pk1y"] <= mono_vals[i+1][1]["pk1y"]
                     for i in range(len(mono_vals)-1)
                     if mono_vals[i][1]["n"]>0 and mono_vals[i+1][1]["n"]>0
                     and mono_vals[i][1]["pk1y"] is not None and mono_vals[i+1][1]["pk1y"] is not None)
    print(f"     Expectancy monotonic:  {'✅ YES' if mono_exp else '⚠️ NO — inversions present'}")
    print(f"     Peak_1Y monotonic:     {'✅ YES' if mono_pk  else '⚠️ NO — inversions present'}")

    # 4. Highest risk-adjusted alpha class
    best_sharpe_cls = max(classes, key=lambda c: (_group_stats(class_groups[c], c).get("sharpe") or 0))
    best_pk_cls     = max(classes, key=lambda c: (_group_stats(class_groups[c], c).get("pk1y") or 0))
    print(f"\n  4. HIGHEST RISK-ADJUSTED ALPHA: {best_sharpe_cls} (Sharpe={_group_stats(class_groups[best_sharpe_cls], best_sharpe_cls)['sharpe']:.3f})")
    print(f"     HIGHEST ABSOLUTE ALPHA:       {best_pk_cls} (Peak_1Y={_group_stats(class_groups[best_pk_cls], best_pk_cls)['pk1y']:.1f}%)")

    # 5. Oversized / undersized
    print(f"\n  5. CLASS SIZE ASSESSMENT:")
    for cls in classes:
        n = n_by_cls[cls]
        pct = n / total * 100 if total > 0 else 0
        if pct > 50:
            print(f"     ⚠️  {cls} is OVERSIZED ({pct:.1f}% of all signals)")
        elif pct < 3 and n > 0:
            print(f"     ⚠️  {cls} is UNDERSIZED ({pct:.1f}% = {n} signals)")
    print(f"     Most populated class: {max(classes, key=lambda c: n_by_cls[c])} ({max(n_by_cls.values())} signals)")
    print(f"     Least populated class: {min(classes, key=lambda c: n_by_cls[c])} ({min(n_by_cls.values())} signals)")

    # 6. Architecture decision
    print(f"\n  6. ARCHITECTURE DECISION:")
    issues = []
    if not mono_exp:
        issues.append("Expectancy not monotonic → score thresholds may need recalibration")
    if not mono_pk:
        issues.append("Peak_1Y not monotonic → long-term quality not aligned with class labels")
    if max(n_by_cls.values()) / total > 0.60:
        issues.append("One class dominates > 60% of signals → class boundaries too loose")
    if min(n_by_cls.values()) < 5:
        issues.append("At least one class has < 5 signals → statistically unreliable")

    if not issues:
        print(f"     ✅ KEEP — Classification hierarchy functioning correctly")
    else:
        print(f"     ⚠️  RECALIBRATION RECOMMENDED:")
        for issue in issues:
            print(f"       - {issue}")

    print(f"\n{'='*70}")
    print(f"  AUDIT COMPLETE")
    print(f"{'='*70}\n")


if __name__ == "__main__":
    run_audit()
