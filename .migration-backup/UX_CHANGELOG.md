# UX Changelog — Constitutional Presentation Layer V2

**Version:** 2.0  
**Date:** 2026-06-21  
**Authority:** FULL  
**Scope:** Presentation ONLY — zero production logic changes

---

## Summary

Transforms the system from "technical scanner" to "professional constitutional investment platform."
Language, labels, and structure updated. Scoring, signals, and logic are frozen.

---

## Changes

### Platform Identity

| Before | After |
|--------|-------|
| EGX Institutional Swing Scanner | EGX Constitutional Morning Brief |
| EGX Scanner | EGX Constitutional Morning Brief |
| EGX Autonomous Bottom Discovery Platform | EGX Constitutional Investment Platform |
| EGX Executive Operations Center | EGX Constitutional Investment Platform |

### Email

| Before | After |
|--------|-------|
| Subject: `EGX Scanner — {date}` | Subject: `EGX Constitutional Morning Brief · {date}` |
| Header: "EGX Institutional Swing Scanner" | Header: "EGX Constitutional Morning Brief" |
| Footer: "EGX Institutional Scanner · TradingView Data Engine" | Footer: "EGX Constitutional Investment Platform · Research-Driven · Constitutionally Governed" |

### Telegram

| Before | After |
|--------|-------|
| `📊 EGX Daily Scan — {date}` | `📋 EGX Constitutional Morning Brief / {date}` |
| `{N} setup(s) above threshold` | `{N} constitutional setup(s) above monitoring threshold` |
| `No setups reached the Wait threshold (≥35) today.` | `No constitutional entry setups reached monitoring threshold today. Portfolio positions continue under constitutional management.` |
| `Signal *BUY*` | `Signal *Constitutional BUY*` |
| `SMC Score *71/100*` | `Signal Quality *71/100*` |
| `Open Positions (N)` | `Portfolio Positions (N)` |
| `EARLY BUY — Research Shadow` | `Research Tracking — Pre-Confirmation` |
| WAIT emoji: 🟡 | Watch emoji: 🔵 |

### Email HTML

| Before | After |
|--------|-------|
| "TOP RANKED OPPORTUNITIES" | "RANKED OPPORTUNITIES" |
| "0.60 × Expectancy + 0.40 × SMC Score" | "Ranked by Factor Expectancy + Signal Quality" |
| "A-TIER — Top Opportunities (#1–#5)" | "Premier Opportunities (#1–#5)" |
| "B-TIER — Watchlist (#6–#10)" | "Monitored Opportunities (#6–#10)" |
| Column: "SMC" | Column: "Signal Quality" |
| Column: "Rank Score / SMC" | Column: "Rank Score / Signal Quality" |
| Row label: "A-TIER / B-TIER" | Row label: "PREMIER / MONITOR" |
| "Open Positions — Dynamic Target" | "Portfolio Positions — Constitutional Targets" |
| "SMC Indicator Breakdown" | "Factor Contribution" |
| "ENTRY ZONES — AVERAGING STRATEGY" | "ENTRY STRATEGY — AVERAGING PLAN" |
| "PATTERN INTELLIGENCE — HISTORICAL ANALYSIS" | "PATTERN INTELLIGENCE — HISTORICAL CONTEXT" |

### Dashboard

| Before | After |
|--------|-------|
| H1: "⚡ EGX Executive Operations Center" | H1: "⚡ EGX Constitutional Investment Platform" |
| Subtitle: "EGX Autonomous Bottom Discovery Platform — Live State · 11 Sections" | Subtitle: "Research-Driven · Constitutionally Governed · 27-Symbol Universe · Live State" |
| Section 1 header: "ALPHA ENGINE STATUS" | Section 1 header: "CONSTITUTIONAL ENGINE STATUS" |
| Footer: "EGX Autonomous Bottom Discovery Platform" | Footer: "EGX Constitutional Investment Platform · Research-Driven · Constitutionally Governed" |

---

## New Files

| File | Purpose |
|------|---------|
| `presentation/presentation_language.py` | All constitutional vocabulary |
| `presentation/presentation_model.py` | Typed data containers |
| `presentation/presentation_theme.py` | Colors, stars, visual constants |
| `presentation/presentation_formatter.py` | TelegramFormatter, EmailFormatter, DashboardFormatter |
| `PRESENTATION_ARCHITECTURE.md` | Architecture documentation |
| `LANGUAGE_GUIDE.md` | Complete vocabulary mapping |
| `EMAIL_TEMPLATE_V2.md` | Email layout reference |
| `TELEGRAM_TEMPLATE_V2.md` | Telegram format reference |
| `DASHBOARD_LAYOUT_V2.md` | Dashboard layout reference |
| `UX_CHANGELOG.md` | This file |
| `PRESENTATION_STYLE_GUIDE.md` | Style decisions and rationale |

---

## What Was NOT Changed

No trading logic. No score computation. No entry/exit criteria.
No R1-R8 factors. No weights. No thresholds. No gates.
No portfolio manager. No candidate pool. No heatmap behavior.
No research lab. No knowledge base. No constitution.
