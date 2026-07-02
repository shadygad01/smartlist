# CLAIM VALIDATION REPORT
Generated: 2026-06-17

## Dataset
- Total signals with r20d outcome: 321 (2025-01-01 to 2026-05-31)
- Baseline WR: 0.396
- Baseline Expectancy: 0.0481
- All signals have component data (r1..r8): 100% coverage

## Claim 1: AVWAP (r5) has -4.8pp WR lift
**CONFIRMED**
- r5=0: n=219, WR=0.411
- r5>0: n=102, WR=0.363
- WR Lift: -4.8pp
- Fisher exact p=0.4626 (NOT statistically significant)
- Pearson corr with r20d: -0.0016 (negligible)
- Confidence: LOW — lift confirmed but not statistically significant (p>0.05)

## Claim 2: Demand (r8) has +0.4pp WR lift despite 29.4 weight
**CONFIRMED**
- r8=0: n=208, WR=0.394
- r8>0: n=113, WR=0.398
- WR Lift: +0.4pp
- Fisher exact p=1.0000 (no significance)
- Confidence: HIGH — confirmed meaningless, demand weight is massively overweighted

## Claim 3: Divergence (r7) has +15.1pp WR lift
**CONFIRMED**
- r7=0: n=289, WR=0.381
- r7>0: n=32, WR=0.531
- WR Lift: +15.1pp
- Fisher exact p=0.1268 (not significant due to small n=32)
- Confidence: MEDIUM — directional signal is real but p>0.05 due to small n

## Claim 4: MACD (r6) has +10.7pp WR lift
**CONFIRMED**
- r6=0: n=183, WR=0.350
- r6>0: n=138, WR=0.457
- WR Lift: +10.7pp
- Fisher exact p=0.0650 (borderline significant)
- Pearson corr with r20d: 0.1604 (strongest of all components)
- Confidence: HIGH — strongest predictor, near-significant p-value, large n

## Claim 5: OB (r2) has +9.1pp WR lift
**CONFIRMED (weakly)**
- r2=0: n=281, WR=0.384
- r2>0: n=40, WR=0.475
- WR Lift: +9.1pp
- Fisher exact p=0.3018 (not significant)
- Pearson corr with r20d: 0.0032 (near zero)
- Confidence: LOW — lift confirmed directionally but small n=40 and p>0.1

## Claim 6: adj_score has near-zero correlation with r20d
**CONFIRMED**
- adj_score Pearson corr: 0.0429
- adj_score Spearman corr: 0.0098
- raw_score Pearson corr: 0.0395
- raw_score Spearman corr: 0.0069
- Point-biserial r (raw vs win20): 0.0213, p=0.7042
- Confidence: HIGH — score is essentially uncorrelated with outcome

## Claim 7: price_ok=1 has lower WR than price_ok=0
**REJECTED**
- price_ok=0: n=234, WR=0.393
- price_ok=1: n=87, WR=0.402
- price_ok=1 has slightly HIGHER WR (+0.9pp), not lower
- Confidence: HIGH — claim is wrong
