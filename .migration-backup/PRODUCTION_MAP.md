# Production Map

**Status:** IMMUTABLE  
**Constitutional Engine Commit:** eb15b1b1a6dc930ed238bd9efa018af95b5d4f3f  
**Engine SHA-256:** 34de8666dd4afda777f03e8b542b42efa82c61056e9a982fa4438215789167d9  

---

## Production Execution Flow

```
scheduler.py (08:30 Cairo)
    │
    ▼
main.py  ──→ egx_context.py (market calendar)
    │
    ├──→ signal_engine.py (R1-R8 scoring, swings geometry)
    │        └──→ config/scanner_config.py (27 symbols)
    │
    ├──→ discount_reversal_engine.py [FROZEN]
    │        └──→ R1 gate → R2→R3→R4→R5→R6→R7→R8 → compute_final_score()
    │
    ├──→ pattern_engine.py (6-indicator pattern scoring)
    │
    ├──→ signal_logger.py  →  signal_log.json
    ├──→ signal_db.py      →  egx_research.db
    ├──→ snapshot_engine.py → feat_*/snap_* columns
    │
    ├──→ daily_tracker.py (+28 days → BQ scores)
    │
    └──→ research_report.py (weekly HTML)
             └──→ research_engine.py (ML feature importance)

scheduler.py (research cycle)
    │
    ├──→ research_engine.py → research_results.json
    ├──→ weight_optimizer.py → optimization_results.json
    ├──→ validation_engine.py → validation_runs table
    └──→ production_promoter.py → config/ (atomic write, audit logged)

candidate_pool_builder.py (daily)
    └──→ candidate_pool.db (append-only, 811 rows)
             └──→ portfolio_manager.py → portfolio_manager.db
                      └──→ portfolio_advisor.py → portfolio_advisor.db
```

---

## Production Files — NEVER MODIFY

| File | SHA-256 lock | Protection level |
|------|-------------|-----------------|
| `discount_reversal_engine.py` | 34de8666... | FROZEN — Constitutional |
| `config/scanner_config.py` | 609c46c9... | FROZEN — Universe source |
| `signal_engine.py` | — | PRODUCTION |
| `main.py` | — | PRODUCTION |
| `portfolio_manager.py` | — | PRODUCTION |
| `portfolio_advisor.py` | — | PRODUCTION |
| `candidate_pool_builder.py` | — | PRODUCTION |
| `heatmap.py` | — | PRODUCTION — SPECIAL PROTECTION |
| `scheduler.py` | — | PRODUCTION |

---

## Production Data Sources — NEVER WRITE FROM RESEARCH

| Data | Written by | Read by |
|------|-----------|--------|
| `egx_research.db.signals` | signal_db.py (via main.py) | research_engine, feature_extractor |
| `signal_log.json` | signal_logger.py | backfill, dashboard |
| `candidate_pool.db` | candidate_pool_builder.py | portfolio_manager, advisor |
| `portfolio_manager.db` | portfolio_manager.py | portfolio_advisor |
| `config/weights.json` | production_promoter.py ONLY | all scoring modules |
| `config/gates_config.json` | production_promoter.py ONLY | challenger_eligibility |
| `config/thresholds.json` | production_promoter.py ONLY | main.py |

---

## Constitutional Universe

27 symbols via `get_constitutional_universe()`:

```
ABUK.CA  ADIB.CA  ARCC.CA  BTFH.CA  CCAP.CA  COMI.CA  EAST.CA
EFID.CA  EFIH.CA  EGAL.CA  EMFD.CA  ETEL.CA  FWRY.CA  GBCO.CA
HELI.CA  HRHO.CA  ISPH.CA  JUFO.CA  MCQE.CA  OIH.CA   ORAS.CA
ORHD.CA  ORWE.CA  PHDC.CA  RAYA.CA  RMDA.CA  TMGH.CA
```

---

## Station Weights (FROZEN)

```
R4 Base Formation    30%   ← highest weight
R5 Low Protection    20%
R2 Discount Quality  15%
R6 Recovery          15%
R3 Residency         10%
R8 Volume            10%
R7 MACD              multiplier (not additive): <20→×0.50, <40→×0.75
R1 Hard Gate         reject if close >= eq (no score contribution)
```

---

## Portfolio Policy (FROZEN)

```
Target positions: 12-15 (equal weight)
Sector cap:       25%  (Industrial: inherited breach at 40%, cap enforced on new entries)
Correlation cap:  0.80 pairwise
Ranking:          R2 ONLY (final_score is anti-predictive for MFE)
State machine:    NEW → PRIMARY_BUY → BUY_RESERVE → WATCH → HELD → REDUCED → EXIT → ARCHIVED
```

---

## Heatmap Protection

`heatmap.py` is PRODUCTION with SPECIAL PROTECTION status.

DO NOT:
- Rewrite
- Replace
- Redesign
- Remove
- Rename
- Change UI
- Change output
- Change workflow

Only dependency-only repairs if imports break.
