# RL SHADOW EVALUATION REPORT
Generated: 2026-06-17

## Data Availability
- rl_score column exists in signals table: YES
- rl_signal column exists: YES
- Signals with non-NULL rl_score: **0** (no data)

## Conclusion
**RL shadow evaluation cannot be performed — no rl_score data in database.**

The RL system (smc_rl_weights.json) has computed weight configurations but has NOT been
applied to score historical signals. The `rl_score` and `rl_signal` columns are empty.

## RL Weights Assessment (from smc_rl_weights.json)
- Trained on 395 signals, 40 epochs
- Final loss: 0.2386
- RL performance claims: 68.4% top-quartile win rate (in-sample)
- **CRITICAL NOTE**: RL performance metrics are in-sample only, not walk-forward validated
- RL weights drastically reduce MACD (1.077 vs production 14.87) — contradicts empirical evidence

## Recommendation
- RL weights should NOT be promoted to production without out-of-sample validation
- The RL reduction of MACD weight contradicts empirical finding that MACD is the strongest predictor
- Shadow mode logging should be enabled in production to collect rl_score data for future evaluation
