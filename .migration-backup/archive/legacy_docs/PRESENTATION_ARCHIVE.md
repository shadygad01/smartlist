# Presentation Archive — Constitutional Presentation Rebuild V3

**Generated:** 2026-06-21  
**Authority:** MAXIMUM  
**Status:** ARCHIVED — functions exist in codebase but NOT called from active paths

---

## Archived Functions (dashboard.py)

These functions remain in dashboard.py for reference but are NOT invoked by `build_dashboard()`.

| Function | Lines (approx) | Original Role | Data Source |
|----------|----------------|---------------|-------------|
| `_section_top_ranked()` | ~1935-2100 | RANKED OPPORTUNITIES panel | scan_results.json, rank_history.json |
| `_section_top_watchlist()` | ~2100-2160 | WAIT WATCHLIST panel | scan_results.json |
| `_section_executive_summary()` | ~2160-2241 | EXECUTIVE SUMMARY | egx_research.db, deployment_log |
| `_section_alpha_status()` | ~160-285 | Constitutional Engine Status | egx_research.db (signals, validation_runs) |
| `_section_bottom_pipeline()` | ~285-375 | Signal Discovery Pipeline | egx_research.db (bottom_quality) |
| `_section_todays_learning()` | ~375-470 | Research Insights / Backbone | continuous_learning |
| `_section_current_research()` | ~470-560 | Active Research Evolution | CRL / egx_research.db |
| `_section_production_snapshot()` | ~560-650 | Today's Signals | scan_results.json |
| `_section_knowledge_findings()` | ~650-800 | Knowledge Base | research/knowledge/knowledge_base.db |
| `_section_alpha_performance()` | ~800-1000 | Constitutional Performance | egx_research.db, backtest_report.json |
| `_section_changes_since_yesterday()` | ~1000-1100 | Changes Since Yesterday | rank_history.json, egx_research.db |
| `_section_deployment_history()` | ~1100-1400 | Deployment History | egx_research.db (deployment_log) |
| `_section_classification_fib()` | ~1470-1630 | Signal Classification & Fibonacci | egx_research.db (signals, fib_outcomes) |
| `_section_pattern_intelligence()` | ~1632-1928 | Pattern Intelligence 2.0 | egx_research.db (pattern_knowledge_base) |

## Archived Functions (main.py)

These functions remain in main.py but are NOT called from `build_report()`.

| Function | Original Role |
|----------|---------------|
| `build_ez_html(r)` | Entry Strategy — Averaging Plan HTML block |
| `build_pattern_html(r)` | Pattern Intelligence — Historical Context HTML block |
| `_build_ranking_block_legacy()` | Stub (emptied) — was Premier/Monitored Opportunities |

---

## String Constants — Retained but Unused in Active Paths

| Constant | Location | Original Use |
|----------|----------|--------------|
| `COL_FACTOR_CONTRIB` | presentation_language.py | Email factor contribution column header |
| `COL_ENTRY_STRATEGY` | presentation_language.py | Email entry strategy section header |
| `COL_PATTERN_INTEL` | presentation_language.py | Email pattern intelligence section header |
| `TIER_PREMIER` | presentation_language.py | Email ranking label |
| `TIER_MONITOR` | presentation_language.py | Email ranking label |
| `COL_RANK_SCORE` | presentation_language.py | Email rank score column header |

---

## Frozen (Unchanged)

- `signal_engine.py` — R1-R8, weights, scoring — FROZEN
- `config/weights.json`, `config/thresholds.json`, `config/gates_config.json` — FROZEN
- `config/scanner_config.py` — 27-symbol universe — FROZEN
- `heatmap.py` — calculations FROZEN, presentation constants updated in prior session
- All backtest files — FROZEN
- All research/CRL files — FROZEN
- `portfolio_advisor.py`, `portfolio_manager.py`, `candidate_pool_builder.py` — FROZEN
