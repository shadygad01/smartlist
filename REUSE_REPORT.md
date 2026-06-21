# Reuse Report

**Generated:** 2026-06-21 (CRL Phase 8 — Auto Discovery)

---

## Unused Variables / JSON Data

| Asset | File/Path | Status | Recommendation |
|-------|----------|--------|----------------|
| `edge_discovery_results.json` (44M) | root | UNUSED in production | Move to `research/knowledge/`. CRL should index its findings. |
| `walk_forward_state.json` | root | Research-only | Move to `research/backtests/walk_forward_state.json` |
| `gx_learning_memory.json` | root | Research-only | Move to `research/knowledge/` |
| `gx_research_memory.json` | root | Research-only | Move to `research/knowledge/` |
| `knowledge_base.json` | root | Superseded by `research/knowledge/knowledge_base.db` | Retain as source; DB is primary |
| `learned_weights.json` | root | Pattern engine state | Register in CRL experiment registry |
| `smc_rl_weights.json` | root | RL research output | Register in CRL experiment registry |
| `optimization_results.json` | root | Research output | Move to `research/experiments/` |
| `historical_backtest_results.json` | root | Research output | Move to `research/backtests/` |
| `adaptive_learning_results.json` | root | Research output | Move to `research/reports/` |
| `challenger_validation_report.json` | root | Research output | Move to `research/validation/` |
| `system_audit_results.json` | root | Research audit | Move to `research/reports/` |
| `logic_analysis_results.json` | root | Research output | Move to `research/experiments/` |
| `data.json` | root | Unknown purpose | Investigate; archive if unused |
| `changed_symbols.json` | root | Cache invalidation metadata | Utility — retain in root |
| `rank_history.json` | root | 17 bytes only | Nearly empty; likely stale |

---

## Unused Scripts / Dead Code Candidates

| File | Evidence of Non-Use | Recommendation |
|------|-------------------|----------------|
| `_research_allocator.py` | Underscore prefix, no import found | **ARCHIVED** (done) |
| `backtest_analysis.py` | No callers in scan | Register as CRL backtest tool |
| `standalone_backtest_script.py` | Requires `egypt_stocks_5yr_data_updated.csv` (7.2M) | Register in `research/backtests/` |
| `outcome_enricher.py` | Referenced in comments; no live caller | Register as CRL utility |
| `extended_logger.py` | `extended_signal_log.json` does not exist | Register as CRL utility |
| `edge_report.py` | Referenced but no confirmed live caller | Register as CRL report tool |
| `multi_period_analyzer.py` | Referenced in labs but unclear live path | Register in CRL portfolio research |

---

## Duplicate Functionality

| Category | Files | Recommendation |
|----------|-------|----------------|
| Backfilling | `backfill_signal_log.py`, `backfill_research_db.py`, `backfill_egx30.py`, `backfill_discount_signals.py`, `backfill_signal_log_smc.py`, `backfill_positions.py`, `backfill_hist_features.py`, `full_backfill_all_in_one.py (archived)` | **Keep all.** Each targets a different table/format. Register all in CRL backtest library. |
| Backtesting | `backtest.py`, `backtest_regime_aware.py`, `historical_backtest.py`, `walk_forward_backtester.py`, `standalone_backtest_script.py` | **Keep all.** Each covers a different scenario. Index in BACKTEST_LIBRARY.md. |
| Knowledge storage | `knowledge_base.json`, `gx_research_memory.json`, `research/knowledge/knowledge_base.db` | **DB is primary CRL store.** JSON files are source/legacy; retain. |
| Learning layers | `gx_learning_layer.py`, `continuous_learning.py`, `adaptive_learning.py` | **Keep all.** Three independent functions: meta-learning, loop orchestration, diagnosis. |

---

## Unused Tables in egx_research.db

| Table | Row Count | Status |
|-------|-----------|--------|
| `report_log` | 0 | Empty — register as CRL tracking table |
| `early_buy_research` | 53 | Active research — register in CRL |
| `pattern_knowledge_base` | 261 | Active — link to CRL station research |
| `pattern_telemetry` | 560 | Active — link to CRL pattern research |
| `fib_outcomes` | 431 | Active — link to CRL portfolio/backtest research |

---

## Unused Reports / Documents

| File | Last Modified | Recommendation |
|------|-------------|----------------|
| `reports/RESEARCH_WASTE_REPORT.md` | pre-CRL | Register as CRL finding |
| `reports/RESEARCH_ROI_REPORT.md` | pre-CRL | Register as CRL finding |
| `reports/WORLD_COMPARISON_REPORT.md` | pre-CRL | Register as CRL finding |
| `INDEPENDENT_AUDIT_AR.md` | pre-CRL | Register as CRL validated finding |

---

## Summary Statistics

| Metric | Count |
|--------|-------|
| Total Python files | 89 |
| Production files | 23 |
| Research files | 35 |
| Utility files | 25 |
| Legacy/Archive files | 3 (2 pre-existing + 1 archived today) |
| Dead code (no callers, no active use) | ~6 files |
| JSON data files | 26 |
| JSON unused/stale | ~8 files |
| Empty tables in egx_research.db | 1 (report_log) |
| **Dead code %** | ~7% of Python files |
| **Reuse opportunity %** | ~85% of research files already integrated |
| **Production integrity** | CONFIRMED |
