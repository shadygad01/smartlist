# GATE CONTRIBUTION REPORT

**Date**: 2026-06-17  
**Dataset**: 2025+ signals with r20d outcomes (n=321)

## Gate 1 — Discount Gate (cur < eq)

All logged signals passed this gate by definition — only signals where `cur < eq` enter
the full scoring path. Signals at/above EQ receive all-zero scores and are logged as Skip.

**Cannot be evaluated independently from this dataset** (no premium-zone signals logged).

## Gate 2 — Price Gate (r1_price >= PRICE_GATE)

Price gate threshold = `price_gate_frac_normal × W_PRICE = 0.55 × 7.69 = 4.23 pts`

This is extremely permissive — originally designed at 16/30 = 53% of W_PRICE but
after weight optimization W_PRICE dropped from 30 → 7.69, making the gate almost meaningless.

| price_ok | n | WR | Expectancy |
|---|---|---|---|
| 0 (Wait — fails gate) | 234 | 39.3% | +4.8% |
| 1 (Buy — passes gate) | 87 | 40.2% | +4.8% |

**Lift: +0.9pp WR**

Prior audit found WR(price_ok=0)=41% > WR(price_ok=1)=32% — this is NOW REVERSED in
current data (40.2% > 39.3%), suggesting the gate direction is correct but the threshold
is too loose. The gate needs `W_PRICE` restored to a higher value OR the fraction raised.

## Gate 3 — Score Gate (raw_score >= 35)

Since the DB only logs signals with raw >= 35, we analyze score quality by band:

| Band | n | WR | Expectancy | Premium |
|---|---|---|---|---|
| 40-49 (low) | 55 | 38.2% | +3.5% | baseline |
| 50-59 (mid) | 29 | 37.9% | +4.3% | +0.8% |
| 60-69 (good) | 103 | **40.8%** | **+5.5%** | **+2.0%** |
| 70-79 (strong) | 100 | 40.0% | +5.0% | +1.5% |
| 80+ (max) | 34 | 38.2% | +4.6% | +1.1% |

Score sweet spot: **60-69** band has highest WR and expectancy.

## Individual Gate Lift Summary

Computed as: WR when gate fires (score > 0) vs WR when gate does not fire

| Gate | Weight | ON WR | OFF WR | WR Lift | Signal (Alpha) |
|---|---|---|---|---|---|
| r7_div | 3 | 53.1% | 38.1% | **+15.1pp** | HIGH |
| r6_macd | 4 | 45.7% | 35.0% | **+10.7pp** | HIGH |
| r2_ob | 10 | 47.5% | 38.4% | **+9.1pp** | HIGH |
| r1_price | 7.69 | 42.3% | 37.0% | +5.3pp | MEDIUM |
| r4_htf | 0.70 | 41.2% | 38.4% | +2.8pp | LOW |
| r3_liquidity | 15.24 | 41.3% | 38.7% | +2.6pp | LOW |
| r5_avwap | 7.10 | 36.3% | 41.1% | **-4.8pp** | NEGATIVE |
| r8_demand | 29.36 | 39.8% | 39.4% | +0.4pp | MINIMAL |

## Critical Misalignment: Weights vs Alpha

Current production weights are **inversely correlated** with alpha lift:

- r8_demand has the HIGHEST weight (29.36) but LOWEST lift (+0.4pp)
- r7_div has the LOWEST weight (3) but HIGHEST lift (+15.1pp)
- r5_avwap has HIGH weight (7.10) but NEGATIVE lift

This represents a severe weight-alpha misalignment created by the optimizer.

## Recommendations

1. **Immediate**: Set `W_AVWAP=0` in weights.json (or disable AVWAP gate) — saves -4.8pp drag
2. **Short-term**: Increase `r7_div` weight significantly (3 → 10+)
3. **Short-term**: Increase `r6_macd` weight (4 → 12+)
4. **Short-term**: Increase `r2_ob` weight (10 → 15+)
5. **Medium-term**: Reduce `r8_demand` weight (29 → 10-15) — reallocate to high-alpha gates
6. **Restore** `W_PRICE` fraction: current gate at 4.2pts is too loose
