# Research Map

**CRL Version:** 1.0  
**Generated:** 2026-06-21  

---

## research/ Directory Structure

```
research/
├── labs/           ← Experimental lab notebooks and scripts
├── experiments/    ← CRL experiment outputs and data
├── validation/     ← Walk-forward validation results
├── backtests/      ← Backtest output files
├── patterns/       ← Pattern discovery and knowledge
├── stations/       ← Per-station R1-R8 research
├── portfolio/      ← Portfolio allocator experiments
├── reports/        ← Generated research reports
├── knowledge/      ← knowledge_base.db + archived JSON
└── tools/          ← Research utilities and helpers
```

---

## Active Research Modules

| Module | Location | Output | Schedule |
|--------|---------|--------|---------|
| `research_engine.py` | root | `research_results.json` | Weekly (research_report.py) |
| `edge_discovery.py` | root | `edge_discovery_results.json` (44M) | On-demand |
| `rule_discovery.py` | root | `reports/` | On-demand |
| `pattern_discovery.py` | root | `egx_research.db.pattern_*` | On-demand |
| `pattern_kb.py` | root | `egx_research.db.pattern_knowledge_base` | Continuous |
| `system_audit.py` | root | `system_audit_results.json` | On-demand |
| `adaptive_learning.py` | root | `adaptive_learning_results.json` | scheduler.py |
| `gx_learning_layer.py` | root | `gx_learning_report_{date}.html` | scheduler.py |
| `decision_engine.py` | root | `reports/decision_engine_report_{date}.html` | scheduler.py |
| `weight_optimizer.py` | root | `optimization_results.json` | scheduler.py |
| `smc_rl_optimizer.py` | root | `smc_rl_weights.json` | scheduler.py |
| `walk_forward_backtester.py` | root | `walk_forward_state.json` | scheduler.py |

### labs/

| Lab | Purpose | Dependencies |
|-----|---------|-------------|
| `factor_lab.py` | R1-R8 factor analysis (win rate, expectancy, correlation) | signal_db, scipy |
| `drift_lab.py` | Drift detection, bias flags, system health monitoring | system_audit, extend_metrics |
| `parameter_lab.py` | Parameter sensitivity analysis | logic_analyzer, study_indicators |
| `regime_lab.py` | Regime detection and conditional performance | signal_db |
| `interaction_lab.py` | Interaction effects between stations | signal_db |
| `report_builder.py` | Lab report formatting and output | — |

---

## Research Data Sources

| Source | Access Method | Available For |
|--------|-------------|--------------|
| `egx_research.db.signals` | `signal_db.py` | All research (read-only) |
| `egx_research.db.bottom_quality` | `signal_db.py` | BQ research |
| `egx_research.db.fib_outcomes` | Direct SQLite | Fibonacci exit study |
| `egx_research.db.pattern_knowledge_base` | Direct SQLite | Pattern research |
| `egx_research.db.early_buy_research` | Direct SQLite | EARLY BUY research |
| `candidate_pool.db` | `candidate_pool_builder.py` | Portfolio research |
| `portfolio_manager.db` | `portfolio_manager.py` | Portfolio state research |
| `signal_log.json` | `signal_logger.py` | Signal quality research |
| `historical_data/*.csv` | Direct pandas | Point-in-time OHLCV |
| `research_results.json` | Direct JSON | Feature importance |
| `backtest_report.json` | Direct JSON | Backtest metrics |

---

## Research Reports Index

| Report | Location | Content |
|--------|---------|---------|
| `AVWAP_AUDIT.md` | reports/ | AVWAP station audit and decision |
| `AVWAP_DECISION.md` | reports/ | AVWAP removal/retention decision |
| `ENTRY_ENGINE_MAP.md` | reports/ | Complete entry signal map |
| `ENTRY_INFLUENCE_MATRIX.md` | reports/ | Factor influence matrix |
| `ENTRY_TIMING_ANALYSIS.md` | reports/ | Entry timing quality analysis |
| `EXPECTANCY_DECOMPOSITION.md` | reports/ | Expectancy by factor decomposition |
| `FEATURE_IMPORTANCE_REPORT.md` | reports/ | ML feature importance ranking |
| `FINAL_ALPHA_REPORT.md` | reports/ | Final alpha signal study |
| `FINAL_RESOLUTION_VERDICT.md` | reports/ | System-wide verdict |
| `GATE_CONTRIBUTION_REPORT.md` | reports/ | Gate contribution to win rate |
| `HOT_RELOAD_FIX_REPORT.md` | reports/ | Hot reload fix documentation |
| `NEXT_BEST_IMPROVEMENT.md` | reports/ | Priority improvement ranking |
| `PRODUCTION_PATCH_REPORT.md` | reports/ | Production patch history |
| `PRODUCTION_PERFORMANCE.md` | reports/ | Live production performance |
| `REGIME_FILTER_REPORT.md` | reports/ | Regime filter research |
| `RESEARCH_ROI_REPORT.md` | reports/ | Research ROI analysis |
| `RESEARCH_WASTE_REPORT.md` | reports/ | Research waste identification |
| `RL_DECISION_REPORT.md` | reports/ | RL optimization decision |
| `RL_SHADOW_REPORT.md` | reports/ | RL shadow mode results |
| `SCORE_GATE_ANALYSIS.md` | reports/ | Score gate optimization |
| `SYSTEM_TRUTH_REPORT.md` | reports/ | System truth and audit |
| `THRESHOLD_OPTIMIZATION.md` | reports/ | Threshold parameter optimization |
| `WEIGHT_IMPACT_REPORT.md` | reports/ | Weight change impact analysis |
| `WEIGHT_REBALANCING.md` | reports/ | Weight rebalancing study |
| `WORLD_COMPARISON_REPORT.md` | reports/ | EGX vs world market comparison |
| `CLAIM_VALIDATION.md` | reports/ | Claim validation audit |
| `INDEPENDENT_AUDIT_AR.md` | root | Independent system audit |
| `docs/R1R8_EVOLUTION_ROADMAP.md` | docs/ | R1-R8 planned evolution |
| `docs/R1R8_VIOLATION_REPORT.md` | docs/ | R1-R8 constitutional violations |
| `docs/R1R8_CORRECTION_REPORT.md` | docs/ | R1-R8 corrections log |

---

## Research Constitution

Every future research idea MUST follow this path:

```
New Idea / Observation
    ↓
Register in EXPERIMENT_REGISTRY.md + knowledge_base.db
    ↓
Build experiment in research/experiments/ or research/stations/
    ↓  (never in production files)
Run walk-forward against constitutional baseline
    (2026-01-01 to 2026-06-21, same 27 symbols)
    ↓
Compute Spearman rho / evidence
    ↓
Record in knowledge_base.db
    ↓
Update EXPERIMENT_REGISTRY.md status
    ↓
If VERIFIED → write Recommendation
    ↓
If recommendation requires production change:
    → Draft Constitutional Amendment
    → Submit with AUTHORITY: FULL
    → validation_engine.py gates
    → production_promoter.py only
    ↓
PRODUCTION NEVER LEARNS DIRECTLY
CRL ALWAYS LEARNS FIRST
```

---

## Research Governance Rules

1. No research module may write to `config/` directly.
2. No research module may modify `egx_research.db.signals` (read-only for research).
3. `production_promoter.py` is the only legitimate production modification path.
4. All experiments must use `get_constitutional_universe()` — no hardcoded symbols.
5. No lookahead: point-in-time constraint must be enforced in all experiments.
6. Evidence threshold for constitutional change: minimum 500 signals, Spearman p<0.01.
7. Weight changes and station redesigns cannot happen in the same mandate.
