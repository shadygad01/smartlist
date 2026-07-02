# RESEARCH_WASTE_REPORT
*Generated: 2026-06-17 | Authority Mode Production Audit*

---

## Import Graph: main.py Direct Imports

```
main.py imports:
  signal_engine (ACTIVE — scoring engine)
  signal_db (ACTIVE — DB logging)
  pattern_engine (ACTIVE — display only)
  signal_logger (ACTIVE — logging)
  backfill_signal_log (ACTIVE — backfill utility)
  egx_context (ACTIVE — Ramadan/CBE calendar)
  daily_tracker (ACTIVE — outcome tracking)
  research_report (ACTIVE — email reporting)
  ranking_engine [lazy, per-stock] (ACTIVE — stock_mult)
  continuous_learning [lazy, post-scan] (ACTIVE — weight update chain)
  pattern_engine [lazy, post-scan] (ACTIVE — weight log update)
```

**NOT imported** (directly or transitively from main.py):
- optimization_engine.py (called by continuous_learning)
- validation_engine.py (called by continuous_learning)
- production_promoter.py (called by continuous_learning)
- weight_optimizer.py (called by optimization_engine)
- walk_forward_backtester.py (called by optimization_engine, results discarded)
- smc_rl_optimizer.py (called by optimization_engine, results discarded)
- historical_backtest.py (standalone)
- decision_engine.py (standalone)
- adaptive_learning.py (standalone)

---

## Category 1: Dead Code (Never in Production Path)

### decision_engine.py
**Verdict: DEAD**

- Never imported by main.py, continuous_learning.py, or any module in the call chain
- Reads: `backtest_report.json`, `adaptive_learning_results.json`, `edge_discovery_results.json`, `system_audit_results.json`, `optimization_results.json`, `historical_backtest_results.json`, `gx_learning_memory.json`, `research_results.json`
- Writes: `decision_engine_results.json`
- Only consumer of output: `discount_zone_miner.py` (also not in production path)
- Evidence: grep of main.py for "decision_engine" returns zero hits

### adaptive_learning.py
**Verdict: DEAD**

- Never imported by main.py
- Writes: `adaptive_learning_results.json`, HTML report
- Output consumers: `gx_learning_layer.py`, `cache_orchestrator.py`, `decision_engine.py` — all outside production chain
- No path to config/weights.json or adj_score
- Evidence: grep of main.py for "adaptive_learning" returns zero hits

---

## Category 2: Disconnected Weight Files

### smc_rl_weights.json + smc_rl_optimizer.py
**Verdict: DISCONNECTED — RL weights never used in production**

- `smc_rl_optimizer.py` writes `smc_rl_weights.json`
- `smc_rl_weights.json` is NOT read by `signal_engine.py`, `main.py`, `ranking_engine.py`, or `production_promoter.py`
- Only readers: `gx_research_memory.py` (lines 424, 456), `cache_orchestrator.py`
- The RL optimizer ran 2026-06-13, produced weights (W_PRICE=30.6, W_DZ=15.1) that are more aligned with original weights and contradicts the current config
- These optimized weights are being computed and silently discarded
- **Waste magnitude**: RL optimization performed with n=395, 40 epochs, all_win_rate=67.8% in backtest — but results are never promoted

### walk_forward_state.json + walk_forward_backtester.py
**Verdict: DISCONNECTED — walk-forward weights never used**

- `walk_forward_backtester.py` writes `walk_forward_state.json`
- `walk_forward_state.json` not read by any production module
- Only readers: `gx_research_memory.py`, `cache_orchestrator.py`
- Walk-forward results computed by `optimization_engine._run_walk_forward()` but the params_after dict is returned in-memory and NEVER passed to `production_promoter`

---

## Category 3: Broken Circuit — Hot-Reload Gap

### config/weights.json write without reload
**Verdict: BROKEN CIRCUIT**

The production path for weight updates:
```
main.py (post-scan)
  → continuous_learning.schedule_daily()
    → _run_optimization()
      → optimization_engine.run()
        → weight_optimizer.optimize_weights()
    → _run_validation()
      → validation_engine.validate()
    → production_promoter.promote()
      → WRITES config/weights.json ← HAPPENS HERE
      → signal_engine.reload_weights() ← NEVER CALLED
```

Evidence:
```bash
grep -n "reload_weights" /home/user/smartlist/main.py → ZERO HITS
grep -n "reload_weights" /home/user/smartlist/continuous_learning.py → ZERO HITS
grep -n "reload_weights" /home/user/smartlist/production_promoter.py → ZERO HITS
```

`signal_engine.reload_weights()` exists at `signal_engine.py:120-144` but is NEVER called in production. The function would reload `config/weights.json` and update all W_* globals. Without this call, any weight promotion requires process restart.

**Impact**: 8 promotions × average weight change = 8 sets of "improved" weights that were silently ineffective until the next cold start.

---

## Category 4: Stale DB Tables (Written, Rarely/Never Read by Production)

| Table | Rows | Written By | Read By Production |
|---|---|---|---|
| optimization_history | 5 | optimization_engine | `get_best_run()` in optimization_engine (never called from CL) |
| experiment_log | 51 | labs/research | dashboard.py only |
| deployment_log | 8 | production_promoter | `get_promotion_history()` — never called from main.py |
| validation_runs | 24 | validation_engine | Internal to validation_engine checks only |
| config_snapshots | (exists) | production_promoter | Rollback only (never triggered) |

`optimization_history.get_best_run()` is defined but never called from `continuous_learning.py` — each cycle runs fresh optimization without consulting historical best.

---

## Category 5: JSON Files Written But Never Read by Production

| File | Written By | Production Reader | Status |
|---|---|---|---|
| smc_rl_weights.json | smc_rl_optimizer.py | NONE | DEAD |
| walk_forward_state.json | walk_forward_backtester.py | NONE | DEAD |
| optimization_results.json | weight_optimizer.py | decision_engine.py only | DEAD |
| adaptive_learning_results.json | adaptive_learning.py | decision_engine.py only | DEAD |
| historical_backtest_results.json | historical_backtest.py | gx_learning_layer.py only | DEAD |
| decision_engine_results.json | decision_engine.py | discount_zone_miner.py | DEAD |
| edge_discovery_results.json | edge_discovery.py | decision_engine.py only | DEAD |
| learned_weights.json | pattern_engine.py | pattern_engine.py (self-read) | PATTERN ONLY |

---

## Category 6: Optimization Modes That Cannot Promote

`optimization_engine.py` supports three modes:
1. `_run_expectancy_gradient()` → calls `weight_optimizer.optimize_weights()` → returns dict → **CAN BE PROMOTED**
2. `_run_walk_forward()` → calls `walk_forward_backtester` → returns state → **CANNOT BE PROMOTED** (path ends here)
3. `_run_rl_gradient()` → calls `smc_rl_optimizer` → returns params → **CANNOT BE PROMOTED** (path ends here)

Modes 2 and 3 compute valid optimizations but their results have no path to `config/weights.json`. All computation is wasted.

---

## Waste Inventory Summary

| Waste Type | Files Affected | Severity |
|---|---|---|
| Dead code (never runs in production) | decision_engine.py, adaptive_learning.py | HIGH |
| Disconnected weight files (computed but unused) | smc_rl_weights.json, walk_forward_state.json | HIGH |
| Broken hot-reload (promotions silently ineffective) | All 8 promotions | HIGH |
| Orphaned optimization modes (walk-forward + RL can't promote) | walk_forward_backtester.py, smc_rl_optimizer.py | MEDIUM |
| Stale DB tables (written but not queried in production) | optimization_history, experiment_log, config_snapshots | MEDIUM |
| Orphaned JSON files (7 files, no production consumer) | See Category 5 | MEDIUM |

---

## Three Fixes That Would Eliminate Most Waste

1. **Add `signal_engine.reload_weights()` call after `production_promoter.promote()`** in `continuous_learning.py`. 1 line. Would make all weight promotions take effect immediately.

2. **Wire walk_forward and RL results through production_promoter**: after `_run_walk_forward()` and `_run_rl_gradient()`, route best weights through validation and promotion. The RL result (W_PRICE=30.6, all_win_rate=67.8%) is worth promoting.

3. **Delete or archive dead code**: `decision_engine.py`, `adaptive_learning.py` — they consume CPU, read files, and generate reports that nothing reads. Archiving them removes confusion about what's live.
