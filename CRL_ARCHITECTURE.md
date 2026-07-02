# Constitutional Research Lab (CRL) Architecture

**Version:** 1.0  
**Created:** 2026-06-21  
**Authority:** FULL  

---

## Core Principle

```
Production is immutable.
Heatmap is protected.
CRL is the only place where the system is allowed to learn.
Every experiment becomes knowledge.
Every production change requires constitutional evidence.
Reuse before rewrite.
Archive before remove.
Delete nothing.
```

---

## System Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    PRODUCTION LAYER                          │
│  (IMMUTABLE — no CRL code may modify)                       │
│                                                             │
│  main.py → signal_engine.py → discount_reversal_engine.py  │
│  candidate_pool_builder.py → portfolio_manager.py           │
│  portfolio_advisor.py → heatmap.py → scheduler.py           │
└──────────────────────────┬──────────────────────────────────┘
                           │ reads ONLY (signal_db, JSON)
                           ▼
┌─────────────────────────────────────────────────────────────┐
│                    CRL RESEARCH LAYER                        │
│                                                             │
│  research/stations/    ← R1-R8 per-station experiments      │
│  research/experiments/ ← registered CRL experiments         │
│  research/backtests/   ← walk-forward, replay, validation   │
│  research/validation/  ← challenger + validation engine     │
│  research/patterns/    ← pattern discovery and KB           │
│  research/portfolio/   ← allocator and advisor experiments  │
│  research/labs/        ← symlink to labs/ (active)          │
│  research/knowledge/   ← knowledge_base.db (PRIMARY STORE)  │
│  research/reports/     ← generated research reports         │
│  research/tools/       ← CRL utilities                      │
└──────────────────────────┬──────────────────────────────────┘
                           │ evidence only
                           ▼
┌─────────────────────────────────────────────────────────────┐
│              VALIDATION GATE                                 │
│                                                             │
│  validation_engine.py                                       │
│  Requirements: ≥65% OOS WR, <20pp overfit, ≥10% expectancy │
└──────────────────────────┬──────────────────────────────────┘
                           │ APPROVED only
                           ▼
┌─────────────────────────────────────────────────────────────┐
│              PRODUCTION PROMOTER                             │
│                                                             │
│  production_promoter.py                                     │
│  Atomic write to config/ with audit trail + Telegram alert  │
└─────────────────────────────────────────────────────────────┘
```

---

## CRL Directories

### research/labs/
Symlink destination for active lab experiments.
Links to `labs/` (factor_lab, drift_lab, parameter_lab, regime_lab, interaction_lab).

### research/experiments/
CRL experiment output files.
Named: `crl_{exp_id}_{date}.json`

### research/validation/
Walk-forward validation outputs.
Challenger system reports.
`challenger_validation_report.json` → here.

### research/backtests/
Backtest outputs and replays.
`historical_backtest_results.json` → here.
`walk_forward_state.json` → here.

### research/stations/
Per-station R1-R8 research notebooks and scripts.
One subdirectory per station: `r1/`, `r2/`, ... `r8/`

### research/patterns/
Pattern discovery outputs.
`pattern_knowledge_base` access tools.

### research/portfolio/
Portfolio allocator experiments.
Challenger allocation research.

### research/reports/
Auto-generated HTML and markdown research reports.
Links: `gx_learning_report_{date}.html`, `walk_forward_report_{date}.html`

### research/knowledge/
**PRIMARY KNOWLEDGE STORE**
`knowledge_base.db` — 4 tables:
- `findings` — verified statistical conclusions
- `station_knowledge` — per-station Spearman evidence
- `experiment_registry` — all CRL experiments lifecycle
- `backtest_library` — all backtest results

### research/tools/
CRL utilities: query tools, report generators, experiment scaffolding.

---

## Experiment Lifecycle

```
1. OPEN
   Idea identified. Registered in EXPERIMENT_REGISTRY.md
   Entry in knowledge_base.db → experiment_registry

2. INVESTIGATING
   Experiment script written in research/experiments/
   Uses production data as read-only source

3. Walk-Forward
   Same date range: 2026-01-01 to 2026-06-21 (constitutional baseline)
   Same 27 symbols
   No lookahead (point-in-time constraint)

4. VERIFIED or REJECTED
   Evidence recorded in knowledge_base.db → findings
   Spearman rho, p-value, n_signals documented
   EXPERIMENT_REGISTRY.md updated

5. If VERIFIED and production-actionable:
   Constitutional Amendment Proposal drafted
   AUTHORITY: FULL required
   validation_engine.py gates applied
   production_promoter.py executes

6. ARCHIVED or SUPERSEDED
   If no longer relevant
   Legacy Manifest updated
```

---

## Knowledge Base Schema

```sql
-- Verified statistical conclusions
CREATE TABLE findings (
    research_id     TEXT PRIMARY KEY,
    question        TEXT NOT NULL,
    dataset         TEXT,
    method          TEXT,
    evidence        TEXT,        -- JSON: {rho, p_value, n, etc.}
    conclusion      TEXT NOT NULL,
    confidence      TEXT NOT NULL,  -- LOW / MEDIUM / HIGH
    future_rec      TEXT,
    related_files   TEXT,
    related_reports TEXT,
    status          TEXT DEFAULT 'VERIFIED',
    recorded_at     TEXT NOT NULL
);

-- Per-station Spearman evidence
CREATE TABLE station_knowledge (
    station         TEXT NOT NULL,    -- R1..R8, FINAL
    finding_id      TEXT PRIMARY KEY,
    metric          TEXT,             -- MAE_40, MFE_40, ret_40, low_break
    spearman_rho    REAL,
    n_signals       INTEGER,
    verdict         TEXT,
    notes           TEXT,
    recorded_at     TEXT NOT NULL
);

-- All CRL experiments lifecycle
CREATE TABLE experiment_registry (
    exp_id          TEXT PRIMARY KEY,
    title           TEXT NOT NULL,
    question        TEXT NOT NULL,
    dataset         TEXT,
    window          TEXT,
    method          TEXT,
    walk_forward    INTEGER DEFAULT 0,
    variables       TEXT,
    evidence        TEXT,
    result          TEXT,
    confidence      TEXT,
    recommendation  TEXT,
    status          TEXT DEFAULT 'OPEN',  -- OPEN/INVESTIGATING/VERIFIED/REJECTED/SUPERSEDED/ARCHIVED
    source_file     TEXT,
    created_at      TEXT NOT NULL,
    updated_at      TEXT
);

-- All backtest results
CREATE TABLE backtest_library (
    backtest_id     TEXT PRIMARY KEY,
    title           TEXT NOT NULL,
    script_file     TEXT,
    dataset         TEXT,
    date_range      TEXT,
    n_signals       INTEGER,
    win_rate        REAL,
    profit_factor   REAL,
    cagr_pct        REAL,
    max_dd_pct      REAL,
    calmar          REAL,
    notes           TEXT,
    output_files    TEXT,
    recorded_at     TEXT NOT NULL
);
```

---

## CRL Governance

### What CRL CAN do

- Read from any production database (read-only)
- Write to `research/knowledge/knowledge_base.db`
- Write to `research/experiments/` output files
- Write to `research/reports/` (HTML/JSON reports)
- Create new scripts in `research/` directories
- Register experiments in `EXPERIMENT_REGISTRY.md`
- Submit Constitutional Amendment Proposals

### What CRL CANNOT do

- Modify `discount_reversal_engine.py`
- Modify `signal_engine.py`
- Modify `config/scanner_config.py`
- Modify `config/weights.json` directly
- Modify `config/gates_config.json` directly
- Modify `config/thresholds.json` directly
- Modify `portfolio_manager.py`
- Modify `portfolio_advisor.py`
- Modify `candidate_pool_builder.py`
- Modify `heatmap.py`
- Modify `main.py`
- Modify `scheduler.py`
- Delete any file
- Bypass `validation_engine.py` + `production_promoter.py`

### Amendment Requirements

1. **Mandate:** AUTHORITY: FULL
2. **Evidence:** Spearman / quartile data (≥500 signals, p<0.01)
3. **Scope:** Implementation defect only (not conceptual preference)
4. **Validation:** Walk-forward before and after, same baseline
5. **Isolation:** Station fix and weight change cannot be in same mandate

---

## File Count Summary

| Category | Count |
|----------|-------|
| Production files | 23 |
| Research files | 35 |
| Utility files | 25 |
| Labs | 6 |
| Tests | 7 |
| Config | 4 |
| Archive | 3 |
| CRL documents | 12 |
| **Total Python** | **89** |
| **Total all files** | **200+** |
