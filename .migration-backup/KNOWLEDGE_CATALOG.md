# Knowledge Catalog

**CRL Version:** 1.0  
**Generated:** 2026-06-21  
**Primary store:** `research/knowledge/knowledge_base.db`  
**Legacy store:** `knowledge_base.json`, `gx_research_memory.json`  

---

## Verified Findings — Station Research

| ID | Station | Metric | Rho | N | Verdict |
|----|---------|--------|-----|---|---------|
| SF-R2-MAE | R2 | Spearman vs MAE_40 | +0.286*** | 782 | STRONGEST_PREDICTOR |
| SF-R3-MAE | R3 | Spearman vs MAE_40 | +0.243*** | 782 | POSITIVE |
| SF-R4-MAE | R4 | Spearman vs MAE_40 | +0.157*** | 782 | POSITIVE |
| SF-R7-MAE | R7 | Spearman vs MAE_40 | +0.106** | 782 | POSITIVE |
| SF-R7-MFE | R7 | Spearman vs MFE_40 | +0.081* | 782 | POSITIVE |
| SF-R5-MFE | R5 | Spearman vs MFE_40 | -0.174*** | 782 | ANTI_PREDICTIVE |
| SF-R6-MFE | R6 | Spearman vs MFE_40 | -0.202*** | 782 | ANTI_PREDICTIVE |
| SF-R6-MAE | R6 | Spearman vs MAE_40 | -0.136*** | 782 | ANTI_PREDICTIVE |
| SF-FINAL-MAE | FINAL | Spearman vs MAE_40 | +0.137*** | 782 | GOOD |
| SF-FINAL-MFE | FINAL | Spearman vs MFE_40 | -0.049 | 782 | NEUTRAL |

---

## Verified Findings — System Architecture

| Finding | Conclusion | Confidence | Files |
|---------|-----------|-----------|-------|
| R2 is primary ranking station | rho(R2,MAE)=+0.286***. final_score is anti-predictive (rho=-0.087 vs ret_40). R2 ONLY for ranking. | HIGH | portfolio_manager.py |
| R7 continuous repair successful | 36→747 unique values. Direction improved: rho +0.252→+0.106 (corrected). No lookahead. | HIGH | discount_reversal_engine.py |
| R5 cannot be repaired (yet) | All repair variants worsened Spearman. Binary 7-value structure retained. | LOW | discount_reversal_engine.py |
| R6 anti-predictive structurally | Early CHOCH/BOS = premature entry. Cannot fix without weight-change mandate. | MEDIUM | discount_reversal_engine.py |
| R8 low discrimination | 40-point score band (46-86). Near-zero Spearman. Baseline window too wide. | LOW | discount_reversal_engine.py |
| R1 EQ gate is correct structural boundary | 50th percentile of 80-bar range (eq) is the discount/premium dividing line. No evidence to change. | HIGH | signal_engine.py, discount_reversal_engine.py |

---

## Verified Findings — Backtest Results

| Finding | Value | Source |
|---------|-------|--------|
| 5-year win rate | 69.4% (729/1051 signals) | BT-MAIN-5YR |
| 5-year expectancy | +16.7% per signal | BT-MAIN-5YR |
| 5-year profit factor | 9.85 | BT-MAIN-5YR |
| 5-year CAGR | 100.1% | BT-MAIN-5YR |
| 5-year max drawdown | -3.52% | BT-MAIN-5YR |
| Calmar ratio | 28.44 | BT-MAIN-5YR |
| Engine found all 15 manual positions | +9 additional | BT-CONST-WF |
| Engine avg return 2026 | +26.7% | BT-CONST-WF |
| Manual avg return 2026 | +30.8% | BT-CONST-WF |

---

## Verified Findings — Feature Importance (research_results.json)

**Method:** Spearman correlation vs MFE_20d (n=668 signals in egx_research.db)

| Feature | Rho vs MFE_20d | Direction | Meaning |
|---------|---------------|-----------|---------|
| snap_reclaim_spd | -0.165 | Negative | Faster price reclaim = weaker MFE |
| feat_vwap_dist | -0.137 | Negative | Closer to VWAP = weaker MFE |
| snap_num_touches | -0.129 | Negative | More OB touches = weaker MFE |
| feat_equal_lows_count | -0.129 | Negative | More equal lows = weaker MFE |
| feat_dist_last_bos | -0.125 | Negative | Closer to BOS = weaker MFE |
| r4_htf | +0.061 | Positive | HTF confirmation improves MFE |
| sweep_detected | +0.055 | Positive | Liquidity sweep before entry improves MFE |
| hvn_hit | +0.053 | Positive | HVN zone improves MFE |
| r3_liquidity | +0.049 | Positive | Better liquidity improves MFE |
| r8_demand | +0.049 | Positive | Demand zone quality improves MFE |

---

## Factor Findings (knowledge_base.json)

| Factor | Verdict | Win Rate | Expectancy | Suggested Weight |
|--------|---------|----------|-----------|-----------------|
| r4_htf | POSITIVE | 47% | 5.5% | 0.84 (normalized) |
| r7_div | TAIL_DRIVER | 40% | 4.8% | 12.69 (tail contribution 31%) |
| r2_ob | NEGATIVE | — | — | 10.13 |
| r1_price | — | — | — | — |
| r3_liquidity | — | — | — | — |
| r5_avwap | — | — | — | — |
| r6_macd | — | — | — | — |
| r8_demand | — | — | — | — |

**Note:** Factor labels in knowledge_base.json use the OLD naming convention (r1_price, r2_ob, etc.)
which maps to the pre-constitutional R-factor numbering. Do not confuse with
Constitutional R1-R8 which use a different numbering scheme.

---

## Portfolio Knowledge

| Finding | Value | Confidence |
|---------|-------|-----------|
| Constitutional engine avg return 2026 | +26.7% | HIGH |
| Manual portfolio avg return 2026 | +30.8% | HIGH |
| Portfolio max pairwise correlation | 0.671 | HIGH |
| Industrial sector inherited breach | 40% (cap 25%) | CONFIRMED |
| Real Estate sector inherited breach | 33.3% (cap 25%) | CONFIRMED |
| ABUK.CA is best available candidate | R2=75.1 (Exceptional) — blocked by Industrial cap | HIGH |
| All 15 manual positions found by engine | Plus 9 additional | HIGH |

---

## Pattern Knowledge (pattern_knowledge_base — 261 rows)

Source: `egx_research.db.pattern_knowledge_base`  
Populated by: `pattern_kb.py` (2/3-flag combinations, MFE40-based validation)  
Access: `SELECT * FROM pattern_knowledge_base ORDER BY mfe40_avg DESC`  

---

## Knowledge Gaps (Identified, Not Yet Filled)

| Gap | Priority | CRL Experiment |
|-----|---------|----------------|
| Optimal holding period by signal quality tier | MEDIUM | Not assigned |
| R5 repair with larger dataset | LOW | CRL-R5-BINARY (REJECTED — retry at >2000 signals) |
| R6 redesign evidence | MEDIUM | Requires weight-change mandate + new walk-forward |
| R8 baseline window sensitivity | LOW | CRL-R8-RANGE (VERIFIED defect) |
| Equal weight vs R2-weighted | MEDIUM | Not assigned |
| CBE rate cycle vs EGX correlation | LOW | Not assigned |
| Banking sector entry signals | MEDIUM | EGAL.CA and COMI.CA on watchlist |
| EARLY BUY auto-promotion criteria | MEDIUM | early_buy_research (53 rows available) |

---

## How to Add a Finding

```python
import sqlite3, json
from datetime import datetime

conn = sqlite3.connect('research/knowledge/knowledge_base.db')
conn.execute('''
INSERT OR IGNORE INTO findings
(research_id, question, dataset, method, evidence, conclusion,
 confidence, future_rec, related_files, status, recorded_at)
VALUES (?,?,?,?,?,?,?,?,?,?,?)
''', (
    'CRL-XXXX',
    'What question does this answer?',
    'Dataset source + n_signals',
    'Method used',
    json.dumps({'rho': 0.0, 'n': 0, 'p_value': 0.0}),
    'Conclusion text',
    'HIGH',
    'Future recommendation',
    'related_file.py',
    'VERIFIED',
    datetime.now().isoformat()
))
conn.commit()
conn.close()
```
