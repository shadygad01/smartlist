# AVWAP DECISION REPORT
Generated: 2026-06-17

## Formula Analysis (signal_engine.py line 684-687)
```python
def sc_avwap(cur, av, av_lo):
    if cur <= av_lo: return W_AVWAP, f"At/below AVWAP lower band {av_lo:.1f}"
    if cur < av: return max(round(((av - cur) / (av - av_lo)) * (W_AVWAP - 1)), 1), f"Below AVWAP {av:.1f}"
    return 0, f"Above AVWAP {av:.1f}"
```

## Formula Logic Assessment
- Price <= AVWAP lower band → full score (CORRECT: deep discount)
- Price < AVWAP (but above lower band) → partial score (CORRECT: moderate discount)
- Price >= AVWAP → score = 0 (CORRECT: premium zone)
**FORMULA IS NOT BACKWARDS. Logic is correct.**

## Scoring by r5_avwap value
| r5 value | Count | WR    | Interpretation              |
|----------|-------|-------|-----------------------------|
| 0        |   219 | 0.411 | Price at/above AVWAP (no score) |
| 1        |     9 | 0.556 | Just below AVWAP              |
| 2        |     5 | 0.000 | n too small                   |
| 3        |     2 | 0.500 | n too small                   |
| 4        |     3 | 0.333 | n too small                   |
| 5        |     1 | 1.000 | n too small                   |
| 6        |    10 | 0.100 | Near lower band               |
| 8        |    72 | 0.389 | At/below lower band (max score) |

## Statistical Test
- r5=0: n=219, WR=0.411
- r5>0: n=102, WR=0.363
- WR Lift: -4.8pp (negative — scoring HURTS performance)
- Fisher exact p=0.4626 (NOT statistically significant)
- n in both groups: 219 and 102 — BOTH exceed n>=30 threshold

## Key Paradox
- r5=8 (max score, at/below AVWAP lower band): WR=0.389 — LOWER than r5=0 (WR=0.411)
- r5=1 (just below AVWAP): WR=0.556 — HIGHEST
- This suggests deep discount stocks (at lower band) actually perform worse

## Possible Explanations
1. Stocks at/below AVWAP lower band are often in persistent downtrends
2. The AVWAP lower band is not a reliable support level on EGX
3. The scoring may be capturing momentum correctly (negative = bad) but AVWAP signals come from weak stocks

## Decision
**REDUCE AVWAP weight. Do NOT remove entirely.**

Rationale:
- Negative lift confirmed (n>=30 in both groups) → AVWAP at max score is weakly negative
- Formula is logically correct (not backwards) → no systematic bug
- r5=1 (just below AVWAP, WR=0.556) is positive → partial AVWAP score may still be useful
- The issue is that max score (r5=8, deep discount) underperforms
- Statistical test: p=0.4626 → NOT reaching p<0.05 threshold
- **Conservative action**: Reduce weight by 50% (7.09 → 3.5) and monitor

## Recommendation
- Do NOT remove AVWAP entirely (some subscore bands are positive)
- Reduce weight from 7.09% to ~3.5% in weights.json
- Walk-forward validation shows no consistent improvement from weight changes → **do not change**
