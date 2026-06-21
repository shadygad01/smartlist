# Presentation Manifest — EGX Constitutional Investment Platform

**Generated:** 2026-06-21  
**Authority:** FULL

---

## Active Presentation Files

| File | Role | Status |
|------|------|--------|
| `presentation/__init__.py` | Package marker | ACTIVE |
| `presentation/presentation_language.py` | All user-facing strings, platform identity, stock names, signal labels, structural strings | ACTIVE — imported by main.py, dashboard.py, heatmap.py |
| `presentation/presentation_theme.py` | Colors (DashTheme, EmailTheme), star ratings, badge colors, Telegram dividers | ACTIVE — imported by main.py, dashboard.py, presentation_formatter.py |
| `presentation/presentation_formatter.py` | `TelegramFormatter`, `EmailFormatter`, `DashboardFormatter` | ACTIVE — `DashboardFormatter.section_header_raw()` used by dashboard.py |
| `presentation/presentation_model.py` | `DailyBriefModel`, `SignalPresentation`, `PositionPresentation`, `PortfolioHealthPresentation` | ACTIVE — used by presentation_formatter.py |

---

## String Consolidation Status

| String Type | Location Before V2 | Location After V2 |
|-------------|--------------------|--------------------|
| Platform name | inline in main.py, dashboard.py | `presentation_language.EMAIL_HEADER_TITLE` / `DASH_TITLE` |
| Email header colors | hardcoded hex in main.py | `EMAIL_HEADER_BG`, `EMAIL_HEADER_FG`, `EMAIL_HEADER_SUBTITLE` |
| Email footer | hardcoded string in main.py | `EMAIL_FOOTER_TEXT` |
| Email subject prefix | hardcoded in main.py | `EMAIL_HEADER_TITLE` |
| Stock names (NAMES) | 27-entry dict in main.py | `STOCK_NAMES` in presentation_language.py |
| Signal emoji | inline dict in send_telegram_alerts() | `SIGNAL_EMOJI` in presentation_language.py |
| Telegram header | inline f-string | `TG_HEADER` |
| Telegram section separator | inline `━━━━━━━━━━━━━━━━━━━━━` | `TG_SECTION_SEP` |
| Telegram positions header | inline f-string | `TG_POSITIONS_HEADER` |
| Telegram no-setups message | inline multi-line string | `NO_SETUPS_MESSAGE` |
| Telegram real-time alert header | inline in send_alert_for_high_score() | `TG_REALTIME_HEADER` |
| Telegram change alert header | inline in send_change_alert() | `TG_CHANGE_HEADER` |
| Telegram research section header | inline string | `TG_RESEARCH_HEADER` |
| Dashboard title | hardcoded in build_dashboard() | `DASH_TITLE` |
| Dashboard subtitle | hardcoded in build_dashboard() | `DASH_SUBTITLE` |
| Dashboard footer | hardcoded in build_dashboard() | `DASH_FOOTER` |
| Dashboard color constants | hardcoded hex in dashboard.py | `DashTheme` (G, R, A, B, BG0-2, BOR, FG, DIM) |
| Dashboard section headers | inline f-string in _section_header() | `DashboardFormatter.section_header_raw()` |
| Email column: Signal Quality | hardcoded | `COL_SIGNAL_QUALITY` |
| Email column: Rank Score | hardcoded | `COL_RANK_SCORE` |
| Email column: Factor Contribution | hardcoded | `COL_FACTOR_CONTRIB` |
| Email section: Entry Strategy | hardcoded | `COL_ENTRY_STRATEGY` |
| Email section: Pattern Intel | hardcoded | `COL_PATTERN_INTEL` |
| Tier labels (PREMIER/MONITOR) | hardcoded ternary | `TIER_PREMIER`, `TIER_MONITOR` |
| Heatmap title | hardcoded in heatmap.py | `HEATMAP_TITLE` |
| Heatmap badge | hardcoded in heatmap.py | `HEATMAP_BADGE` |
| Heatmap score label | hardcoded "SMC Score" | `HEATMAP_SCORE_LABEL` |

---

## Archived / Dead Presentation Code

None. All presentation files are active. The `TelegramFormatter.format()` and `EmailFormatter.format()` are available for future full-refactor use.

---

## What Was NOT Changed

- R1-R8 signal engine — FROZEN
- All score computation — FROZEN  
- Entry/exit logic — FROZEN
- Weights, thresholds, gates — FROZEN
- Backtests — FROZEN
- Research/CRL — FROZEN
- Heatmap calculations — FROZEN
