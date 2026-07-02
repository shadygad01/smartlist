# RL SHADOW MODE REPORT

**Date**: 2026-06-17

## Implementation Summary

### Changes Made

1. `signal_db.py`: Added `import json` at top
2. `signal_db.py`: Added `_load_rl_weights()` function — lazy-loads `smc_rl_weights.json` once
3. `signal_db.py`: Added `_compute_rl_score()` function — normalizes production gate scores using RL weights
4. `signal_db.py` `_migrate_schema()`: Added `rl_score INTEGER` and `rl_signal TEXT` columns
5. `signal_db.py` `log_signals()`: Computes `_rl_score` and `_rl_signal` before each INSERT, stores in DB

### Zero Impact on Live Decisions

The RL score is:
- Computed from the SAME r1-r8 gate scores (no new data fetched)
- Stored alongside `raw_score` and `adj_score` as shadow columns
- NOT used in the BUY/Wait/Skip classification
- NOT used in entry zone calculation
- NOT surfaced in Telegram alerts

### RL Weights (Current)

From `smc_rl_weights.json` (trained 2026-06-13, 395 samples, 40 epochs):

| Gate | RL Weight | Prod Default | Change |
|---|---|---|---|
| r1_price | 30.635 | 30 | +2.1% |
| r2_ob | 9.604 | 10 | -4.0% |
| r3_liquidity | 14.986 | 20 | -25.1% |
| r4_htf | 9.636 | 10 | -3.6% |
| r5_avwap | 4.095 | 8 | -48.8% |
| r6_macd | 1.077 | 4 | -73.1% |
| r7_div | 3.12 | 3 | +4.0% |
| r8_demand | 15.138 | 15 | +0.9% |

Key RL signals: AVWAP and MACD weights cut dramatically (-49%, -73%). Liquidity cut -25%.

### Score Computation

```python
def _compute_rl_score(r1, r2, r3, r4, r5, r6, r7, r8, rl_weights):
    # For each gate: fraction = score / prod_max_weight
    # RL contribution = fraction × rl_max_weight
    # Scale to 100 by dividing by sum(rl_maxes)
```

### RL Signal Classification

| rl_score | rl_signal |
|---|---|
| >= 70 | Strong Buy |
| 50-69 | Buy |
| 35-49 | Weak Buy |
| < 35 | Skip |

### Validation

```
RL weights loaded: 9 keys (r1-r8 + pattern_score)
RL computed score (mock: r1=20,r2=7,r3=15,r4=8,r5=4,r6=3,r7=2,r8=12): 72
rl_score column in signals table: True
rl_signal column in signals table: True
```

## Next Step

After 30+ new signals are logged with rl_score:
- Compare rl_signal accuracy vs production signal_type
- If rl_score > prod adj_score correlates with better outcomes → graduate RL to production
- Use RL weight suggestions to update `config/weights.json` via `production_promoter.promote()`
