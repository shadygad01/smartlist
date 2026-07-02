# WORLD_COMPARISON_REPORT
*Generated: 2026-06-17 | Authority Mode Production Audit*

---

## Data Inventory

- **Dataset**: 2026-01-01 to 2026-06-14 BUY signals
- **Total BUY signals**: 220 (217 Strong Buy, 3 Buy)
- **With r20d outcomes**: 218 (99.1%)
- **Win threshold**: r20d > 7%
- **stock_mult / ctx_mult**: NULL for 208/220 signals (Jan–May 2026); populated only for 12/220 (June 2026). All June signals have no r20d outcomes yet.
- **Component data (r1..r8)**: Populated for 71/220 signals (June only, no outcomes)

**Critical limitation**: Because stock_mult and ctx_mult are NULL for all 218 signals with r20d outcomes, Worlds A/E/F are mathematically identical. Worlds B/C/D cannot be computed from current DB state (component columns show data integrity failure — stored values mismatched with raw_score for 99%+ of rows). World G (pattern filter) is uncomputable (pattern_score=NULL for 218/220 rows).

---

## World Definitions

| World | Description |
|---|---|
| A | Current system: adj_score with stock_mult × ctx_mult, current weights |
| B | Original weights (W_PRICE=30, W_OB=10, W_LIQ=20, W_HTF=10, W_AVWAP=8, W_MACD=4, W_DIV=3, W_DZ=15), stock_mult=1.0 |
| C | Optimized weights (current config), stock_mult from ranking |
| D | Pure SMC: raw_score only, no multipliers, original weights |
| E | SMC + ranking: raw_score × stock_mult only (no ctx_mult) |
| F | SMC + ranking + ctx: adj_score, current weights |
| G | adj_score + pattern filter (signals with pattern_score > threshold only) |

---

## World Comparison Results

| World | n_triggered | n_outcomes | WR (>7%) | Avg R20 | Avg Win | Avg Loss | Expectancy |
|---|---|---|---|---|---|---|---|
| **A** (current) | 220 | 218 | 40.83% | 5.27% | 18.07% | -3.56% | **5.27%** |
| **B** (original weights) | N/A¹ | N/A | N/A | N/A | N/A | N/A | N/A |
| **C** (current weights + mult) | N/A¹ | N/A | N/A | N/A | N/A | N/A | N/A |
| **D** (pure SMC) | N/A¹ | N/A | N/A | N/A | N/A | N/A | N/A |
| **E** (SMC + stock_mult) | 217 | 217 | 41.01% | 5.28% | 18.07% | -3.61% | **5.28%** |
| **F** (adj_score, current) | 217 | 217 | 41.01% | 5.28% | 18.07% | -3.61% | **5.28%** |
| **G** (+ pattern filter) | N/A² | N/A | N/A | N/A | N/A | N/A | N/A |

¹ Cannot compute: component data unavailable for signals with r20d outcomes  
² Cannot compute: pattern_score=NULL for all signals with r20d outcomes

**Finding: Worlds A, E, F are identical in practice** because stock_mult=ctx_mult=1.0 for all evaluated signals. The entire multiplier/research system (ranking_engine → stock_mult) was not operational for Jan–May 2026 production signals.

---

## Alternative World Analysis: Score Gate Thresholds

Since Worlds B–G cannot be computed from available data, the most informative counterfactual is varying the adj_score gate:

| Gate | n_triggered | n_outcomes | WR | Avg R20 | Expectancy | Δ vs A |
|---|---|---|---|---|---|---|
| adj >= 35 (All) | 220 | 218 | 40.83% | 5.27% | 5.27% | Baseline |
| adj >= 55 (current) | 217 | 217 | 41.01% | 5.28% | 5.28% | +0.01% |
| adj >= 65 | 216 | 216 | 40.74% | 5.22% | 5.22% | -0.05% |
| adj >= 70 | 125 | 125 | 39.20% | 4.89% | 4.89% | -0.38% |
| adj >= 75 | 65 | 65 | 38.46% | 5.09% | 5.09% | -0.18% |
| adj >= 80 | 31 | 31 | 38.71% | 4.34% | 4.34% | -0.93% |
| adj >= 85 | 20 | 20 | **45.00%** | **7.60%** | **7.60%** | **+2.33%** |
| adj >= 90 | 3 | 3 | 33.33% | 0.42% | 0.42% | -4.85% |

**Best gate: adj >= 85** gives WR=45%, expectancy=7.60% — but only 20 signals total (9.1% of current volume). Filtering to IB-tier would reduce signal count by 91%.

---

## adj_score Quintile Performance

| Quintile | adj Range | n | WR >7% | Avg R20 | Rank |
|---|---|---|---|---|---|
| Q1 (lowest) | 47–66 | 43 | **51.2%** | **+8.7%** | #1 |
| Q2 | 66–68 | 43 | 39.5% | +3.0% | #4 |
| Q3 | 68–72 | 43 | 41.9% | +5.5% | #3 |
| Q4 | 72–78 | 43 | 34.9% | +4.3% | #5 |
| Q5 (highest) | 78–95 | 46 | 43.5% | +5.9% | #2 |

**Inverting finding**: Q1 (lowest scores 47–66) has the best WR (51.2%) and best avg r20d (+8.7%). Q4 (second highest scores 72–78) is the worst. Score is an unreliable ranking signal — it predicts volume of the setup, not forward returns.

---

## Monthly Regime Analysis (Best Counterfactual for Timing)

| Month | n | WR >7% | Avg R20 | n Skip | WR if skipped |
|---|---|---|---|---|---|
| 2026-01 | 2 | 50.0% | +10.9% | — | — |
| **2026-02** | **63** | **19.1%** | **-2.6%** | 63 | +6.0% theoretical |
| 2026-03 | 38 | 55.3% | +9.0% | — | — |
| 2026-04 | 76 | 61.8% | +11.7% | — | — |
| **2026-05** | **39** | **20.5%** | **+1.6%** | 39 | +5.1% theoretical |
| 2026-06 | 2 | — | — | — | — |

**Best counterfactual World**: "Skip February and May entirely." A regime filter that skips signals in bearish market months (EGX30 in downtrend) would avoid 102 signals (46.4%) with 19-20% WR, improving overall WR from 40.8% to approximately 58%. This is the highest-impact single improvement available in the data.

---

## SMC RL Optimizer Weights vs Current (Counterfactual)

The smc_rl_optimizer computed these weights (2026-06-13, n=395, loss=0.238):

| Component | RL Optimal | Current Config | Direction |
|---|---|---|---|
| r1_price | 30.6 | 7.7 | Current 75% lower |
| r8_demand | 15.1 | 29.4 | Current 95% higher |
| r4_htf | 9.6 | 0.7 | Current 93% lower |
| r6_macd | 1.1 | 14.9 | Current 1,254% higher |

If RL weights were promoted (they are not), using W_PRICE=30.6 would raise the price gate from ~4.2 to ~16.8, significantly reducing signals passing price_ok — likely reducing signal volume by 60%+ but potentially increasing quality.

**The RL optimizer indicates the current config/weights.json overweights DZ and MACD vs what the data supports.**

---

## Summary

| Dimension | Finding | Confidence |
|---|---|---|
| World A vs E/F | Identical — multipliers non-operational | HIGH |
| Worlds B/C/D | Uncomputable from DB | HIGH |
| World G (pattern) | Uncomputable from DB | HIGH |
| Best available world | "Regime filter" (skip EGX30 downtrend months) | MEDIUM |
| Score gate optimization | adj >= 85 best Sharpe, loses 91% volume | MEDIUM |
| RL weights vs current | RL favors original weights; current config diverges | HIGH |
