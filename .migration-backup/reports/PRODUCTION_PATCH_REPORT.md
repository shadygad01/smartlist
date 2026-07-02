# PRODUCTION PATCH REPORT
Generated: 2026-06-17

## Changes Applied
**NONE — All tested changes failed walk-forward validation criteria.**

## Validation Criteria (from mission spec)
1. Walk-forward validated (improves out-of-sample in 2+ consecutive periods) — FAILED for all candidates
2. Expectancy improvement (not just WR) — marginal at best
3. n >= 30 in test period — met for splits 3 and 4 only
4. Not curve-fitted — FAILED: 2025 H2 consistently underperforms regardless of configuration

## Production Config Status
- config/weights.json: UNCHANGED
- config/gates_config.json: UNCHANGED
- signal_engine.py: UNCHANGED
- main.py: UNCHANGED

## Current System Health
- Raw score: uncorrelated with r20d (r=0.021, p=0.70) — score is not a good predictor
- MACD is the best predictor (Pearson r=0.16, Fisher p=0.065)
- Demand is the most overweighted component (29.4% weight, IV=0.001)
- AVWAP shows mild negative lift but not statistically significant

## Why No Changes Were Applied
The walk-forward analysis revealed that the system performance is primarily regime-driven:
- 2025 H2 (Jul-Dec): WR ~30%, negative/low expectancy regardless of configuration
- 2026 H1 (Jan-May): WR ~41-48%, positive expectancy regardless of configuration

This regime dependency means weight/threshold tweaks cannot consistently improve outcomes.
The regime filter already in production (gates_config.json: regime_filter_enabled=true) is
the appropriate mechanism.
