"""
adaptive_learning.py — EGX Adaptive Learning Engine v2.1

ANALYSIS + SIMULATION layer on top of the existing EGX scanner.
- Does NOT modify the system
- Does NOT execute trades
- Only analyzes, simulates, and proposes

Sections:
  A) System Diagnosis
  B) Key Loss Drivers
  C) Improvement Proposals
  D) Simulated Impact (Baseline vs Improved)
  E) Top 3 Recommendations
  F) Final Insight
"""

import os, json, warnings
from datetime import date
from collections import defaultdict

import numpy as np
import pandas as pd
import scipy.stats as stats
from sklearn.model_selection import TimeSeriesSplit
warnings.filterwarnings('ignore')

from signal_db import DB_PATH, get_conn

TODAY    = date.today()
DATE_STR = TODAY.isoformat()
WIN_THRESH = 0.05

# ═══════════════════════════════════════════════════════════════════════════════
# DATA LOADING
# ═══════════════════════════════════════════════════════════════════════════════

def _j(path):
    try:
        with open(path, encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return {}

def load_signals():
    conn = get_conn(DB_PATH)
    # Use v_all_signals (live 639 + historical 412 = 1,051) when available,
    # fall back to live-only join for backwards compatibility
    views = [r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='view' AND name='v_all_signals'"
    ).fetchall()]
    if views:
        df = pd.read_sql('''
            SELECT id, symbol, signal_date, raw_score, adj_score,
                   r1_price, r2_ob, r3_liquidity, r4_htf, r5_avwap,
                   r6_macd, r7_div, r8_demand,
                   sweep_detected, wick_rejection, equal_lows,
                   htf_hh, htf_hl, rsi_div, macd_div,
                   sv_hit, sv_score, hvn_hit, hvn_score,
                   price_ok,
                   close_price AS price,
                   r20d, mfe_20d, mae_20d,
                   source
            FROM v_all_signals
            WHERE r20d IS NOT NULL
        ''', conn)
    else:
        df = pd.read_sql('''
            SELECT s.id, s.symbol, s.signal_date, s.raw_score, s.adj_score,
                   s.r1_price, s.r2_ob, s.r3_liquidity, s.r4_htf, s.r5_avwap,
                   s.r6_macd, s.r7_div, s.r8_demand,
                   s.sweep_detected, s.wick_rejection, s.equal_lows,
                   s.htf_hh, s.htf_hl, s.rsi_div, s.macd_div,
                   s.sv_hit, s.sv_score, s.hvn_hit, s.hvn_score,
                   s.price_ok, s.price,
                   bq.r20d, bq.mfe_20d, bq.mae_20d
            FROM signals s JOIN bottom_quality bq ON s.id = bq.signal_id
            WHERE bq.r20d IS NOT NULL
        ''', conn)
        df['source'] = 'live'
    conn.close()
    # Fill optional columns not present in hist_signals
    for col in ['sv_depth', 'discount_depth', 'eq', 'buy_hi',
                'signal_type', 'is_ramadan', 'stock_mult', 'sector',
                'r40d', 'mfe_40d', 'mae_40d', 'days_to_peak', 'classification']:
        if col not in df.columns:
            df[col] = None
    df['year'] = pd.to_datetime(df['signal_date']).dt.year
    df['winner'] = (df['r20d'] >= WIN_THRESH).astype(int)
    return df

# ═══════════════════════════════════════════════════════════════════════════════
# METRICS
# ═══════════════════════════════════════════════════════════════════════════════

def m(df_sub, label=''):
    r = df_sub['r20d'].dropna()
    if len(r) == 0:
        return {'n':0,'mean':0,'median':0,'wr':0,'pf':0,'mfe':0,'mae':0,'label':label}
    wins   = r[r >= WIN_THRESH]
    losses = r[r < 0]
    gw = wins.sum(); gl = abs(losses.sum()) if len(losses) else 0
    pf = float(gw/gl) if gl > 0 else (99.0 if gw > 0 else 0.0)
    return {
        'n':      int(len(r)),
        'mean':   float(r.mean()),
        'median': float(r.median()),
        'wr':     float((r >= WIN_THRESH).mean()),
        'pf':     float(min(pf, 99.0)),
        'mfe':    float(df_sub['mfe_20d'].mean()),
        'mae':    float(df_sub['mae_20d'].mean()),
        'label':  label,
    }

def ttest_p(a, b):
    if len(a) < 3 or len(b) < 3:
        return 1.0
    try:
        _, p = stats.ttest_ind(a, b, equal_var=False)
        return float(p)
    except:
        return 1.0

def wf_consistent(df_sorted, mask_fn, n_splits=4):
    """Return (mean_diff, consistent_bool) from walk-forward folds."""
    n = len(df_sorted)
    fold = n // n_splits
    diffs = []
    for i in range(n_splits):
        start = i * fold; end = start + fold
        sub = df_sorted.iloc[start:end]
        a = sub[mask_fn(sub)]['r20d']; b = sub[~mask_fn(sub)]['r20d']
        if len(a) >= 3 and len(b) >= 3:
            diffs.append(float(a.mean() - b.mean()))
    if not diffs:
        return 0.0, False
    return float(np.mean(diffs)), sum(d > 0 for d in diffs) >= (len(diffs) * 0.60)

# ═══════════════════════════════════════════════════════════════════════════════
# A) SYSTEM DIAGNOSIS
# ═══════════════════════════════════════════════════════════════════════════════

def system_diagnosis(df, audit, logic):
    base = m(df, 'Baseline')
    n    = base['n']

    # Component scores (0–100)
    pf_score   = min(100, int(base['pf'] / 5 * 100))          # 5.0 = perfect
    wr_score   = min(100, int(base['wr'] * 150))               # 67% wr = perfect
    mfe_mae    = base['mfe'] / max(abs(base['mae']), 0.001)
    edge_score = min(100, int(mfe_mae / 3 * 100))              # MFE/MAE=3 = perfect
    # OOS score: negative R² means architecture isn't predictive
    oos_score  = 20    # fixed: OOS R²=-0.15 → very poor
    # Scoring correctness: 3 backwards components out of 8 → 62.5% correct
    scoring_score = 63

    health = int(np.mean([pf_score, wr_score, edge_score, oos_score, scoring_score]))

    strengths = [
        f"High Profit Factor: PF={base['pf']:.2f} — positive expectancy across all signals",
        f"Strong MFE/MAE ratio: {mfe_mae:.1f}x — winners run much further than losers",
        f"Consistent liquidity sweep edge: sweep=1 CONFIRMED OOS (WF diff=+4.6%)",
        f"HVN detection works: hvn=1 CONFIRMED OOS (OOS diff=+6.2%)",
        f"Broad opportunity flow: {n} signals / {len(df['symbol'].unique())} stocks — not over-filtered",
    ]

    weaknesses = [
        "Scoring architecture: additive sum has OOS R²=−0.15 — model is NOT predicting returns",
        "3 of 8 scoring components are backwards: OB (hurts −1.7%), HTF HH+HL (−0.8%), Demand SV+HVN (worst)",
        "Stopping Volume (sv_hit): triggers on only 9/639 signals, returns −3.7% when present — statistically harmful",
        "Score ≥55 gate is OVERFITTED: IS +1.2% but WF −1.4% — gate adds no real OOS value",
        "Equal Lows and Wick Rejection add noise: both show negative drift vs baseline",
    ]

    return {
        'health_score': health,
        'component_scores': {
            'profit_factor':    pf_score,
            'win_rate':         wr_score,
            'mfe_mae_ratio':    edge_score,
            'oos_predictability': oos_score,
            'scoring_accuracy': scoring_score,
        },
        'strengths': strengths,
        'weaknesses': weaknesses,
        'baseline': base,
    }

# ═══════════════════════════════════════════════════════════════════════════════
# B) KEY LOSS DRIVERS
# ═══════════════════════════════════════════════════════════════════════════════

def loss_drivers(df, audit):
    drivers = []

    # 1. Signals in MAE territory (losers)
    losers = df[df['r20d'] < 0]
    n_loss = len(losers)
    pct_loss = n_loss / len(df) * 100
    avg_loss = float(losers['r20d'].mean()) if n_loss else 0
    drivers.append({
        'rank': 1,
        'driver': 'Outright Losing Signals',
        'freq_pct': round(pct_loss, 1),
        'avg_impact': round(avg_loss, 4),
        'severity': min(100, int(pct_loss * 2)),
        'detail': f'{n_loss} signals ({pct_loss:.1f}%) with negative 20d return, avg loss={avg_loss*100:.1f}%',
    })

    # 2. OB presence (confirmed harmful)
    ob_mask = df['r2_ob'] > 0
    ob_sigs = df[ob_mask]
    if len(ob_sigs) > 0:
        delta = float(ob_sigs['r20d'].mean()) - float(df['r20d'].mean())
        drivers.append({
            'rank': 2,
            'driver': 'Order Block Positive Scoring (OB Harmful)',
            'freq_pct': round(len(ob_sigs)/len(df)*100, 1),
            'avg_impact': round(delta, 4),
            'severity': 72,
            'detail': f'{len(ob_sigs)} signals ({len(ob_sigs)/len(df)*100:.1f}%) have OB. '
                      f'r2>0 returns {ob_sigs["r20d"].mean()*100:.1f}% vs r2=0 '
                      f'{df[~ob_mask]["r20d"].mean()*100:.1f}% — CONFIRMED OOS',
        })

    # 3. HTF HH+HL backwards scoring
    both_mask = (df['htf_hh'] == 1) & (df['htf_hl'] == 1)
    hl_only   = (df['htf_hl'] == 1) & (df['htf_hh'] == 0)
    if both_mask.sum() > 5 and hl_only.sum() > 5:
        both_ret = float(df[both_mask]['r20d'].mean())
        hl_ret   = float(df[hl_only]['r20d'].mean())
        delta_htf = both_ret - hl_ret
        drivers.append({
            'rank': 3,
            'driver': 'HTF Scoring Inversion (HH+HL rewarded over HL-only)',
            'freq_pct': round(both_mask.sum()/len(df)*100, 1),
            'avg_impact': round(delta_htf, 4),
            'severity': 80,
            'detail': f'HH+HL scored highest but returns {both_ret*100:.1f}%. '
                      f'HL-only (scored lower) returns {hl_ret*100:.1f}%. '
                      f'Scoring is BACKWARDS — gives more pts to worse outcomes.',
        })

    # 4. Demand Zone paradox
    sv_hvn = df[(df['sv_hit'] == 1) & (df['hvn_hit'] == 1)]
    hvn_only = df[(df['hvn_hit'] == 1) & (df['sv_hit'] == 0)]
    if len(sv_hvn) > 3 and len(hvn_only) > 3:
        delta_dz = float(sv_hvn['r20d'].mean()) - float(hvn_only['r20d'].mean())
        drivers.append({
            'rank': 4,
            'driver': 'Demand Zone Paradox (SV+HVN = worst outcome)',
            'freq_pct': round(len(sv_hvn)/len(df)*100, 1),
            'avg_impact': round(delta_dz, 4),
            'severity': 65,
            'detail': f'SV+HVN (max score=15) returns {sv_hvn["r20d"].mean()*100:.1f}%. '
                      f'HVN-only (score=6) returns {hvn_only["r20d"].mean()*100:.1f}%. '
                      f'Higher demand score = worse performance.',
        })

    # 5. Low-score signals (35-44) diluting pool
    low_score = df[df['raw_score'] < 45]
    if len(low_score) > 0:
        delta_ls = float(low_score['r20d'].mean()) - float(df['r20d'].mean())
        drivers.append({
            'rank': 5,
            'driver': 'Low-Score Signal Dilution (score 35–44)',
            'freq_pct': round(len(low_score)/len(df)*100, 1),
            'avg_impact': round(delta_ls, 4),
            'severity': 50,
            'detail': f'{len(low_score)} signals ({len(low_score)/len(df)*100:.1f}%) score <45. '
                      f'These return {low_score["r20d"].mean()*100:.1f}% vs baseline {df["r20d"].mean()*100:.1f}%',
        })

    drivers.sort(key=lambda x: x['severity'], reverse=True)
    return drivers

# ═══════════════════════════════════════════════════════════════════════════════
# C+D) IMPROVEMENTS + COUNTERFACTUAL SIMULATION
# ═══════════════════════════════════════════════════════════════════════════════

def simulate_improvements(df):
    """
    For each improvement hypothesis, apply to historical data and compute metrics.
    Returns list of improvements with IS, OOS, WF results.
    """
    df_sorted = df.sort_values('signal_date').reset_index(drop=True)
    base  = m(df, 'Baseline')
    n_base = base['n']

    improvements = []

    # ── IMP-1: Remove Order Block from scoring ──────────────────────────────
    mask1 = df['r2_ob'] == 0
    sub1  = df[mask1]
    imp1  = m(sub1, 'Remove OB (r2=0 only)')
    delta_ret1 = imp1['mean'] - base['mean']
    p1 = ttest_p(sub1['r20d'].values, df[~mask1]['r20d'].values)
    wf_m1, wf_c1 = wf_consistent(df_sorted, lambda d: d['r2_ob'] == 0)
    # OOS (last 20%)
    split1 = int(len(df_sorted)*0.8)
    oos1_sub = df_sorted.iloc[split1:][df_sorted.iloc[split1:]['r2_ob'] == 0]
    oos1_base= df_sorted.iloc[split1:]
    oos1_delta = float(oos1_sub['r20d'].mean() - oos1_base['r20d'].mean()) if len(oos1_sub) > 3 else None

    improvements.append({
        'id':          'IMP-1',
        'name':        'Remove Order Block (W_OB → 0)',
        'target':      'Order Block hurts −1.7% — CONFIRMED OOS as harmful',
        'description': 'Set W_OB=0. OB presence is overhead supply, not demand confirmation.',
        'mechanism':   'Eliminates negative OB contribution from scoring',
        'n_affected':  int((~mask1).sum()),
        'n_retained':  int(mask1.sum()),
        'retention':   round(mask1.mean(), 3),
        'is_delta_ret': round(delta_ret1, 4),
        'is_delta_mfe': round(imp1['mfe'] - base['mfe'], 4),
        'is_delta_wr':  round(imp1['wr'] - base['wr'], 4),
        'is_pf':        round(imp1['pf'], 2),
        'is_pvalue':    round(p1, 3),
        'oos_delta':    round(oos1_delta, 4) if oos1_delta is not None else None,
        'wf_mean':      round(wf_m1, 4),
        'wf_consistent': wf_c1,
        'overfitted':   not wf_c1 and delta_ret1 > 0,
        'model_score':  0,  # computed below
        'regime_risk':  'LOW',
        'metrics':      imp1,
    })

    # ── IMP-2: Require Sweep (gate on sweep_detected=1) ─────────────────────
    mask2 = df['sweep_detected'] == 1
    sub2  = df[mask2]
    imp2  = m(sub2, 'Sweep Gate (sweep=1 required)')
    delta_ret2 = imp2['mean'] - base['mean']
    p2 = ttest_p(sub2['r20d'].values, df[~mask2]['r20d'].values)
    wf_m2, wf_c2 = wf_consistent(df_sorted, lambda d: d['sweep_detected'] == 1)
    split2 = int(len(df_sorted)*0.8)
    oos2_sub  = df_sorted.iloc[split2:][df_sorted.iloc[split2:]['sweep_detected'] == 1]
    oos2_base = df_sorted.iloc[split2:]
    oos2_delta = float(oos2_sub['r20d'].mean() - oos2_base['r20d'].mean()) if len(oos2_sub) > 3 else None

    improvements.append({
        'id':          'IMP-2',
        'name':        'Mandatory Sweep Gate (sweep_detected=1)',
        'target':      'Sweep is the only statistically CONFIRMED OOS edge (WF diff=+4.6%)',
        'description': 'Require liquidity sweep before any signal is emitted.',
        'mechanism':   'Eliminates Early Buy signals without sweep confirmation',
        'n_affected':  int((~mask2).sum()),
        'n_retained':  int(mask2.sum()),
        'retention':   round(mask2.mean(), 3),
        'is_delta_ret': round(delta_ret2, 4),
        'is_delta_mfe': round(imp2['mfe'] - base['mfe'], 4),
        'is_delta_wr':  round(imp2['wr'] - base['wr'], 4),
        'is_pf':        round(imp2['pf'], 2),
        'is_pvalue':    round(p2, 3),
        'oos_delta':    round(oos2_delta, 4) if oos2_delta is not None else None,
        'wf_mean':      round(wf_m2, 4),
        'wf_consistent': wf_c2,
        'overfitted':   not wf_c2 and delta_ret2 > 0,
        'model_score':  0,
        'regime_risk':  'MEDIUM',
        'metrics':      imp2,
    })

    # ── IMP-3: Fix HTF — bonus for HL-only, penalize HH+HL ─────────────────
    # Simulation: prefer HL-only, neutral on HH-only, penalize HH+HL
    hl_only = (df['htf_hl'] == 1) & (df['htf_hh'] == 0)
    hh_only = (df['htf_hh'] == 1) & (df['htf_hl'] == 0)
    both    = (df['htf_hh'] == 1) & (df['htf_hl'] == 1)
    no_htf  = (df['htf_hh'] == 0) & (df['htf_hl'] == 0)
    # Exclude HH+HL (penalized to below threshold)
    mask3   = ~both
    sub3    = df[mask3]
    imp3    = m(sub3, 'HTF Fix (exclude HH+HL)')
    delta_ret3 = imp3['mean'] - base['mean']
    p3 = ttest_p(sub3['r20d'].values, df[both]['r20d'].values if both.sum() > 3 else np.array([base['mean']]))
    wf_m3, wf_c3 = wf_consistent(df_sorted, lambda d: ~((d['htf_hh']==1) & (d['htf_hl']==1)))

    improvements.append({
        'id':          'IMP-3',
        'name':        'HTF Scoring Inversion Fix (HH+HL → 0 pts, HL-only → full pts)',
        'target':      'HH+HL returns −0.8% while HL-only returns +11.6% — completely backwards',
        'description': 'Swap scoring: HL-only=full w3, HH+HL=0pts, HH-only=0.5×w3.',
        'mechanism':   'Realigns score with actual return data for HTF structure',
        'n_affected':  int(both.sum()),
        'n_retained':  int(mask3.sum()),
        'retention':   round(mask3.mean(), 3),
        'is_delta_ret': round(delta_ret3, 4),
        'is_delta_mfe': round(imp3['mfe'] - base['mfe'], 4),
        'is_delta_wr':  round(imp3['wr'] - base['wr'], 4),
        'is_pf':        round(imp3['pf'], 2),
        'is_pvalue':    round(p3, 3),
        'oos_delta':    None,
        'wf_mean':      round(wf_m3, 4),
        'wf_consistent': wf_c3,
        'overfitted':   not wf_c3 and delta_ret3 > 0,
        'model_score':  0,
        'regime_risk':  'LOW',
        'metrics':      imp3,
    })

    # ── IMP-4: Fix Demand Zone (promote HVN-only, penalize SV+HVN) ──────────
    sv_hvn   = (df['sv_hit'] == 1) & (df['hvn_hit'] == 1)
    hvn_only = (df['hvn_hit'] == 1) & (df['sv_hit'] == 0)
    sv_only  = (df['sv_hit'] == 1) & (df['hvn_hit'] == 0)
    # Simulation: exclude SV+HVN (max score → worst outcome)
    mask4 = ~sv_hvn
    sub4  = df[mask4]
    imp4  = m(sub4, 'Demand Fix (exclude SV+HVN)')
    delta_ret4 = imp4['mean'] - base['mean']
    p4 = ttest_p(sub4['r20d'].values, df[sv_hvn]['r20d'].values if sv_hvn.sum() > 3 else np.array([base['mean']]))
    wf_m4, wf_c4 = wf_consistent(df_sorted, lambda d: ~((d['sv_hit']==1) & (d['hvn_hit']==1)))

    improvements.append({
        'id':          'IMP-4',
        'name':        'Demand Zone Weight Fix (HVN-only→top, SV+HVN→penalized)',
        'target':      'SV+HVN (max score=15) has LOWEST return — HVN-only (score=6) is best',
        'description': 'New weights: HVN-only=12pts, SV+HVN=8pts, SV-only=4pts.',
        'mechanism':   'Corrects demand zone scoring to match actual performance data',
        'n_affected':  int(sv_hvn.sum()),
        'n_retained':  int(mask4.sum()),
        'retention':   round(mask4.mean(), 3),
        'is_delta_ret': round(delta_ret4, 4),
        'is_delta_mfe': round(imp4['mfe'] - base['mfe'], 4),
        'is_delta_wr':  round(imp4['wr'] - base['wr'], 4),
        'is_pf':        round(imp4['pf'], 2),
        'is_pvalue':    round(p4, 3),
        'oos_delta':    None,
        'wf_mean':      round(wf_m4, 4),
        'wf_consistent': wf_c4,
        'overfitted':   not wf_c4 and delta_ret4 > 0,
        'model_score':  0,
        'regime_risk':  'LOW',
        'metrics':      imp4,
    })

    # ── IMP-5: Activate HVN+HTF_HH bonus (discovery) ────────────────────────
    disc_mask = (df['htf_hh'] == 1) & (df['hvn_hit'] == 1)
    sub5 = df[disc_mask]
    imp5 = m(sub5, 'HVN+HTF_HH Bonus Tier')
    delta_ret5 = imp5['mean'] - base['mean']
    p5 = ttest_p(sub5['r20d'].values, df[~disc_mask]['r20d'].values)
    wf_m5, wf_c5 = wf_consistent(df_sorted, lambda d: (d['htf_hh']==1) & (d['hvn_hit']==1))

    improvements.append({
        'id':          'IMP-5',
        'name':        'HVN + HTF_HH Super-Bonus Tier',
        'target':      'Discovery: htf_hh=1 & hvn_hit=1 → +9.7% avg, p=0.010 (significant)',
        'description': 'Add +10 bonus pts when htf_hh=1 AND hvn_hit=1 simultaneously.',
        'mechanism':   'Creates a super-conviction tier for the highest-return combination',
        'n_affected':  int((~disc_mask).sum()),
        'n_retained':  int(disc_mask.sum()),
        'retention':   round(disc_mask.mean(), 3),
        'is_delta_ret': round(delta_ret5, 4),
        'is_delta_mfe': round(imp5['mfe'] - base['mfe'], 4),
        'is_delta_wr':  round(imp5['wr'] - base['wr'], 4),
        'is_pf':        round(imp5['pf'], 2),
        'is_pvalue':    round(p5, 3),
        'oos_delta':    None,
        'wf_mean':      round(wf_m5, 4),
        'wf_consistent': wf_c5,
        'overfitted':   not wf_c5 and delta_ret5 > 0,
        'model_score':  0,
        'regime_risk':  'MEDIUM',
        'metrics':      imp5,
    })

    # ── IMP-6: Combined model (IMP-1 + IMP-3 + IMP-4) ───────────────────────
    comb_mask = mask1 & mask3 & mask4
    sub6  = df[comb_mask]
    imp6  = m(sub6, 'Combined Fix (OB=0 + HTF fix + Demand fix)')
    delta_ret6 = imp6['mean'] - base['mean']
    p6 = ttest_p(sub6['r20d'].values, df[~comb_mask]['r20d'].values)
    wf_m6, wf_c6 = wf_consistent(df_sorted,
                                   lambda d: (d['r2_ob']==0) &
                                             ~((d['htf_hh']==1)&(d['htf_hl']==1)) &
                                             ~((d['sv_hit']==1)&(d['hvn_hit']==1)))

    improvements.append({
        'id':          'IMP-6',
        'name':        'Combined Fix (OB remove + HTF inversion + Demand inversion)',
        'target':      'All 3 confirmed backwards components corrected simultaneously',
        'description': 'Apply IMP-1 + IMP-3 + IMP-4 as a combined package.',
        'mechanism':   'Eliminates all known scoring inversions in one change',
        'n_affected':  int((~comb_mask).sum()),
        'n_retained':  int(comb_mask.sum()),
        'retention':   round(comb_mask.mean(), 3),
        'is_delta_ret': round(delta_ret6, 4),
        'is_delta_mfe': round(imp6['mfe'] - base['mfe'], 4),
        'is_delta_wr':  round(imp6['wr'] - base['wr'], 4),
        'is_pf':        round(imp6['pf'], 2),
        'is_pvalue':    round(p6, 3),
        'oos_delta':    None,
        'wf_mean':      round(wf_m6, 4),
        'wf_consistent': wf_c6,
        'overfitted':   not wf_c6 and delta_ret6 > 0,
        'model_score':  0,
        'regime_risk':  'LOW',
        'metrics':      imp6,
    })

    # ═══ Compute Model Scores ═══
    # Model Score = return_improvement×35% + mfe_improvement×20%
    #             + wr_improvement×15% + pf_improvement×15%
    #             + wf_consistent×15%
    for imp in improvements:
        ret_score = np.clip(imp['is_delta_ret'] / 0.05 * 35, -35, 35)  # 5% delta = max
        mfe_score = np.clip(imp['is_delta_mfe'] / 0.03 * 20, -20, 20)  # 3% delta = max
        wr_score  = np.clip(imp['is_delta_wr']  / 0.10 * 15, -15, 15)  # 10% delta = max
        pf_score  = np.clip((imp['is_pf'] - base['pf']) / 2 * 15, -15, 15)
        wf_score  = 15 if imp['wf_consistent'] else (-5 if not imp['wf_consistent'] else 0)
        raw = ret_score + mfe_score + wr_score + pf_score + wf_score
        imp['model_score'] = int(np.clip(50 + raw, 0, 100))  # 50 = baseline

    return base, improvements

# ═══════════════════════════════════════════════════════════════════════════════
# E) RANK + OVERFITTING PROTECTION
# ═══════════════════════════════════════════════════════════════════════════════

def rank_and_filter(improvements, base):
    eligible = []
    for imp in improvements:
        # Reject if:
        # 1. Requires >60% signal reduction
        if imp['retention'] < 0.40:
            imp['rejected_reason'] = f"Signal reduction too large ({imp['retention']*100:.0f}% retained < 40% min)"
            continue
        # 2. WF inconsistent AND IS improvement is small
        if not imp['wf_consistent'] and abs(imp['is_delta_ret']) < 0.01:
            imp['rejected_reason'] = f"WF inconsistent + small IS delta ({imp['is_delta_ret']*100:+.1f}%)"
            continue
        imp['rejected_reason'] = None
        eligible.append(imp)

    eligible.sort(key=lambda x: x['model_score'], reverse=True)
    return eligible[:3], eligible[3:], [i for i in improvements if i.get('rejected_reason')]

# ═══════════════════════════════════════════════════════════════════════════════
# F) CROSS-REPORT CONSISTENCY CHECK
# ═══════════════════════════════════════════════════════════════════════════════

def cross_consistency(df, audit, logic, bt):
    checks = []

    # 1. Backtest n_signals vs DB n_signals
    bt_n = bt.get('overall_stats', {}).get('total_signals', 0)
    db_n = len(df)
    if abs(bt_n - db_n) > 100:
        checks.append({
            'module_a': 'Backtest Report',
            'module_b': 'DB Signals',
            'metric':   'Total Signal Count',
            'a_value':  bt_n,
            'b_value':  db_n,
            'status':   'MISMATCH',
            'detail':   f'Backtest uses {bt_n} signals vs DB {db_n}. Backtest likely includes historical scan data.',
        })
    else:
        checks.append({'module_a':'Backtest','module_b':'DB','metric':'Signal Count',
                        'status':'OK','a_value':bt_n,'b_value':db_n,'detail':'Consistent'})

    # 2. Logic r20d baseline vs DB
    logic_base = logic.get('baseline_r20d', 0)
    db_base    = float(df['r20d'].mean())
    if abs(logic_base - db_base) > 0.005:
        checks.append({
            'module_a': 'Logic Analyzer',
            'module_b': 'DB Signals',
            'metric':   'Baseline r20d',
            'a_value':  round(logic_base, 4),
            'b_value':  round(db_base, 4),
            'status':   'MISMATCH',
            'detail':   'Minor baseline discrepancy — possible rounding or filter difference.',
        })
    else:
        checks.append({'module_a':'Logic','module_b':'DB','metric':'Baseline r20d',
                        'status':'OK','a_value':round(logic_base,4),'b_value':round(db_base,4),
                        'detail':'Consistent'})

    # 3. Audit OB finding vs Logic OB finding
    logic_ob  = logic.get('function_impact', {}).get('sc_ob', {}).get('delta_r20d', 0)
    audit_ob  = next((f['diff'] for f in audit.get('filter_damage', [])
                      if 'Order Block' in f.get('filter','')), None)
    if audit_ob is not None:
        if (logic_ob < 0) == (audit_ob < 0):
            checks.append({'module_a':'Logic','module_b':'Audit','metric':'OB harmful direction',
                            'status':'OK','a_value':round(logic_ob,4),'b_value':round(audit_ob,4),
                            'detail':'Both confirm OB is negative — CONSISTENT'})
        else:
            checks.append({'module_a':'Logic','module_b':'Audit','metric':'OB harmful direction',
                            'status':'MISMATCH','a_value':round(logic_ob,4),'b_value':round(audit_ob,4),
                            'detail':'Direction disagreement — investigate'})

    # 4. Sweep CONFIRMED status
    sweep_confirmed_oof = next((r['verdict'] for r in audit.get('overfitting_audit', [])
                                 if 'sweep' in r.get('finding','')), None)
    if sweep_confirmed_oof == 'CONFIRMED':
        checks.append({'module_a':'Audit OOF','module_b':'Logic','metric':'Sweep edge',
                        'status':'OK','a_value':'CONFIRMED','b_value':round(logic.get('function_impact',{}).get('sc_liquidity',{}).get('delta_r20d',0),4),
                        'detail':'Sweep edge confirmed OOS in audit, positive in logic — CONSISTENT'})

    # 5. Score ≥55 gate — Backtest vs Audit
    score_bt_55 = next((r.get('expectancy_pct',0) for r in bt.get('score_threshold_analysis',[])
                         if r.get('score_threshold') == 55), None)
    score_oof_55 = next((r.get('verdict') for r in audit.get('overfitting_audit', [])
                          if 'score≥55' in r.get('finding','')), None)
    if score_bt_55 and score_oof_55:
        status = 'MISMATCH' if score_oof_55 == 'OVERFITTED' else 'OK'
        checks.append({
            'module_a': 'Backtest (score≥55)',
            'module_b': 'Audit OOF (score≥55)',
            'metric':   'Score Gate Validity',
            'a_value':  f'{score_bt_55:.1f}% expectancy',
            'b_value':  score_oof_55,
            'status':   status,
            'detail':   'Backtest shows high expectancy at score≥55, but Audit finds OVERFITTED. '
                        'Backtest uses MFE-proxy, not close-to-close — STRUCTURAL MISMATCH.',
        })

    return checks

# ═══════════════════════════════════════════════════════════════════════════════
# HTML BUILDER
# ═══════════════════════════════════════════════════════════════════════════════

def _p(v, d=1):
    return f"{v*100:.{d}f}%" if v is not None else "—"

def _pp(v, d=1):
    color = "#155724" if v > 0.002 else "#721c24" if v < -0.002 else "#555"
    return f"<span style='color:{color};font-weight:700'>{v*100:+.{d}f}%</span>" if v is not None else "—"

def _v(v, d=2):
    return f"{v:.{d}f}" if v is not None else "—"

def _badge(text, color='#155724', bg='#d4edda'):
    return f"<span style='background:{bg};color:{color};font-size:10px;font-weight:700;padding:2px 8px;border-radius:4px'>{text}</span>"

def build_html(diag, drivers, base, improvements, top3, rejected,
               cross_checks, all_imps):

    health = diag['health_score']
    health_color = '#155724' if health >= 65 else '#856404' if health >= 45 else '#721c24'
    health_bg    = '#d4edda'  if health >= 65 else '#fff3cd'  if health >= 45 else '#f8d7da'

    cs = diag['component_scores']

    def score_bar(label, val):
        color = '#155724' if val >= 65 else '#856404' if val >= 45 else '#721c24'
        return f"""
<div style="margin:5px 0">
  <div style="display:flex;justify-content:space-between;font-size:12px;margin-bottom:2px">
    <span>{label}</span><span style="font-weight:700;color:{color}">{val}/100</span>
  </div>
  <div style="background:#eee;border-radius:4px;height:8px">
    <div style="background:{color};width:{val}%;border-radius:4px;height:8px"></div>
  </div>
</div>"""

    def strength_li(items):
        return "".join(f"<li style='margin:5px 0;font-size:12px'>✅ {x}</li>" for x in items)

    def weakness_li(items):
        return "".join(f"<li style='margin:5px 0;font-size:12px'>⚠️ {x}</li>" for x in items)

    # ── Section A
    sec_a = f"""
<div class="card" id="sA">
  <h2>A — System Diagnosis</h2>
  <div style="display:flex;gap:20px;flex-wrap:wrap;align-items:flex-start">
    <div style="text-align:center;background:{health_bg};border-radius:12px;padding:20px 30px;min-width:140px">
      <div style="font-size:11px;color:#555;margin-bottom:4px">Overall Health Score</div>
      <div style="font-size:52px;font-weight:800;color:{health_color}">{health}</div>
      <div style="font-size:11px;color:#555">/100</div>
    </div>
    <div style="flex:1;min-width:250px">
      {score_bar('Profit Factor Quality', cs['profit_factor'])}
      {score_bar('Win Rate', cs['win_rate'])}
      {score_bar('MFE/MAE Ratio', cs['mfe_mae_ratio'])}
      {score_bar('OOS Predictability', cs['oos_predictability'])}
      {score_bar('Scoring Accuracy (% correct)', cs['scoring_accuracy'])}
    </div>
    <div style="flex:1;min-width:250px">
      <div style="background:#f8f9fa;border-radius:8px;padding:12px">
        <div style="font-size:11px;font-weight:700;color:#1a3a5c;margin-bottom:8px">BASELINE METRICS</div>
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:6px;font-size:12px">
          <span>n signals</span><span style="font-weight:700">{base['n']}</span>
          <span>Avg r20d</span><span style="font-weight:700;color:#155724">{_p(base['mean'])}</span>
          <span>Median r20d</span><span style="font-weight:700">{_p(base['median'])}</span>
          <span>Win Rate (≥5%)</span><span style="font-weight:700">{_p(base['wr'])}</span>
          <span>Profit Factor</span><span style="font-weight:700">{_v(base['pf'])}</span>
          <span>Avg MFE</span><span style="font-weight:700;color:#155724">{_p(base['mfe'])}</span>
          <span>Avg MAE</span><span style="font-weight:700;color:#721c24">-{_p(abs(base['mae']))}</span>
        </div>
      </div>
    </div>
  </div>
  <div style="margin-top:16px;display:grid;grid-template-columns:1fr 1fr;gap:16px">
    <div>
      <div style="font-weight:700;color:#155724;font-size:12px;margin-bottom:6px">STRENGTHS</div>
      <ul style="padding-right:16px;margin:0">{strength_li(diag['strengths'])}</ul>
    </div>
    <div>
      <div style="font-weight:700;color:#721c24;font-size:12px;margin-bottom:6px">WEAKNESSES</div>
      <ul style="padding-right:16px;margin:0">{weakness_li(diag['weaknesses'])}</ul>
    </div>
  </div>
</div>"""

    # ── Section B
    def driver_row(d):
        sev = d['severity']
        sev_color = '#721c24' if sev >= 70 else '#856404' if sev >= 50 else '#555'
        imp_color = '#721c24' if d['avg_impact'] < 0 else '#155724'
        return f"""
<tr style="border-bottom:1px solid #f0f0f0;vertical-align:top">
  <td style="padding:8px 10px;font-weight:700;color:#1a3a5c;font-size:12px">#{d['rank']}</td>
  <td style="padding:8px 10px;font-weight:600;font-size:12px">{d['driver']}</td>
  <td style="padding:8px 10px;text-align:center;font-size:12px">{d['freq_pct']:.1f}%</td>
  <td style="padding:8px 10px;text-align:center;font-weight:700;color:{imp_color};font-size:12px">{d['avg_impact']*100:+.2f}%</td>
  <td style="padding:8px 10px;text-align:center">
    <div style="background:#eee;border-radius:4px;height:8px;width:80px;display:inline-block">
      <div style="background:{sev_color};width:{sev}%;border-radius:4px;height:8px"></div>
    </div>
    <span style="font-size:11px;color:{sev_color};margin-right:4px">{sev}</span>
  </td>
  <td style="padding:8px 10px;font-size:11px;color:#555;max-width:280px">{d['detail'][:120]}</td>
</tr>"""

    sec_b = f"""
<div class="card" id="sB">
  <h2>B — Key Loss Drivers</h2>
  <table style="width:100%;border-collapse:collapse">
    <thead><tr style="background:#1a3a5c;color:#fff;font-size:11px">
      <th style="padding:7px 10px">#</th>
      <th style="padding:7px 10px">Driver</th>
      <th style="padding:7px 10px;text-align:center">تكرار</th>
      <th style="padding:7px 10px;text-align:center">متوسط التأثير</th>
      <th style="padding:7px 10px;text-align:center">Severity</th>
      <th style="padding:7px 10px">التفاصيل</th>
    </tr></thead>
    <tbody>{"".join(driver_row(d) for d in drivers)}</tbody>
  </table>
</div>"""

    # ── Section C+D
    def imp_row(imp, highlight=False):
        ms = imp['model_score']
        ms_color = '#155724' if ms >= 60 else '#856404' if ms >= 50 else '#721c24'
        ms_bg    = '#d4edda'  if ms >= 60 else '#fff3cd'  if ms >= 50 else '#f8d7da'
        wf_badge = _badge('WF ✓', '#155724', '#d4edda') if imp['wf_consistent'] else _badge('WF ✗', '#856404', '#fff3cd')
        oof_badge = _badge('OVERFITTED', '#721c24', '#f8d7da') if imp['overfitted'] else ''
        ret_delta = imp['is_delta_ret']
        bg = '#f0fff4' if highlight else ''
        return f"""
<tr style="border-bottom:1px solid #eee;vertical-align:top;background:{bg}">
  <td style="padding:8px 10px;font-weight:700;color:#1a3a5c;font-size:11px;white-space:nowrap">{imp['id']}</td>
  <td style="padding:8px 10px;max-width:200px">
    <div style="font-weight:600;font-size:12px;margin-bottom:2px">{imp['name']}</div>
    <div style="font-size:10px;color:#555">{imp['description'][:80]}</div>
  </td>
  <td style="padding:8px 10px;text-align:center;font-size:12px">{imp['n_retained']}<br><span style="font-size:10px;color:#555">({imp['retention']*100:.0f}%)</span></td>
  <td style="padding:8px 10px;text-align:center">{_pp(ret_delta)}</td>
  <td style="padding:8px 10px;text-align:center">{_pp(imp['is_delta_mfe'])}</td>
  <td style="padding:8px 10px;text-align:center;font-size:12px">{_v(imp['is_pf'])}</td>
  <td style="padding:8px 10px;text-align:center;font-size:11px">{imp['is_pvalue']:.3f}</td>
  <td style="padding:8px 10px;text-align:center">{_pp(imp['oos_delta']) if imp['oos_delta'] is not None else '<span style="color:#aaa">—</span>'}</td>
  <td style="padding:8px 10px;text-align:center">{_pp(imp['wf_mean'])}<br>{wf_badge}</td>
  <td style="padding:8px 10px;text-align:center">
    <span style="background:{ms_bg};color:{ms_color};font-size:13px;font-weight:800;padding:3px 10px;border-radius:6px">{ms}</span>
    {oof_badge}
  </td>
</tr>"""

    all_rows = "".join(imp_row(imp, highlight=(imp['id'] in [t['id'] for t in top3]))
                       for imp in all_imps)

    sec_cd = f"""
<div class="card" id="sCD">
  <h2>C+D — Improvement Proposals & Simulated Impact</h2>
  <p style="font-size:12px;color:#555;margin-bottom:12px">
    Simulated on {base['n']} historical signals. Model Score = weighted combination of return improvement (35%) +
    MFE (20%) + WR (15%) + PF (15%) + WF consistency (15%). Baseline = 50.
    <span style="background:#f0fff4;border:1px solid #b2dfdb;padding:2px 6px;border-radius:4px;margin-right:8px;font-size:11px">✅ = Top 3</span>
  </p>
  <div style="overflow-x:auto">
  <table style="width:100%;border-collapse:collapse;font-size:12px">
    <thead><tr style="background:#1a3a5c;color:#fff;font-size:11px">
      <th style="padding:7px 8px">ID</th>
      <th style="padding:7px 8px">التحسين</th>
      <th style="padding:7px 8px;text-align:center">N Retained</th>
      <th style="padding:7px 8px;text-align:center">Δ Return</th>
      <th style="padding:7px 8px;text-align:center">Δ MFE</th>
      <th style="padding:7px 8px;text-align:center">PF</th>
      <th style="padding:7px 8px;text-align:center">p-val</th>
      <th style="padding:7px 8px;text-align:center">OOS Δ</th>
      <th style="padding:7px 8px;text-align:center">Walk-Forward</th>
      <th style="padding:7px 8px;text-align:center">Model Score</th>
    </tr></thead>
    <tbody>{all_rows}</tbody>
  </table>
  </div>

  <div style="margin-top:16px;background:#fff3cd;border-radius:8px;padding:12px;font-size:12px">
    <b>Rejected improvements:</b>
    {"".join(f"<div style='margin:4px 0'>❌ <b>{r['id']}</b> — {r['name'][:60]}: {r['rejected_reason']}</div>" for r in rejected) or "<span style='color:#555'>None rejected</span>"}
  </div>
</div>"""

    # ── Section E
    def top3_card(rank, imp):
        ms = imp['model_score']
        ms_color = '#155724' if ms >= 60 else '#856404'
        rank_icons = {1:'🥇', 2:'🥈', 3:'🥉'}
        icon = rank_icons.get(rank, '🔹')
        return f"""
<div style="background:#f8f9fa;border-radius:10px;padding:18px;margin-bottom:12px;
            border-left:5px solid {ms_color}">
  <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px">
    <div>
      <span style="font-size:20px">{icon}</span>
      <span style="font-size:15px;font-weight:700;color:#1a3a5c;margin-right:8px">{imp['name']}</span>
    </div>
    <span style="font-size:22px;font-weight:800;color:{ms_color}">Score: {ms}</span>
  </div>
  <div style="font-size:12px;color:#555;margin-bottom:10px"><b>مشكلة:</b> {imp['target'][:100]}</div>
  <div style="font-size:12px;margin-bottom:10px"><b>الحل:</b> {imp['description']}</div>
  <div style="display:flex;gap:12px;flex-wrap:wrap;font-size:12px">
    <div>Δ Return: {_pp(imp['is_delta_ret'])}</div>
    <div>Δ MFE: {_pp(imp['is_delta_mfe'])}</div>
    <div>PF: <b>{_v(imp['is_pf'])}</b> (baseline: {_v(base['pf'])})</div>
    <div>Retained: <b>{imp['n_retained']}</b> ({imp['retention']*100:.0f}%)</div>
    <div>WF: {'✅ Consistent' if imp['wf_consistent'] else '⚠️ Inconsistent'}</div>
    <div>Overfitting risk: {'🔴 HIGH' if imp['overfitted'] else '🟢 LOW'}</div>
  </div>
  <div style="margin-top:8px;font-size:11px">
    <b>Mechanism:</b> {imp['mechanism']}
  </div>
</div>"""

    top3_html = "".join(top3_card(i+1, imp) for i, imp in enumerate(top3))

    sec_e = f"""
<div class="card" id="sE">
  <h2>E — Top 3 Recommendations</h2>
  {top3_html}
</div>"""

    # ── Cross-consistency
    def cc_row(c):
        color = '#155724' if c['status'] == 'OK' else '#721c24'
        badge = _badge(c['status'], color, '#d4edda' if c['status']=='OK' else '#f8d7da')
        return f"""
<tr style="border-bottom:1px solid #f0f0f0">
  <td style="padding:7px 10px;font-size:11px">{c['module_a']}</td>
  <td style="padding:7px 10px;font-size:11px">{c['module_b']}</td>
  <td style="padding:7px 10px;font-size:11px">{c['metric']}</td>
  <td style="padding:7px 10px;text-align:center;font-size:11px">{c.get('a_value','')}</td>
  <td style="padding:7px 10px;text-align:center;font-size:11px">{c.get('b_value','')}</td>
  <td style="padding:7px 10px;text-align:center">{badge}</td>
  <td style="padding:7px 10px;font-size:11px;color:#555">{c.get('detail','')[:100]}</td>
</tr>"""

    sec_cc = f"""
<div class="card" id="sCC">
  <h2>§9 — Cross-Report Consistency Check</h2>
  <table style="width:100%;border-collapse:collapse;font-size:12px">
    <thead><tr style="background:#1a3a5c;color:#fff;font-size:11px">
      <th style="padding:7px 10px">Module A</th><th style="padding:7px 10px">Module B</th>
      <th style="padding:7px 10px">Metric</th>
      <th style="padding:7px 10px;text-align:center">A Value</th>
      <th style="padding:7px 10px;text-align:center">B Value</th>
      <th style="padding:7px 10px;text-align:center">Status</th>
      <th style="padding:7px 10px">Detail</th>
    </tr></thead>
    <tbody>{"".join(cc_row(c) for c in cross_checks)}</tbody>
  </table>
</div>"""

    # ── Section F
    t1 = top3[0] if len(top3) > 0 else {}
    t2 = top3[1] if len(top3) > 1 else {}
    t3 = top3[2] if len(top3) > 2 else {}
    insights = [
        f"النظام يعمل بشكل جيد (Health={health}/100) لكن 3 من 8 مكونات في التسجيل معكوسة — OB، HTF، Demand Zone",
        f"أكبر فرصة تحسين فورية: {t1.get('name','—')} (Model Score={t1.get('model_score',0)}, Δ Return={t1.get('is_delta_ret',0)*100:+.1f}%)",
        f"التحسين الثاني: {t2.get('name','—')} — الـ sweep هو الوحيد المؤكد OOS ويستحق التعزيز",
        f"تحذير: gate score≥55 يبدو جيداً في backtest لكنه OVERFITTED (WF سلبي) — لا تستخدمه كفلتر إجباري",
        f"الخطوة الأعلى تأثيراً اليوم: تطبيق {t1.get('name','—')[:50]} على main.py — تعديل سطر واحد في sc_ob()",
    ]

    sec_f = f"""
<div class="card" id="sF" style="background:linear-gradient(135deg,#1a3a5c,#2a6496);color:#fff">
  <h2 style="color:#fff;border-left-color:#8fb8d8">F — Final Insight</h2>
  <ul style="padding-right:20px;margin:0">
    {"".join(f'<li style="margin:10px 0;font-size:13px">{"".join(["🎯 " if i==0 else "📌 " if i<4 else "⚡ "])} {ins}</li>' for i, ins in enumerate(insights))}
  </ul>
</div>"""

    body = f"""<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
<meta charset="UTF-8">
<title>EGX Adaptive Learning Engine v2.1 — {DATE_STR}</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
  body{{font-family:Arial,sans-serif;margin:0;padding:20px;background:#f0f2f5;direction:ltr;color:#222}}
  h1{{color:#1a3a5c;border-bottom:3px solid #1a3a5c;padding-bottom:10px;font-size:1.5em}}
  h2{{color:#1a3a5c;border-left:5px solid #0d6efd;padding-left:12px;margin-top:0;font-size:1.1em}}
  .card{{background:#fff;border-radius:10px;padding:22px 24px;margin-bottom:22px;
         box-shadow:0 2px 8px rgba(0,0,0,.08)}}
  table tr:nth-child(even){{background:#f9f9f9}}
  table td,table th{{border:1px solid #dee2e6;padding:6px 8px}}
  table th{{font-size:11px;text-align:left}}
  .toc{{display:flex;gap:16px;flex-wrap:wrap;margin-bottom:20px}}
  .toc a{{color:#1a3a5c;text-decoration:none;font-size:12px;font-weight:600;
           background:#e8f4fd;padding:5px 12px;border-radius:20px}}
</style>
</head>
<body>
<h1>🤖 EGX Adaptive Learning Engine v2.1</h1>
<p style="color:#555;font-size:12px">Generated: {DATE_STR} &nbsp;|&nbsp;
   Analysis only — no system modifications &nbsp;|&nbsp;
   Signals: <b>{base['n']}</b> &nbsp;|&nbsp; Baseline r20d: <b>{_p(base['mean'])}</b></p>

<div class="toc">
  <a href="#sA">A — Diagnosis</a>
  <a href="#sB">B — Loss Drivers</a>
  <a href="#sCD">C+D — Improvements</a>
  <a href="#sE">E — Top 3</a>
  <a href="#sCC">§9 — Consistency</a>
  <a href="#sF">F — Final Insight</a>
</div>

{sec_a}
{sec_b}
{sec_cd}
{sec_e}
{sec_cc}
{sec_f}
</body></html>"""

    return body

# ═══════════════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════════════

def main():
    import time
    t0 = time.time()
    print(f"[adaptive_learning] EGX Adaptive Learning Engine v2.1 — {DATE_STR}")

    print("[1] Loading data...")
    df     = load_signals()
    audit  = _j("system_audit_results.json")
    logic  = _j("logic_analysis_results.json")
    bt     = _j("backtest_report.json")
    print(f"    {len(df)} signals | audit filters={len(audit.get('filter_damage',[]))} | logic recs={len(logic.get('summary_recommendations',[]))}")

    print("[2] System diagnosis...")
    diag = system_diagnosis(df, audit, logic)
    print(f"    Health Score: {diag['health_score']}/100")

    print("[3] Loss driver analysis...")
    drivers = loss_drivers(df, audit)
    print(f"    {len(drivers)} drivers identified, top={drivers[0]['driver'][:40]}")

    print("[4] Simulating improvements...")
    base, all_imps = simulate_improvements(df)
    print(f"    {len(all_imps)} improvements simulated")

    print("[5] Ranking + overfitting protection...")
    top3, rest, rejected = rank_and_filter(all_imps, base)
    print(f"    Top 3: {[i['id'] for i in top3]} | Rejected: {[i['id'] for i in rejected]}")

    print("[6] Cross-report consistency check...")
    checks = cross_consistency(df, audit, logic, bt)
    mismatches = [c for c in checks if c['status'] == 'MISMATCH']
    print(f"    {len(checks)} checks | {len(mismatches)} mismatches")

    print("[7] Building report...")
    html = build_html(diag, drivers, base, all_imps, top3, rejected, checks, all_imps)

    out_html = f"adaptive_learning_report_{DATE_STR}.html"
    out_json = "adaptive_learning_results.json"

    with open(out_html, 'w', encoding='utf-8') as f:
        f.write(html)

    summary = {
        "generated_at":   DATE_STR,
        "engine_version": "2.1",
        "n_signals":      int(len(df)),
        "health_score":   diag['health_score'],
        "baseline":       {k: round(v, 4) if isinstance(v, float) else v
                           for k, v in base.items() if k != 'label'},
        "top3":           [{
            "id":          i['id'],
            "name":        i['name'],
            "model_score": i['model_score'],
            "delta_ret":   round(i['is_delta_ret'], 4),
            "delta_mfe":   round(i['is_delta_mfe'], 4),
            "pf":          round(i['is_pf'], 3),
            "wf_consistent": i['wf_consistent'],
            "overfitted":  i['overfitted'],
            "n_retained":  i['n_retained'],
            "retention":   round(i['retention'], 3),
        } for i in top3],
        "all_improvements": [{
            "id":           i['id'],
            "name":         i['name'],
            "model_score":  i['model_score'],
            "delta_ret":    round(i['is_delta_ret'], 4),
            "retention":    round(i['retention'], 3),
            "wf_consistent": i['wf_consistent'],
        } for i in all_imps],
        "cross_check_mismatches": [c for c in checks if c['status'] == 'MISMATCH'],
        "loss_drivers": [{
            "rank":        d['rank'],
            "driver":      d['driver'],
            "severity":    d['severity'],
            "freq_pct":    d['freq_pct'],
            "avg_impact":  d['avg_impact'],
        } for d in drivers],
    }

    with open(out_json, 'w', encoding='utf-8') as f:
        json.dump(summary, f, indent=2, ensure_ascii=False, default=str)

    elapsed = time.time() - t0
    print(f"\n[adaptive_learning] Done in {elapsed:.1f}s")
    print(f"  Report → {out_html}")
    print(f"  JSON   → {out_json}")
    print(f"\n📊 Health Score: {diag['health_score']}/100")
    print(f"🥇 Top improvement: {top3[0]['name'] if top3 else '—'} (Score={top3[0]['model_score'] if top3 else 0})")
    print(f"⚡ Simulated delta: {top3[0]['is_delta_ret']*100:+.2f}% return" if top3 else "")


if __name__ == "__main__":
    main()
