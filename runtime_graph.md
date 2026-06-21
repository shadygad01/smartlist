# Runtime Graph — EGX Constitutional Investment Platform

**Generated:** 2026-06-21  
**Authority:** FULL  
**Status:** PRODUCTION

---

## Execution Graph

```
Market Data (yfinance / TradingView)
    │
    ▼
download_data(symbol)                    main.py:analyze()
    │
    ▼
signal_engine.score_signal()             signal_engine.py
    │  R1-R8 factors, weights, gates
    │  FROZEN — not modified
    ▼
analyze(symbol) → result dict            main.py
    │  {signal, score, price, target, factor_exp_score, ...}
    ▼
daily_scan() / manual_scan()             main.py
    │
    ├── save_history(stock, r)           main.py → signal_history.json
    ├── save_scan_results(results)       main.py → scan_results.json
    ├── save_rank_history(results)       main.py → rank_history.json
    ├── db_log_signals(results)          signal_db.py → egx_research.db
    ├── log_signal(...)                  signal_logger.py → signal_log.json
    │
    ├── candidate_pool_builder.py        → candidate_pool.db
    ├── portfolio_manager.py             → portfolio_manager.db
    ├── portfolio_advisor.py             → portfolio_advisor.db
    │
    ├── build_report(results)            main.py → HTML email
    │       │
    │       └── send_email(html)         main.py → SMTP
    │
    ├── send_telegram_alerts(results)    main.py → Telegram API
    │
    └── build_dashboard()               dashboard.py → dashboard.html
```

---

## Function Map

### main.py

| Function | Caller | Output |
|----------|--------|--------|
| `download_data(symbol)` | `analyze()` | DataFrame |
| `analyze(symbol)` | `daily_scan()` | result dict |
| `build_report(results)` | `_run_scan_workflow()` | HTML string |
| `send_email(html)` | `_run_scan_workflow()` | SMTP send |
| `send_telegram_alerts(results)` | `_run_scan_workflow()` | Telegram API |
| `send_alert_for_high_score(stock, score, result)` | `continuous_scan()` | Telegram API |
| `send_change_alert(changed_stocks)` | `_run_scan_workflow()` | Telegram API |
| `build_dashboard()` | `dashboard.py:main()` | dashboard.html |
| `load_open_positions()` | many | open_positions.json |
| `save_open_positions()` | position ops | open_positions.json |

### dashboard.py

| Function | Output |
|----------|--------|
| `_section_alpha_status()` | Constitutional Engine Status HTML |
| `_section_bottom_pipeline()` | Signal Discovery Pipeline HTML |
| `_section_todays_learning()` | Research Insights HTML |
| `_section_current_research()` | Active Research HTML |
| `_section_production_snapshot()` | Today's Constitutional Signals HTML |
| `_section_knowledge_findings()` | Knowledge Base Highlights HTML |
| `_section_alpha_performance()` | Constitutional Performance HTML |
| `_section_changes_since_yesterday()` | Changes Since Yesterday HTML |
| `_section_deployment_history()` | Deployment History HTML |
| `_section_system_health()` | System Health HTML |
| `_section_classification_fib()` | Portfolio Intelligence HTML |
| `_section_pattern_intelligence()` | Pattern Intelligence HTML |
| `_section_top_ranked()` | Ranked Opportunities HTML |
| `_section_top_watchlist()` | Wait Watchlist HTML |
| `_section_executive_summary()` | Executive Summary HTML |
| `build_dashboard()` | dashboard.html (full page) |

---

## Formatter Map

| Channel | Formatter | Source |
|---------|-----------|--------|
| Dashboard HTML | `DashboardFormatter.section_header_raw()` | `presentation/presentation_formatter.py` |
| Dashboard colors | `DashTheme` (G, R, A, B, BG0-2, BOR, FG, DIM) | `presentation/presentation_theme.py` |
| Email header | `EMAIL_HEADER_TITLE`, `EMAIL_HEADER_BG`, etc. | `presentation/presentation_language.py` |
| Email footer | `EMAIL_FOOTER_TEXT` | `presentation/presentation_language.py` |
| Email columns | `COL_SIGNAL_QUALITY`, `COL_RANK_SCORE`, etc. | `presentation/presentation_language.py` |
| Telegram header | `TG_HEADER`, `TG_SECTION_SEP`, `TG_POSITIONS_HEADER` | `presentation/presentation_language.py` |
| Telegram signal emoji | `_SIGNAL_EMOJI` (from `SIGNAL_EMOJI`) | `presentation/presentation_language.py` |
| Telegram no-setups | `NO_SETUPS_MESSAGE` | `presentation/presentation_language.py` |
| Heatmap title | `HEATMAP_TITLE`, `HEATMAP_BADGE`, `HEATMAP_SCORE_LABEL` | `presentation/presentation_language.py` |
| Stock names | `STOCK_NAMES` (NAMES = STOCK_NAMES) | `presentation/presentation_language.py` |

---

## Database Map

| Database | Writer | Reader | Dashboard Section |
|----------|--------|--------|-------------------|
| `egx_research.db` | `signal_db.py` | `dashboard.py` | Constitutional Engine Status, Performance |
| `portfolio_manager.db` | `portfolio_manager.py` | `dashboard.py` | Portfolio Intelligence |
| `portfolio_advisor.db` | `portfolio_advisor.py` | `dashboard.py` | Portfolio Intelligence |
| `candidate_pool.db` | `candidate_pool_builder.py` | `dashboard.py` | Portfolio Intelligence |
| `research/knowledge/knowledge_base.db` | `knowledge_base.py` | `dashboard.py` | Knowledge Base Highlights |

---

## Cache Map

| Cache | Path | Produced by | Consumed by |
|-------|------|-------------|-------------|
| Scan results | `scan_results.json` | `main.py:save_scan_results()` | `dashboard.py`, `heatmap.py` |
| Signal history | `signal_history.json` | `main.py:save_history()` | `dashboard.py`, `heatmap.py` |
| Rank history | `rank_history.json` | `main.py:save_rank_history()` | `dashboard.py` |
| Open positions | `open_positions.json` | `main.py:save_open_positions()` | `main.py`, `heatmap.py`, `dashboard.py` |
| Candidate pool | `candidate_pool.json` | `candidate_pool_builder.py` | `dashboard.py` |
| TV quote cache | `_tv_quote_cache` (in-memory) | `tv_prefetch_all_quotes()` | `analyze()` |

---

## Presentation Layer Files

| File | Role | Imported by |
|------|------|-------------|
| `presentation/presentation_language.py` | All user-facing strings, vocab | `main.py`, `dashboard.py`, `heatmap.py` |
| `presentation/presentation_theme.py` | Colors, stars, visual constants | `main.py`, `dashboard.py`, `presentation_formatter.py` |
| `presentation/presentation_formatter.py` | `TelegramFormatter`, `EmailFormatter`, `DashboardFormatter` | `main.py`, `dashboard.py` |
| `presentation/presentation_model.py` | `DailyBriefModel`, `SignalPresentation`, etc. | `presentation_formatter.py` |

---

## Frozen Components (NEVER MODIFIED)

- `signal_engine.py` — R1-R8 factors, weights, scoring
- `config/weights.json` — factor weights
- `config/thresholds.json` — scoring thresholds
- `config/gates_config.json` — regime filter, price gate fractions
- `config/scanner_config.py` — 27-symbol constitutional universe
- All backtest files
- All research/CRL files
- Knowledge base
- Heatmap calculation logic
- Constitution
