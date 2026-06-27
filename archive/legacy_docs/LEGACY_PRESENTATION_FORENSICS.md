# Legacy Presentation Forensics — Constitutional Forensic Investigation

**Generated:** 2026-06-21  
**Mode:** ZERO TRUST — RUNTIME VERIFIED  
**Authority:** MAXIMUM

---

## PHASE 1 — ALL LEGACY OCCURRENCES FOUND

### ACTIVE (Runtime-Reachable) — Before This Session

| File | Line | Function | Term | Runtime Path | Content |
|------|------|----------|------|-------------|---------|
| main.py | 2507 | send_change_email → _stock_card | Pattern Intelligence | send_change_email() → _stock_card() | `🧠 Pattern Intelligence` in HTML |
| main.py | 2604 | send_change_email → _stock_card | Rank Score | send_change_email() → _stock_card() | `Rank Score` label in HTML |
| main.py | 2614 | send_change_email → _stock_card | SMC | send_change_email() → _stock_card() | `SMC` label in HTML |
| main.py | 2718 | send_change_email | EGX SMC Scanner | send_change_email() | `EGX SMC Scanner © 2026` in footer |
| main.py | 1309 | build_report | R2 | build_report() | `r2` value in portfolio table |
| main.py | 1331 | build_report | R2 | build_report() | `<th>R2</th>` column header |
| main.py | 2699 | send_change_alert | Signal Quality | send_change_alert() → Telegram | `Signal Quality *score/100*` in message |
| main.py | 2727 | __main__ | EGX SMC Scanner | startup print | `EGX SMC Scanner — GitHub Actions Mode` |
| main.py | 1860 | send_alert_for_high_score | Signal Quality | send_alert_for_high_score() → Telegram | `Signal Quality *score/100*` |
| main.py | 1844-1851 | send_alert_for_high_score | Pattern Intelligence | send_alert_for_high_score() → Telegram | Pattern pi_line block |
| dashboard.py | 2342 | _section_current_portfolio | R2 | build_dashboard() | `r2 = p.get("r2_score")` |
| dashboard.py | 2368 | _section_current_portfolio | R2 | build_dashboard() | `<th>R2</th>` column header |

### DEAD CODE (Not Runtime-Reachable) — Before This Session

| File | Lines | Function | Legacy Content | Caller |
|------|-------|----------|----------------|--------|
| dashboard.py | 1636-1928 | _section_pattern_intelligence() | "Pattern Intelligence 2.0", pattern tables | NOT called by build_dashboard() |
| dashboard.py | 1935-2100 | _section_top_ranked() | "Rank Score", "SMC", ranked opportunities | NOT called by build_dashboard() |
| dashboard.py | 2100-2165 | _section_top_watchlist() | "Rank Score", "SMC", "SMC" | NOT called by build_dashboard() |
| dashboard.py | 2165-2241 | _section_executive_summary() | alpha metrics | NOT called by build_dashboard() |
| dashboard.py | 160-285 | _section_alpha_status() | signals table, egx_research.db | NOT called by build_dashboard() |
| dashboard.py | 285-375 | _section_bottom_pipeline() | bottom_quality table | NOT called by build_dashboard() |
| dashboard.py | 375-470 | _section_todays_learning() | CRL / research | NOT called by build_dashboard() |
| dashboard.py | 470-560 | _section_current_research() | CRL evolution | NOT called by build_dashboard() |
| dashboard.py | 560-650 | _section_production_snapshot() | scan_results.json, "SMC Score" | NOT called by build_dashboard() |
| dashboard.py | 650-800 | _section_knowledge_findings() | knowledge_base | NOT called by build_dashboard() |
| dashboard.py | 800-1000 | _section_alpha_performance() | egx_research.db, backtest | NOT called by build_dashboard() |
| dashboard.py | 1000-1100 | _section_changes_since_yesterday() | rank_history.json | NOT called by build_dashboard() |
| dashboard.py | 1100-1400 | _section_deployment_history() | deployment_log | NOT called by build_dashboard() |
| dashboard.py | 1470-1630 | _section_classification_fib() | signals table, fib_outcomes | NOT called by build_dashboard() |
| main.py | 1107-1200 | build_pattern_html() | "PATTERN INTELLIGENCE" | NOT called by build_report() |
| main.py | 1040-1103 | build_ez_html() | "ENTRY STRATEGY" | NOT called by build_report() |
| heatmap.py | 170 | HTML meta | SMC | meta tag only, standalone file |

---

## PHASE 2 — RUNTIME TRACE

### build_dashboard()
```
build_dashboard()
  → build_portfolio_snapshot()          [portfolio_advisor.db, portfolio_manager.db, knowledge_base.db]
  → _section_portfolio_header(snap)    [snap.health_stars, snap.health_label, snap.health_narrative]
  → _section_today(snap)               [snap.high_conviction_buys, snap.future_priorities, snap.watch_list]
  → _section_current_portfolio(snap)   [snap.held_positions]
  → _section_portfolio_health_metrics(snap) [snap.sector_allocation, snap.max_correlation]
  → _section_research_insights(snap)   [snap.research_insights, snap.knowledge_count]
  → _section_system_health()           [scheduler_state.json, scan_status.json]
```
No signal engine. No egx_research.db. No scan_results.json.

### build_report()
```
build_report()
  → build_portfolio_snapshot()          [portfolio_advisor.db, portfolio_manager.db, knowledge_base.db]
  → Renders: exec_summary, opp_block, future_block, portfolio_block, health_block, watch_block, research_block
```
No signal engine. No factor tables. No pattern tables.

### send_telegram_alerts()
```
send_telegram_alerts()
  → build_portfolio_snapshot()          [portfolio_advisor.db, portfolio_manager.db, knowledge_base.db]
  → Renders: health, opportunities, future priorities, watch list, research insight
```

---

## PHASE 3 — DEPENDENCY GRAPH

```
PortfolioSnapshot ←─── portfolio_advisor.db
                  ←─── portfolio_manager.db
                  ←─── knowledge_base.db
        │
        ├──→ build_dashboard()
        ├──→ build_report() (email)
        └──→ send_telegram_alerts()

DISCONNECTED (dead code, never called):
  signal_engine → scores → scan_results.json → [old sections]
  egx_research.db → [old sections]
  pattern_engine → [old sections]
```

---

## PHASE 4 — LEGACY SCORE (AFTER FIXES)

| Channel | Legacy % | Constitutional % |
|---------|----------|-----------------|
| Dashboard HTML | 0% | 100% |
| Email (build_report) | 0% | 100% |
| Telegram (morning brief) | 0% | 100% |
| Change Alert Email (send_change_email) | 0% | 100% |
| Real-time Alert Telegram (send_alert_for_high_score) | 0% | 100% |
| Change Alert Telegram (send_change_alert) | 0% | 100% |
| Heatmap | 0%* | 100%* |

*Heatmap calculations frozen per constitutional rules; presentation strings already updated in prior session.

---

## PHASE 13 — PRESENTATION PURITY TEST

**Dashboard:**
- Fields displayed: Portfolio Health, Holdings, Opportunities, Future Priorities, Watch List, Sector Allocation, Correlation, Research Insights, Knowledge Count
- All sourced from PortfolioSnapshot
- Purity: **100%**

**Email:**
- Sections: Executive Summary, Opportunities, Future Priorities, Portfolio, Health, Watch, Research
- All sourced from PortfolioSnapshot
- Purity: **100%**

**Telegram:**
- Sections: Health, Opportunities, Priorities, Watch, Research
- All sourced from PortfolioSnapshot
- Purity: **100%**

**Overall Presentation Purity: 100%**
**Legacy Fields Remaining: 0**
