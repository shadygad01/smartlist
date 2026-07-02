# Legacy Presentation Report — Constitutional Presentation Rebuild V3

**Generated:** 2026-06-21  
**Authority:** MAXIMUM  
**Status:** REMOVED

---

## Removed Legacy Sections

### main.py — Removed from build_report()

| Legacy Element | Description | Replacement |
|----------------|-------------|-------------|
| `_build_ranking_block()` | Premier/Monitored Opportunities table (top 10 BUY by blended score) | Today's Opportunities from PortfolioSnapshot |
| `build_pattern_html(r)` | Pattern Intelligence block per stock | Removed |
| `build_ez_html(r)` | Entry Strategy — Averaging Plan block per stock | Removed |
| Per-stock factor table (`ind_rows`, COL_FACTOR_CONTRIB) | R1-R8 factor contribution table | Removed |
| Per-stock score breakdown (Rank Score / Expectancy / SMC) | Score metric display | Removed |
| "Premier Opportunities (#1–#5)" | Tier label | Removed |
| "Monitored Opportunities (#6–#10)" | Tier label | Removed |
| `bar()`, `pill()` per-stock rendering | UI helpers for score visualization | Removed |
| `fresh_badge()` per-stock rendering | Data freshness badge | Removed |
| Open positions block (from open_positions.json via results) | Portfolio sourced from live scan | Portfolio from PortfolioSnapshot.held_positions |
| `SUMMARY_SIGNALS` per-stock email loop | All-stock signal table | Removed |

### send_telegram_alerts() — Removed

| Legacy Element | Description | Replacement |
|----------------|-------------|-------------|
| Pattern Intelligence line (per alert) | `pi_line` with pat score, win_rate, avg_gain | Removed |
| EARLY BUY Research section | `TG_RESEARCH_HEADER` block for `early_buy_research` stocks | Removed |
| Position sizing suggestion per alert | `suggested_position_size()` result in alert | Removed |
| Per-stock signal alerts (score ≥ 35) | Full per-stock breakdown with signal details | Replaced with Morning Brief format |
| Sorted alerts loop with BUY/WAIT handling | 26-stock scan presentation | Replaced with PortfolioSnapshot |
| `ctx_str` (context label per stock) | Score context tag display | Removed |
| `raw_tag` (raw score display) | Raw vs adjusted score display | Removed |

### dashboard.py — No Longer Called from build_dashboard()

| Function | Legacy Role |
|----------|-------------|
| `_section_top_ranked()` | Ranked Opportunities from scan_results.json |
| `_section_top_watchlist()` | Wait/Watchlist from scan_results.json |
| `_section_executive_summary()` | Exec summary from egx_research.db |
| `_section_alpha_status()` | Constitutional Engine Status from egx_research.db |
| `_section_production_snapshot()` | Today's Signals from scan_results.json |
| `_section_alpha_performance()` | Performance from egx_research.db + backtest_report.json |
| `_section_todays_learning()` | CRL/Learning from continuous_learning |
| `_section_bottom_pipeline()` | Signal Discovery Pipeline from egx_research.db |
| `_section_current_research()` | Active Research from CRL |
| `_section_knowledge_findings()` | Knowledge Base (kept but not in new nav) |
| `_section_classification_fib()` | Signal Classification from egx_research.db |
| `_section_pattern_intelligence()` | Pattern Intelligence 2.0 from pattern_knowledge_base |

---

## New Architecture

### Data Source
**Single object:** `PortfolioSnapshot` (from `presentation/portfolio_snapshot.py`)

| Field | Source |
|-------|--------|
| health_stars, health_label, health_narrative | `portfolio_advisor.db → advisor_reports` |
| held_positions | `portfolio_manager.db → portfolio_snapshots.holdings_json` |
| high_conviction_buys | `portfolio_advisor.db → advisor_recommendations WHERE category='ADD'` |
| buy_with_awareness | `portfolio_advisor.db → advisor_recommendations WHERE category='FUTURE_PRIORITY'` |
| future_priorities | `advisor_reports.summary_json['FUTURE_PRIORITY']` |
| watch_list | `advisor_reports.summary_json['WATCH']` |
| sector_allocation | `portfolio_snapshots.portfolio_health_json.sector_weights` |
| max_correlation | `portfolio_snapshots.portfolio_health_json.max_held_correlation` |
| capacity_used_pct | `portfolio_snapshots.portfolio_health_json.capacity_used_pct` |
| research_insights | `research/knowledge/knowledge_base.db → findings WHERE status='VERIFIED'` |
| knowledge_count | `COUNT(*) FROM findings` |

### New Dashboard Sections (build_dashboard)
1. `_section_portfolio_header(snap)` — Health stars, narrative, capacity flags
2. `_section_today(snap)` — High conviction, future priorities, watch list
3. `_section_current_portfolio(snap)` — Holdings table with return and R2
4. `_section_portfolio_health_metrics(snap)` — Sector bars, correlation, capacity
5. `_section_research_insights(snap)` — Latest verified findings
6. `_section_system_health()` — Operational timestamps (retained)

### New Email Sections (build_report)
1. Header (EMAIL_HEADER_TITLE, date)
2. Executive Summary (health narrative, capacity, correlation)
3. Today's Opportunities (high_conviction_buys + buy_with_awareness)
4. Future Priorities
5. Current Portfolio (holdings table)
6. Portfolio Health (sector allocation, correlation, capacity)
7. Watch List
8. Research Insight (top 3 findings)
9. Footer (EMAIL_FOOTER_TEXT)

### New Telegram Format (send_telegram_alerts)
- Portfolio Health (stars, label, position count)
- Today's Opportunities (high conviction buys)
- Future Priorities
- Watch List
- Research Insight (latest finding)
- Timestamp
