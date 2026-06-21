# Backtest Library

**CRL Version:** 1.0  
**Generated:** 2026-06-21  
**Full data:** `research/knowledge/knowledge_base.db → backtest_library`  

---

## Production-Validated Backtests

### BT-MAIN-5YR — 5-Year EGX SMC Backtest

**Script:** `backtest.py`  
**Dataset:** `egx_research.db + signal_log.json`  
**Date range:** 2021-05-05 to 2026-05-20  
**Signals:** 1,051 (all resolved)  
**Method:** Z3-optimized; price gate, OB quality, liquidity, HTF, AVWAP, MACD, divergence, demand  

| Metric | Value |
|--------|-------|
| Win rate | 69.4% |
| Wins / Losses | 729 / 322 |
| Avg win | +26.3% |
| Avg loss | -5.1% |
| Expectancy | +16.7% per signal |
| Profit Factor | 9.85 |
| CAGR | 100.1% |
| Max Drawdown | -3.52% |
| Calmar Ratio | 28.44 |
| Sharpe-like | 3.02 |

**Output files:** `backtest_report.json`  
**Notes:** Outcome breakdown: large 66, medium 355, small 307, flat 323.  

---

### BT-CONST-WF — Constitutional Engine Walk-Forward 2026

**Script:** `candidate_pool_builder.py` + `portfolio_manager.py`  
**Dataset:** 27-symbol constitutional universe  
**Date range:** 2026-01-01 to 2026-06-21  
**Signals:** 782 (23/27 symbols triggered)  

| Metric | Engine | Manual Portfolio |
|--------|--------|-----------------|
| Avg return | +26.7% | +30.8% |
| >20% signals | 11 | 8 |
| >50% signals | 5 | 4 |
| Peak avg return | +36.8% | — |
| Positions found | 15/15 manual + 9 additional | 15 |
| Spearman final_score vs MAE_40 | +0.137*** GOOD | — |

**Output files:** `CONSTITUTION_VERSION.md`  
**Notes:** Engine found all 15 manual positions plus 9 additional high-quality signals.  

---

### BT-HIST-REPLAY — Historical Signal Replay

**Script:** `historical_backtest.py`  
**Dataset:** `historical_data/*.csv` (29 symbol OHLCV)  
**Date range:** 2021+ to 2026  
**Signals:** ~500+  
**Output files:** `historical_backtest_results.json`  
**Notes:** Point-in-time replay, no lookahead. Used for R1-R8 station validation.  

---

### BT-WF-ADAPTIVE — Walk-Forward Adaptive (Weight Learning)

**Script:** `walk_forward_backtester.py`  
**Dataset:** `egx_research.db`  
**Method:** Chronological gradient update on R1-R8 weights per resolved signal  
**Output files:** `walk_forward_state.json`, `reports/walk_forward_report_{date}.html`  
**Status:** RESEARCH ONLY — weights never promoted to production without validation_engine gate  
**Notes:** Current walk_forward_state.json has 612K of weight history + equity curve.  

---

### BT-RL-WEIGHTS — RL-Light Policy Gradient Weight History

**Script:** `smc_rl_optimizer.py`  
**Method:** Online gradient update on R1-R8 + pattern_score  
**Output files:** `smc_rl_weights.json`, `reports/smc_rl_report_{date}.html`  
**Status:** RESEARCH ONLY  
**Notes:** RL weights require validation_engine pass before any promotion.  

---

### BT-REGIME-AWARE — Regime-Aware Backtesting

**Script:** `backtest_regime_aware.py`  
**Dataset:** `egx_research.db`  
**Method:** Conditional backtesting under different market regimes  
**Output files:** TBD  
**Status:** Research utility  

---

### BT-STANDALONE — Standalone Wide-Format Backtest

**Script:** `standalone_backtest_script.py`  
**Dataset:** `egypt_stocks_5yr_data_updated.csv` (7.2M, wide format)  
**Method:** Z3 averaging with score gate and price gate  
**Output files:** `standalone_backtest_results.csv`  
**Status:** Research utility  
**Notes:** Requires `egypt_stocks_5yr_data_updated.csv` to be present. Uses `get_constitutional_universe()`.  

---

### BT-CHALLENGER — Challenger vs Production Comparison

**Script:** `challenger_validation.py`  
**Dataset:** `egx_research.db`  
**Method:** Comparative walk-forward (Production R1-R8 vs Challenger Ridge+Expectancy)  
**Output files:** `challenger_validation_report.json`  
**Notes:** 6 metrics: WR, profit factor, MFE, Spearman. Challenger layer runs in shadow mode.  

---

## Backtest Index by Purpose

| Purpose | Script | Output |
|---------|--------|--------|
| Production baseline | `backtest.py` | `backtest_report.json` |
| Constitutional validation | `candidate_pool_builder.py` | `CONSTITUTION_VERSION.md` |
| Station R1-R8 validation | `historical_backtest.py` | `historical_backtest_results.json` |
| Weight adaptation research | `walk_forward_backtester.py` | `walk_forward_state.json` |
| RL weight research | `smc_rl_optimizer.py` | `smc_rl_weights.json` |
| Regime filtering | `backtest_regime_aware.py` | reports/ |
| Challenger system | `challenger_validation.py` | `challenger_validation_report.json` |
| Single-file analysis | `standalone_backtest_script.py` | `standalone_backtest_results.csv` |
| Historical replay | `historical_backtest.py` | `historical_backtest_results.json` |

---

## Backtest Governance Rules

1. All backtests are RESEARCH. No backtest directly modifies production.
2. Weight changes from backtests must pass `validation_engine.py` before promotion.
3. `production_promoter.py` is the only mechanism for applying validated results.
4. Walk-forward baseline: 2026-01-01 to 2026-06-21 (constitutional reference).
5. New backtests must use `get_constitutional_universe()` — no hardcoded symbol lists.
6. Point-in-time constraint: `hist = df[df['Date'] <= sig_date].tail(120)` — no lookahead.
