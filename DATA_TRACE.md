# Data Trace — EGX Constitutional Investment Platform

**Generated:** 2026-06-21  
**Authority:** FULL

---

## Dashboard

### Section 1 — Constitutional Engine Status
| Field | DB | Query | Formatter | Render |
|-------|-----|-------|-----------|--------|
| 15-point checklist | `egx_research.db → signals` | `SELECT adj_score, r1..r8 FROM signals ORDER BY created_at DESC LIMIT 1` | `_section_alpha_status()` | HTML checklist |
| Active weights | `egx_research.db → signals` | factor weight columns | inline | HTML row |
| Signal count | `egx_research.db → signals` | `COUNT(*)` | inline | HTML number |
| OOS WR | `egx_research.db → bottom_quality` | `win_rate` column | inline | HTML % |

### Section 5 — Today's Constitutional Signals
| Field | Source | Path |
|-------|--------|------|
| Signal | `scan_results.json → signal` | `heatmap.py` fallback: `signal_history.json` |
| Score | `scan_results.json → score` | `_section_production_snapshot()` |
| Price | `scan_results.json → price` | inline |
| Factor Expectancy | `scan_results.json → factor_exp_score` | inline |

### Section 7 — Constitutional Performance
| Field | Source | Path |
|-------|--------|------|
| Win Rate | `egx_research.db → bottom_quality.win_rate` | `_db_scalar()` |
| Signal count | `egx_research.db → signals COUNT(*)` | `_db_scalar()` |
| Backtest WR | `backtest_report.json → win_rate` | `_load("backtest_report.json")` |
| OOS WR | `egx_research.db → bottom_quality.win_rate` | `_db_scalar()` |

### Section 11 — Portfolio Intelligence
| Field | Source | Path |
|-------|--------|------|
| Portfolio Health ★★☆☆☆ | `portfolio_advisor.db → advisor_reports.health_stars, health_label` | `_section_classification_fib()` |
| Health narrative | `portfolio_advisor.db → advisor_reports.health_narrative` | inline |
| 15 HELD positions | `portfolio_manager.db → candidate_states WHERE state='HELD'` | inline |
| 1 BUY_RESERVE | `portfolio_manager.db → candidate_states WHERE state='BUY_RESERVE'` | inline |
| 8 WATCH | `portfolio_manager.db → candidate_states WHERE state='WATCH'` | inline |
| Future Priorities | `portfolio_advisor.db → advisor_reports.summary_json['FUTURE_PRIORITY']` | inline |
| Sector concentration | `portfolio_advisor.db → advisor_reports.full_report_text` | inline |
| Recommendations | `portfolio_advisor.db → advisor_recommendations` | inline |

### Section 6 — Knowledge Base Highlights
| Field | Source | Path |
|-------|--------|------|
| Findings | `research/knowledge/knowledge_base.db → findings` | `_section_knowledge_findings()` |
| Station knowledge | `research/knowledge/knowledge_base.db → station_knowledge` | inline |

---

## Email

| Section | Field | Source |
|---------|-------|--------|
| Header | Date | `now_cairo()` |
| Header | Title | `presentation_language.EMAIL_HEADER_TITLE` |
| Ranked Opportunities | Score | `results[s]['score']` |
| Ranked Opportunities | Signal | `results[s]['signal']` |
| Ranked Opportunities | Price | `results[s]['price']` |
| Ranked Opportunities | Target | `results[s]['target']` |
| Ranked Opportunities | Signal Quality col | `presentation_language.COL_SIGNAL_QUALITY` |
| Portfolio Positions | Entry price | `open_positions.json[sym]['entry_price']` |
| Portfolio Positions | Target | `open_positions.json[sym]['target']` |
| Pattern Intelligence | win_rate | `results[s]['pattern']['win_rate']` |
| Entry Strategy | zones | `calc_entry_zones(...)` |
| Factor Contribution | R1-R8 scores | `results[s]` dict |
| Footer | Text | `presentation_language.EMAIL_FOOTER_TEXT` |

---

## Telegram

| Section | Field | Source |
|---------|-------|--------|
| Header | Platform name | `presentation_language.TG_HEADER` |
| Header | Date | `now_cairo()` |
| No-setups message | Text | `presentation_language.NO_SETUPS_MESSAGE` |
| Portfolio Positions | N positions | `open_positions.json` |
| Portfolio Positions | Entry price | `open_positions.json[sym]['entry_price']` |
| Portfolio Positions | P&L | `(current_price - entry) / entry × 100` |
| Signal | Emoji | `presentation_language.SIGNAL_EMOJI[signal.upper()]` |
| Signal | Label | `results[s]['signal']` |
| Signal | Quality | `results[s]['score']` |
| Signal | Price | `results[s]['price']` |
| Signal | Target | `results[s]['target']` |

---

## Heatmap

| Element | Source |
|---------|--------|
| Title | `presentation_language.HEATMAP_TITLE` |
| Badge | `presentation_language.HEATMAP_BADGE` |
| Score label | `presentation_language.HEATMAP_SCORE_LABEL` |
| Cell color | score → CSS gradient (inline) |
| Score | `scan_results.json → score` or `signal_history.json` |
| Position data | `open_positions.json` |
| Sector grouping | `SECTORS` list in `heatmap.py` |
| Peak scores | computed from `signal_history.json` |
