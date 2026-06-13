"""
Rule Discovery Engine
=====================
Discovers repeatable market edges from historical EGX signals.

Four mining methods:
  1. Decision Trees  — path extraction from depth-limited trees
  2. RuleFit         — linear combination of tree rules  (requires imodels)
  3. Association Rules — Apriori on discretized features (requires mlxtend)
  4. Bayesian Rule List — sequential covering rules      (requires imodels)

Filters:  n >= 15 samples  |  p-value <= 0.10 (Mann-Whitney U vs complement)

Usage:
    python rule_discovery.py                   # full run, saves JSON + HTML
    python rule_discovery.py --dry-run         # print summary, no files
    python rule_discovery.py --db=custom.db    # custom DB path
"""

from __future__ import annotations

import json
import re
import sys
import warnings
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats as scipy_stats
from sklearn.preprocessing import KBinsDiscretizer
from sklearn.tree import DecisionTreeRegressor

warnings.filterwarnings("ignore")

from signal_db import DB_PATH, get_conn

# ── Config ────────────────────────────────────────────────────────────────────
WIN_THRESHOLD    = 8.0    # mfe_pct >= this → "win"
MIN_RULE_SAMPLES = 15
MAX_P_VALUE      = 0.10
MAX_DT_DEPTH     = 4
N_BINS           = 3
BIN_LABELS       = ["low", "med", "high"]
TOP_FINGERPRINTS = 20
TOP_RULES_GLOBAL = 60     # cap before dedup
EDGE_JSON_PATH   = "edge_discovery_results.json"

# ── Feature columns ───────────────────────────────────────────────────────────
FEAT_COLS = [
    "feat_dist_swing_low", "feat_dealing_range_pos", "feat_candles_since_bos",
    "feat_dist_last_bos", "feat_sweep_depth_pct", "feat_equal_lows_count",
    "feat_vol_spike_ratio", "feat_candles_since_sweep", "feat_accumulation_score",
    "feat_consec_red", "feat_down_days_pct", "feat_atr_compression",
    "feat_vol_contraction", "feat_dist_20d_low", "feat_dist_50d_low",
    "feat_dist_52w_low", "feat_vwap_dist", "feat_rs_vs_egx30",
    "feat_egx30_trend_val",
]
SNAP_COLS = [
    "snap_atr", "snap_wick_ratio", "snap_compression", "snap_consol_len",
    "snap_bos", "snap_bos_dist", "snap_choch", "snap_pivot_str",
    "snap_num_touches", "snap_sweep_size", "snap_vol_exp", "snap_reclaim_spd",
    "snap_dist_lo", "snap_prem_disc",
]
# Individual SMC indicator scores (stored in signals table, previously unused by ML)
SMC_SCORE_COLS = [
    "r1_price", "r2_ob", "r3_liquidity", "r4_htf",
    "r5_avwap", "r6_macd", "r7_div", "r8_demand",
]
ALL_FEAT_COLS = FEAT_COLS + SNAP_COLS + SMC_SCORE_COLS


# ─────────────────────────────────────────────────────────────────────────────
# Data loading
# ─────────────────────────────────────────────────────────────────────────────

def load_signal_data(db_path: str = DB_PATH) -> pd.DataFrame:
    conn = get_conn(db_path)
    view_exists = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='view' AND name='v_all_signals'"
    ).fetchone()
    if view_exists:
        df = pd.read_sql_query(
            "SELECT * FROM v_all_signals WHERE feat_dist_swing_low IS NOT NULL ORDER BY signal_date",
            conn,
        )
    else:
        feat_select = ", ".join(f"s.{c}" for c in ALL_FEAT_COLS)
        df = pd.read_sql_query(f"""
            SELECT
                s.id, s.symbol, s.signal_date, s.signal_type, s.raw_score,
                bq.bq_score, bq.mfe_20d, bq.mae_20d, bq.classification,
                {feat_select}
            FROM signals s
            JOIN bottom_quality bq ON bq.signal_id = s.id
            WHERE s.feat_dist_swing_low IS NOT NULL
        """, conn)
    conn.close()

    df["mfe_pct"] = df["mfe_20d"] * 100.0
    df["mae_pct"] = df["mae_20d"] * 100.0
    return df


def _prep_features(df: pd.DataFrame, min_fill_ratio: float = 0.5) -> list[str]:
    """Return feature columns with enough non-null data; fill remaining with median."""
    n = len(df)
    usable = []
    for col in ALL_FEAT_COLS:
        if col not in df.columns:
            continue
        fill_ratio = df[col].notna().mean()
        if fill_ratio < min_fill_ratio:
            continue
        df[col] = df[col].fillna(df[col].median())
        usable.append(col)
    return usable


# ─────────────────────────────────────────────────────────────────────────────
# Rule helpers
# ─────────────────────────────────────────────────────────────────────────────

def _rule_text(conditions: list[tuple]) -> str:
    parts = []
    for feat, op, val in conditions:
        # Pretty format
        display_op = "≤" if op == "<=" else (">" if op == ">" else op)
        parts.append(f"{feat} {display_op} {val:.4g}")
    return "  AND  ".join(parts)


def _eval_rule(df: pd.DataFrame, conditions: list[tuple]) -> pd.Series | None:
    mask = pd.Series(True, index=df.index)
    for feat, op, val in conditions:
        if feat not in df.columns:
            return None
        col = df[feat]
        if op in ("<=", "le"):
            mask &= col <= val
        elif op in (">", "gt"):
            mask &= col > val
        elif op in (">=", "ge"):
            mask &= col >= val
        elif op in ("<", "lt"):
            mask &= col < val
        elif op == "==":
            mask &= col == val
    return mask


def _compute_rule_stats(
    df: pd.DataFrame,
    mask: pd.Series,
    rule_text: str,
    source: str,
    conditions: list[tuple] | None = None,
) -> dict | None:
    matched = df[mask]
    n = int(mask.sum())
    if n < MIN_RULE_SAMPLES:
        return None

    mfe = matched["mfe_pct"].dropna()
    mae = matched["mae_pct"].dropna()
    bq  = matched["bq_score"].dropna()

    if len(mfe) < MIN_RULE_SAMPLES:
        return None

    unmatched_mfe = df[~mask]["mfe_pct"].dropna()
    if len(unmatched_mfe) >= 5:
        try:
            _, p_value = scipy_stats.mannwhitneyu(mfe, unmatched_mfe,
                                                   alternative="greater")
        except Exception:
            p_value = 1.0
    else:
        p_value = 1.0

    win_rate   = float((mfe >= WIN_THRESHOLD).mean())
    mfe_mean   = float(mfe.mean())
    mae_mean   = float(mae.mean())
    expectancy = mfe_mean * win_rate + mae_mean * (1 - win_rate)

    return {
        "rule_text":   rule_text,
        "conditions":  conditions or [],
        "source":      source,
        "n":           n,
        "mfe_mean":    round(mfe_mean, 2),
        "mae_mean":    round(mae_mean, 2),
        "bq_mean":     round(float(bq.mean()), 1) if len(bq) else None,
        "win_rate":    round(win_rate, 4),
        "expectancy":  round(expectancy, 2),
        "p_value":     round(float(p_value), 4),
        "significant": bool(p_value <= MAX_P_VALUE),
        "mfe_p75":     round(float(mfe.quantile(0.75)), 2),
        "mfe_p90":     round(float(mfe.quantile(0.90)), 2),
        "symbols":     sorted(matched["symbol"].unique().tolist()),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Method 1 — Decision Tree rules
# ─────────────────────────────────────────────────────────────────────────────

def _walk_tree(dt: DecisionTreeRegressor, feature_names: list[str]) -> list[list[tuple]]:
    tree = dt.tree_
    paths: list[list[tuple]] = []

    def recurse(node: int, conds: list[tuple]) -> None:
        left  = tree.children_left[node]
        right = tree.children_right[node]
        if left == right:          # leaf
            paths.append(list(conds))
            return
        fname  = feature_names[tree.feature[node]]
        thresh = round(float(tree.threshold[node]), 4)
        recurse(left,  conds + [(fname, "<=", thresh)])
        recurse(right, conds + [(fname, ">",  thresh)])

    recurse(0, [])
    return paths


def _discover_dt(df: pd.DataFrame, feat_cols: list[str]) -> list[dict]:
    if len(df) < MIN_RULE_SAMPLES * 2:
        return []
    X = df[feat_cols].values
    y = df["mfe_pct"].values

    rules: list[dict] = []
    # Fit at multiple depths to capture both coarse and fine patterns
    for depth in (2, 3, MAX_DT_DEPTH):
        try:
            dt = DecisionTreeRegressor(
                max_depth=depth,
                min_samples_leaf=MIN_RULE_SAMPLES,
                random_state=42,
            )
            dt.fit(X, y)
        except Exception as exc:
            print(f"  [dt] depth={depth} failed: {exc}")
            continue

        for conditions in _walk_tree(dt, feat_cols):
            mask = _eval_rule(df, conditions)
            if mask is None or mask.sum() < MIN_RULE_SAMPLES:
                continue
            stats = _compute_rule_stats(df, mask, _rule_text(conditions), "dt", conditions)
            if stats:
                rules.append(stats)

    return rules


# ─────────────────────────────────────────────────────────────────────────────
# Method 2 — RuleFit
# ─────────────────────────────────────────────────────────────────────────────

def _parse_rulefit_rule(rule_str: str) -> list[tuple]:
    """Parse RuleFit rule string — handles both 'and' and '&' separators."""
    conditions = []
    # Split on ' and ' (lowercase, imodels new API) or ' & '
    for part in re.split(r"\s+and\s+|\s*&\s*", rule_str.strip(), flags=re.IGNORECASE):
        m = re.match(r"([\w.]+)\s*(<=|>=|<|>|==)\s*([-\d.eE+]+)", part.strip())
        if m:
            feat, op, val = m.groups()
            try:
                conditions.append((feat, op, round(float(val), 4)))
            except ValueError:
                pass
    return conditions


def _discover_rulefit(df: pd.DataFrame, feat_cols: list[str]) -> list[dict]:
    try:
        from imodels import RuleFitRegressor
    except ImportError:
        print("  [rulefit] imodels not available — skipping")
        return []

    if len(df) < MIN_RULE_SAMPLES * 2:
        return []

    X = df[feat_cols].values
    y = df["mfe_pct"].values

    try:
        rfit = RuleFitRegressor(max_rules=300, random_state=42)
        rfit.fit(X, y, feature_names=feat_cols)
        # New imodels API: rules_ is a list of Rule objects (no get_rules())
        raw_rules = getattr(rfit, "rules_", None)
        if raw_rules is None:
            print("  [rulefit] rules_ attribute not found — skipping")
            return []
    except Exception as exc:
        print(f"  [rulefit] failed: {exc}")
        return []

    results: list[dict] = []
    for rule_obj in raw_rules:
        rule_str = getattr(rule_obj, "rule", None) or str(rule_obj)
        if not rule_str:
            continue
        conditions = _parse_rulefit_rule(rule_str)
        if not conditions:
            continue
        mask = _eval_rule(df, conditions)
        if mask is None or mask.sum() < MIN_RULE_SAMPLES:
            continue
        stats = _compute_rule_stats(df, mask, _rule_text(conditions), "rulefit", conditions)
        if stats:
            results.append(stats)

    return results


# ─────────────────────────────────────────────────────────────────────────────
# Method 3 — Association Rules (Apriori)
# ─────────────────────────────────────────────────────────────────────────────

def _discretize(df: pd.DataFrame, feat_cols: list[str]) -> tuple[pd.DataFrame, dict]:
    """Return one-hot binary DataFrame and bin_info dict for back-translation."""
    kbd = KBinsDiscretizer(n_bins=N_BINS, encode="ordinal", strategy="quantile")
    X_bin = kbd.fit_transform(df[feat_cols]).astype(int)
    bin_edges = kbd.bin_edges_

    bin_info: dict[str, tuple] = {}   # "feat_low" → (orig_col, bin_idx, lo, hi)
    bin_df = pd.DataFrame(index=df.index)
    for i, col in enumerate(feat_cols):
        edges = bin_edges[i]
        actual_bins = len(edges) - 1          # may be < N_BINS for low-variance cols
        for b in range(actual_bins):
            label    = BIN_LABELS[b] if b < len(BIN_LABELS) else f"bin{b}"
            bin_col  = f"{col}_{label}"
            lo       = round(float(edges[b]),   4)
            hi       = round(float(edges[b+1]), 4) if b+1 < len(edges) else None
            bin_df[bin_col]   = X_bin[:, i] == b
            bin_info[bin_col] = (col, b, lo, hi)

    return bin_df, bin_info


def _bin_conditions(antecedents, bin_info: dict) -> list[tuple]:
    conditions = []
    for item in antecedents:
        if item not in bin_info:
            continue
        col, b, lo, hi = bin_info[item]
        if b == 0:                          # low bin  → feat <= hi
            conditions.append((col, "<=", hi))
        elif b == 2:                        # high bin → feat > lo
            conditions.append((col, ">",  lo))
        else:                               # med bin  → lo < feat <= hi
            if hi is not None:
                conditions.append((col, "<=", hi))
            conditions.append((col, ">", lo))
    return conditions


def _discover_assoc(df: pd.DataFrame, feat_cols: list[str]) -> list[dict]:
    try:
        from mlxtend.frequent_patterns import apriori, association_rules as mlxtend_ar
    except ImportError:
        print("  [assoc] mlxtend not available — skipping")
        return []

    if len(df) < MIN_RULE_SAMPLES * 2:
        return []

    n = len(df)
    min_support = max(MIN_RULE_SAMPLES / n, 0.05)

    bin_df, bin_info = _discretize(df, feat_cols)
    bin_df["MFE_HIGH"] = (df["mfe_pct"] >= WIN_THRESHOLD).values

    try:
        freq = apriori(bin_df.astype(bool), min_support=min_support,
                       use_colnames=True, max_len=4, low_memory=True)
        if freq.empty:
            return []
        arules = mlxtend_ar(freq, metric="confidence", min_threshold=0.50)
    except Exception as exc:
        print(f"  [assoc] failed: {exc}")
        return []

    if arules.empty:
        return []

    target = frozenset({"MFE_HIGH"})
    mfe_rules = arules[arules["consequents"] == target].copy()
    if mfe_rules.empty:
        return []

    results: list[dict] = []
    for _, row in mfe_rules.iterrows():
        antecedents = list(row["antecedents"])
        if "MFE_HIGH" in antecedents:
            continue
        conditions = _bin_conditions(antecedents, bin_info)
        if not conditions:
            continue
        mask = _eval_rule(df, conditions)
        if mask is None or mask.sum() < MIN_RULE_SAMPLES:
            continue
        stats = _compute_rule_stats(df, mask, _rule_text(conditions), "assoc", conditions)
        if stats:
            results.append(stats)

    return results


# ─────────────────────────────────────────────────────────────────────────────
# Method 4 — Bayesian Rule Learning (BRL / GreedyRuleList fallback)
# ─────────────────────────────────────────────────────────────────────────────

def _discover_bayes(df: pd.DataFrame, feat_cols: list[str]) -> list[dict]:
    n = len(df)
    if n < MIN_RULE_SAMPLES * 2:
        return []

    # Try BayesianRuleListClassifier first, fall back to GreedyRuleListClassifier
    brl_cls = None
    try:
        from imodels import BayesianRuleListClassifier
        brl_cls = BayesianRuleListClassifier
    except ImportError:
        try:
            from imodels import GreedyRuleListClassifier as brl_cls
        except ImportError:
            print("  [bayes] imodels not available — skipping")
            return []

    bin_df, bin_info = _discretize(df, feat_cols)
    X_disc = bin_df[[c for c in bin_df.columns]].astype(int).values
    disc_feat_names = [c for c in bin_df.columns]
    y_binary = (df["mfe_pct"] >= WIN_THRESHOLD).astype(int).values

    try:
        kwargs: dict = {"random_state": 42}
        if brl_cls.__name__ == "BayesianRuleListClassifier":
            kwargs.update(
                max_iter=5000,
                listlengthprior=3,
                listwidthprior=1,
                maxcardinality=2,
                minsupport=float(MIN_RULE_SAMPLES) / n,
                class1label="high_mfe",
            )
        brl = brl_cls(**kwargs)
        brl.fit(X_disc, y_binary, feature_names=disc_feat_names)
    except Exception as exc:
        print(f"  [bayes] fit failed: {exc}")
        return []

    # ── Extract sequential rules from IF-THEN/ELSE IF output ─────────────────
    # BRL outputs: "IF cond THEN prob%", "ELSE IF cond THEN prob%", "ELSE prob%"
    # Each rule in the list applies to samples NOT covered by prior rules.
    # We must evaluate them sequentially with a remaining_mask to avoid overlap.
    raw_lines = str(brl).splitlines()
    if_lines: list[str] = []
    for l in raw_lines:
        stripped = l.strip()
        upper = stripped.upper()
        if upper.startswith("IF ") or upper.startswith("ELSE IF "):
            # Normalize: strip leading "ELSE " so all start with "IF "
            normalized = re.sub(r"^ELSE\s+", "", stripped, flags=re.IGNORECASE).strip()
            if_lines.append(normalized)

    results: list[dict] = []
    remaining_mask = pd.Series(True, index=df.index)
    # Accumulated negations of prior single-condition rules (for full sequential context)
    prior_neg: list[tuple] = []

    for line in if_lines:
        # Extract the antecedent: everything between "IF" and "THEN"
        m = re.match(r"IF\s+(.+?)\s+THEN", line, re.IGNORECASE)
        if not m:
            continue
        antecedent_str = m.group(1)
        # Split on AND
        parts = re.split(r"\bAND\b", antecedent_str, flags=re.IGNORECASE)
        antecedents = []
        for part in parts:
            part = part.strip()
            fm = re.match(r"([\w_]+)\s*[><=!]+\s*[\d.]+", part)
            if fm and fm.group(1) in bin_info:
                antecedents.append(fm.group(1))
        if not antecedents:
            continue
        conditions = _bin_conditions(antecedents, bin_info)
        if not conditions:
            continue
        rule_mask = _eval_rule(df, conditions)
        if rule_mask is None:
            continue

        # Sequential mask: only samples not yet covered by any prior rule
        seq_mask = remaining_mask & rule_mask
        remaining_mask = remaining_mask & ~rule_mask  # advance coverage window

        # Build full conditions = accumulated prior negations + this rule's conditions.
        # This gives each sequential rule a unique dedup key that includes its context.
        full_conditions = prior_neg + conditions

        if seq_mask.sum() < MIN_RULE_SAMPLES:
            # Still advance prior_neg for subsequent rules
            if len(conditions) == 1:
                feat, op, val = conditions[0]
                neg_op = "<=" if op == ">" else ">" if op == "<=" else None
                if neg_op:
                    prior_neg = prior_neg + [(feat, neg_op, val)]
            continue

        stats = _compute_rule_stats(df, seq_mask, _rule_text(full_conditions), "bayes", full_conditions)
        if stats:
            results.append(stats)

        # Accumulate negation of this rule for the next rule's context.
        # Only flip simple single-condition rules (OR-logic of multi-condition
        # negations can't be expressed as AND, so skip those).
        if len(conditions) == 1:
            feat, op, val = conditions[0]
            neg_op = "<=" if op == ">" else ">" if op == "<=" else None
            if neg_op:
                prior_neg = prior_neg + [(feat, neg_op, val)]

    return results


# ─────────────────────────────────────────────────────────────────────────────
# Rule merging & deduplication
# ─────────────────────────────────────────────────────────────────────────────

def _dedup_rules(rules: list[dict]) -> list[dict]:
    """Remove near-duplicate rules (same conditions, different source)."""
    seen: set[str] = set()
    out: list[dict] = []
    for r in rules:
        key = frozenset((c[0], c[1], round(c[2], 2)) for c in r.get("conditions", []))
        k = str(sorted(key))
        if k not in seen:
            seen.add(k)
            out.append(r)
    return out


def _merge_and_rank(all_rules: list[dict]) -> list[dict]:
    """Merge rules from all methods, dedup, filter, rank by expectancy."""
    valid = [r for r in all_rules if r.get("n", 0) >= MIN_RULE_SAMPLES]
    deduped = _dedup_rules(valid)
    # Rank: primary = expectancy, secondary = mfe_mean, tertiary = n
    ranked = sorted(
        deduped,
        key=lambda r: (r.get("expectancy", 0), r.get("mfe_mean", 0), r.get("n", 0)),
        reverse=True,
    )
    return ranked


# ─────────────────────────────────────────────────────────────────────────────
# Per-stock rules
# ─────────────────────────────────────────────────────────────────────────────

def _per_stock_rules(df: pd.DataFrame, feat_cols: list[str]) -> dict[str, list[dict]]:
    result: dict[str, list[dict]] = {}
    for symbol, sdf in df.groupby("symbol"):
        if len(sdf) < MIN_RULE_SAMPLES:
            result[symbol] = []
            continue
        sdf = sdf.reset_index(drop=True)
        rules = _discover_dt(sdf, feat_cols)
        valid = [r for r in rules if r.get("n", 0) >= MIN_RULE_SAMPLES and r.get("significant")]
        result[symbol] = sorted(valid, key=lambda r: r.get("expectancy", 0), reverse=True)[:10]
    return result


# ─────────────────────────────────────────────────────────────────────────────
# Bottom DNA
# ─────────────────────────────────────────────────────────────────────────────

def _compute_bottom_dna(df: pd.DataFrame, feat_cols: list[str]) -> dict:
    q90 = df["mfe_pct"].quantile(0.90)
    q10 = df["mfe_pct"].quantile(0.10)
    top_df = df[df["mfe_pct"] >= q90].copy()
    bot_df = df[df["mfe_pct"] <= q10].copy()

    dna: dict = {
        "top_10_pct": {
            "n":             int(len(top_df)),
            "mfe_threshold": round(float(q90), 2),
            "mfe_mean":      round(float(top_df["mfe_pct"].mean()), 2),
            "bq_mean":       round(float(top_df["bq_score"].mean()), 1),
            "symbols":       top_df["symbol"].value_counts().head(10).to_dict(),
        },
        "bot_10_pct": {
            "n":             int(len(bot_df)),
            "mfe_threshold": round(float(q10), 2),
            "mfe_mean":      round(float(bot_df["mfe_pct"].mean()), 2),
            "bq_mean":       round(float(bot_df["bq_score"].mean()), 1),
            "symbols":       bot_df["symbol"].value_counts().head(10).to_dict(),
        },
        "features":            {},
        "high_return_ranges":  {},
    }

    for col in feat_cols:
        top_v   = top_df[col].dropna()
        bot_v   = bot_df[col].dropna()
        all_v   = df[col].dropna()
        if len(top_v) < 3 or len(bot_v) < 3:
            continue
        try:
            _, p = scipy_stats.mannwhitneyu(top_v, bot_v, alternative="two-sided")
        except Exception:
            p = 1.0
        dna["features"][col] = {
            "top_mean":       round(float(top_v.mean()), 4),
            "bot_mean":       round(float(bot_v.mean()), 4),
            "global_mean":    round(float(all_v.mean()), 4),
            "top_vs_global":  round(float(top_v.mean() - all_v.mean()), 4),
            "bot_vs_global":  round(float(bot_v.mean() - all_v.mean()), 4),
            "top_vs_bot":     round(float(top_v.mean() - bot_v.mean()), 4),
            "p_value":        round(float(p), 4),
            "significant":    bool(p <= 0.10),
        }
        dna["high_return_ranges"][col] = {
            "p25":    round(float(top_v.quantile(0.25)), 4),
            "median": round(float(top_v.median()),       4),
            "p75":    round(float(top_v.quantile(0.75)), 4),
        }

    return dna


# ─────────────────────────────────────────────────────────────────────────────
# Main orchestration
# ─────────────────────────────────────────────────────────────────────────────

def run_rule_discovery(db_path: str = DB_PATH, dry_run: bool = False) -> dict:
    print("=" * 62)
    print("  RULE DISCOVERY ENGINE")
    print("=" * 62)

    df = load_signal_data(db_path)
    print(f"  Loaded {len(df)} signals from DB")

    if len(df) < MIN_RULE_SAMPLES * 2:
        print(f"  Not enough data (need ≥{MIN_RULE_SAMPLES * 2})")
        return {}

    feat_cols = _prep_features(df)
    print(f"  Usable features: {len(feat_cols)} / {len(ALL_FEAT_COLS)}")
    print(f"  MFE range: {df['mfe_pct'].min():.1f}% → {df['mfe_pct'].max():.1f}%  "
          f"avg={df['mfe_pct'].mean():.1f}%")
    print(f"  Win rate (≥{WIN_THRESHOLD}%): "
          f"{(df['mfe_pct'] >= WIN_THRESHOLD).mean():.1%}\n")

    # ── Run all four methods ──────────────────────────────────────────────────
    all_rules: list[dict] = []

    print("  [1/4] Decision Trees ...")
    dt_rules = _discover_dt(df, feat_cols)
    print(f"        {len(dt_rules)} raw rules")
    all_rules.extend(dt_rules)

    print("  [2/4] RuleFit ...")
    rf_rules = _discover_rulefit(df, feat_cols)
    print(f"        {len(rf_rules)} raw rules")
    all_rules.extend(rf_rules)

    print("  [3/4] Association Rules ...")
    ar_rules = _discover_assoc(df, feat_cols)
    print(f"        {len(ar_rules)} raw rules")
    all_rules.extend(ar_rules)

    print("  [4/4] Bayesian Rule Learning ...")
    brl_rules = _discover_bayes(df, feat_cols)
    print(f"        {len(brl_rules)} raw rules")
    all_rules.extend(brl_rules)

    # ── Merge, filter, rank ───────────────────────────────────────────────────
    ranked = _merge_and_rank(all_rules)
    significant = [r for r in ranked if r.get("significant")]
    print(f"\n  Total raw:    {len(all_rules)}")
    print(f"  After dedup:  {len(ranked)}")
    print(f"  Significant:  {len(significant)}")

    # ── Per-stock rules ───────────────────────────────────────────────────────
    print("\n  Per-stock rules ...")
    ps_rules = _per_stock_rules(df, feat_cols)
    ps_qualifying = {s: r for s, r in ps_rules.items() if r}
    print(f"  Stocks with ≥{MIN_RULE_SAMPLES} signals: "
          f"{sum(1 for s in ps_rules if len(df[df.symbol==s]) >= MIN_RULE_SAMPLES)}")
    print(f"  Stocks with qualifying rules: {len(ps_qualifying)}")

    # ── Bottom DNA ────────────────────────────────────────────────────────────
    print("\n  Bottom DNA analysis ...")
    dna = _compute_bottom_dna(df, feat_cols)
    sig_feats = sum(1 for v in dna["features"].values() if v.get("significant"))
    print(f"  Significant DNA features: {sig_feats}")

    # ── Top fingerprints ──────────────────────────────────────────────────────
    top_fp = significant[:TOP_FINGERPRINTS]

    # ── Source breakdown ──────────────────────────────────────────────────────
    source_counts: dict[str, int] = defaultdict(int)
    for r in significant:
        source_counts[r["source"]] += 1

    results = {
        "generated_at":  datetime.utcnow().isoformat(),
        "date":          date.today().isoformat(),
        "n_signals":     int(len(df)),
        "n_features":    int(len(feat_cols)),
        "win_threshold": WIN_THRESHOLD,
        "global_win_rate": round(float((df["mfe_pct"] >= WIN_THRESHOLD).mean()), 4),
        "global_mfe_mean": round(float(df["mfe_pct"].mean()), 2),
        "global_mae_mean": round(float(df["mae_pct"].mean()), 2),
        "global_bq_mean":  round(float(df["bq_score"].mean()), 1),
        "total_rules_raw":         len(all_rules),
        "total_rules_significant": len(significant),
        "source_counts":           dict(source_counts),
        "rules":                   ranked,
        "significant_rules":       significant,
        "top_rules":               sorted(
            significant, key=lambda x: float(x.get("expectancy", 0) or 0), reverse=True
        )[:20],
        "per_stock_rules":         ps_rules,
        "bottom_dna":              dna,
        "top_fingerprints":        top_fp,
        "feat_cols":               feat_cols,
    }

    if dry_run:
        print("\n  [dry-run] Skipping file write.")
        _print_summary(results)
        return results

    with open(EDGE_JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, default=str)
    print(f"\n  Saved → {EDGE_JSON_PATH}")

    _print_summary(results)
    return results


def _print_summary(res: dict) -> None:
    print("\n" + "─" * 62)
    print("  TOP 10 RULES BY EXPECTANCY")
    print("─" * 62)
    for i, r in enumerate(res.get("significant_rules", [])[:10], 1):
        print(f"  [{i:2d}] n={r['n']:3d}  MFE={r['mfe_mean']:+.1f}%  "
              f"WR={r['win_rate']:.0%}  E={r['expectancy']:+.1f}%  "
              f"p={r['p_value']:.3f}  [{r['source']}]")
        print(f"       {r['rule_text'][:80]}")

    print("\n  BOTTOM DNA — Top 10% vs Worst 10%")
    dna_feats = res.get("bottom_dna", {}).get("features", {})
    sig_sorted = sorted(
        [(k, v) for k, v in dna_feats.items() if v.get("significant")],
        key=lambda x: abs(x[1].get("top_vs_bot", 0)),
        reverse=True,
    )
    for col, v in sig_sorted[:8]:
        print(f"  {col:35s}  top={v['top_mean']:+.3f}  bot={v['bot_mean']:+.3f}  "
              f"Δ={v['top_vs_bot']:+.3f}  p={v['p_value']:.3f}")


if __name__ == "__main__":
    dry = "--dry-run" in sys.argv
    db  = DB_PATH
    for a in sys.argv[1:]:
        if a.startswith("--db="):
            db = a[5:]
    run_rule_discovery(db_path=db, dry_run=dry)
