# Presentation Architecture

**CRL Version:** 1.0  
**Created:** 2026-06-21  
**Authority:** FULL  
**Layer:** Presentation ONLY — no trading logic  

---

## Principle

```
Production logic is immutable.
Presentation is the only layer that translates output into language.
All three channels (Email, Telegram, Dashboard) share one vocabulary.
No duplicated formatting logic.
```

---

## Module Structure

```
presentation/
├── __init__.py                  ← package marker
├── presentation_language.py     ← ALL user-facing vocabulary
├── presentation_model.py        ← typed data containers
├── presentation_theme.py        ← colors, stars, visual constants
└── presentation_formatter.py    ← TelegramFormatter, EmailFormatter, DashboardFormatter
```

---

## Data Flow

```
Signal Engine (FROZEN)
    ↓ raw dict {score, signal, r1..r8, ...}
presentation_model.py
    → SignalPresentation / PositionPresentation / DailyBriefModel
    ↓ typed, translated, presentation-ready
presentation_formatter.py
    → TelegramFormatter  → Telegram message chunks
    → EmailFormatter     → HTML email body
    → DashboardFormatter → Dashboard section HTML
presentation_language.py  ← vocabulary consumed by all formatters
presentation_theme.py     ← colors/stars consumed by all formatters
```

---

## File Responsibilities

### `presentation_language.py`
- `SIGNAL_LABELS` — maps raw signal strings to constitutional vocabulary
- `SIGNAL_EMOJI` — maps signals to display emoji
- `CATEGORY_LABELS` — maps portfolio categories to display names
- `SECTION_HEADERS` — all section titles used across channels
- `translate_signal()`, `translate_bq_action()`, `translate_category()` — helpers

### `presentation_model.py`
- `SignalPresentation` — one scanner signal ready for any formatter
- `PositionPresentation` — one open position ready for display
- `PortfolioHealthPresentation` — health stars + narrative
- `DailyBriefModel` — complete daily scan data bundle

### `presentation_theme.py`
- `stars(n)` — returns ★★★☆☆ string for n ∈ {0..5}
- `signal_quality_stars(r2)` — Signal Quality stars from R2 score
- `portfolio_health_stars(score)` — Portfolio Health stars
- `signal_badge_colors(score)` — (text, bg, border) for HTML badges
- `EmailTheme` — email color constants
- `DashTheme` — dashboard color constants

### `presentation_formatter.py`
- `TelegramFormatter.format(brief)` → `list[str]` message chunks
- `EmailFormatter.subject(brief)` → subject line string
- `EmailFormatter.format(brief, inner_html)` → full HTML email
- `DashboardFormatter.section_header(key, icon)` → HTML section title

---

## What Was Changed (Presentation Only)

| File | Changed | What |
|------|---------|------|
| `main.py` | Yes | Email subject, HTML header, Telegram labels, footer, ranking labels |
| `dashboard.py` | Yes | Platform title, section header labels, footer |
| `presentation/` | Created | New shared presentation layer (4 files) |

## What Was NOT Changed

| File | Status |
|------|--------|
| `signal_engine.py` | UNCHANGED — scoring untouched |
| `discount_reversal_engine.py` | UNCHANGED |
| `candidate_pool_builder.py` | UNCHANGED |
| `portfolio_manager.py` | UNCHANGED |
| `portfolio_advisor.py` | UNCHANGED |
| `heatmap.py` | UNCHANGED |
| `config/weights.json` | UNCHANGED |
| `config/gates_config.json` | UNCHANGED |
| `config/thresholds.json` | UNCHANGED |
| R1-R8 logic | UNCHANGED |
| Score computation | UNCHANGED |
| Buy/Sell criteria | UNCHANGED |
