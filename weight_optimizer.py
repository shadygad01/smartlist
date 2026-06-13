"""
weight_optimizer.py — Full Quant Research Engine for EGX SMC Scanner

THE ONLY HARDCODED RULE: ENTRY MUST BE IN DISCOUNT ZONE (price < EQ / r1 >= 1)
Everything else is data-driven and subject to challenge or replacement.

Optimizes for: Expected Return → Profit Factor → MFE → Consistency
NOT for: Win Rate alone

A 40% win rate with +35% avg winner and -8% avg loser
is SUPERIOR to 70% win rate with +8% avg winner and -6% avg loser.
Expected = 0.4×35 - 0.6×8 = +9.2% vs 0.7×8 - 0.3×6 = +3.8%
"""

import os
import sys
import json
import sqlite3
import warnings
from datetime import datetime
from collections import defaultdict

import numpy as np
import pandas as pd
from scipy import stats
from scipy.optimize import minimize

warnings.filterwarnings("ignore")

try:
    from sklearn.ensemble import RandomForestRegressor, GradientBoostingRegressor
    from sklearn.model_selection import TimeSeriesSplit
    from sklearn.linear_model import Ridge
    from sklearn.inspection import permutation_importance
    SKLEARN_OK = True
except ImportError:
    SKLEARN_OK = False

from signal_db import DB_PATH, get_conn

# ── Constants ──────────────────────────────────────────────────────────────────

R_COLS   = ['r1_price', 'r2_ob', 'r3_liquidity', 'r4_htf',
            'r5_avwap', 'r6_macd', 'r7_div', 'r8_demand']
R_MAX    = {'r1_price': 30, 'r2_ob': 10, 'r3_liquidity': 20, 'r4_htf': 10,
            'r5_avwap':  8, 'r6_macd': 4,  'r7_div': 3,    'r8_demand': 15}
R_LABELS = {'r1_price': 'Price Zone', 'r2_ob': 'Order Block',
            'r3_liquidity': 'Liquidity', 'r4_htf': 'HTF Structure',
            'r5_avwap': 'AVWAP', 'r6_macd': 'MACD',
            'r7_div': 'Divergence', 'r8_demand': 'Demand Zone'}
R_CURRENT_W = {'r1_price': 30, 'r2_ob': 10, 'r3_liquidity': 20, 'r4_htf': 10,
               'r5_avwap':  8, 'r6_macd': 4,  'r7_div': 3,    'r8_demand': 15}

WIN_THRESH   = 0.05     # 5% = meaningful win
RETAIN_MIN   = 0.40     # never kill >60% of signals
TODAY_STR    = datetime.utcnow().strftime("%Y-%m-%d")
REPORT_FILE  = f"reports/weight_optimizer_report_{TODAY_STR}.html"
RESULTS_FILE = "optimization_results.json"


# ── Data Loading ───────────────────────────────────────────────────────────────

def load_data(db_path: str = DB_PATH) -> pd.DataFrame:
    conn = get_conn(db_path)
    views = [r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='view' AND name='v_all_signals'"
    ).fetchall()]
    if views:
        df = pd.read_sql("""
            SELECT id, symbol, signal_date, raw_score,
                   r1_price, r2_ob, r3_liquidity, r4_htf,
                   r5_avwap, r6_macd, r7_div, r8_demand,
                   r20d, mfe_20d, mae_20d,
                   source
            FROM v_all_signals
            WHERE r20d IS NOT NULL AND mfe_20d IS NOT NULL
        """, conn)
    else:
        df = pd.read_sql("""
            SELECT s.id, s.symbol, s.signal_date, s.signal_type, s.raw_score,
                   s.r1_price, s.r2_ob, s.r3_liquidity, s.r4_htf,
                   s.r5_avwap, s.r6_macd, s.r7_div, s.r8_demand,
                   bq.r20d, bq.mfe_20d, bq.mae_20d,
                   bq.r40d, bq.mfe_40d, bq.mae_40d,
                   bq.bq_score, bq.time_to_recovery, bq.drawdown_duration,
                   bq.days_to_peak, bq.classification
            FROM signals s
            JOIN bottom_quality bq ON s.id = bq.signal_id
            WHERE bq.r20d IS NOT NULL
              AND bq.mfe_20d IS NOT NULL
        """, conn)
        df['source'] = 'live'
    conn.close()
    for col in ['signal_type', 'r40d', 'mfe_40d', 'mae_40d', 'bq_score',
                'time_to_recovery', 'drawdown_duration', 'days_to_peak', 'classification']:
        if col not in df.columns:
            df[col] = None
    df['signal_date'] = pd.to_datetime(df['signal_date'])
    df = df.sort_values('signal_date').reset_index(drop=True)

    # Normalized r-values [0, 1]
    for col in R_COLS:
        df[f'n_{col}'] = (df[col].fillna(0).clip(0, R_MAX[col]) / R_MAX[col])

    # Derived
    df['win_20']   = (df['r20d'] > 0).astype(int)
    df['win_5pct'] = (df['r20d'] >= WIN_THRESH).astype(int)
    df['year']     = df['signal_date'].dt.year

    return df


# ── Metrics Engine ─────────────────────────────────────────────────────────────

def compute_metrics(df: pd.DataFrame, label: str = "") -> dict:
    """Compute all 10 requested metrics for a subset of signals."""
    if df.empty:
        return {'n': 0, 'label': label}

    r    = df['r20d'].dropna()
    mfe  = df['mfe_20d'].dropna()
    mae  = df['mae_20d'].dropna()
    n    = len(r)

    if n == 0:
        return {'n': 0, 'label': label}

    wins   = r[r > 0]
    losses = r[r <= 0]

    win_rate = len(wins) / n
    avg_win  = wins.mean()  if len(wins)   > 0 else 0.0
    avg_loss = losses.mean() if len(losses) > 0 else 0.0
    pf       = (wins.sum() / abs(losses.sum())) if losses.sum() != 0 else float('inf')

    # Expected return = mean r20d (equivalent to WR×avgW + (1-WR)×avgL)
    exp_ret = r.mean()

    # Max drawdown = worst single trade loss
    max_dd = r.min()

    # Recovery time (from DB if available)
    rec = df['time_to_recovery'].dropna()
    recovery_time = rec.mean() if len(rec) > 0 else None

    # Risk-adjusted return (Sharpe-like, annualized ≈ 252/20 periods per year)
    ann_factor = (252 / 20) ** 0.5
    risk_adj   = (r.mean() / r.std() * ann_factor) if r.std() > 0 else 0.0

    # Consistency = % of rolling 10-trade windows with positive mean
    if n >= 10:
        rolling_ret = r.rolling(10).mean().dropna()
        consistency = (rolling_ret > 0).mean()
    else:
        consistency = win_rate

    # Calmar-like = mean_return / abs(max_dd)
    calmar = abs(exp_ret / max_dd) if max_dd < 0 else float('inf')

    return {
        'label':             label,
        'n':                 n,
        'win_rate':          win_rate,
        'win_rate_5pct':     (r >= WIN_THRESH).mean(),
        'expected_return':   exp_ret,
        'median_return':     r.median(),
        'avg_win':           avg_win,
        'avg_loss':          avg_loss,
        'mfe':               mfe.mean(),
        'mae':               mae.mean(),
        'max_dd':            max_dd,
        'recovery_time':     recovery_time,
        'profit_factor':     pf,
        'opportunity_count': n,
        'risk_adj_return':   risk_adj,
        'consistency':       consistency,
        'calmar':            calmar,
    }


# ── Baseline ──────────────────────────────────────────────────────────────────

def baseline_metrics(df: pd.DataFrame) -> dict:
    return compute_metrics(df, "All signals (baseline)")


# ── Phase 1: Individual Indicator Analysis ────────────────────────────────────

def analyze_indicators(df: pd.DataFrame) -> list:
    """For each r1-r8: show expected return by value range + find optimal threshold."""
    results = []
    base = compute_metrics(df)

    for col in R_COLS:
        mx  = R_MAX[col]
        lbl = R_LABELS[col]
        vals = df[col].dropna()

        # Spearman correlation with r20d and mfe_20d
        r20_corr, r20_p = stats.spearmanr(df[col].fillna(0), df['r20d'])
        mfe_corr, mfe_p = stats.spearmanr(df[col].fillna(0), df['mfe_20d'])

        # Expected return by unique value (or bin if too many unique values)
        unique_vals = sorted(vals.unique())
        by_value = []
        for v in unique_vals:
            sub = df[df[col] == v]
            if len(sub) >= 5:
                m = compute_metrics(sub)
                m['value'] = v
                by_value.append(m)

        # Find optimal minimum threshold: at each cutoff, measure improvement vs baseline
        # while checking retention
        best_threshold = None
        best_exp_ret = base['expected_return']
        best_mfe     = base['mfe']
        best_n       = base['n']
        threshold_scan = []
        for v in unique_vals[1:]:  # skip 0 as threshold
            sub = df[df[col] >= v]
            ret = len(sub) / base['n']
            if ret < RETAIN_MIN:
                break
            m = compute_metrics(sub, f"{col} >= {v}")
            threshold_scan.append({
                'threshold': v,
                'n': len(sub),
                'retention': ret,
                'exp_ret': m['expected_return'],
                'mfe': m['mfe'],
                'pf': m['profit_factor'],
            })
            if m['expected_return'] > best_exp_ret and ret >= RETAIN_MIN:
                best_exp_ret = m['expected_return']
                best_mfe     = m['mfe']
                best_n       = len(sub)
                best_threshold = v

        results.append({
            'col':            col,
            'label':          lbl,
            'max_val':        mx,
            'current_weight': R_CURRENT_W[col],
            'corr_r20d':      r20_corr,
            'corr_r20d_p':    r20_p,
            'corr_mfe':       mfe_corr,
            'corr_mfe_p':     mfe_p,
            'by_value':       by_value,
            'threshold_scan': threshold_scan,
            'best_threshold': best_threshold,
            'best_exp_ret':   best_exp_ret,
            'best_mfe':       best_mfe,
            'best_n':         best_n,
            'zero_pct':       (vals == 0).mean(),
            'mean_val':       vals.mean(),
        })

    return results


# ── Phase 2: Score Quintile & Non-linearity Analysis ─────────────────────────

def analyze_score_nonlinearity(df: pd.DataFrame) -> dict:
    """Check if score→return relationship is linear or shows sweet spot."""
    df2 = df.copy()
    df2['score_q'] = pd.qcut(df2['raw_score'], q=5, labels=['Q1','Q2','Q3','Q4','Q5'],
                              duplicates='drop')
    by_quintile = []
    for q in ['Q1','Q2','Q3','Q4','Q5']:
        sub = df2[df2['score_q'] == q]
        if len(sub) >= 5:
            m = compute_metrics(sub, f"Score {q}")
            m['score_range'] = (sub['raw_score'].min(), sub['raw_score'].max())
            by_quintile.append(m)

    # Find sweet spot: range with max expected return
    if by_quintile:
        best_q = max(by_quintile, key=lambda x: x['expected_return'])
    else:
        best_q = None

    # Score threshold scan
    score_scan = []
    for thr in range(20, 90, 5):
        sub = df[df['raw_score'] >= thr]
        ret = len(sub) / len(df)
        if ret < RETAIN_MIN:
            break
        m = compute_metrics(sub)
        score_scan.append({
            'threshold': thr, 'n': len(sub), 'retention': ret,
            'exp_ret': m['expected_return'], 'mfe': m['mfe'], 'pf': m['profit_factor'],
        })

    return {
        'by_quintile':    by_quintile,
        'best_quintile':  best_q,
        'score_scan':     score_scan,
    }


# ── Phase 3: Feature Importance (Random Forest) ───────────────────────────────

def feature_importance_analysis(df: pd.DataFrame) -> dict:
    """RF feature importance with walk-forward validation."""
    if not SKLEARN_OK:
        return {'error': 'sklearn not available'}

    n_cols = [f'n_{c}' for c in R_COLS]
    X = df[n_cols].fillna(0).values
    y_r20d = df['r20d'].values
    y_mfe  = df['mfe_20d'].values

    results = {}

    for target_name, y in [('r20d', y_r20d), ('mfe_20d', y_mfe)]:
        rf = RandomForestRegressor(
            n_estimators=300, max_depth=5, min_samples_leaf=15,
            random_state=42, n_jobs=-1
        )

        # Walk-forward CV (time-ordered)
        tscv  = TimeSeriesSplit(n_splits=5)
        oos_r2s = []
        fold_importances = []

        for train_idx, test_idx in tscv.split(X):
            rf.fit(X[train_idx], y[train_idx])
            score = rf.score(X[test_idx], y[test_idx])
            oos_r2s.append(score)
            fold_importances.append(rf.feature_importances_)

        # Full-dataset importance
        rf.fit(X, y)
        full_imp = rf.feature_importances_

        # Average fold importances
        avg_fold_imp = np.mean(fold_importances, axis=0)

        imp_df = pd.DataFrame({
            'feature':       [R_LABELS[c] for c in R_COLS],
            'col':           R_COLS,
            'full_imp':      full_imp,
            'oos_imp':       avg_fold_imp,
            'current_weight': [R_CURRENT_W[c] for c in R_COLS],
        }).sort_values('full_imp', ascending=False)

        results[target_name] = {
            'oos_r2':      np.mean(oos_r2s),
            'oos_r2_std':  np.std(oos_r2s),
            'importances': imp_df.to_dict('records'),
        }

    return results


# ── Phase 4: Pairwise Interaction Analysis ────────────────────────────────────

def interaction_analysis(df: pd.DataFrame) -> list:
    """Test every pair of r-components: do combinations outperform singles?"""
    base = compute_metrics(df)
    interactions = []

    top_cols = ['r1_price', 'r3_liquidity', 'r4_htf', 'r5_avwap', 'r6_macd', 'r8_demand']

    for i, c1 in enumerate(top_cols):
        for c2 in top_cols[i+1:]:
            # Both present (>0 for both)
            both = df[(df[c1] > 0) & (df[c2] > 0)]
            c1_only = df[(df[c1] > 0) & (df[c2] == 0)]
            c2_only = df[(df[c1] == 0) & (df[c2] > 0)]
            neither = df[(df[c1] == 0) & (df[c2] == 0)]

            if len(both) < 10 or len(both) / len(df) < RETAIN_MIN:
                continue

            m_both    = compute_metrics(both)
            m_c1only  = compute_metrics(c1_only)
            m_c2only  = compute_metrics(c2_only)
            m_neither = compute_metrics(neither)

            # Is combination synergistic?
            synergy = m_both['expected_return'] - max(
                m_c1only.get('expected_return', 0),
                m_c2only.get('expected_return', 0)
            )

            interactions.append({
                'c1': c1, 'c2': c2,
                'c1_label': R_LABELS[c1], 'c2_label': R_LABELS[c2],
                'n_both':    len(both),
                'n_c1only':  len(c1_only),
                'n_c2only':  len(c2_only),
                'n_neither': len(neither),
                'ret_both':    m_both.get('expected_return', 0),
                'ret_c1only':  m_c1only.get('expected_return', 0),
                'ret_c2only':  m_c2only.get('expected_return', 0),
                'ret_neither': m_neither.get('expected_return', 0),
                'mfe_both':    m_both.get('mfe', 0),
                'pf_both':     m_both.get('profit_factor', 1),
                'synergy':     synergy,
                'retention':   len(both) / len(df),
            })

    return sorted(interactions, key=lambda x: x['ret_both'], reverse=True)


# ── Phase 5: Walk-Forward Weight Optimization ─────────────────────────────────

def optimize_weights(df: pd.DataFrame) -> dict:
    """
    Find optimal linear weights for r1-r8 to maximize expected return.
    Uses walk-forward validation to prevent overfitting.
    Constraint: discount zone entry preserved (r1 >= 1).
    """
    n_cols = [f'n_{c}' for c in R_COLS]
    X = df[n_cols].fillna(0).values
    y = df['r20d'].values

    def new_score(w, X_data):
        return X_data @ w

    def objective(w):
        w = np.maximum(w, 0)  # weights must be non-negative
        w = w / (w.sum() + 1e-9)  # normalize to sum=1
        scores = new_score(w, X)
        # Select signals above median score
        thresh = np.percentile(scores, 50)
        mask   = scores >= thresh
        if mask.sum() < 20:
            return 0.0
        return -y[mask].mean()  # maximize expected return

    # Current normalized weights (as reference)
    total_w = sum(R_CURRENT_W.values())  # 100
    current_w_norm = np.array([R_CURRENT_W[c] / total_w for c in R_COLS])

    # Bounds: each weight can be 0 to 3× current (scaled)
    bounds = [(0, 0.6)] * len(R_COLS)
    # r1_price (discount zone) must keep weight > 0 (hardcoded constraint)
    bounds[0] = (0.05, 0.6)

    best_result = None
    best_val    = float('inf')

    # Multiple random starts to avoid local minima
    rng = np.random.RandomState(42)
    for _ in range(50):
        w0 = rng.dirichlet(np.ones(len(R_COLS)))
        res = minimize(objective, w0, method='L-BFGS-B', bounds=bounds,
                       options={'maxiter': 1000, 'ftol': 1e-9})
        if res.fun < best_val:
            best_val    = res.fun
            best_result = res

    if best_result is None:
        return {}

    opt_w = np.maximum(best_result.x, 0)
    opt_w = opt_w / opt_w.sum()

    # Walk-forward out-of-sample validation
    if SKLEARN_OK:
        tscv = TimeSeriesSplit(n_splits=5)
        oos_improvements = []
        for train_idx, test_idx in tscv.split(X):
            X_tr, y_tr = X[train_idx], y[train_idx]
            X_te, y_te = X[test_idx],  y[test_idx]

            if len(y_tr) < 30:
                continue

            # Fit on train
            def obj_train(w):
                w = np.maximum(w, 0)
                w = w / (w.sum() + 1e-9)
                scores = X_tr @ w
                thresh = np.percentile(scores, 50)
                mask   = scores >= thresh
                if mask.sum() < 10:
                    return 0.0
                return -y_tr[mask].mean()

            res_tr = minimize(obj_train, current_w_norm, method='L-BFGS-B',
                              bounds=bounds, options={'maxiter': 500})
            w_tr = np.maximum(res_tr.x, 0)
            w_tr = w_tr / w_tr.sum()

            # Evaluate on test (out-of-sample)
            scores_te     = X_te @ w_tr
            scores_base   = X_te @ current_w_norm
            thresh_te     = np.percentile(scores_te, 50)
            thresh_base   = np.percentile(scores_base, 50)
            mask_opt      = scores_te   >= thresh_te
            mask_base     = scores_base >= thresh_base

            if mask_opt.sum() >= 5 and mask_base.sum() >= 5:
                imp = y_te[mask_opt].mean() - y_te[mask_base].mean()
                oos_improvements.append(imp)

        oos_mean = float(np.mean(oos_improvements)) if oos_improvements else 0.0
        oos_std  = float(np.std(oos_improvements))  if oos_improvements else 0.0
    else:
        oos_mean, oos_std = 0.0, 0.0

    # Build recommended weights (back to absolute scale)
    opt_w_abs = {c: float(opt_w[i] * 100) for i, c in enumerate(R_COLS)}

    # Compare: what metrics does top-50% by new weights vs current weights give?
    scores_opt  = X @ opt_w
    scores_curr = X @ current_w_norm
    thresh_opt  = np.percentile(scores_opt, 50)
    thresh_curr = np.percentile(scores_curr, 50)
    mask_opt    = scores_opt  >= thresh_opt
    mask_curr   = scores_curr >= thresh_curr

    m_opt  = compute_metrics(df[mask_opt],  "Optimized weights (top 50%)")
    m_curr = compute_metrics(df[mask_curr], "Current weights (top 50%)")

    return {
        'optimal_weights':       opt_w_abs,
        'current_weights':       R_CURRENT_W,
        'oos_improvement_mean':  oos_mean,
        'oos_improvement_std':   oos_std,
        'metrics_optimized':     m_opt,
        'metrics_current':       m_curr,
        'weight_vector':         opt_w.tolist(),
    }


# ── Phase 6: Redundancy & Harm Detection ─────────────────────────────────────

def redundancy_analysis(df: pd.DataFrame) -> dict:
    """Find correlated, redundant, or harmful indicators."""
    n_cols = [f'n_{c}' for c in R_COLS]
    X = df[n_cols].fillna(0)

    # Inter-indicator correlation (Spearman)
    corr_matrix = pd.DataFrame(index=R_COLS, columns=R_COLS, dtype=float)
    for c1 in R_COLS:
        for c2 in R_COLS:
            corr_matrix.loc[c1, c2] = stats.spearmanr(
                df[c1].fillna(0), df[c2].fillna(0)
            )[0]

    # Identify redundant pairs (|corr| > 0.5)
    redundant = []
    for i, c1 in enumerate(R_COLS):
        for c2 in R_COLS[i+1:]:
            corr = abs(corr_matrix.loc[c1, c2])
            if corr > 0.5:
                redundant.append({'pair': f"{c1}+{c2}", 'corr': corr})

    # Harmful indicators: negative correlation with r20d
    harmful = []
    for col in R_COLS:
        corr, p = stats.spearmanr(df[col].fillna(0), df['r20d'])
        if corr < -0.02:
            harmful.append({
                'col': col, 'label': R_LABELS[col],
                'corr_r20d': corr, 'p_value': p,
                'current_weight': R_CURRENT_W[col]
            })

    # Marginal value: add/remove each indicator, compare expected return
    base = compute_metrics(df)
    marginal = []
    for col in R_COLS:
        # "Without this indicator" = set col to 0 (same as col=0 signals baseline)
        sub_zero = df[df[col] == 0]
        sub_pos  = df[df[col] > 0]
        if len(sub_zero) >= 10 and len(sub_pos) >= 10:
            m_zero = compute_metrics(sub_zero)
            m_pos  = compute_metrics(sub_pos)
            marginal.append({
                'col':       col,
                'label':     R_LABELS[col],
                'n_zero':    len(sub_zero),
                'n_pos':     len(sub_pos),
                'ret_zero':  m_zero['expected_return'],
                'ret_pos':   m_pos['expected_return'],
                'mfe_zero':  m_zero['mfe'],
                'mfe_pos':   m_pos['mfe'],
                'pf_zero':   m_zero['profit_factor'],
                'pf_pos':    m_pos['profit_factor'],
                'delta_ret': m_pos['expected_return'] - m_zero['expected_return'],
                'delta_mfe': m_pos['mfe'] - m_zero['mfe'],
            })

    return {
        'corr_matrix': corr_matrix.to_dict(),
        'redundant':   redundant,
        'harmful':     harmful,
        'marginal':    sorted(marginal, key=lambda x: x['delta_ret'], reverse=True),
    }


# ── Phase 7: Recommendations Engine ──────────────────────────────────────────

def generate_recommendations(df, ind_analysis, score_nl, feat_imp, interactions,
                              opt_weights, redundancy) -> list:
    """Rank all findings by expected impact on performance."""
    base = compute_metrics(df)
    recs = []

    # ── R1: Indicator threshold improvements ──────────────────────────────────
    for ind in ind_analysis:
        col = ind['col']
        thr = ind['best_threshold']
        if thr is None or thr == 0:
            continue

        sub = df[df[col] >= thr]
        m   = compute_metrics(sub, f"{ind['label']} >= {thr}")
        if m['n'] < 10:
            continue
        retention = m['n'] / base['n']
        if retention < RETAIN_MIN:
            continue

        delta_ret = m['expected_return'] - base['expected_return']
        delta_mfe = m['mfe'] - base['mfe']

        # t-test for significance
        t, p = stats.ttest_ind(
            sub['r20d'].dropna(),
            df[df[col] < thr]['r20d'].dropna()
        )
        conf = 1 - p if not np.isnan(p) else 0.5

        recs.append({
            'type':       'Indicator Gate',
            'indicator':  ind['label'],
            'col':        col,
            'change':     f"Minimum threshold: {col} >= {thr} (current: no gate)",
            'current':    'No minimum gate',
            'proposed':   f"Gate: {col} >= {thr}",
            'sample_n':   m['n'],
            'retention':  retention,
            'win_rate':   m['win_rate'],
            'exp_ret':    m['expected_return'],
            'median_ret': m['median_return'],
            'mfe':        m['mfe'],
            'mae':        m['mae'],
            'max_dd':     m['max_dd'],
            'pf':         m['profit_factor'],
            'opportunities': m['n'],
            'confidence': conf,
            'delta_ret':  delta_ret,
            'delta_mfe':  delta_mfe,
        })

    # ── R2: Score threshold ────────────────────────────────────────────────────
    if score_nl.get('score_scan'):
        best_score = max(score_nl['score_scan'], key=lambda x: x['exp_ret'])
        thr = best_score['threshold']
        sub = df[df['raw_score'] >= thr]
        m   = compute_metrics(sub, f"Score >= {thr}")
        if m['n'] >= 10 and m['n'] / base['n'] >= RETAIN_MIN:
            delta_ret = m['expected_return'] - base['expected_return']
            recs.append({
                'type':       'Score Gate',
                'indicator':  'Total Score',
                'col':        'raw_score',
                'change':     f"Minimum score gate: raw_score >= {thr}",
                'current':    'No score gate',
                'proposed':   f"Score >= {thr}",
                'sample_n':   m['n'],
                'retention':  m['n'] / base['n'],
                'win_rate':   m['win_rate'],
                'exp_ret':    m['expected_return'],
                'median_ret': m['median_return'],
                'mfe':        m['mfe'],
                'mae':        m['mae'],
                'max_dd':     m['max_dd'],
                'pf':         m['profit_factor'],
                'opportunities': m['n'],
                'confidence': 0.7,
                'delta_ret':  delta_ret,
                'delta_mfe':  m['mfe'] - base['mfe'],
            })

    # ── R3: Harmful indicator de-weighting ────────────────────────────────────
    for h in redundancy.get('harmful', []):
        col = h['col']
        sub = df[df[col] == 0]
        m   = compute_metrics(sub, f"Exclude {h['label']} signals")
        if m['n'] < 10 or m['n'] / base['n'] < RETAIN_MIN:
            continue
        delta_ret = m['expected_return'] - base['expected_return']
        recs.append({
            'type':       'Weight Reduction',
            'indicator':  h['label'],
            'col':        col,
            'change':     f"Reduce weight to 0 (current: {h['current_weight']})",
            'current':    str(h['current_weight']),
            'proposed':   '0 (remove from scoring)',
            'sample_n':   m['n'],
            'retention':  m['n'] / base['n'],
            'win_rate':   m['win_rate'],
            'exp_ret':    m['expected_return'],
            'median_ret': m['median_return'],
            'mfe':        m['mfe'],
            'mae':        m['mae'],
            'max_dd':     m['max_dd'],
            'pf':         m['profit_factor'],
            'opportunities': m['n'],
            'confidence': 1 - h.get('p_value', 0.5),
            'delta_ret':  delta_ret,
            'delta_mfe':  m['mfe'] - base['mfe'],
        })

    # ── R4: Weight optimization recommendation ────────────────────────────────
    if opt_weights and 'metrics_optimized' in opt_weights:
        m_opt  = opt_weights['metrics_optimized']
        m_curr = opt_weights['metrics_current']
        if m_opt.get('n', 0) >= 10:
            delta_ret = m_opt.get('expected_return', 0) - m_curr.get('expected_return', 0)
            oos_imp   = opt_weights.get('oos_improvement_mean', 0)
            conf = 0.85 if oos_imp > 0 else 0.55
            new_w = opt_weights.get('optimal_weights', {})
            proposed_str = ", ".join(
                f"{R_LABELS.get(c, c)}={v:.1f}"
                for c, v in sorted(new_w.items(), key=lambda x: -x[1])
            )
            recs.append({
                'type':       'Weight Optimization',
                'indicator':  'All r1-r8',
                'col':        'all',
                'change':     'Rebalance r1-r8 weights based on RF importance + optimization',
                'current':    'r1=30, r2=10, r3=20, r4=10, r5=8, r6=4, r7=3, r8=15',
                'proposed':   proposed_str,
                'sample_n':   m_opt.get('n', 0),
                'retention':  m_opt.get('n', 0) / base['n'],
                'win_rate':   m_opt.get('win_rate', 0),
                'exp_ret':    m_opt.get('expected_return', 0),
                'median_ret': m_opt.get('median_return', 0),
                'mfe':        m_opt.get('mfe', 0),
                'mae':        m_opt.get('mae', 0),
                'max_dd':     m_opt.get('max_dd', 0),
                'pf':         m_opt.get('profit_factor', 1),
                'opportunities': m_opt.get('n', 0),
                'confidence': conf,
                'delta_ret':  delta_ret,
                'delta_mfe':  m_opt.get('mfe', 0) - base.get('mfe', 0),
                'oos_improvement': oos_imp,
            })

    # ── R5: Top interactions ───────────────────────────────────────────────────
    for ix in interactions[:3]:
        c1, c2 = ix['c1'], ix['c2']
        sub = df[(df[c1] > 0) & (df[c2] > 0)]
        m   = compute_metrics(sub)
        if m['n'] < 10 or m['n'] / base['n'] < 0.10:
            continue
        delta_ret = ix['ret_both'] - base['expected_return']
        if delta_ret <= 0:
            continue
        recs.append({
            'type':       'Interaction Gate',
            'indicator':  f"{R_LABELS[c1]} + {R_LABELS[c2]}",
            'col':        f"{c1}+{c2}",
            'change':     f"Premium filter: require both {c1}>0 AND {c2}>0",
            'current':    'No interaction gate',
            'proposed':   f"{c1}>0 AND {c2}>0",
            'sample_n':   m['n'],
            'retention':  m['n'] / base['n'],
            'win_rate':   m['win_rate'],
            'exp_ret':    m['expected_return'],
            'median_ret': m['median_return'],
            'mfe':        m['mfe'],
            'mae':        m['mae'],
            'max_dd':     m['max_dd'],
            'pf':         m['profit_factor'],
            'opportunities': m['n'],
            'confidence': 0.70,
            'delta_ret':  delta_ret,
            'delta_mfe':  m['mfe'] - base['mfe'],
        })

    # Sort by delta_ret (impact on expected return)
    recs.sort(key=lambda x: x.get('delta_ret', 0), reverse=True)

    return recs


# ── HTML Report ───────────────────────────────────────────────────────────────

_CSS = """
:root{--bg:#0d1117;--card:#161b22;--border:#30363d;--text:#e6edf3;--sub:#8b949e;
      --green:#3fb950;--red:#f85149;--yellow:#d29922;--blue:#58a6ff;--purple:#bc8cff;
      --orange:#ffa657}
*{box-sizing:border-box;margin:0;padding:0}
body{background:var(--bg);color:var(--text);font-family:'Segoe UI',system-ui,sans-serif;
     font-size:14px;line-height:1.6;padding:20px}
h1{font-size:1.6em;color:var(--blue);margin-bottom:4px}
h2{font-size:1.15em;color:var(--text);border-bottom:1px solid var(--border);
   padding-bottom:6px;margin:28px 0 14px}
h3{font-size:1em;color:var(--blue);margin:18px 0 8px}
.meta{color:var(--sub);font-size:0.82em;margin-bottom:20px}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(180px,1fr));gap:12px;margin:14px 0}
.kpi{background:var(--card);border:1px solid var(--border);border-radius:8px;padding:14px}
.kpi .val{font-size:1.5em;font-weight:700;color:var(--blue)}
.kpi .lbl{color:var(--sub);font-size:0.8em;margin-top:2px}
.good{color:var(--green)!important}.bad{color:var(--red)!important}
.warn{color:var(--yellow)!important}.purple{color:var(--purple)!important}
.orange{color:var(--orange)!important}
table{width:100%;border-collapse:collapse;margin:10px 0;font-size:0.83em}
th{background:var(--card);color:var(--sub);text-align:left;
   padding:7px 10px;border-bottom:1px solid var(--border)}
td{padding:7px 10px;border-bottom:1px solid var(--border);color:var(--text)}
tr:hover td{background:rgba(255,255,255,0.03)}
.badge{display:inline-block;padding:2px 8px;border-radius:12px;font-size:0.75em;font-weight:600}
.badge-green{background:rgba(63,185,80,.15);color:var(--green)}
.badge-red{background:rgba(248,81,73,.15);color:var(--red)}
.badge-yellow{background:rgba(210,153,34,.15);color:var(--yellow)}
.badge-blue{background:rgba(88,166,255,.15);color:var(--blue)}
.section{background:var(--card);border:1px solid var(--border);border-radius:8px;padding:20px;margin:16px 0}
.bar-wrap{background:#21262d;border-radius:4px;height:10px;width:100%;overflow:hidden;display:inline-block;vertical-align:middle;width:80px}
.bar{height:100%;border-radius:4px}
nav{display:flex;gap:10px;flex-wrap:wrap;margin-bottom:20px}
nav a{color:var(--blue);text-decoration:none;padding:4px 10px;border:1px solid var(--border);
      border-radius:20px;font-size:0.82em}
nav a:hover{background:var(--card)}
.warn-box{background:rgba(210,153,34,.1);border:1px solid var(--yellow);
          border-radius:6px;padding:12px 16px;margin:10px 0;color:var(--yellow)}
.info-box{background:rgba(88,166,255,.07);border:1px solid var(--blue);
          border-radius:6px;padding:12px 16px;margin:10px 0;color:var(--blue)}
.good-box{background:rgba(63,185,80,.07);border:1px solid var(--green);
          border-radius:6px;padding:12px 16px;margin:10px 0;color:var(--green)}
.rank-badge{display:inline-block;width:26px;height:26px;line-height:26px;text-align:center;
            border-radius:50%;font-weight:700;font-size:0.8em;margin-right:6px}
.r1{background:var(--yellow);color:#000}
.r2{background:var(--sub);color:#000}
.r3{background:#c04000;color:#fff}
"""

def _pct(v, decimals=1):
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return "—"
    return f"{v*100:+.{decimals}f}%"

def _pct_plain(v, decimals=1):
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return "—"
    return f"{v*100:.{decimals}f}%"

def _fmt(v, decimals=2):
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return "—"
    return f"{v:.{decimals}f}"

def _color_ret(v):
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return "—"
    cls = "good" if v > 0.02 else ("warn" if v > 0 else "bad")
    return f'<span class="{cls}">{_pct(v)}</span>'

def _conf_badge(v):
    if v >= 0.85:
        return '<span class="badge badge-green">High</span>'
    elif v >= 0.70:
        return '<span class="badge badge-yellow">Medium</span>'
    else:
        return '<span class="badge badge-red">Low</span>'

def _ret_badge(v):
    if v >= 0.80:
        return f'<span class="badge badge-green">{_pct_plain(v)}</span>'
    elif v >= 0.60:
        return f'<span class="badge badge-yellow">{_pct_plain(v)}</span>'
    else:
        return f'<span class="badge badge-red">{_pct_plain(v)}</span>'

def _bar(v, max_v=0.4, color="#58a6ff"):
    pct = min(abs(v) / max_v, 1) * 100 if max_v > 0 else 0
    return f'<span class="bar-wrap"><span class="bar" style="width:{pct:.0f}%;background:{color}"></span></span>'

def _metrics_row(m: dict, highlight_base: dict = None) -> str:
    def _cmp(key, fmt_fn, higher_better=True):
        v  = m.get(key)
        bv = highlight_base.get(key) if highlight_base else None
        s  = fmt_fn(v) if callable(fmt_fn) else _pct(v)
        if bv is not None and v is not None and not np.isnan(float(v)):
            delta = (v - bv) * (1 if higher_better else -1)
            cls   = "good" if delta > 0.002 else ("bad" if delta < -0.002 else "")
            s     = f'<span class="{cls}">{s}</span>'
        return s

    pf_v = m.get('profit_factor', 1)
    pf_s = (f'{pf_v:.2f}' if pf_v != float('inf') else '∞')

    return (
        f"<td>{m.get('n', 0)}</td>"
        f"<td>{_pct_plain(m.get('win_rate'))}</td>"
        f"<td>{_color_ret(m.get('expected_return'))}</td>"
        f"<td>{_color_ret(m.get('median_return'))}</td>"
        f"<td>{_pct(m.get('mfe'))}</td>"
        f"<td>{_pct(m.get('mae'))}</td>"
        f"<td>{_pct(m.get('max_dd'))}</td>"
        f"<td>{pf_s}</td>"
        f"<td>{m.get('n', 0)}</td>"
        f"<td>{_fmt(m.get('risk_adj_return', 0), 2)}</td>"
        f"<td>{_pct_plain(m.get('consistency'))}</td>"
    )

def _metrics_header() -> str:
    cols = ["N", "Win Rate", "Avg Return", "Median Ret", "MFE", "MAE",
            "Max DD", "Profit Factor", "Opportunities", "Risk Adj", "Consistency"]
    return "".join(f"<th>{c}</th>" for c in cols)


def build_html(df, base, ind_analysis, score_nl, feat_imp, interactions,
               opt_weights, redundancy, recommendations, run_ts) -> str:

    nav_links = (
        '<a href="#baseline">📊 Baseline</a>'
        '<a href="#indicators">📈 Indicators</a>'
        '<a href="#interactions">🔗 Interactions</a>'
        '<a href="#importance">🌲 Importance</a>'
        '<a href="#optimization">⚖️ Weights</a>'
        '<a href="#redundancy">🔍 Redundancy</a>'
        '<a href="#recommendations">🎯 Recommendations</a>'
    )

    # ── Baseline section ──────────────────────────────────────────────────────
    def kpi(val, lbl, cls=""):
        return f'<div class="kpi"><div class="val {cls}">{val}</div><div class="lbl">{lbl}</div></div>'

    win_r = base.get('win_rate', 0)
    exp_r = base.get('expected_return', 0)
    mfe_v = base.get('mfe', 0)
    mae_v = base.get('mae', 0)
    pf_v  = base.get('profit_factor', 1)
    rs_v  = base.get('risk_adj_return', 0)

    baseline_html = f"""
<div id="baseline" class="section">
<h2>📊 Phase 0 — Baseline (All {base['n']} Signals, {df['signal_date'].min().year}–{df['signal_date'].max().year})</h2>
<div class="info-box">
<strong>Optimization objective:</strong> Expected Return → Profit Factor → MFE → Consistency<br>
NOT win rate alone. A 40% win rate with +35% avg winner beats 70% win rate with +8% avg winner.
</div>
<div class="grid">
{kpi(base['n'], 'Total Signals')}
{kpi(_pct_plain(win_r), 'Win Rate', 'warn' if win_r < 0.5 else 'good')}
{kpi(_pct(exp_r), 'Avg Return (r20d)', 'good' if exp_r > 0 else 'bad')}
{kpi(_pct(mfe_v), 'Avg MFE', 'good' if mfe_v > 0.05 else '')}
{kpi(_pct(mae_v), 'Avg MAE', 'bad')}
{kpi(f'{pf_v:.2f}', 'Profit Factor', 'good' if pf_v > 1.5 else 'warn')}
{kpi(_fmt(rs_v), 'Risk Adj Return', 'good' if rs_v > 0.5 else '')}
{kpi(_pct_plain(base.get('consistency', 0)), 'Consistency', '')}
</div>
<table>
<tr>{_metrics_header()}</tr>
<tr>{_metrics_row(base)}</tr>
</table>
</div>"""

    # ── Individual indicators section ─────────────────────────────────────────
    ind_rows = ""
    for ind in ind_analysis:
        thr  = ind.get('best_threshold')
        gain = ind['best_exp_ret'] - base['expected_return']
        gain_str = (f'<span class="good">+{gain*100:.1f}%</span>'
                    if gain > 0.005 else
                    f'<span class="warn">{gain*100:+.1f}%</span>')
        corr_r20 = ind['corr_r20d']
        corr_cls = "good" if corr_r20 > 0.05 else ("bad" if corr_r20 < -0.02 else "warn")
        thr_str  = str(thr) if thr else "—"
        ret_str  = _ret_badge(ind['best_n'] / base['n']) if thr else "—"
        ind_rows += (
            f"<tr>"
            f"<td><strong>{ind['label']}</strong></td>"
            f"<td>{ind['current_weight']}</td>"
            f"<td>{ind['max_val']}</td>"
            f"<td>{_pct_plain(ind['zero_pct'])}</td>"
            f"<td>{_fmt(ind['mean_val'], 1)}</td>"
            f"<td><span class='{corr_cls}'>{corr_r20:+.3f}</span></td>"
            f"<td>{ind['corr_mfe']:+.3f}</td>"
            f"<td>{thr_str}</td>"
            f"<td>{gain_str}</td>"
            f"<td>{ret_str}</td>"
            f"</tr>"
        )

    # Per-indicator value tables
    ind_detail = ""
    for ind in ind_analysis:
        col = ind['col']
        if not ind.get('by_value'):
            continue
        rows = ""
        for bv in ind['by_value']:
            v = bv['value']
            is_base = (v == 0)
            cls = " style='opacity:0.6'" if is_base else ""
            rows += (
                f"<tr{cls}>"
                f"<td><strong>{v}</strong></td>"
                f"<td>{bv['n']}</td>"
                f"<td>{_color_ret(bv.get('expected_return'))}</td>"
                f"<td>{_color_ret(bv.get('median_return'))}</td>"
                f"<td>{_pct(bv.get('mfe'))}</td>"
                f"<td>{_pct(bv.get('mae'))}</td>"
                f"<td>{_fmt(bv.get('profit_factor'), 2)}</td>"
                f"</tr>"
            )
        ind_detail += f"""
<h3>{ind['label']} (r={ind['current_weight']}/max={ind['max_val']}, corr_r20d={ind['corr_r20d']:+.3f})</h3>
<table>
<tr><th>Value</th><th>N</th><th>Avg Ret</th><th>Median</th><th>MFE</th><th>MAE</th><th>PF</th></tr>
{rows}
</table>"""

    indicators_html = f"""
<div id="indicators" class="section">
<h2>📈 Phase 1 — Individual Indicator Analysis</h2>
<div class="warn-box">
⚠️ Indicators with negative correlation to r20d are contributing noise or inverse signals.
Re-weighting or gating them may improve expected return without killing opportunity flow.
</div>
<table>
<tr><th>Indicator</th><th>Current W</th><th>Max</th><th>% Zero</th><th>Mean Val</th>
<th>Corr r20d ↑</th><th>Corr MFE ↑</th><th>Best Gate</th><th>ΔExp Ret</th><th>Retention</th></tr>
{ind_rows}
</table>
{ind_detail}
</div>"""

    # ── Score non-linearity section ────────────────────────────────────────────
    q_rows = ""
    for q in score_nl.get('by_quintile', []):
        sr = q.get('score_range', (0, 0))
        q_rows += (
            f"<tr><td>{q['label']}</td>"
            f"<td>{sr[0]:.0f}–{sr[1]:.0f}</td>"
            f"<td>{q['n']}</td>"
            f"<td>{_color_ret(q.get('expected_return'))}</td>"
            f"<td>{_color_ret(q.get('median_return'))}</td>"
            f"<td>{_pct(q.get('mfe'))}</td>"
            f"<td>{_fmt(q.get('profit_factor'), 2)}</td></tr>"
        )
    score_html = f"""
<div class="section">
<h3>Score Non-Linearity (Is Higher Score Always Better?)</h3>
<table>
<tr><th>Quintile</th><th>Score Range</th><th>N</th>
<th>Avg Return</th><th>Median</th><th>MFE</th><th>PF</th></tr>
{q_rows}
</table>
</div>"""

    # ── Interactions section ───────────────────────────────────────────────────
    ix_rows = ""
    for ix in interactions[:15]:
        syn_cls = "good" if ix['synergy'] > 0.005 else ("bad" if ix['synergy'] < -0.005 else "warn")
        ix_rows += (
            f"<tr>"
            f"<td>{ix['c1_label']}</td><td>{ix['c2_label']}</td>"
            f"<td>{ix['n_both']}</td>"
            f"<td>{_color_ret(ix['ret_both'])}</td>"
            f"<td>{_color_ret(ix['ret_c1only'])}</td>"
            f"<td>{_color_ret(ix['ret_c2only'])}</td>"
            f"<td>{_color_ret(ix['ret_neither'])}</td>"
            f"<td><span class='{syn_cls}'>{ix['synergy']*100:+.1f}%</span></td>"
            f"<td>{_ret_badge(ix['retention'])}</td>"
            f"</tr>"
        )

    interactions_html = f"""
<div id="interactions" class="section">
<h2>🔗 Phase 2 — Pairwise Interaction Analysis</h2>
<table>
<tr><th>Factor 1</th><th>Factor 2</th><th>N Both</th>
<th>Both Present</th><th>Only F1</th><th>Only F2</th><th>Neither</th>
<th>Synergy</th><th>Retention</th></tr>
{ix_rows}
</table>
</div>"""

    # ── Feature importance section ─────────────────────────────────────────────
    if SKLEARN_OK and feat_imp and 'r20d' in feat_imp:
        fi_data  = feat_imp['r20d']
        fi_rows  = ""
        for row in fi_data['importances']:
            pct_imp = row['full_imp'] * 100
            curr_w  = row['current_weight']
            bar_html = _bar(row['full_imp'], max_v=0.4, color="#58a6ff")
            fi_rows += (
                f"<tr>"
                f"<td><strong>{row['feature']}</strong></td>"
                f"<td>{curr_w}</td>"
                f"<td>{pct_imp:.1f}%  {bar_html}</td>"
                f"<td>{row['oos_imp']*100:.1f}%</td>"
                f"</tr>"
            )
        fi_note = (
            f"Walk-forward OOS R² = {fi_data['oos_r2']:.3f} "
            f"± {fi_data['oos_r2_std']:.3f}"
        )
        importance_html = f"""
<div id="importance" class="section">
<h2>🌲 Phase 3 — Random Forest Feature Importance</h2>
<p class="meta">{fi_note} — predicting r20d (20-day forward return)</p>
<table>
<tr><th>Feature</th><th>Current Weight</th><th>Full-Dataset Importance</th><th>OOS Importance</th></tr>
{fi_rows}
</table>
</div>"""
    else:
        importance_html = ""

    # ── Weight optimization section ────────────────────────────────────────────
    if opt_weights and 'optimal_weights' in opt_weights:
        new_w = opt_weights['optimal_weights']
        total_new = sum(new_w.values())
        w_rows = ""
        for col in R_COLS:
            cur = R_CURRENT_W[col]
            new = new_w.get(col, cur)
            new_scaled = new / total_new * 100
            delta = new_scaled - cur
            delta_cls = "good" if delta > 2 else ("bad" if delta < -2 else "warn")
            w_rows += (
                f"<tr><td>{R_LABELS[col]}</td>"
                f"<td>{cur}</td>"
                f"<td>{new_scaled:.1f} <span class='{delta_cls}'>({delta:+.1f})</span></td>"
                f"</tr>"
            )

        m_opt  = opt_weights.get('metrics_optimized', {})
        m_curr = opt_weights.get('metrics_current', {})
        oos_imp = opt_weights.get('oos_improvement_mean', 0)
        oos_std = opt_weights.get('oos_improvement_std', 0)
        oos_cls = "good" if oos_imp > 0.002 else ("warn" if oos_imp > 0 else "bad")

        optimization_html = f"""
<div id="optimization" class="section">
<h2>⚖️ Phase 4 — Weight Optimization</h2>
<div class="info-box">
OOS improvement (walk-forward): <span class="{oos_cls}">{oos_imp*100:+.2f}% ± {oos_std*100:.2f}%</span><br>
Positive OOS improvement = recommendation has out-of-sample validity.
</div>
<table>
<tr><th>Indicator</th><th>Current Weight</th><th>Recommended Weight</th></tr>
{w_rows}
</table>
<h3>Performance Comparison (Top 50% by each scoring method)</h3>
<table>
<tr><th>Method</th>{_metrics_header()}</tr>
<tr><td>Current weights</td>{_metrics_row(m_curr)}</tr>
<tr><td>Optimized weights</td>{_metrics_row(m_opt, m_curr)}</tr>
</table>
</div>"""
    else:
        optimization_html = ""

    # ── Redundancy section ─────────────────────────────────────────────────────
    marg = redundancy.get('marginal', [])
    marg_rows = ""
    for m_item in marg:
        delta_cls = "good" if m_item['delta_ret'] > 0.005 else ("bad" if m_item['delta_ret'] < -0.005 else "warn")
        marg_rows += (
            f"<tr>"
            f"<td>{m_item['label']}</td>"
            f"<td>{m_item['n_pos']} vs {m_item['n_zero']}</td>"
            f"<td>{_color_ret(m_item['ret_pos'])}</td>"
            f"<td>{_color_ret(m_item['ret_zero'])}</td>"
            f"<td><span class='{delta_cls}'>{m_item['delta_ret']*100:+.1f}%</span></td>"
            f"<td>{m_item['delta_mfe']*100:+.1f}%</td>"
            f"<td>{m_item['pf_pos']:.2f} vs {m_item['pf_zero']:.2f}</td>"
            f"</tr>"
        )

    harmful = redundancy.get('harmful', [])
    harm_boxes = ""
    for h in harmful:
        harm_boxes += f"""
<div class="warn-box">
⚠️ <strong>{h['label']}</strong>: Spearman corr with r20d = {h['corr_r20d']:+.3f}
(p={h['p_value']:.3f}) — signals WITH this component show LOWER expected returns.
Current weight = {h['current_weight']}. Consider reducing or making it context-dependent.
</div>"""

    redundancy_html = f"""
<div id="redundancy" class="section">
<h2>🔍 Phase 5 — Redundancy & Harm Detection</h2>
{harm_boxes}
<h3>Marginal Value: Does Having r>0 Actually Help? (sorted by impact)</h3>
<table>
<tr><th>Indicator</th><th>N (pos vs zero)</th><th>Ret when Present</th>
<th>Ret when Absent</th><th>ΔRet</th><th>ΔMFE</th><th>PF (present vs absent)</th></tr>
{marg_rows}
</table>
</div>"""

    # ── Recommendations section ────────────────────────────────────────────────
    rec_rows = ""
    for i, rec in enumerate(recommendations[:15]):
        rank = i + 1
        badge_cls = "r1" if rank == 1 else ("r2" if rank == 2 else "r3")
        badge = f'<span class="rank-badge {badge_cls}">{rank}</span>' if rank <= 3 else f'<span style="color:var(--sub)">{rank}.</span> '

        delta_ret = rec.get('delta_ret', 0)
        impact_bar = _bar(abs(delta_ret), max_v=0.05, color="#3fb950" if delta_ret > 0 else "#f85149")

        rec_rows += f"""
<tr>
<td>{badge}{rec['type']}</td>
<td>{rec['indicator']}</td>
<td style="font-size:0.8em;color:var(--sub)">{rec['current']}</td>
<td style="font-size:0.8em;color:var(--blue)">{rec['proposed']}</td>
<td>{rec.get('sample_n', 0)}</td>
<td>{_ret_badge(rec.get('retention', 1))}</td>
<td>{_pct_plain(rec.get('win_rate'))}</td>
<td>{_color_ret(rec.get('exp_ret'))}</td>
<td>{_color_ret(rec.get('median_ret'))}</td>
<td>{_pct(rec.get('mfe'))}</td>
<td>{_pct(rec.get('mae'))}</td>
<td>{_pct(rec.get('max_dd'))}</td>
<td>{_fmt(rec.get('pf'), 2)}</td>
<td>{rec.get('opportunities', 0)}</td>
<td>{_conf_badge(rec.get('confidence', 0.5))}</td>
<td>{_color_ret(delta_ret)} {impact_bar}</td>
</tr>"""

    recommendations_html = f"""
<div id="recommendations" class="section">
<h2>🎯 Phase 6 — Recommendations (Ranked by Expected Return Impact)</h2>
<div class="good-box">
All recommendations preserve ≥{RETAIN_MIN*100:.0f}% signal retention.
Ranked by delta expected return (higher = more impactful).
Discount Zone entry (r1 ≥ 1) is mandatory and preserved in all recommendations.
</div>
<table style="font-size:0.79em">
<tr>
<th>Rank / Type</th><th>Indicator</th><th>Current</th><th>Proposed</th>
<th>N</th><th>Retention</th><th>Win %</th><th>Avg Ret</th><th>Median</th>
<th>MFE</th><th>MAE</th><th>Max DD</th><th>PF</th><th>Opp.</th>
<th>Confidence</th><th>ΔExp Ret</th>
</tr>
{rec_rows}
</table>
</div>"""

    # ── Final assembly ─────────────────────────────────────────────────────────
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>EGX Weight Optimizer — {run_ts}</title>
<style>{_CSS}</style>
</head>
<body>
<h1>⚖️ EGX SMC — Quantitative Weight Optimization Engine</h1>
<p class="meta">Generated: {run_ts} · Dataset: {base['n']} signals · {df['signal_date'].min().year}–{df['signal_date'].max().year}</p>
<div class="warn-box">
<strong>HARDCODED CONSTRAINT:</strong> ENTRY MUST BE IN DISCOUNT ZONE (price &lt; EQ). This cannot be changed.<br>
Everything else — weights, thresholds, scoring logic — is subject to data-driven optimization.
</div>
<nav>{nav_links}</nav>
{baseline_html}
{indicators_html}
{score_html}
{interactions_html}
{importance_html}
{optimization_html}
{redundancy_html}
{recommendations_html}
</body>
</html>"""


# ── Main ───────────────────────────────────────────────────────────────────────

def main(db_path: str = DB_PATH):
    run_ts = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
    print(f"[weight_optimizer] Starting at {run_ts}")

    print("[1/8] Loading data from DB...")
    df = load_data(db_path)
    print(f"      {len(df)} signals loaded")

    print("[2/8] Computing baseline metrics...")
    base = baseline_metrics(df)
    print(f"      n={base['n']}  exp_ret={base['expected_return']:.3f}  "
          f"mfe={base['mfe']:.3f}  pf={base['profit_factor']:.2f}")

    print("[3/8] Analyzing individual indicators...")
    ind_analysis = analyze_indicators(df)

    print("[4/8] Score non-linearity analysis...")
    score_nl = analyze_score_nonlinearity(df)

    print("[5/8] Feature importance (Random Forest)...")
    feat_imp = feature_importance_analysis(df)
    if 'r20d' in feat_imp:
        oos = feat_imp['r20d']['oos_r2']
        print(f"      OOS R² = {oos:.4f}")

    print("[6/8] Interaction analysis...")
    interactions = interaction_analysis(df)

    print("[7/8] Weight optimization...")
    opt_weights = optimize_weights(df)
    if opt_weights and 'oos_improvement_mean' in opt_weights:
        print(f"      OOS improvement = {opt_weights['oos_improvement_mean']*100:+.2f}%")

    print("[8/8] Redundancy analysis + recommendations...")
    redundancy = redundancy_analysis(df)
    recommendations = generate_recommendations(
        df, ind_analysis, score_nl, feat_imp, interactions, opt_weights, redundancy
    )

    # Save results JSON
    results = {
        'generated_at':      run_ts,
        'n_signals':         base['n'],
        'baseline':          {k: (float(v) if isinstance(v, (np.floating, np.integer)) else v)
                              for k, v in base.items()},
        'optimal_weights':   opt_weights.get('optimal_weights', {}),
        'current_weights':   R_CURRENT_W,
        'oos_improvement':   opt_weights.get('oos_improvement_mean', 0),
        'top_recommendations': [
            {k: (float(v) if isinstance(v, (np.floating, np.integer)) else v)
             for k, v in rec.items()}
            for rec in recommendations[:10]
        ],
        'harmful_indicators': redundancy.get('harmful', []),
    }
    with open(RESULTS_FILE, 'w', encoding='utf-8') as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    print(f"Results saved → {RESULTS_FILE}")

    # Build and save HTML report
    html = build_html(df, base, ind_analysis, score_nl, feat_imp, interactions,
                      opt_weights, redundancy, recommendations, run_ts)
    os.makedirs("reports", exist_ok=True)
    with open(REPORT_FILE, 'w', encoding='utf-8') as f:
        f.write(html)
    print(f"Report saved → {REPORT_FILE}")
    print(f"\n[weight_optimizer] Done — {len(recommendations)} recommendations generated")


if __name__ == "__main__":
    db = DB_PATH
    for a in sys.argv[1:]:
        if a.startswith("--db="):
            db = a[5:]
    main(db_path=db)
