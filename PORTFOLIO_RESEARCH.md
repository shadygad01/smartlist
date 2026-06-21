# Portfolio Research Catalog

**CRL Version:** 1.0  
**Generated:** 2026-06-21  

---

## Active Portfolio State (2026-06-21)

**15 held positions** (equal weight ~6.7% each):

| Ticker | Sector | Return | R2 |
|--------|--------|--------|-----|
| HELI.CA | Real Estate | +95.3% | 82.7 |
| PHDC.CA | Real Estate | +77.9% | 79.2 |
| ORHD.CA | Real Estate | +51.7% | 78.9 |
| EMFD.CA | Real Estate | +37.5% | 77.5 |
| ARCC.CA | Industrial | +26.0% | 76.2 |
| RMDA.CA | Healthcare | +25.8% | 97.8 |
| JUFO.CA | Industrial | +13.2% | 85.6 |
| TMGH.CA | Real Estate | +12.2% | 89.0 |
| ORWE.CA | Industrial | +9.2% | 73.7 |
| GBCO.CA | Telecom | +6.9% | 93.9 |
| ISPH.CA | Healthcare | +5.4% | 95.1 |
| EAST.CA | Industrial | +5.0% | 95.7 |
| EFID.CA | Industrial | +4.2% | 86.2 |
| HRHO.CA | Industrial | +0.0% | 85.5 |
| BTFH.CA | FinTech | +0.0% | 89.7 |

**Engine avg return:** +26.7%  
**Manual avg return:** +30.8%  

---

## Sector Concentration Study

**Current sector allocation:**

| Sector | Weight | vs Cap (25%) | Status |
|--------|--------|-------------|--------|
| Industrial | 40.0% | +15.0pp | INHERITED BREACH |
| Real Estate | 33.3% | +8.3pp | INHERITED BREACH |
| Healthcare | 13.3% | — | WITHIN CAP |
| Telecom | 6.7% | — | WITHIN CAP |
| FinTech | 6.7% | — | WITHIN CAP |

**Policy:** Sector cap is 25%. Inherited breaches (pre-manager) are noted but not force-exited.  
The manager enforces the cap on ALL NEW ENTRIES. Natural turnover will reduce concentration.  
**Research recommendation:** Future entries should prioritize Telecom, Healthcare, FinTech.

---

## Correlation Study

**Method:** 60-day return correlation across all held pairs (351 pairs for 27 symbols).  
**Cap:** 0.80 pairwise  
**Current max:** 0.671 (WITHIN CAP)  

**Highest correlations among held positions:**

| Pair | Correlation | Sector | Risk |
|------|------------|--------|------|
| EMFD.CA / HRHO.CA | 0.671 | Real Estate / Industrial | Acceptable |
| ORHD.CA / HRHO.CA | 0.579 | Real Estate / Industrial | Acceptable |
| HRHO.CA / TMGH.CA | 0.581 | Industrial / Real Estate | Acceptable |
| RMDA.CA / ISPH.CA | 0.642 | Healthcare / Healthcare | Acceptable |
| JUFO.CA / GBCO.CA | 0.570 | Industrial / Telecom | Acceptable |

**Finding:** All 105 held pairs below 0.80 cap. Portfolio correlation is manageable.  
**Research question:** How does EGX-wide correlation behave during CBE rate cycle changes?  

---

## Equal Weight Study

**Current position weight:** 6.7% (15 positions)  
**Policy:** Equal weight  
**Research question:** Does equal-weight outperform R2-weighted in EGX discount-zone context?  
**Status:** OPEN (CRL experiment not yet run)  

**Expected direction:** Equal weight likely more robust for small-universe high-concentration markets.  
**Method:** Walk-forward comparison equal vs R2-proportional weighting on 782 signals.  

---

## Holding Period Study

**Available data:** `egx_research.db.tracking` (556 rows)  
**Forward return windows:** 5d, 10d, 20d, 90d, 120d, 180d, 252d  
**Current findings from backtest_report.json:**

| Metric | Value |
|--------|-------|
| Avg return (all signals) | +16.7% |
| Median return | +12.0% |
| Win rate (r20d-based) | 69.4% |
| Profit factor | 9.85 |

**Research question:** What is the optimal holding period for constitutional discount-zone entries?  
**Status:** OPEN — `extend_metrics.py` has computed 90d/120d/180d/252d columns  

---

## Allocator Experiments

### Constitutional Candidate Pool Allocator

**Script:** `candidate_pool_builder.py`  
**Method:** Scan all 27 symbols daily, emit one record per BUY-zone day  
**Key:** candidate_id = SHA-256(ticker|signal_date|entry_price) — immutable  
**Universe:** 2026-01-01 to 2026-06-21 = 811 candidates, 24/27 symbols  
**Append-only:** INSERT OR IGNORE — history never rewritten  

### Portfolio Manager State Machine

**Script:** `portfolio_manager.py`  
**States:** NEW → PRIMARY_BUY → BUY_RESERVE → WATCH → HELD → REDUCED → EXIT → ARCHIVED  
**Ranking:** R2 ONLY (final_score excluded — anti-predictive)  
**Sector gate:** 25% cap (enforced on new entries)  
**Correlation gate:** 0.80 pairwise  
**Capacity gate:** 12-15 positions  

**Current snapshot (2026-06-21):**
- 15 HELD (at capacity)
- 1 BUY_RESERVE: ABUK.CA (R2=75.1, blocked by Industrial cap)
- 8 WATCH: ETEL, MCQE, EGAL, OIH, EFIH, FWRY, COMI, CCAP

### Portfolio Advisor (Intelligence Layer)

**Script:** `portfolio_advisor.py`  
**Method:** Dual evaluation: Signal Quality ★ + Portfolio Fit ★ (never mixed)  
**Categories:** KEEP, KEEP_EVOLVED, HIGH_CONVICTION_BUY, BUY_WITH_AWARENESS, FUTURE_PRIORITY, WATCH  
**Health scale:** ★★★★★ Stable → ★☆☆☆☆ Review Recommended  

---

## Challenger System Research

**Scripts:** `challenger_scanner.py`, `challenger_eligibility_engine.py`, `challenger_expectancy_engine.py`, `challenger_allocation_engine.py`, `challenger_validation.py`  
**Method:** 3-layer shadow system running in parallel with production:
1. Layer 1: Binary discount gate (eligibility)
2. Layer 2: Ridge regression R2-R8 → expected MFE (expectancy)
3. Layer 3: Capital allocation grades A+/A/B/C/D

**Output:** `challenger_validation_report.json`, `egx_research.db.challenger_results`  
**Status:** Shadow testing — not yet promoted  

---

## Diversification Studies

### Sector Diversification

**Goal:** Reduce Industrial from 40% → 25%, Real Estate from 33% → 25%  
**Method:** Natural turnover — exits in overweight sectors, entries in underweight sectors  
**Timeline:** 3-6 exit cycles estimated  
**No forced exits required**  

### Banking / Under-Represented Sectors

**Candidates:** EGAL.CA (Banking, R2=53.2), COMI.CA (Banking, R2=48.6)  
**Gap:** Banking currently 0% in held portfolio  
**Watch status:** Both on watchlist; R2 below 60 threshold for immediate entry  

---

## Portfolio Research Roadmap (Open)

| Research Question | Status | Priority |
|------------------|--------|---------|
| Equal weight vs R2-proportional | OPEN | MEDIUM |
| Optimal holding period (multi-period) | OPEN | MEDIUM |
| Sector rotation impact on BQ scores | OPEN | LOW |
| CBE rate cycle correlation effect | OPEN | LOW |
| Challenger system promotion readiness | OPEN | HIGH |
| Banking sector entry timing | OPEN | MEDIUM |
| ABUK.CA entry on Industrial exit | OPEN | HIGH |
