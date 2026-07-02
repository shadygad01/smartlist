# Experiment Registry

**CRL Version:** 1.0  
**Generated:** 2026-06-21  
**Total experiments:** 28 (5 CRL + 23 gx_research_memory)  
**Full data:** `research/knowledge/knowledge_base.db → experiment_registry`  

---

## Status Definitions

| Status | Meaning |
|--------|---------|
| OPEN | Experiment identified, not yet run |
| INVESTIGATING | Active investigation underway |
| VERIFIED | Evidence gathered, conclusion confirmed |
| REJECTED | Attempted, evidence rejected the hypothesis |
| SUPERSEDED | Replaced by a newer experiment |
| ARCHIVED | Closed without conclusion |

---

## CRL Verified Experiments

### CRL-R2-RANKING — R2 as Primary Ranking Station

**Question:** Is R2 the best station to use for portfolio ranking?  
**Station:** R2 Discount Quality  
**Dataset:** Constitutional walk-forward 2026-01-01 to 2026-06-21 (782 signals)  
**Window:** Full period  
**Method:** Spearman rank correlation R2 vs all outcome metrics (MAE_40, MFE_40, ret_40, low_break)  
**Walk-Forward:** Yes  
**Variables:** r2_score, final_score, MAE_40, MFE_40, ret_40  
**Evidence:**
- rho(R2, MAE_40) = +0.286*** — strongest predictor across all stations
- rho(final_score, ret_40) = -0.087 — final_score is net anti-predictive
- R2 is the only positively-predictive signal-quality station
**Result:** R2 confirmed as primary ranking station. final_score NEVER used for ranking.  
**Confidence:** HIGH  
**Recommendation:** Portfolio manager ranks by R2 only. Constitution enforces this.  
**Status:** VERIFIED  
**Files:** `portfolio_manager.py`, `candidate_pool_builder.py`, `CONSTITUTION_VERSION.md`

---

### CRL-R5-BINARY — R5 Binary Score Repair Attempt

**Question:** Can R5 be repaired to produce continuous scores without losing Spearman?  
**Station:** R5 Low Protection  
**Dataset:** Constitutional walk-forward 2026-01-01 to 2026-06-21 (782 signals)  
**Window:** Full period  
**Method:** Multiple repair variants: weight redistribution, no_new_low extension, failed_breakdown expansion, ATR proximity, volatility component  
**Walk-Forward:** Yes  
**Variables:** r5_score (original 7 values), repaired variants, Spearman vs MAE_40/MFE_40  
**Evidence:**
- Original: 7 unique values (discrete: 0, 60, 70, 100 variants)
- All repair attempts: Spearman worsened or collapsed
- Root cause: binary underlying measurements cannot produce continuous score without additional signals
**Result:** All repair variants rejected. 7 unique values retained.  
**Confidence:** LOW (insufficient dataset)  
**Recommendation:** Do not repair until dataset >2000 signals. Deferred.  
**Status:** REJECTED  
**Files:** `discount_reversal_engine.py`, `CONSTITUTION_VERSION.md`

---

### CRL-R6-ANTIPRED — R6 Recovery Anti-Predictive Investigation

**Question:** Why does R6 produce anti-predictive results for MFE and MAE?  
**Station:** R6 Recovery  
**Dataset:** Constitutional walk-forward 2026-01-01 to 2026-06-21 (782 signals)  
**Method:** Spearman rank correlation R6 vs MFE_40, MAE_40; component analysis  
**Walk-Forward:** Yes  
**Variables:** r6_score, higher_low, recovery_pct, choch_bonus, bos_bonus  
**Evidence:**
- rho(R6, MFE_40) = -0.202*** (strongly anti-predictive)
- rho(R6, MAE_40) = -0.136*** (anti-predictive)
- Pattern: high R6 = early CHOCH/BOS = premature entry = worse outcomes
**Result:** Structural finding confirmed. Early recovery detection = premature entry signal.  
**Confidence:** MEDIUM (structural, well-evidenced)  
**Recommendation:** Redesign to weight LATER confirmation stages. Requires weight-change mandate.  
**Status:** VERIFIED  
**Files:** `discount_reversal_engine.py`, `CONSTITUTION_VERSION.md`

---

### CRL-R7-REPAIR — R7 MACD Phase Continuous Repair

**Question:** Can R7 be improved from 36 to continuous unique values without lookahead?  
**Station:** R7 MACD Phase  
**Dataset:** Constitutional walk-forward 2026-01-01 to 2026-06-21 (782 signals)  
**Method:** 4-term continuous scoring surface: location(45%) + curl/slope(35%) + recovery(20%) + overextension gate  
**Walk-Forward:** Yes  
**Variables:** r7_score (old 36 unique values → new 747)  
**Evidence:**
- Before: 36 unique values (effectively constant 65)
- After: 747 unique values (continuous)
- rho(R7, MAE_40) = +0.106** (improved direction)
- rho(R7, MFE_40) = +0.081* (weakly positive)
- No lookahead introduced — all computed from closes up to signal date
**Result:** R7 repair successful. Continuous MACD surface significantly more discriminating.  
**Confidence:** HIGH  
**Recommendation:** R7 frozen at V1.0 continuous surface.  
**Status:** VERIFIED  
**Files:** `discount_reversal_engine.py`, `CONSTITUTION_VERSION.md`

---

### CRL-R8-RANGE — R8 Volume Behaviour Limited Range

**Question:** Why does R8 only produce values 46-90 and show near-zero Spearman?  
**Station:** R8 Volume  
**Dataset:** Constitutional walk-forward 2026-01-01 to 2026-06-21 (782 signals)  
**Method:** Unique value count + Spearman vs all outcome metrics  
**Evidence:**
- Score range: 46-86 (40-point band instead of full 0-100)
- Spearman: near-zero on MAE_40, MFE_40, ret_40
- Root cause: baseline window may be too wide (excludes only 5 recent bars)
**Result:** R8 is a low-discrimination station with compressed range.  
**Confidence:** LOW  
**Recommendation:** Review R8 baseline window in future mandate. Low urgency.  
**Status:** VERIFIED  
**Files:** `discount_reversal_engine.py`, `CONSTITUTION_VERSION.md`

---

## Open Research Items (from gx_research_memory.json)

These 23 items exist in `gx_research_memory.json`. All currently in `?` state (metadata placeholder).  
Registered in `research/knowledge/knowledge_base.db → experiment_registry`.

| ID | Description | Status |
|----|------------|--------|
| RI-PRICE-INV | Price score inversion study | OPEN |
| RI-OB-HARM | Order block harmonics study | OPEN |
| RI-HTF-INV | Higher-timeframe inversion | OPEN |
| RI-DEM-PAR | Demand zone parametrics | OPEN |
| RI-LIQ-WICK | Liquidity wick study | OPEN |
| RI-DIV-RSI | RSI divergence research | OPEN |
| RI-MACD-REDUCE | MACD weight reduction study | OPEN |
| RI-AVWAP-REDUCE | AVWAP weight reduction study | OPEN |
| RI-GATE-LIQ20 | Liquidity gate at 20th percentile | OPEN |
| RI-GATE-SCORE | Score gate threshold optimization | OPEN |
| RI-OPT-REBAL | Optimization rebalancing | OPEN |
| RI-SWEEP-GATE | Sweep detection gate | OPEN |
| RI-HVN-CONF | HVN confirmation study | OPEN |
| RI-ARCH-ADDITIVE | Additive architecture study | OPEN |
| RI-HTF-FIX-IMPACT | HTF fix impact measurement | OPEN |
| RI-HVN-HTF-BONUS | HVN+HTF bonus interaction | OPEN |
| RI-RL-NEG-DISC | RL negative discriminator | OPEN |
| RI-WF-DRIFT | Walk-forward drift detection | OPEN |
| RI-MICRO-FEATURES | Micro feature study | OPEN |
| RI-QUANT-R2 | Quantitative R2 analysis | OPEN |
| RI-DIV-MACD | MACD divergence study | OPEN |
| RI-SYS-PROMOTE | System promotion criteria | OPEN |
| RI-SYS-WFSCOPE | Walk-forward scope definition | OPEN |

---

## New Experiment Template

```
### CRL-XXXX — Title

**Question:** [Specific falsifiable question]
**Station/Component:** [R1-R8, portfolio, system]
**Dataset:** [Source + date range + n_signals]
**Window:** [In-sample / out-of-sample / walk-forward split]
**Method:** [Statistical method]
**Walk-Forward:** [Yes/No]
**Variables:** [What is measured]
**Evidence:** [Data results]
**Result:** [Conclusion]
**Confidence:** [LOW / MEDIUM / HIGH]
**Recommendation:** [What to do next]
**Status:** [OPEN / INVESTIGATING / VERIFIED / REJECTED]
**Files:** [Related source files]
```

---

## Research Pipeline

```
New idea or observation
    ↓
Create experiment entry in EXPERIMENT_REGISTRY.md
    ↓
Run in research/experiments/ (never in production files)
    ↓
Walk-forward validation (same date range as constitutional baseline)
    ↓
Record evidence in knowledge_base.db
    ↓
Update status: VERIFIED / REJECTED
    ↓
If VERIFIED → write Recommendation
    ↓
If recommendation = production change:
    → Constitutional Amendment Proposal
    → AUTHORITY: FULL required
    → production_promoter.py only
```
