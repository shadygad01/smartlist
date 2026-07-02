# FEATURE IMPORTANCE REPORT
Generated: 2026-06-17

## Dataset: 321 signals with r20d outcomes (2025-2026)

## Method 1: WR Lift (r_i=0 vs r_i>0)
| Component  | n(0) | WR(0) | n(>0) | WR(>0) | Lift   | Cohen_d | Fisher_p |
|------------|------|-------|-------|--------|--------|---------|----------|
| Price (r1) |  165 | 0.370 |   156 |  0.423 | +5.3pp |   0.157 |   0.3616 |
| OB (r2)    |  281 | 0.384 |    40 |  0.475 | +9.1pp |   0.023 |   0.3018 |
| Liq (r3)   |  212 | 0.387 |   109 |  0.413 | +2.6pp |   0.094 |   0.7179 |
| HTF (r4)   |  190 | 0.384 |   131 |  0.412 | +2.8pp |   0.133 |   0.6433 |
| AVWAP (r5) |  219 | 0.411 |   102 |  0.363 | -4.8pp |   0.004 |   0.4626 |
| MACD (r6)  |  183 | 0.350 |   138 |  0.457 |+10.7pp |   0.273 |   0.0650 |
| DIV (r7)   |  289 | 0.381 |    32 |  0.531 |+15.1pp |   0.165 |   0.1268 |
| Demand (r8)|  208 | 0.394 |   113 |  0.398 | +0.4pp |   0.095 |   1.0000 |

**RANKING by WR Lift**: DIV > MACD > OB > Price > HTF > Liq > Demand > AVWAP (negative)

## Method 2: Pearson + Spearman Correlation with r20d
| Component  | Pearson | Spearman |
|------------|---------|----------|
| MACD (r6)  |  0.1604 |   0.1615 |
| Liq (r3)   |  0.0592 |   0.0636 |
| DIV (r7)   |  0.0538 |   0.0644 |
| Demand (r8)|  0.0414 |   0.0347 |
| HTF (r4)   |  0.0199 |   0.0295 |
| OB (r2)    |  0.0032 |   0.0258 |
| Price (r1) |  0.0105 |   0.0489 |
| AVWAP (r5) | -0.0016 |   0.0270 |

**RANKING by correlation**: MACD >> Liq > DIV > Demand > HTF > Price > OB > AVWAP

## Method 3: Information Value (IV)
| Component  |    IV   | Strength  |
|------------|---------|-----------|
| MACD (r6)  | 0.0488  | Weak      |
| Price (r1) | 0.0445  | Weak      |
| DIV (r7)   | 0.0346  | Weak      |
| OB (r2)    | 0.0193  | Very Weak |
| HTF (r4)   | 0.0152  | Very Weak |
| AVWAP (r5) | 0.0091  | Very Weak |
| Liq (r3)   | 0.0043  | Very Weak |
| Demand (r8)| 0.0011  | None      |

## Method 4: WR by raw_score Band
| Band   |   n | WR    | Mean_r20d |
|--------|-----|-------|-----------|
| 35-44  |  27 | 0.407 |   0.0551  |
| 45-54  |  45 | 0.378 |   0.0290  |
| 55-64  |  20 | 0.250 |   0.0314  |
| 65-74  | 159 | 0.421 |   0.0526  |
| 75-84  |  49 | 0.347 |   0.0408  |
| 85+    |  21 | 0.476 |   0.0793  |
**Note**: No monotonic relationship. Score is NOT a reliable signal filter.

## Method 5: Random Forest Permutation Importance
| Component  | Perm_Imp |
|------------|----------|
| MACD (r6)  |   0.1028 |
| AVWAP (r5) |   0.0533 |
| OB (r2)    |   0.0318 |
| HTF (r4)   |   0.0178 |
| Price (r1) |   0.0156 |
| DIV (r7)   |   0.0142 |
| Liq (r3)   |   0.0061 |
| Demand (r8)|   0.0020 |

## Consensus Feature Ranking
1. **MACD (r6)**: Strongest predictor across ALL methods. Current weight 14.87% — appropriate.
2. **DIV (r7)**: High WR lift (+15pp) but small n=32. Current weight 10.58% — reasonable.
3. **Price (r1)**: Moderate lift. Current weight 7.69% — underweighted vs RF importance.
4. **OB (r2)**: Good lift but low n. Current weight 14.47% — possibly overweighted.
5. **HTF (r4)**: Weak but positive. Current weight 0.70% — severely underweighted.
6. **Liq (r3)**: Weak lift. Current weight 15.24% — overweighted.
7. **Demand (r8)**: Negligible lift (+0.4pp). Current weight 29.36% — SEVERELY overweighted.
8. **AVWAP (r5)**: NEGATIVE lift (-4.8pp). Current weight 7.10% — should be reduced.

## Critical Imbalance: Demand (r8) weight=29.36% but IV=0.0011 (essentially zero predictive power)
