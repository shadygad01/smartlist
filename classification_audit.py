#!/usr/bin/env python3
"""
main.py Signal Classification Audit
======================================
Traces every historical bar through the exact classification logic from main.py.
Produces: SKIP / WAIT / EARLY BUY / BUY / STRONG BUY / VERY STRONG BUY / INSTITUTIONAL BUY
Plus counterfactual: if PRICE_GATE disabled, how many additional signals per class?

DO NOT MODIFY — audit/analysis only. No code changes.
"""

import os, sys, warnings
import numpy as np
import pandas as pd
from pathlib import Path
from collections import defaultdict

warnings.filterwarnings("ignore")

# ── Import scanner functions from main.py (single source of truth) ───────────
print("[audit] Importing scanner functions from main.py...")
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

# ── Config ────────────────────────────────────────────────────────────────────
LOCAL_DATA_DIR = Path("historical_data/historical_data")
MIN_WINDOW     = 110
GAP_DAYS       = 20
SCORE_GATE     = 35   # global Skip gate

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


def sig_info_label(score: int) -> str:
    if score >= 85: return "Institutional Buy"
    if score >= 70: return "Very Strong Buy"
    if score >= 55: return "Strong Buy"
    if score >= 35: return "Buy"
    return "Skip"


# ── Full scoring without price-gate early exit ────────────────────────────────

def _score_full(df_slice: pd.DataFrame, symbol: str) -> dict | None:
    """
    Run full SMC scoring — NO price gate early exit.
    Returns all r1..r8 components regardless of r1 value.
    Returns None only on technical failure (not enough data, bad prices).
    """
    if len(df_slice) < 20:
        return None
    try:
        cur = float(df_slice["Close"].iloc[-1])
        if not np.isfinite(cur) or cur <= 0:
            return None

        hi, lo, eq, buy_hi, sell_lo = swings(df_slice)

        # Gate 0: discount zone check
        if cur >= eq:
            return {"above_eq": True}

        # ── Full scoring (no price gate fast-fail) ────────────────────────
        r1, _  = sc_price(cur, lo, hi, eq, buy_hi, sell_lo)
        r2, _  = sc_ob(df_slice, cur, eq, lo, buy_hi)
        r3, _  = sc_liquidity(df_slice, cur)
        r4, _  = sc_htf(df_slice)

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

        return {
            "above_eq": False,
            "cur": cur, "r1": r1, "r2": r2, "r3": r3, "r4": r4,
            "r5": r5,   "r6": r6, "r7": r7, "r8": r8,
        }
    except Exception:
        return None


# ── Classification logic (mirrors main.py lines 722-795) ─────────────────────

def _classify(symbol: str, scores: dict, force_price_ok: bool = False) -> str:
    """
    Apply main.py classification gates.
    force_price_ok=True simulates PRICE_GATE disabled (counterfactual).
    """
    r1  = scores["r1"];  r2 = scores["r2"];  r3 = scores["r3"]
    r4  = scores["r4"];  r5 = scores["r5"];  r6 = scores["r6"]
    r7  = scores["r7"];  r8 = scores["r8"]

    total = min(r1+r2+r3+r4+r5+r6+r7+r8, 100)

    # Gate 1: global score gate
    if total < SCORE_GATE:
        return "Skip"

    # Gate 2: price gate
    price_gate = PRICE_GATE_WHITELIST if symbol in WHITELIST else PRICE_GATE_NORMAL
    price_ok   = force_price_ok or (r1 >= price_gate)
    if not price_ok:
        return "Wait"

    # Gate 3: adjusted score gate
    stock_mult        = STOCK_QUALITY.get(symbol, 1.0)
    ctx_mult          = 1.0   # no live context in historical audit
    score             = min(int(round(total * stock_mult * ctx_mult)), 100)
    _entry_score_gate = 35 if symbol in WHITELIST else 40
    if score < _entry_score_gate:
        return "Wait"

    # Gate 4: liquidity gate
    liq_ok = (r3 >= W_LIQ)
    if not liq_ok:
        return "Early Buy"

    # Gate 5: sig_info classification
    return sig_info_label(score)


# ── Per-Symbol Scan ────────────────────────────────────────────────────────────

def _scan_symbol(symbol: str, verbose: bool = False):
    df = _load_ohlcv(symbol)
    n  = len(df)
    if n < MIN_WINDOW:
        return None

    # Counters per gate (raw, no dedup)
    raw = defaultdict(int)
    # Counterfactual (price gate disabled)
    cf  = defaultdict(int)
    # Dedup tracking (for actual qualifying signals in base case)
    last_qualifying = -GAP_DAYS - 1

    # Track bars for waterfall
    total_bars      = n - MIN_WINDOW
    above_eq        = 0
    score_fail      = 0
    price_gate_fail = 0
    adj_score_fail  = 0
    liq_fail        = 0
    classified      = defaultdict(int)   # Buy, Strong Buy, etc.

    # Dedup buckets for actual signals (base case qualifying path)
    dedup_rejected  = 0
    dedup_classified = defaultdict(int)

    last_qualifying_base = -GAP_DAYS - 1

    for t in range(MIN_WINDOW, n):
        df_slice = df.iloc[:t + 1]
        scores   = _score_full(df_slice, symbol)

        if scores is None:
            continue

        # Gate 0: above EQ
        if scores.get("above_eq"):
            above_eq += 1
            continue

        cls_base = _classify(symbol, scores, force_price_ok=False)
        cls_cf   = _classify(symbol, scores, force_price_ok=True)

        raw[cls_base] += 1
        cf[cls_cf]    += 1

        # Waterfall counters (before dedup)
        total_score = min(scores["r1"]+scores["r2"]+scores["r3"]+scores["r4"]+
                          scores["r5"]+scores["r6"]+scores["r7"]+scores["r8"], 100)
        if total_score < SCORE_GATE:
            score_fail += 1
        else:
            price_gate_val = PRICE_GATE_WHITELIST if symbol in WHITELIST else PRICE_GATE_NORMAL
            if scores["r1"] < price_gate_val:
                price_gate_fail += 1
            else:
                stock_mult = STOCK_QUALITY.get(symbol, 1.0)
                score_adj  = min(int(round(total_score * stock_mult)), 100)
                _esg       = 35 if symbol in WHITELIST else 40
                if score_adj < _esg:
                    adj_score_fail += 1
                else:
                    if scores["r3"] < W_LIQ:
                        liq_fail += 1
                        classified["Early Buy"] += 1
                    else:
                        classified[sig_info_label(score_adj)] += 1

        # Dedup: apply GAP_DAYS only on Buy-family outcomes (base case)
        if cls_base not in ("Skip", "Wait"):
            if t - last_qualifying_base < GAP_DAYS:
                dedup_rejected += 1
            else:
                last_qualifying_base = t
                dedup_classified[cls_base] += 1

    return {
        "symbol":           symbol,
        "total_bars":       total_bars,
        "above_eq":         above_eq,
        "dz_bars":          total_bars - above_eq,
        "score_fail":       score_fail,
        "price_gate_fail":  price_gate_fail,
        "adj_score_fail":   adj_score_fail,
        "liq_fail":         liq_fail,
        "classified":       dict(classified),
        "dedup_rejected":   dedup_rejected,
        "dedup_classified": dict(dedup_classified),
        "raw":              dict(raw),
        "cf":               dict(cf),
    }


# ── Aggregation ───────────────────────────────────────────────────────────────

def run_audit():
    print(f"\n{'='*65}")
    print(f"  MAIN.PY SIGNAL CLASSIFICATION AUDIT")
    print(f"  {len(ALL_SYMBOLS)} symbols | MIN_WINDOW={MIN_WINDOW} | GAP_DAYS={GAP_DAYS}")
    print(f"  W_PRICE={W_PRICE:.2f} | PRICE_GATE_NORMAL={PRICE_GATE_NORMAL} | PRICE_GATE_WL={PRICE_GATE_WHITELIST}")
    print(f"  W_LIQ={W_LIQ:.2f} | SCORE_GATE={SCORE_GATE}")
    print(f"{'='*65}\n")

    # Global accumulators
    total_bars_all       = 0
    above_eq_all         = 0
    dz_bars_all          = 0
    score_fail_all       = 0
    price_gate_fail_all  = 0
    adj_score_fail_all   = 0
    liq_fail_all         = 0
    classified_all       = defaultdict(int)
    dedup_rejected_all   = 0
    dedup_classified_all = defaultdict(int)
    raw_all              = defaultdict(int)
    cf_all               = defaultdict(int)

    per_symbol = []

    for i, symbol in enumerate(ALL_SYMBOLS, 1):
        print(f"  [{i:2d}/{len(ALL_SYMBOLS)}] {symbol:<12}", end=" ", flush=True)
        res = _scan_symbol(symbol, verbose=True)
        if res is None:
            print("skipped (insufficient data)")
            continue

        total_bars_all      += res["total_bars"]
        above_eq_all        += res["above_eq"]
        dz_bars_all         += res["dz_bars"]
        score_fail_all      += res["score_fail"]
        price_gate_fail_all += res["price_gate_fail"]
        adj_score_fail_all  += res["adj_score_fail"]
        liq_fail_all        += res["liq_fail"]
        for k, v in res["classified"].items():
            classified_all[k] += v
        dedup_rejected_all  += res["dedup_rejected"]
        for k, v in res["dedup_classified"].items():
            dedup_classified_all[k] += v
        for k, v in res["raw"].items():
            raw_all[k] += v
        for k, v in res["cf"].items():
            cf_all[k] += v

        per_symbol.append(res)

        buy_total = sum(v for k, v in res["classified"].items())
        print(f"bars={res['total_bars']:4d}  DZ={res['dz_bars']:4d}  "
              f"sf={res['score_fail']:3d}  pg={res['price_gate_fail']:3d}  "
              f"liq={res['liq_fail']:3d}  buy={buy_total:3d}")

    # ── WATERFALL ─────────────────────────────────────────────────────────────
    pass_score     = dz_bars_all - score_fail_all
    pass_price     = pass_score  - price_gate_fail_all
    pass_adj       = pass_price  - adj_score_fail_all
    buy_family_pre = pass_adj    # = liq_fail_all + sum(classified_all)
    after_dedup    = sum(dedup_classified_all.values())

    # Counterfactual: with price gate disabled
    # base WAIT due to price gate = price_gate_fail_all (those that had total>=35 but r1 < gate)
    # cf adds those back — cf_all["Early Buy"] / cf_all["Buy"] / etc. vs raw_all
    cf_upgrade_early  = cf_all.get("Early Buy", 0) - raw_all.get("Early Buy", 0)
    cf_upgrade_buy    = cf_all.get("Buy", 0)        - raw_all.get("Buy", 0)
    cf_upgrade_strong = cf_all.get("Strong Buy", 0) - raw_all.get("Strong Buy", 0)
    cf_upgrade_vstrong= cf_all.get("Very Strong Buy", 0) - raw_all.get("Very Strong Buy", 0)
    cf_upgrade_inst   = cf_all.get("Institutional Buy", 0) - raw_all.get("Institutional Buy", 0)
    cf_wait_remain    = cf_all.get("Wait", 0)

    print(f"\n{'='*65}")
    print(f"  WATERFALL: TOTAL CANDIDATES → FINAL BUY SIGNALS")
    print(f"{'='*65}")
    print(f"  Total scannable bars (after MIN_WINDOW=110)  : {total_bars_all:>7,}")
    print(f"  ── GATE 0 (Discount Zone: cur >= eq)         : -{above_eq_all:>6,}  blocked")
    print(f"  Remaining: DZ bars (cur < eq)                : {dz_bars_all:>7,}")
    print(f"  ── GATE 1 (Score < 35)                       : -{score_fail_all:>6,}  → Skip")
    print(f"  Remaining: DZ bars with score >= 35          : {pass_score:>7,}  ← 5,776 universe")
    print(f"  ── GATE 2 (Price: r1 < PRICE_GATE)           : -{price_gate_fail_all:>6,}  → Wait")
    print(f"  Remaining after price gate                   : {pass_price:>7,}")
    print(f"  ── GATE 3 (Adj score < entry gate 35/40)     : -{adj_score_fail_all:>6,}  → Wait")
    print(f"  Remaining after adj score gate               : {pass_adj:>7,}")
    print(f"  ── GATE 4 (Liq: r3 < W_LIQ={W_LIQ:.2f})       : -{liq_fail_all:>6,}  → Early Buy")
    print(f"  Remaining: Buy-eligible (all gates passed)   : {sum(classified_all.values()):>7,}")
    print(f"  ── DEDUP  (GAP_DAYS={GAP_DAYS} — buy family)         : -{dedup_rejected_all:>6,}  deduplicated")
    print(f"  FINAL BUY SIGNALS (post-dedup)               : {after_dedup:>7,}")

    print(f"\n{'─'*65}")
    print(f"  CLASSIFICATION BREAKDOWN (before dedup)")
    print(f"{'─'*65}")
    print(f"  Skip                : {raw_all.get('Skip', 0):>7,}  (above_eq + score<35 via raw[])")
    print(f"  Wait                : {raw_all.get('Wait', 0):>7,}  (price gate + adj score gate)")
    print(f"  Early Buy           : {raw_all.get('Early Buy', 0):>7,}  (r3 < W_LIQ)")
    print(f"  Buy                 : {raw_all.get('Buy', 0):>7,}  (score 35–54)")
    print(f"  Strong Buy          : {raw_all.get('Strong Buy', 0):>7,}  (score 55–69)")
    print(f"  Very Strong Buy     : {raw_all.get('Very Strong Buy', 0):>7,}  (score 70–84)")
    print(f"  Institutional Buy   : {raw_all.get('Institutional Buy', 0):>7,}  (score >= 85)")

    print(f"\n{'─'*65}")
    print(f"  CLASSIFICATION BREAKDOWN (after dedup, GAP_DAYS={GAP_DAYS})")
    print(f"{'─'*65}")
    print(f"  Early Buy           : {dedup_classified_all.get('Early Buy', 0):>7,}")
    print(f"  Buy                 : {dedup_classified_all.get('Buy', 0):>7,}")
    print(f"  Strong Buy          : {dedup_classified_all.get('Strong Buy', 0):>7,}")
    print(f"  Very Strong Buy     : {dedup_classified_all.get('Very Strong Buy', 0):>7,}")
    print(f"  Institutional Buy   : {dedup_classified_all.get('Institutional Buy', 0):>7,}")
    print(f"  TOTAL               : {after_dedup:>7,}")

    print(f"\n{'─'*65}")
    print(f"  GATE REJECTION REASONS (5,776 candidate universe = DZ + score>=35)")
    print(f"{'─'*65}")
    cand = pass_score
    if cand > 0:
        pg_pct  = price_gate_fail_all / cand * 100
        adj_pct = adj_score_fail_all  / cand * 100
        liq_pct = liq_fail_all        / cand * 100
        buy_pct = sum(classified_all.values()) / cand * 100
    else:
        pg_pct = adj_pct = liq_pct = buy_pct = 0.0

    print(f"  Rejected by Price Gate       : {price_gate_fail_all:>6,}  ({pg_pct:.1f}% of {cand:,})")
    print(f"  Rejected by Adj Score Gate   : {adj_score_fail_all:>6,}  ({adj_pct:.1f}%)")
    print(f"  Liq Gate → Early Buy         : {liq_fail_all:>6,}  ({liq_pct:.1f}%)")
    print(f"  Passed All Gates → Buy family: {sum(classified_all.values()):>6,}  ({buy_pct:.1f}%)")

    print(f"\n{'─'*65}")
    print(f"  COUNTERFACTUAL: IF PRICE_GATE_NORMAL DISABLED (r1 gate removed)")
    print(f"{'─'*65}")
    print(f"  Currently Wait due to price gate : {price_gate_fail_all:>6,}")
    print(f"  Additional Early Buy             : +{cf_upgrade_early:>5,}")
    print(f"  Additional Buy                   : +{cf_upgrade_buy:>5,}")
    print(f"  Additional Strong Buy            : +{cf_upgrade_strong:>5,}")
    print(f"  Additional Very Strong Buy       : +{cf_upgrade_vstrong:>5,}")
    print(f"  Additional Institutional Buy     : +{cf_upgrade_inst:>5,}")
    cf_total_new = cf_upgrade_early + cf_upgrade_buy + cf_upgrade_strong + cf_upgrade_vstrong + cf_upgrade_inst
    print(f"  TOTAL NEW BUY SIGNALS            : +{cf_total_new:>5,}")
    print(f"  Still Wait (adj score gate)      : {cf_wait_remain:>6,}")

    print(f"\n{'─'*65}")
    print(f"  KEY FINDING: PRICE GATE COMPATIBILITY")
    print(f"{'─'*65}")
    print(f"  Max r1 achievable (W_PRICE)      : {W_PRICE:.2f}")
    print(f"  PRICE_GATE_NORMAL                : {PRICE_GATE_NORMAL}")
    print(f"  PRICE_GATE_WHITELIST             : {PRICE_GATE_WHITELIST}")
    print(f"  r1 can ever reach PRICE_GATE_NORMAL: {'YES' if W_PRICE >= PRICE_GATE_NORMAL else 'NO — GATE ALWAYS FAILS'}")
    print(f"  r1 can ever reach PRICE_GATE_WL  : {'YES' if W_PRICE >= PRICE_GATE_WHITELIST else 'NO — GATE ALWAYS FAILS'}")
    whitelist_blocked = sum(
        res["price_gate_fail"] for res in per_symbol
        if res["symbol"] in WHITELIST
    )
    normal_blocked = sum(
        res["price_gate_fail"] for res in per_symbol
        if res["symbol"] not in WHITELIST
    )
    print(f"  Price gate blocks (WHITELIST)    : {whitelist_blocked:>6,}")
    print(f"  Price gate blocks (NORMAL)       : {normal_blocked:>6,}")

    print(f"\n{'='*65}")
    print(f"  AUDIT COMPLETE")
    print(f"{'='*65}\n")


if __name__ == "__main__":
    run_audit()
