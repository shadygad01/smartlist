# ENTRY_INFLUENCE_MATRIX
*Generated: 2026-06-17 | Authority Mode Production Audit*

---

## Classification Key

- **DIRECT_ENTRY**: Directly modifies adj_score or gates BUY/Wait/Skip classification in `analyze()`
- **INDIRECT_VIA_WEIGHTS**: Changes `config/weights.json` → affects W_PRICE/W_OB/etc. on next process start
- **INDIRECT_VIA_STOCK_MULT**: Changes data in `egx_research.db` → `ranking_engine` reads → stock_mult → adj_score
- **REPORTING_ONLY**: Only HTML/email/JSON output; zero path to signal classification
- **DEAD_CODE**: File exists but has no connection to any live scoring path

---

## File-by-File Classification

### ranking_engine.py
**Classification: DIRECT_ENTRY**

- Imported: YES — lazy `import ranking_engine as _re` at `main.py:764` inside `analyze()` per-stock
- Effect: `_re.compute_expectancy(symbol)` → `_re._expectancy_to_mult(expectancy)` → `stock_mult` multiplied into adj_score at `main.py:777`
- When sample_n >= 30: uses historical r20d expectancy from `egx_research.db → bottom_quality.r20d`
- When sample_n < 30: falls back to `STOCK_QUALITY` dict (tier-based 0.88–1.15)
- Operational since: June 2026 only (all 2026 prior signals have stock_mult=NULL → fallback silent failure)
- Impact magnitude: stock_mult range 0.80–1.20. On raw_score=50, this shifts adj_score 40–60.

### pattern_engine.py
**Classification: REPORTING_ONLY** (for entry decisions)

- Imported: YES — top-level at `main.py:19` (`analyze_entry_patterns`) and `main.py:2114,2171`
- `analyze_entry_patterns()` called at `main.py:824` per-stock; result stored in `result["pattern"]`
- Pattern data used for: email body display, DB storage (`pattern_score`, `pattern_wr` columns in signals table)
- Pattern score does **NOT** appear in adj_score calculation
- `update_weights_from_log()` at `main.py:2171` writes to `learned_weights.json` — this is pattern_engine-internal and only affects future `pattern_score` display values, not SMC weights
- BUY/Wait/Skip classification at `main.py:787-803` does not reference `pattern_data`

### research_report.py
**Classification: REPORTING_ONLY**

- Imported: YES — `from research_report import maybe_run_weekly_report` at `main.py:29`
- Called at `main.py:2142` after scan completes
- Output: weekly HTML email report with BQ metrics, top signals, research findings
- Writes to: `research_results.json`, `reports/` HTML files, `report_log` DB table
- Does not write `config/weights.json`; does not affect stock_mult or adj_score

### continuous_learning.py
**Classification: INDIRECT_VIA_WEIGHTS** (conditional, deferred)

- Imported: YES — lazy `from continuous_learning import schedule_daily` at `main.py:2146`, called post-scan
- Chain: `schedule_daily()` → `run_learning_cycle()` → `optimization_engine.run()` → `weight_optimizer.optimize_weights()` → if APPROVED by `validation_engine` → `production_promoter.promote()` → writes `config/weights.json`
- Conditions to fire: >= 10 new outcomes AND > 24h since last cycle (rate-limited)
- **Critical gap**: `main.py` never calls `signal_engine.reload_weights()`. New `config/weights.json` is only loaded on process restart, not mid-run. Promotion during scan does not affect current or any subsequent scan in the same process.
- Evidence: `config/weights.json` last updated 2026-06-15; deployment_log has 8 rows total

### optimization_engine.py
**Classification: INDIRECT_VIA_WEIGHTS** (via continuous_learning chain)

- Imported: NO — called only by `continuous_learning._run_optimization()`
- Writes: `optimization_history` table (5 rows)
- Routes to: `weight_optimizer.optimize_weights()` for expectancy gradient; `walk_forward_backtester` or `smc_rl_optimizer` for other modes
- Does NOT write `config/weights.json` directly; returns dict to `continuous_learning`
- RL and walk-forward modes: compute weights but never promote them to config

### validation_engine.py
**Classification: INDIRECT_VIA_WEIGHTS** (as gatekeeper only)

- Imported: NO — called only by `continuous_learning._run_validation()`
- Writes: `validation_runs` table (24 rows)
- Role: gates whether `production_promoter.promote()` runs; if REJECTED, weights don't change
- Does not write weights itself
- Gate thresholds: oos_wr >= 0.65, oos_expectancy >= 0.10 (strict; explains few promotions)

### production_promoter.py
**Classification: INDIRECT_VIA_WEIGHTS** (sole writer of config/weights.json)

- Imported: NO — called only by `continuous_learning._run_promotion()` at `continuous_learning.py:440-450`
- Writes: `config/weights.json` (atomic swap), `config/thresholds.json`, `config_snapshots` table, `deployment_log` table (8 entries = 8 weight updates total)
- This is the only module that physically changes W_PRICE/W_OB/W_LIQ/etc.
- Takes effect only on process restart (reload_weights() never called live)

### weight_optimizer.py
**Classification: INDIRECT_VIA_WEIGHTS** (via continuous_learning chain)

- Imported: NO — called by `optimization_engine._run_expectancy_gradient()`
- Writes: `optimization_results.json`, HTML report in `reports/`
- `optimize_weights()` returns optimal weights dict in-memory; passed through optimization_engine → continuous_learning → production_promoter → config
- Standalone run of `weight_optimizer.main()` writes `optimization_results.json` which is consumed by `decision_engine.py` only (itself dead code)

### walk_forward_backtester.py
**Classification: REPORTING_ONLY**

- Imported: NO — called by `optimization_engine._run_walk_forward()` only
- Writes: `walk_forward_state.json`, HTML reports in `reports/`
- `walk_forward_state.json` is read by `gx_research_memory.py` and `cache_orchestrator.py` — neither is in `main.py` call chain
- Walk-forward weights never reach `config/weights.json`

### smc_rl_optimizer.py
**Classification: REPORTING_ONLY**

- Imported: NO — called by `optimization_engine._run_rl_gradient()` only
- Writes: `smc_rl_weights.json`
- `smc_rl_weights.json` NOT read by `signal_engine.py`, `main.py`, or `ranking_engine.py`
- Current RL weights (2026-06-13): W_PRICE=30.6, W_OB=9.6, W_LIQ=15.0, W_HTF=9.6, W_AVWAP=4.1, W_MACD=1.1, W_DIV=3.1, W_DZ=15.1 — close to original weights, far from current `config/weights.json`
- These optimized weights are computed but never promoted

### cache_orchestrator.py
**Classification: REPORTING_ONLY**

- Imported: NO — standalone CLI tool
- Orchestrates background research jobs via subprocess
- No path to `config/weights.json` or `stock_mult`

### historical_backtest.py
**Classification: INDIRECT_VIA_STOCK_MULT** (passive, indirect)

- Imported: NO — standalone backfill tool
- Writes: `hist_signals` table, `historical_backtest_results.json`
- `hist_signals` table IS queried by `ranking_engine.compute_expectancy()` to build historical r20d distribution for stock_mult computation
- Effect: running historical_backtest adds synthetic historical signals → raises sample_n → enables expectancy-based stock_mult rather than tier-based fallback
- This is a one-time setup effect, not a continuous live path

### policy_optimizer.py
**Classification: DEAD_CODE** (does not exist)

- File not found at `/home/user/smartlist/policy_optimizer.py`
- Not imported anywhere

### promotion_tracker.py
**Classification: DEAD_CODE** (does not exist)

- File not found at `/home/user/smartlist/promotion_tracker.py`
- Not imported anywhere

### decision_engine.py
**Classification: DEAD_CODE**

- Imported: NO — standalone offline tool
- Reads 8 JSON files from other offline tools
- Writes: `decision_engine_results.json`
- Output consumed only by `discount_zone_miner.py` (also not in main.py chain)

### adaptive_learning.py
**Classification: DEAD_CODE** (for production path)

- Imported: NO
- Writes: `adaptive_learning_results.json`, HTML
- Output consumed by: `gx_learning_layer.py`, `cache_orchestrator.py`, `decision_engine.py` — all outside main.py chain

---

## Summary Matrix

| File | Classification | Imports in main.py | Affects adj_score | Writes config/weights.json |
|---|---|---|---|---|
| ranking_engine.py | **DIRECT_ENTRY** | L764 (lazy, per-stock) | YES (stock_mult) | NO |
| pattern_engine.py | REPORTING_ONLY | L19, L2054, L2114, L2171 | NO | NO |
| research_report.py | REPORTING_ONLY | L29 | NO | NO |
| continuous_learning.py | INDIRECT_VIA_WEIGHTS | L2146 (lazy, post-scan) | DEFERRED (next restart) | Via chain |
| optimization_engine.py | INDIRECT_VIA_WEIGHTS | NO (via CL) | DEFERRED | Via chain |
| validation_engine.py | INDIRECT_VIA_WEIGHTS | NO (via CL) | GATE only | NO |
| production_promoter.py | INDIRECT_VIA_WEIGHTS | NO (via CL) | DEFERRED | YES (sole writer) |
| weight_optimizer.py | INDIRECT_VIA_WEIGHTS | NO (via CL chain) | DEFERRED | Via promoter |
| walk_forward_backtester.py | REPORTING_ONLY | NO | NO | NO |
| smc_rl_optimizer.py | REPORTING_ONLY | NO | NO | NO |
| cache_orchestrator.py | REPORTING_ONLY | NO | NO | NO |
| historical_backtest.py | INDIRECT_VIA_STOCK_MULT | NO | Via DB → ranking_engine | NO |
| decision_engine.py | DEAD_CODE | NO | NO | NO |
| adaptive_learning.py | DEAD_CODE | NO | NO | NO |
| policy_optimizer.py | DEAD_CODE | DOES NOT EXIST | — | — |
| promotion_tracker.py | DEAD_CODE | DOES NOT EXIST | — | — |

---

## Critical Structural Finding

The only live-run path that affects a BUY/Wait/Skip decision within the current scan execution is:

**`ranking_engine.compute_expectancy()` → `stock_mult` → `adj_score`**

All weight optimization (continuous_learning → optimization_engine → weight_optimizer → validation_engine → production_promoter) produces results that only take effect on the NEXT process restart, because `main.py` never calls `signal_engine.reload_weights()` after promotion. The 8 deployments recorded in `deployment_log` represent the total weight updates across the system's production life.
