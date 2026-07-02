# WEIGHT REBALANCING REPORT
Generated: 2026-06-17

## Current Production Weights
| Component  | Current Weight |
|------------|---------------|
| r1_price   |          7.69% |
| r2_ob      |         14.47% |
| r3_liquidity|        15.24% |
| r4_htf     |          0.70% |
| r5_avwap   |          7.10% |
| r6_macd    |         14.87% |
| r7_div     |         10.58% |
| r8_demand  |         29.36% |

## Candidate Weight Sets

### Conservative (AVWAP -50%, MACD +25%, DIV +50%)
| Component  | Weight |
|------------|--------|
| r1_price   |  7.29% |
| r2_ob      | 13.72% |
| r3_liquidity| 14.46% |
| r4_htf     |  0.66% |
| r5_avwap   |  3.37% |
| r6_macd    | 17.62% |
| r7_div     | 15.04% |
| r8_demand  | 27.84% |

### Balanced (AVWAP=0, boost PRICE+MACD+DIV, reduce DEMAND)
| Component  | Weight |
|------------|--------|
| r1_price   | 22.22% |
| r2_ob      | 16.67% |
| r3_liquidity| 16.67% |
| r4_htf     |  5.56% |
| r5_avwap   |  0.00% |
| r6_macd    | 11.11% |
| r7_div     | 11.11% |
| r8_demand  | 16.67% |

### Aggressive RL (from smc_rl_weights.json)
| Component  | Weight | RL Note |
|------------|--------|---------|
| r1_price   | 34.70% | Heavy price emphasis |
| r2_ob      | 10.88% | |
| r3_liquidity| 16.97% | |
| r4_htf     | 10.91% | HTF boosted vs production |
| r5_avwap   |  4.64% | Reduced but not zero |
| r6_macd    |  1.22% | SEVERELY reduced (vs production 14.87%) |
| r7_div     |  3.53% | Reduced (vs production 10.58%) |
| r8_demand  | 17.15% | Reduced (vs production 29.36%) |

## In-Sample Simulation (gate=35 on normalized score)
| Name          | n   | WR    | Exp    | dWR    | dExp   |
|---------------|-----|-------|--------|--------|--------|
| Current       |  96 | 0.396 | 0.0537 | ---    | ---    |
| Conservative  |  91 | 0.396 | 0.0567 | -0.000 | +0.003 |
| Balanced      | 100 | 0.390 | 0.0550 | -0.006 | +0.001 |
| Aggressive_RL | 117 | 0.402 | 0.0531 | +0.006 | -0.001 |

## Walk-Forward Validation Results

### Current (baseline)
- Split 1: FAIL (d=-0.053)
- Split 2: FAIL (d=-0.015)  
- Split 3: PASS (d=+0.110)
- Split 4: PASS (d=+0.089)
- Result: 2/4 improvements

### Conservative
- Split 1: FAIL (d=-0.053)
- Split 2: FAIL (d=-0.012)
- Split 3: PASS (d=+0.128)
- Split 4: PASS (d=+0.089)
- Result: 2/4 improvements (same as current)

### Balanced
- Split 1: FAIL (d=-0.038)
- Split 2: FAIL (d=-0.026)
- Split 3: PASS (d=+0.147)
- Split 4: PASS (d=+0.083)
- Result: 2/4 improvements (same as current)

### Aggressive RL
- Split 1: FAIL (d=+0.000, borderline)
- Split 2: FAIL (d=-0.012)
- Split 3: PASS (d=+0.124)
- Split 4: PASS (d=+0.080)
- Result: 2/4 improvements (same as current)

## Critical Observation
All weight sets — including current — show the same 2/4 pattern:
- **2025 H2 periods consistently fail** regardless of weights
- **2026 periods consistently pass** regardless of weights
This means **the signal is driven by market regime, not component weights**.

## Conclusion
**WEIGHT CHANGES REJECTED — Walk-forward validation shows no weight set outperforms current**

- No candidate set consistently outperforms current in 3+ of 4 test periods
- The 2025 H2 failures are regime-driven (bear/volatile market), not weight-driven
- Aggressive RL reduces MACD weight to 1.22% — contradicts feature importance (MACD is #1 predictor)
- In-sample improvements are negligible (max +0.3% expectancy) and do not generalize

## Recommendation
- Keep current weights unchanged
- The regime filter (already enabled in gates_config.json) is the more appropriate lever
- If DEMAND weight reduction is pursued in future, require 3+ consecutive improving periods first
