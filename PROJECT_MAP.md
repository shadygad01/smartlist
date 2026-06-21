# Project Map — EGX Constitutional Signal System

**Generated:** 2026-06-21  
**Total Python files:** 70 (root) + 7 tests + 7 labs + 3 config + 2 archive = 89  
**Total lines:** ~46,000  
**Databases:** 4 (egx_research.db 2.1M, candidate_pool.db 385K, portfolio_manager.db 108K, portfolio_advisor.db 41K)  

---

## PRODUCTION (DO NOT MODIFY)

| File | Purpose | Key Dependencies |
|------|---------|-----------------|
| `main.py` | Daily scan orchestrator (08:30 Cairo) | pattern_engine, signal_logger, signal_db, daily_tracker, research_report, snapshot_engine, egx_context |
| `signal_engine.py` | R1-R8 scoring functions (swings, price, OB, liquidity, HTF, AVWAP, MACD, divergence, demand) | config/scanner_config |
| `discount_reversal_engine.py` | **FROZEN** Constitutional R1-R8 engine | config/scanner_config |
| `pattern_engine.py` | 6-indicator pattern scoring (stoch_rsi, p_vs_ma20, mom_10d/5d, atr_ratio, vol_trend) | config |
| `signal_logger.py` | JSON-based signal log (signal_log.json) | — |
| `signal_db.py` | SQLite egx_research.db interface | egx_research.db |
| `daily_tracker.py` | 60-day outcome tracking, BQ score computation | signal_db |
| `portfolio_manager.py` | State machine (NEW→HELD→EXIT), 12-15 positions, R2-ranked | candidate_pool.db, portfolio_manager.db |
| `portfolio_advisor.py` | Intelligence layer V2: Signal Quality ★ + Portfolio Fit ★ | portfolio_manager.db, candidate_pool.db |
| `candidate_pool_builder.py` | Append-only candidate curation | discount_reversal_engine, candidate_pool.db |
| `ranking_engine.py` | Symbol + factor expectancy ranking | config/scanner_config, signal_db |
| `heatmap.py` | Sector heatmap HTML output | config/scanner_config |
| `dashboard.py` | Interactive HTML dashboard | signal_db, signal_logger |
| `research_report.py` | Weekly HTML research report + email | signal_db, research_engine |
| `scheduler.py` | Autonomous daily orchestrator (Layer 10) | main, research_engine, validation_engine, production_promoter |
| `egx_context.py` | EGX calendar, Ramadan/CBE windows | — |
| `challenger_scanner.py` | 3-layer shadow validation system | eligibility, expectancy, allocation engines |
| `challenger_eligibility_engine.py` | Layer 1: Discount zone binary gate | signal_db |
| `challenger_expectancy_engine.py` | Layer 2: Ridge regression R2-R8 → MFE | signal_db |
| `challenger_allocation_engine.py` | Layer 3: Expectancy → A+/A/B/C/D grades | challenger_expectancy |
| `challenger_validation.py` | Production vs Challenger comparative metrics | egx_research.db |
| `validation_engine.py` | Pre-promotion gates (≥65% OOS WR, <20pp overfit) | egx_research.db |
| `production_promoter.py` | Atomic production deployment with audit trail | config/, egx_research.db |

---

## RESEARCH INFRASTRUCTURE

| File | Purpose | Status |
|------|---------|--------|
| `research_engine.py` | ML analysis: RandomForest/GBM feature importance | Active |
| `weight_optimizer.py` | R1-R8 weight optimization (non-binding) | Active |
| `smc_rl_optimizer.py` | RL-light policy gradient on weights | Active |
| `walk_forward_backtester.py` | Chronological adaptive backtesting | Active |
| `adaptive_learning.py` | Diagnosis + simulated improvement proposals | Active |
| `continuous_learning.py` | Layer 10 learning loop coordinator | Active |
| `system_audit.py` | 9-section system self-audit | Active |
| `optimization_engine.py` | Unified optimization interface + history log | Active |
| `decision_engine.py` | Synthesis of all research outputs → decision | Active |
| `edge_discovery.py` | 1-3 condition combination edge mining | Active |
| `rule_discovery.py` | 4-method rule extraction (DT/RuleFit/Apriori/BRL) | Active |
| `pattern_discovery.py` | K-Means clustering on features | Active |
| `pattern_kb.py` | Self-learning pattern knowledge base V2 | Active |
| `knowledge_base.py` | Persistent statistical findings store | Active |
| `gx_research_memory.py` | Persistent GX research findings lifecycle | Active |
| `gx_learning_layer.py` | Meta-learning master intelligence layer | Active |
| `quant_research_report.py` | 7-stage quant research (CAGR/PF/MFE/Calmar) | Active |
| `early_buy_tracker.py` | EARLY BUY shadow tracking (research only) | Active |

### labs/

| File | Purpose |
|------|---------|
| `labs/factor_lab.py` | Factor analysis (R1-R8 correlations vs outcomes) |
| `labs/drift_lab.py` | Drift detection, bias flags, system health |
| `labs/parameter_lab.py` | Parameter sensitivity analysis |
| `labs/regime_lab.py` | Regime detection research |
| `labs/interaction_lab.py` | Interaction effects between stations |
| `labs/report_builder.py` | Lab report generation |

---

## UTILITIES

| File | Purpose |
|------|---------|
| `feature_extractor.py` | Compute 40+ feat_* and snap_* features |
| `feature_registry.py` | Feature metadata catalog |
| `snapshot_engine.py` | Snapshot features at signal time (14 variables) |
| `extend_metrics.py` | Compute 90d/120d/180d/252d forward returns |
| `outcome_enricher.py` | Post-20-day outcome computation |
| `extended_logger.py` | Extended per-signal variable capture |
| `backfill_signal_log.py` | Historical signal backfill (500-day lookback) |
| `backfill_research_db.py` | Backfill egx_research.db from signal_history.json |
| `backfill_signal_log_smc.py` | Inject SMC historical signals |
| `backfill_positions.py` | Day-by-day position simulation since 2026-01-01 |
| `backfill_egx30.py` | EGX30 5-year OHLCV download + backfill |
| `backfill_discount_signals.py` | Backfill discount_reversal_engine signals |
| `backfill_hist_features.py` | Historical feature backfill |
| `build_history.py` | Build signal_history.json accumulation |
| `backtest.py` | Main 5-year Z3-optimized backtesting engine |
| `backtest_analysis.py` | Backtest result analysis |
| `backtest_regime_aware.py` | Regime-aware backtesting |
| `historical_backtest.py` | Historical signal replay |
| `standalone_backtest_script.py` | Wide-format CSV analysis |
| `study_indicators.py` | Indicator study module |
| `behavior_report.py` | Signal behavior analysis |
| `logic_analyzer.py` | Parameter sensitivity analysis |
| `edge_report.py` | Edge discovery reporting |
| `multi_period_analyzer.py` | Multi-timeframe return analysis |
| `cache_orchestrator.py` | Incremental processing + hash-based skip logic |

---

## LEGACY / ARCHIVE

| File | Location | Reason |
|------|---------|--------|
| `_research_allocator.py` | `archive/legacy/` | Underscore-prefixed inactive module |
| `cache_orchestrator.py` | `archive/` | Moved to archive (superseded) |
| `full_backfill_all_in_one.py` | `archive/` | Superseded by modular backfill scripts |

---

## DATABASES

| Database | Size | Tables | Purpose |
|----------|------|--------|---------|
| `egx_research.db` | 2.1M | 19 tables | PRIMARY research warehouse: signals, tracking, BQ, experiments, optimization |
| `candidate_pool.db` | 385K | 1 table (811 rows) | Constitutional candidate pool (append-only) |
| `portfolio_manager.db` | 108K | 5 tables | Portfolio state machine (24 candidates) |
| `portfolio_advisor.db` | 41K | 2 tables | Advisory recommendations + reports |
| `research/knowledge/knowledge_base.db` | — | 4 tables | CRL unified knowledge store |

---

## CONFIGURATION

| File | Purpose |
|------|---------|
| `config/scanner_config.py` | **SINGLE SOURCE**: 27 EGX constitutional symbols + STOCK_QUALITY tiers |
| `config/weights.json` | R1-R8 weights (r1_price:30, r2_ob:10, r3_liquidity:20, r4_htf:10, r5_avwap:8, r6_macd:4, r7_div:3, r8_demand:15) |
| `config/gates_config.json` | Gate thresholds (OB quality, liquidity quantile, etc.) |
| `config/thresholds.json` | Decision thresholds (price gates, score gates, win_thresh_r20d) |

---

## DATA FILES

| File | Size | Purpose |
|------|------|---------|
| `edge_discovery_results.json` | 44M | Full edge discovery output |
| `signal_log.json` | 3.1M | Live + historical signal log |
| `walk_forward_state.json` | 623K | Walk-forward weight history + equity curve |
| `candidate_pool.json` | 592K | Candidate pool JSON mirror |
| `research_results.json` | 392K | Weekly ML research output |
| `signal_history.json` | 281K | Per-stock signal accumulation |
| `backtest_report.json` | 251K | 5-year backtest metrics |
| `gx_research_memory.json` | 42K | GX research findings (23 items) |
| `gx_learning_memory.json` | 36K | Meta-learning ecosystem state |
| `knowledge_base.json` | 22K | Factor findings (r1-r8 statistics) |
| `learned_weights.json` | 13K | Pattern engine learned weights |
| `historical_data/*.csv` | 3.5M | Per-symbol OHLCV (29 files) |
| `egypt_stocks_5yr_data_updated.csv` | 7.2M | Wide-format 5-year OHLCV |
| `candidate_pool.parquet` | 140K | Parquet mirror of candidate pool |

---

## DOCUMENTATION

| File | Purpose |
|------|---------|
| `CONSTITUTION_VERSION.md` | **FROZEN** engine architecture, SHA-256 hashes, station definitions |
| `CLAUDE.md` | Global response policy |
| `SOURCE_OF_TRUTH.md` | Single source of truth policies |
| `AVERAGING_SYSTEM.md` | Averaging system documentation |
| `docs/LEARNING_LABS_CONSTITUTION.md` | Research labs governance |
| `docs/R1R8_EVOLUTION_ROADMAP.md` | R1-R8 evolution roadmap |
| `docs/R1R8_VIOLATION_REPORT.md` | R1-R8 violation audit |
| `docs/R1R8_CORRECTION_REPORT.md` | R1-R8 correction procedures |
| `reports/*.md` | 26 research + audit reports |
