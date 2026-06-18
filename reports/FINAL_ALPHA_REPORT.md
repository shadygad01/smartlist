# FINAL ALPHA REPORT — EGX TRADING SCANNER
Generated: 2026-06-17
Mission: Full alpha optimization and production hardening

---

## EXECUTIVE SUMMARY

**No production changes were applied.** Walk-forward validation consistently failed to find
any weight or threshold change that improves out-of-sample expectancy in 2+ consecutive periods.
System performance is regime-driven, not configuration-driven.

---

## Q1: Is the current scoring system reliable?
**NO.** raw_score has near-zero correlation with r20d (Pearson r=0.039, Spearman r=0.007,
point-biserial p=0.70). The score predicts outcomes no better than random chance. Score bands
show no monotonic relationship with win rate (55-64 band: WR=0.250 vs 85+ band: WR=0.476).

## Q2: Which components actually predict 20-day returns?
**Ranking by evidence strength:**
1. MACD (r6): WR lift +10.7pp, Pearson r=0.160, Fisher p=0.065, IV=0.049 — STRONGEST
2. Divergence (r7): WR lift +15.1pp (best lift but n=32 only), IV=0.035
3. Price Zone (r1): WR lift +5.3pp, IV=0.044
4. OB (r2): WR lift +9.1pp but n=40 only
5. HTF (r4): WR lift +2.8pp, IV=0.015
6. Liquidity (r3): WR lift +2.6pp, IV=0.004
7. Demand (r8): WR lift +0.4pp, IV=0.001 — WEAKEST positive
8. AVWAP (r5): WR lift -4.8pp — ONLY NEGATIVE PREDICTOR

## Q3: Is AVWAP hurting performance?
**POSSIBLY, but NOT statistically significant (p=0.46).** The formula is correct (not backwards).
The negative lift (-4.8pp) is real in the data but Fisher exact p=0.46 means we cannot reject
the null hypothesis. n=219 and n=102 both exceed the 30-signal threshold. Recommend monitoring
but not changing weights at this time.

## Q4: Is Demand (r8) overweighted at 29.4%?
**YES, severely.** Demand has IV=0.001 (essentially zero) and WR lift=+0.4pp, yet carries
29.36% of the total weight — the largest weight of any component. MACD (strongest predictor)
carries only 14.87%. This imbalance is well-documented but walk-forward fails to confirm
that rebalancing improves out-of-sample performance. The regime effect dominates.

## Q5: Should score threshold be raised?
**NO.** Walk-forward validation shows threshold optimization is pure overfitting. The optimal
threshold jumps from 55 to 60 to 25 across consecutive periods. Raising the gate consistently
reduces test-period expectancy in 3 of 4 walk-forward splits.

## Q6: Do the 7 previous claims hold up?
| Claim | Result |
|-------|--------|
| AVWAP -4.8pp lift | CONFIRMED |
| Demand +0.4pp lift | CONFIRMED |
| Divergence +15.1pp lift | CONFIRMED |
| MACD +10.7pp lift | CONFIRMED |
| OB +9.1pp lift | CONFIRMED |
| adj_score near-zero corr | CONFIRMED |
| price_ok=1 lower WR | REJECTED (price_ok=1 is higher at +0.9pp) |

## Q7: Should RL weights be promoted?
**NO.** Zero rl_score data in the database — cannot validate. RL weights reduce MACD from
14.87% to 1.22%, contradicting the empirical finding that MACD is the strongest predictor.
RL was trained in-sample without walk-forward validation. Do not promote.

## Q8: What is the dominant performance driver?
**Market regime.** All weight sets show identical 2/4 improvement pattern:
- 2025 H2 fails (bear/volatile EGX market) regardless of weights/thresholds
- 2026 H1 passes (trending EGX market) regardless of weights/thresholds
The existing regime_filter_enabled=true in gates_config.json is the correct mechanism.

## Q9: What is the actual system expectancy?
- Overall (n=321): WR=39.6%, AvgWin=+16.9%, AvgLoss=-3.1%, Expectancy=4.81%/20d
- 2025 (n=99): WR=35.4%, Expectancy=3.56%/20d
- 2026 (n=222): WR=41.4%, Expectancy=5.37%/20d

## Q10: What changes are production-ready?
**NONE.** No change survived the full walk-forward validation criteria.

## Q11: What should be done next?
Priority actions ranked by expected impact:
1. **Enable rl_score logging** in production to collect data for future RL shadow evaluation
2. **Monitor MACD signal frequency** — it's the best predictor but appears in only 43% of signals
3. **Demand weight reduction pilot**: Run 6 months shadow mode with balanced weights; re-evaluate
4. **Regime filter tuning**: The regime filter already exists — validate its actual effectiveness
5. **Sample size growth**: With only 321 signals (and 99 in 2025), statistical power is limited.
   Results will improve as more outcome data accumulates.

---

## DATA QUALITY NOTES
- 321 signals have r20d outcomes (Jun 2026 excluded — outcomes not yet available)
- All signals have component data (r1..r8): 100% coverage
- Score range: 40-95 (pre-filtered; sub-40 signals not in DB)
- No rl_score data available

## CONFIDENCE LEVELS
- MACD is top predictor: HIGH (multiple methods agree, borderline p=0.065)
- Demand is overweighted: HIGH (IV≈0, WR lift≈0)
- Weight changes improve outcome: LOW (walk-forward: 2/4 for all candidates)
- AVWAP formula is correct: HIGH (code review confirmed)
- Score is not predictive: HIGH (p=0.70, multiple correlation methods)
