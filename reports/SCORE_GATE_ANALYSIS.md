# SCORE GATE ANALYSIS

**Date**: 2026-06-17  
**Dataset**: 2025-01-01+ signals with r20d outcomes (n=321)

## Signal Type Distribution

| Signal Type | n | WR | Avg R20d |
|---|---|---|---|
| Strong Buy | 334 | 40.1% | +5.1% |
| Buy | 123 | 39.8% | +5.1% |
| Early Buy | 169 | 33.7% | +3.0% |
| Very Strong Buy | 19 | 31.6% | +3.2% |
| Institutional Buy | 1 | 100% | +14.5% |

Note: "Very Strong Buy" (adj_score 70+) paradoxically underperforms "Strong Buy" (55-69).
This suggests over-adjustment by ctx_mult in some stocks.

## Raw Score Gate Bands

| Band | n | WR | Expectancy |
|---|---|---|---|
| 35-39 | 0* | - | - |
| 40-49 | 55 | 38.2% | +3.5% |
| 50-59 | 29 | 37.9% | +4.3% |
| 60-69 | 103 | 40.8% | +5.5% |
| 70-79 | 100 | 40.0% | +5.0% |
| 80+ | 34 | 38.2% | +4.6% |

*All logged signals have raw_score >= 35 by definition (log_signals filters raw < 35)

### Key Finding

Score bands 60-69 have the highest WR (40.8%) and expectancy (+5.5%). The 40-49 band
underperforms despite passing the gate. This suggests the score gate at 35 is too permissive
for non-whitelist stocks — consider raising to 45.

## Price Gate Analysis (raw >= 35)

| Gate Status | n | WR | Expectancy |
|---|---|---|---|
| price_ok=0 (Wait) | 234 | 39.3% | +4.8% |
| price_ok=1 (Buy) | 87 | 40.2% | +4.8% |

### Key Finding

The price gate adds only +0.9pp WR lift. This is far below expectations given prior audit
finding (WR 41% vs 32%). The current `W_PRICE=7.69` (down from original 30) and
`price_gate_frac_normal=0.55` means gate threshold is only 4.2 points out of 100.
The gate is nearly toothless at current weight levels.

**Root cause**: `W_PRICE` was optimized down from 30 → 7.69 by optimizer, making the
price gate threshold = 0.55 × 7.69 = 4.2 pts (very low bar).

## Gate Comparison

All 2025+ signals (n=321):

| Gate | ON WR | OFF WR | Lift |
|---|---|---|---|
| r7_div (Divergence) | 53.1% | 38.1% | **+15.1pp** |
| r6_macd (MACD) | 45.7% | 35.0% | **+10.7pp** |
| r2_ob (Order Block) | 47.5% | 38.4% | **+9.1pp** |
| r1_price (Price zone) | 42.3% | 37.0% | +5.3pp |
| r4_htf (HTF trend) | 41.2% | 38.4% | +2.8pp |
| r3_liquidity (Sweep) | 41.3% | 38.7% | +2.6pp |
| r5_avwap (AVWAP) | 36.3% | 41.1% | **-4.8pp (NEGATIVE)** |
| r8_demand (Demand Zone) | 39.8% | 39.4% | +0.4pp |

## Actionable Findings

1. **Divergence** (r7) is the highest-alpha gate: +15.1pp lift, but only fires on 32/321 signals (10%)
2. **MACD** (r6) has strong lift (+10.7pp) and fires frequently (138/321 = 43%)
3. **Order Block** (r2) has strong lift (+9.1pp) but fires on only 40/321 (12%)
4. **AVWAP** (r5) has NEGATIVE lift — see AVWAP_AUDIT.md
5. **Demand Zone** (r8) has negligible lift (+0.4pp) — questionable alpha value
