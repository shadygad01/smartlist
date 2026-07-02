"""
Edge Discovery Engine
=====================
يكتشف تلقائياً أفضل مجموعات الشروط (حتى 3 شروط) التي ترتبط بـ MFE عالي.

المنهج:
  1. تجربة كل شرط منفرد → اختبار إحصائي (binomtest)
  2. تجربة أزواج الشروط من الشروط المعنوية
  3. تجربة ثلاثيات من الأزواج المعنوية
  4. ترتيب النتائج بـ score = lift × log2(n+1) / (1 + p_value×5)

الضمانات:
  - تقسيم زمني: بيانات الاختبار من آخر 30% فقط
  - لا lookahead: كل المتغيرات من وقت الإشارة
  - حد أدنى MIN_N = 6 إشارة لكل قاعدة
"""
# Constitution §AUTOMATIC ARCHIVING RULE — Research only; no path to production without r1-r8 mapping
RESEARCH_ONLY_LAB = True

import math
import sys
import json
from datetime import date, timedelta
from itertools import combinations
from typing import Optional

try:
    import pandas as pd
    import numpy as np
except ImportError:
    sys.exit("Run: pip install pandas numpy")

try:
    from scipy.stats import binomtest
    SCIPY_OK = True
except ImportError:
    SCIPY_OK = False

from signal_db import DB_PATH, get_mature_signals

WIN_MFE_THRESHOLD = 0.08   # ≥8% MFE = "winner"
MIN_N             = 6      # حد أدنى للإشارات في كل قاعدة
MAX_P             = 0.20   # حد أقصى لـ p-value (توسّع للحصول على نتائج مبكرة)
TRAIN_SPLIT_PCT   = 0.70   # نفس تقسيم research_engine — لا تسرّب

# أنواع إشارات الدخول الفعلي فقط
ML_SIGNAL_TYPES = {"Early Buy", "Buy", "Strong Buy", "Very Strong Buy", "Institutional Buy"}

# ── قائمة الشروط المُختبَرة ───────────────────────────────────────────────────
# كل عنصر: (feature_col, operator, threshold, label_ar)
CONDITION_SPECS = [
    # Boolean features
    ("sv_hit",         "==", 1,    "Stopping Volume اكتُشف"),
    ("hvn_hit",        "==", 1,    "HVN اكتُشف"),
    ("rsi_div",        "==", 1,    "RSI Divergence"),
    ("macd_div",       "==", 1,    "MACD Divergence"),
    ("htf_hh",         "==", 1,    "HTF Higher High"),
    ("htf_hl",         "==", 1,    "HTF Higher Low"),
    ("sweep_detected", "==", 1,    "Sweep of Lows اكتُشف"),
    ("wick_rejection", "==", 1,    "Wick Rejection"),
    ("equal_lows",     "==", 1,    "Equal Lows"),
    ("price_ok",       "==", 1,    "بوابة السعر مفتوحة"),
    # r1_price thresholds
    ("r1_price",       ">=", 15,   "Score السعر ≥15"),
    ("r1_price",       ">=", 20,   "Score السعر ≥20"),
    ("r1_price",       ">=", 24,   "Score السعر ≥24"),
    # r3_liquidity thresholds
    ("r3_liquidity",   ">=", 12,   "Liquidity ≥12"),
    ("r3_liquidity",   ">=", 16,   "Liquidity ≥16"),
    ("r3_liquidity",   "==", 20,   "Liquidity = Max (20)"),
    # r8_demand thresholds
    ("r8_demand",      ">=", 8,    "Demand ≥8"),
    ("r8_demand",      ">=", 12,   "Demand ≥12"),
    # r4_htf thresholds
    ("r4_htf",         ">=", 5,    "HTF Score ≥5"),
    ("r4_htf",         ">=", 7,    "HTF Score ≥7"),
    # raw_score thresholds
    ("raw_score",      ">=", 50,   "Score الكلي ≥50"),
    ("raw_score",      ">=", 60,   "Score الكلي ≥60"),
    # rsi_val thresholds (oversold = good)
    ("rsi_val",        "<=", 30,   "RSI ≤30 (oversold قوي)"),
    ("rsi_val",        "<=", 35,   "RSI ≤35"),
    ("rsi_val",        "<=", 40,   "RSI ≤40"),
    # avwap_gap
    ("avwap_gap",      ">=", 0.4,  "AVWAP Gap ≥0.4"),
    ("avwap_gap",      ">=", 0.6,  "AVWAP Gap ≥0.6"),
    # discount_depth
    ("discount_depth", ">=", 0.4,  "عمق الخصم ≥40%"),
    ("discount_depth", ">=", 0.6,  "عمق الخصم ≥60%"),
    # ob_quality
    ("ob_quality",     ">=", 0.5,  "جودة OB ≥50%"),
    ("ob_quality",     ">=", 0.7,  "جودة OB ≥70%"),
    # vol_spike
    ("vol_spike",      ">=", 1.2,  "حجم التداول ≥1.2x"),
    ("vol_spike",      ">=", 1.5,  "حجم التداول ≥1.5x"),
    # sv_depth
    ("sv_depth",       ">=", 0.4,  "SV Depth ≥40%"),
    ("sv_depth",       ">=", 0.5,  "SV Depth ≥50%"),
    # sv_score / hvn_score
    ("sv_score",       ">=", 0.5,  "SV Score ≥0.5"),
    ("hvn_score",      ">=", 0.5,  "HVN Score ≥0.5"),
    # pattern_eff / pattern_wr
    ("pattern_eff",    ">=", 0.15, "Pattern Eff ≥15%"),
    ("pattern_wr",     ">=", 0.55, "Pattern Win Rate ≥55%"),
]


# ── Helpers ────────────────────────────────────────────────────────────────────

def _apply(series: pd.Series, op: str, threshold) -> pd.Series:
    """يُطبّق شرطاً على عمود ويُرجع boolean mask."""
    if   op == ">=": return series >= threshold
    elif op == "<=": return series <= threshold
    elif op == "==": return series == threshold
    elif op == ">":  return series >  threshold
    elif op == "<":  return series <  threshold
    else:
        raise ValueError(f"Unknown operator: {op}")


def _rule_stats(mask: pd.Series, y_win: pd.Series,
                y_mfe: pd.Series, y_bq: Optional[pd.Series],
                base_win_rate: float) -> Optional[dict]:
    """
    يحسب إحصائيات قاعدة واحدة.
    يُرجع None إذا كان العدد أقل من MIN_N.
    """
    n = int(mask.sum())
    if n < MIN_N:
        return None

    wins      = int(y_win[mask].sum())
    win_rate  = wins / n
    avg_mfe   = round(float(y_mfe[mask].mean()), 4)
    avg_bq    = round(float(y_bq[mask].mean()), 2) if (y_bq is not None and mask.sum() > 0) else None

    p_value = 1.0
    if SCIPY_OK:
        try:
            result  = binomtest(wins, n, max(base_win_rate, 0.01), alternative="greater")
            p_value = result.pvalue
        except Exception:
            p_value = 1.0

    lift  = win_rate / max(base_win_rate, 0.01)
    score = lift * math.log2(n + 1) / (1 + p_value * 5)

    return {
        "n":          n,
        "wins":       wins,
        "win_rate":   round(win_rate, 4),
        "avg_mfe":    avg_mfe,
        "avg_bq":     avg_bq,
        "p_value":    round(p_value, 4),
        "lift":       round(lift, 3),
        "score":      round(score, 3),
    }


def _condition_key(feat, op, threshold) -> str:
    return f"{feat}{op}{threshold}"


# ── Main Discovery ──────────────────────────────────────────────────────────────

def discover_edges(db_path: str = DB_PATH,
                   top_k: int = 20,
                   max_p: float = MAX_P,
                   verbose: bool = True) -> list[dict]:
    """
    يكتشف أفضل مجموعات الشروط ذات الدلالة الإحصائية.

    يُرجع:
        قائمة من top_k قاعدة، كل قاعدة dict:
        {rule, conditions, n, wins, win_rate, avg_mfe, avg_bq, p_value, lift, score}
    """
    if not SCIPY_OK:
        print("[EdgeDisc] scipy not installed — p-values will be 1.0 (no significance testing)")

    signals = get_mature_signals(db_path=db_path)
    if not signals:
        return []

    df = pd.DataFrame(signals).sort_values("signal_date").reset_index(drop=True)

    # إشارات الدخول الفعلي فقط
    if "signal_type" in df.columns:
        df = df[df["signal_type"].isin(ML_SIGNAL_TYPES)].reset_index(drop=True)

    if len(df) < MIN_N * 2:
        if verbose:
            print(f"[EdgeDisc] Only {len(df)} ML signals — need at least {MIN_N*2}")
        return []

    # تقسيم زمني: نختبر القواعد على آخر 30% فقط
    split = int(len(df) * TRAIN_SPLIT_PCT)
    test  = df.iloc[split:].copy().reset_index(drop=True)

    if len(test) < MIN_N:
        if verbose:
            print("[EdgeDisc] Test set too small — using full dataset")
        test = df.copy().reset_index(drop=True)

    if "mfe_20d" not in test.columns:
        if verbose:
            print("[EdgeDisc] mfe_20d column missing")
        return []

    y_win  = (test["mfe_20d"] >= WIN_MFE_THRESHOLD).astype(int)
    y_mfe  = test["mfe_20d"]
    y_bq   = test["bq_score"] if "bq_score" in test.columns else None

    total_wins    = int(y_win.sum())
    base_win_rate = total_wins / max(len(y_win), 1)

    if verbose:
        print(f"[EdgeDisc] Test set: {len(test)} signals | "
              f"base win rate: {base_win_rate:.1%} ({total_wins} winners)")

    # ── Single conditions ─────────────────────────────────────────────────────
    single_results = []   # list of (stats_dict, [(feat, op, thresh, label)])

    for feat, op, threshold, label in CONDITION_SPECS:
        if feat not in test.columns:
            continue
        col = test[feat].dropna()
        if len(col) < MIN_N:
            continue

        valid_mask = test[feat].notna()
        cond_mask  = valid_mask & _apply(test[feat].fillna(-9999), op, threshold)

        stats = _rule_stats(cond_mask, y_win, y_mfe, y_bq, base_win_rate)
        if stats is None:
            continue

        single_results.append((stats, [(feat, op, threshold, label)]))

    # تصفية بالـ max_p للحصول على الشروط المعنوية للمزج لاحقاً
    sig_singles = [(s, c) for s, c in single_results if s["p_value"] <= max_p]

    if verbose:
        print(f"[EdgeDisc] Singles: {len(single_results)} tested, "
              f"{len(sig_singles)} significant (p≤{max_p})")

    # ── Pairs ─────────────────────────────────────────────────────────────────
    pair_results = []
    seen_pairs   = set()

    for (s1, c1), (s2, c2) in combinations(sig_singles, 2):
        feat1, op1, t1, _ = c1[0]
        feat2, op2, t2, _ = c2[0]

        # لا نُكرر نفس الـ feature مع عتبات مختلفة كزوج (سيُغطيها المنفرد)
        if feat1 == feat2:
            continue

        pair_key = tuple(sorted([_condition_key(*c1[0][:3]), _condition_key(*c2[0][:3])]))
        if pair_key in seen_pairs:
            continue
        seen_pairs.add(pair_key)

        valid_mask = test[feat1].notna() & test[feat2].notna()
        cond_mask  = (valid_mask
                      & _apply(test[feat1].fillna(-9999), op1, t1)
                      & _apply(test[feat2].fillna(-9999), op2, t2))

        stats = _rule_stats(cond_mask, y_win, y_mfe, y_bq, base_win_rate)
        if stats is None:
            continue

        pair_results.append((stats, [c1[0], c2[0]]))

    sig_pairs = [(s, c) for s, c in pair_results if s["p_value"] <= max_p]

    if verbose:
        print(f"[EdgeDisc] Pairs:   {len(pair_results)} tested, "
              f"{len(sig_pairs)} significant (p≤{max_p})")

    # ── Triples ───────────────────────────────────────────────────────────────
    triple_results = []
    seen_triples   = set()

    # فقط أفضل 15 زوج معنوي (تقليص الحوسبة)
    top_pairs = sorted(sig_pairs, key=lambda x: x[0]["score"], reverse=True)[:15]

    for (sp, cp), single_sc in [(p, s) for p in top_pairs for s in sig_singles]:
        # الشروط الموجودة في الزوج
        pair_feats = {c[0] for c in cp}
        sfeat = single_sc[0][0]
        if sfeat in pair_feats:
            continue

        all_conds = cp + [single_sc[0]]
        triple_key = tuple(sorted(_condition_key(*c[:3]) for c in all_conds))
        if triple_key in seen_triples:
            continue
        seen_triples.add(triple_key)

        valid_mask = test[all_conds[0][0]].notna()
        for c in all_conds[1:]:
            valid_mask = valid_mask & test[c[0]].notna()

        cond_mask = valid_mask
        for feat, op, threshold, _ in all_conds:
            cond_mask = cond_mask & _apply(test[feat].fillna(-9999), op, threshold)

        stats = _rule_stats(cond_mask, y_win, y_mfe, y_bq, base_win_rate)
        if stats is None:
            continue

        triple_results.append((stats, all_conds))

    sig_triples = [(s, c) for s, c in triple_results if s["p_value"] <= max_p]

    if verbose:
        print(f"[EdgeDisc] Triples: {len(triple_results)} tested, "
              f"{len(sig_triples)} significant (p≤{max_p})")

    # ── Combine and rank ──────────────────────────────────────────────────────
    all_results = single_results + pair_results + triple_results
    all_results.sort(key=lambda x: x[0]["score"], reverse=True)

    output = []
    for stats, conditions in all_results[:top_k]:
        rule_parts = [f"{lbl}" for _, _, _, lbl in conditions]
        rule_text  = " AND ".join(rule_parts)
        cond_dicts = [
            {"feature": f, "op": op, "threshold": t, "label": lbl}
            for f, op, t, lbl in conditions
        ]
        output.append({
            "rule":        rule_text,
            "conditions":  cond_dicts,
            "n_conditions": len(conditions),
            **stats,
        })

    if verbose:
        print(f"[EdgeDisc] Top {len(output)} rules returned")
        if output:
            best = output[0]
            print(f"  Best: [{best['rule']}] "
                  f"n={best['n']} wr={best['win_rate']:.1%} "
                  f"lift={best['lift']:.2f} p={best['p_value']:.3f}")

    return output


# ── Main Entry Point ────────────────────────────────────────────────────────────

def run_edge_discovery(db_path: str = DB_PATH,
                       top_k: int = 20,
                       out_path: Optional[str] = None,
                       verbose: bool = True) -> list[dict]:
    """
    يُشغّل Edge Discovery الكامل ويحفظ النتائج اختيارياً.
    يُستدعى من research_engine.py أو مباشرة.
    """
    results = discover_edges(db_path=db_path, top_k=top_k, verbose=verbose)

    if out_path and results:
        try:
            with open(out_path, "w", encoding="utf-8") as f:
                json.dump({
                    "generated_at":    date.today().isoformat(),
                    "win_threshold":   WIN_MFE_THRESHOLD,
                    "top_k":           top_k,
                    "edges":           results,
                }, f, ensure_ascii=False, indent=2)
            if verbose:
                print(f"[EdgeDisc] Results saved → {out_path}")
        except Exception as e:
            print(f"[EdgeDisc] Save failed: {e}")

    return results


# ── CLI ────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser(description="EGX Edge Discovery Engine")
    p.add_argument("--db",    default=DB_PATH,          help="DB path")
    p.add_argument("--top",   default=20,  type=int,    help="Top K rules to return")
    p.add_argument("--max-p", default=0.20, type=float, help="Max p-value threshold")
    p.add_argument("--out",   default=None,             help="Output JSON path")
    p.add_argument("--quiet", action="store_true")
    args = p.parse_args()

    MAX_P = args.max_p
    edges = run_edge_discovery(
        db_path=args.db, top_k=args.top,
        out_path=args.out, verbose=not args.quiet,
    )

    if edges:
        print(f"\n{'='*65}")
        print(f"{'Rule':<45} {'N':>4} {'WR':>6} {'Lift':>5} {'P':>6}")
        print(f"{'='*65}")
        for e in edges[:10]:
            rule = e["rule"][:44]
            print(f"{rule:<45} {e['n']:>4} "
                  f"{e['win_rate']:>5.1%} {e['lift']:>5.2f} "
                  f"{e['p_value']:>6.3f}")
