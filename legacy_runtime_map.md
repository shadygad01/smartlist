# Legacy Runtime Map — Constitutional Presentation V4

**Generated:** 2026-06-21  
**Mode:** Zero Trust — Runtime Verified  
**Authority:** MAXIMUM

---

## RUNTIME ENTRY POINTS (V4)

| Channel | Entry Point | Runtime File | Data Source |
|---------|-------------|-------------|-------------|
| Dashboard | `python dashboard.py` → `build_dashboard()` | **dashboard_v2.py** | presentation_snapshot.py |
| Email | `main.py build_report()` | **email_v2.py** | presentation_snapshot.py |
| Telegram | `main.py send_telegram_alerts()` | **telegram_v2.py** | presentation_snapshot.py |

---

## PHASE 1 — ALL RUNTIME-REACHABLE PRESENTATION OBJECTS

### V4 Active (Constitutional — called in production)

| File | Function | Status | Data Source |
|------|----------|--------|-------------|
| `presentation/presentation_snapshot.py` | `build_presentation_snapshot()` | ✅ CONSTITUTIONAL | portfolio_advisor.db, portfolio_manager.db, knowledge_base.db |
| `dashboard_v2.py` | `build_dashboard()` | ✅ CONSTITUTIONAL | PresentationSnapshot |
| `dashboard_v2.py` | `_s_header()` | ✅ CONSTITUTIONAL | PresentationSnapshot |
| `dashboard_v2.py` | `_s_opportunities()` | ✅ CONSTITUTIONAL | PresentationSnapshot.opportunities |
| `dashboard_v2.py` | `_s_future()` | ✅ CONSTITUTIONAL | PresentationSnapshot.future_priorities |
| `dashboard_v2.py` | `_s_portfolio()` | ✅ CONSTITUTIONAL | PresentationSnapshot.held_positions |
| `dashboard_v2.py` | `_s_health()` | ✅ CONSTITUTIONAL | PresentationSnapshot.sector_allocation |
| `dashboard_v2.py` | `_s_watch()` | ✅ CONSTITUTIONAL | PresentationSnapshot.watch_list |
| `dashboard_v2.py` | `_s_research()` | ✅ CONSTITUTIONAL | PresentationSnapshot.research_insights |
| `dashboard_v2.py` | `_s_system()` | ✅ CONSTITUTIONAL | scheduler_state.json, scan_status.json |
| `email_v2.py` | `build_email()` | ✅ CONSTITUTIONAL | PresentationSnapshot |
| `telegram_v2.py` | `send_morning_brief()` | ✅ CONSTITUTIONAL | PresentationSnapshot |

### V4 Wrappers (Thin — delegate to V2 runtime)

| File | Function | Delegates To |
|------|----------|--------------|
| `dashboard.py` | `build_dashboard()` | `dashboard_v2.build_dashboard()` |
| `main.py` | `build_report()` | `email_v2.build_email()` |
| `main.py` | `send_telegram_alerts()` | `telegram_v2.send_morning_brief()` |

### Dead Code — Not Runtime-Reachable

| File | Function | Legacy Content | Reachable |
|------|----------|----------------|-----------|
| `dashboard.py` | `_build_dashboard_v1()` | Old section calls, portfolio_snapshot | ❌ NOT CALLED |
| `dashboard.py` | `_section_portfolio_header()` | Old presentation | ❌ NOT CALLED |
| `dashboard.py` | `_section_today()` | Old presentation | ❌ NOT CALLED |
| `dashboard.py` | `_section_current_portfolio()` | Old R2/Entry Quality | ❌ NOT CALLED |
| `dashboard.py` | `_section_portfolio_health_metrics()` | Old metrics | ❌ NOT CALLED |
| `dashboard.py` | `_section_research_insights()` | Old research | ❌ NOT CALLED |
| `dashboard.py` | `_section_alpha_status()` | Scanner / signals | ❌ NOT CALLED |
| `dashboard.py` | `_section_bottom_pipeline()` | bottom_quality table | ❌ NOT CALLED |
| `dashboard.py` | `_section_todays_learning()` | CRL / R1-R8 labels | ❌ NOT CALLED |
| `dashboard.py` | `_section_production_snapshot()` | scan_results.json | ❌ NOT CALLED |
| `dashboard.py` | `_section_knowledge_findings()` | knowledge_base | ❌ NOT CALLED |
| `dashboard.py` | `_section_alpha_performance()` | egx_research.db | ❌ NOT CALLED |
| `dashboard.py` | `_section_changes_since_yesterday()` | rank_history.json | ❌ NOT CALLED |
| `dashboard.py` | `_section_deployment_history()` | deployment_log | ❌ NOT CALLED |
| `dashboard.py` | `_section_pattern_intelligence()` | Pattern Intelligence 2.0 | ❌ NOT CALLED |
| `dashboard.py` | `_section_top_ranked()` | Rank Score, SMC | ❌ NOT CALLED |
| `dashboard.py` | `_section_top_watchlist()` | Rank Score, SMC | ❌ NOT CALLED |
| `dashboard.py` | `_section_executive_summary()` | alpha metrics | ❌ NOT CALLED |
| `main.py` | `_build_report_v1()` | Factor tables, pattern blocks | ❌ NOT CALLED |
| `main.py` | `_send_telegram_alerts_v1()` | Old signal-based TG | ❌ NOT CALLED |
| `main.py` | `build_ez_html()` | ENTRY STRATEGY | ❌ NOT CALLED |
| `main.py` | `build_pattern_html()` | PATTERN INTELLIGENCE | ❌ NOT CALLED |
| `main.py` | `_build_ranking_block_legacy()` | Empty stub | ❌ NOT CALLED |
| `archive/legacy_presentation/` | All V1 files | All legacy content | ❌ ARCHIVED |

---

## PHASE 2 — FORBIDDEN TERM SCAN (RUNTIME-REACHABLE FILES)

Files scanned: `dashboard_v2.py`, `email_v2.py`, `telegram_v2.py`, `presentation/presentation_snapshot.py`

| Term | Result |
|------|--------|
| Pattern Intelligence | ✅ ABSENT |
| Pattern Context | ✅ ABSENT |
| Factor Contribution | ✅ ABSENT |
| Entry Strategy | ✅ ABSENT |
| Signal Score | ✅ ABSENT |
| Rank Score | ✅ ABSENT |
| Station Score | ✅ ABSENT |
| Premier | ✅ ABSENT |
| Monitor (as "Monitored") | ✅ ABSENT |
| Research Shadow | ✅ ABSENT |
| Labs | ✅ ABSENT |
| Top Ranked | ✅ ABSENT |
| Alpha Engine | ✅ ABSENT |
| Validation Score | ✅ ABSENT |
| SMC Score | ✅ ABSENT |
| Signal Quality | ✅ ABSENT |
| EGX SMC Scanner | ✅ ABSENT |
| R2 column header | ✅ ABSENT |

**Runtime Purity: 100%**

---

## PHASE 3 — DEPENDENCY GRAPH

```
PresentationSnapshot ←── portfolio_advisor.db
                     ←── portfolio_manager.db
                     ←── research/knowledge/knowledge_base.db
         │
         ├──→ dashboard_v2.build_dashboard()   [called by dashboard.py wrapper]
         ├──→ email_v2.build_email()            [called by main.build_report()]
         └──→ telegram_v2.send_morning_brief()  [called by main.send_telegram_alerts()]

DISCONNECTED (dead code, never executed):
  signal_engine → scores → scan_results.json  [old presentation sections]
  egx_research.db → [old dashboard sections]
  pattern_engine  → [old build_pattern_html]
  factor_engine   → [old build_report V1]
```

**FORBIDDEN INPUTS VERIFIED ABSENT:**
- signals ❌ (not imported by any V2 file)
- labs ❌
- pattern engine ❌
- factor engine ❌
- validation tables ❌
- research_shadow ❌
- scanner ❌
- score tables ❌
- station tables ❌

---

## ARCHIVED LEGACY FILES

Location: `archive/legacy_presentation/`

| File | Original | Reason |
|------|----------|--------|
| `dashboard_v1.py` | `dashboard.py` (pre-V4) | Full legacy dashboard with Pattern Intelligence, Rank Score, SMC |
| `main_presentation_v1.py` | `main.py` (pre-V4) | Full legacy build_report, send_telegram_alerts V1 |

---

## FINAL ACCEPTANCE TEST

| Criterion | Status |
|-----------|--------|
| Dashboard runtime = dashboard_v2.py | ✅ PASS |
| Email runtime = email_v2.py | ✅ PASS |
| Telegram runtime = telegram_v2.py | ✅ PASS |
| PresentationSnapshot is the ONLY presentation input | ✅ PASS |
| Zero runtime dependency on signals | ✅ PASS |
| Zero runtime dependency on labs | ✅ PASS |
| Zero runtime dependency on pattern engine | ✅ PASS |
| Zero runtime dependency on factor engine | ✅ PASS |
| Zero runtime dependency on validation | ✅ PASS |
| Zero runtime dependency on score tables | ✅ PASS |
| Zero legacy user-visible concepts | ✅ PASS |
| R2 references stripped from advisor text | ✅ PASS |
| Presentation Purity | ✅ 100% |
