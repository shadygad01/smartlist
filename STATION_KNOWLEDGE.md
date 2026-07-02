# Station Knowledge Catalog

**Source:** Constitutional walk-forward (2026-01-01 to 2026-06-21, 782 signals, 23/27 symbols)  
**Method:** Spearman rank correlation (no lookahead, point-in-time)  
**Status:** All findings FROZEN in `CONSTITUTION_VERSION.md`  

---

## Station Performance Summary

| Station | Description | Weight | Spearman vs MAE_40 | Spearman vs MFE_40 | Verdict |
|---------|------------|--------|-------------------|-------------------|---------|
| R1 | Discount Context (Hard Gate) | Gate only | — | — | GATE |
| R2 | Discount Quality | 15% | **+0.286***  STRONGEST** | — | BEST PREDICTOR |
| R3 | Discount Residency | 10% | +0.243*** | — | POSITIVE |
| R4 | Base Formation | 30% | +0.157*** | — | POSITIVE |
| R5 | Low Protection | 20% | (worsens on repair) | -0.174*** | ANTI-PREDICTIVE (MFE) |
| R6 | Recovery | 15% | -0.136*** | -0.202*** | ANTI-PREDICTIVE |
| R7 | MACD Phase | multiplier | +0.106** | +0.081* | POSITIVE |
| R8 | Volume Behaviour | 10% | ~0 | ~0 | NEUTRAL |
| FINAL | compute_final_score() | — | +0.137*** | -0.049 neutral | GOOD (MAE) / NEUTRAL (MFE) |

---

## R1 — Discount Context (Hard Gate)

**Status:** FROZEN  
**Rule:** `close >= eq` → REJECT immediately (return None)  
**Score range:** 60–100 (inside discount), 30–60 (emerging), 0 (premium/extended)  
**R1 multiplier:** `r1_mult = 1.0 + (r1 - 60) / 400`  
**Ranking contribution:** ZERO — gate only  
**Key insight:** The EQ level (50th percentile of 80-bar range) is the constitutional boundary.  

**Known defects:** None  
**Known open research:** None  

---

## R2 — Discount Quality

**Status:** FROZEN  
**Measures:** Proximity to bottom (50 pts) + discount depth (30 pts) + upside to EQ (20 pts)  
**Score range:** 0–100  
**Spearman vs MAE_40:** +0.286*** (STRONGEST entry-quality predictor)  
**Portfolio ranking:** R2 is the ONLY station used for portfolio ranking.  
**Key insight:** Higher R2 = better entry in the discount zone = less adverse excursion.  
`final_score` is anti-predictive for MFE (rho=-0.087). NEVER use final_score for ranking.  

**Known defects:** None  
**CRL experiments:** CRL-R2-RANKING (VERIFIED — R2 confirmed primary ranking station)  

---

## R3 — Discount Residency

**Status:** FROZEN  
**Measures:** Consecutive bars below EQ (sweet spot: 5–30 bars → 100 pts)  
**Score range:** 0–100 (49 unique values, day-count based)  
**Spearman vs MAE_40:** +0.243***  
**Key insight:** 5-30 bars below EQ is optimal. Too fresh (<5 bars) or too stale (>30 bars) score lower.  

**Known defects:** None  
**CRL experiments:** None active  

---

## R4 — Base Formation (Highest Weight)

**Status:** FROZEN  
**Measures:** Adaptive 20/40/60-bar range compression + ATR compression + base duration  
**Lookback:** Selects window with strongest compression from {20, 40, 60}  
**Duration:** Anchored to detected base mid-price band (±7%), not current close  
**Score range:** 0–100  
**Spearman vs MAE_40:** +0.157***  
**Weight:** 30% (highest in formula)  

**Known defects:** None  
**CRL experiments:** None active  

---

## R5 — Low Protection

**Status:** FROZEN — KNOWN DEFECT, DEFERRED  
**Measures:** `no_new_low` (20-bar split) + `failed_breakdown` (vs 20-bar ATL)  
**Score range:** {0, 60, 70, 100} — 7 discrete values (binary limitation)  
**Spearman vs MFE_40:** -0.174*** (ANTI-PREDICTIVE)  
**Weight:** 20%  

**Known defects (D1-D5):** All documented. All repair attempts worsened Spearman.  
**Decision:** Collapse to fewer discrete values; repair attempts failed.  
**CRL experiment:** CRL-R5-BINARY (REJECTED — repair worsened all metrics)  
**Status:** Deferred until larger dataset (>2000 signals) available.  
**Rule:** NO REDESIGN until new mandate permits.  

---

## R6 — Recovery

**Status:** FROZEN — KNOWN ANTI-PREDICTIVE, DEFERRED  
**Measures:** Pivot-based `higher_low` (0/25/45 pts) + adaptive `recovery_pct` + CHOCH/BOS bonus  
**Helpers:** `_find_pivot_lows(context=3)`, `_detect_choch()`, `_detect_bos()`  
**Score range:** 0–100  
**Spearman vs MFE_40:** -0.202*** (ANTI-PREDICTIVE)  
**Spearman vs MAE_40:** -0.136*** (ANTI-PREDICTIVE)  
**Root cause:** Early recovery detection correlates with premature entry.  
**Weight:** 15%  

**CRL experiment:** CRL-R6-ANTIPRED (VERIFIED)  
**Conclusion:** R6 structurally misaligned. Early CHOCH/BOS = premature entry, not confirmation.  
**Recommendation:** Redesign to weight LATER confirmation. Requires weight-change mandate.  
**Rule:** NO REDESIGN until mandate permits.  

---

## R7 — MACD Phase

**Status:** FROZEN V1.0 (repaired from 36 → 747 unique values)  
**Measures:** Continuous surface: location (45%) + curl/slope (35%) + recovery magnitude (20%)  
**Overextension gate:** Built in  
**MACD params:** EMA(12)/EMA(26), signal EMA(9), slope over 5 bars  
**Score range:** 0–100 (continuous, 747 unique values)  
**Spearman vs MAE_40:** +0.106**  
**Spearman vs MFE_40:** +0.081*  
**Spearman vs low_break:** -0.089* (anti-predictive for breakdown)  
**Acts as:** Multiplier, not additive: `r7 < 20 → ×0.50`, `r7 < 40 → ×0.75`  

**CRL experiment:** CRL-R7-REPAIR (VERIFIED — repair successful)  
**History:** Was 36 unique values (constant 65) → now 747 continuous values.  
**Lookahead:** None — all computed from closes up to signal date.  

---

## R8 — Volume Behaviour

**Status:** FROZEN — KNOWN LIMITED RANGE  
**Measures:** Dry-up via `recent_5/baseline` + expansion via `last_3/baseline`  
**Baseline:** Excludes recent 5 bars  
**Score range:** 46–90 (continuous, limited discrimination)  
**Spearman:** Near-zero on all metrics  
**Weight:** 10%  

**CRL experiment:** CRL-R8-RANGE (VERIFIED)  
**Conclusion:** R8 baseline window may be too wide. Low signal/noise.  
**Recommendation:** Review baseline window in future mandate. Low urgency.  
**Rule:** NO REDESIGN until mandate permits.  

---

## Historical Research Found in Repository

### egx_research.db — pattern_knowledge_base (261 rows)
Pattern combinations discovered by `pattern_kb.py` with MFE40-based validation.

### egx_research.db — fib_outcomes (431 rows)
Fibonacci extension outcome tracking for signals.

### egx_research.db — early_buy_research (53 rows)
Shadow tracking of EARLY BUY signals (not yet in production path).

### reports/ research documents
- `AVWAP_AUDIT.md` — AVWAP station audit
- `AVWAP_DECISION.md` — AVWAP decision
- `ENTRY_ENGINE_MAP.md` — Entry signal map
- `FEATURE_IMPORTANCE_REPORT.md` — Feature importance findings
- `GATE_CONTRIBUTION_REPORT.md` — Gate contribution analysis
- `REGIME_FILTER_REPORT.md` — Regime filter research
- `WEIGHT_IMPACT_REPORT.md` — Weight impact studies
- `FINAL_ALPHA_REPORT.md` — Final alpha study
- Full list: see `RESEARCH_MAP.md`

---

## Station Research Pipeline (CRL)

```
Observed station behaviour
    ↓
CRL Experiment (research/stations/)
    ↓
Walk-Forward (2026-01-01 to 2026-06-21 baseline)
    ↓
Spearman rho evidence
    ↓
knowledge_base.db → station_knowledge table
    ↓
Constitutional Amendment Proposal
    ↓
AUTHORITY: FULL mandate required
    ↓
Production (only via production_promoter.py)
```
