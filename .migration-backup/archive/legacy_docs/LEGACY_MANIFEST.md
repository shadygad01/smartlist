# Legacy Manifest

**CRL Version:** 1.0  
**Date:** 2026-06-21  
**Policy:** Archive before remove. Delete nothing. Every archived file is recoverable.  

---

## Archived Files

### archive/legacy/

| File | Original Path | Reason | Last Caller | Dependencies | Git Hash | Future Reuse |
|------|-------------|--------|-------------|-------------|---------|-------------|
| `_research_allocator.py` | `_research_allocator.py` | Underscore-prefixed inactive module. No callers detected. Allocation logic superseded by `candidate_pool_builder.py` + `portfolio_manager.py`. | None detected | signal_db, config | `21da006` | Portfolio allocation research experiments |

### archive/ (pre-existing)

| File | Original Path | Reason | Last Caller | Dependencies | Git Hash | Future Reuse |
|------|-------------|--------|-------------|-------------|---------|-------------|
| `cache_orchestrator.py` | `archive/cache_orchestrator.py` | Moved to archive folder in prior session. Incremental hash-based cache invalidation system. | None detected | signal_db, signal_logger | pre-CRL | Cache performance optimization if scan frequency increases |
| `full_backfill_all_in_one.py` | `archive/full_backfill_all_in_one.py` | Monolithic backfill superseded by modular scripts (backfill_signal_log, backfill_research_db, backfill_hist_features, etc.) | None detected | multiple | pre-CRL | Reference for one-shot historical data setup |

---

## Files Retained In Place (Research — Not Moved)

The following files are research-only but remain in the root because they are
actively imported by the research/learning pipeline. They are documented here
to prevent accidental promotion to production.

| File | Classification | Risk | Caller Chain |
|------|--------------|------|-------------|
| `decision_engine.py` | RESEARCH_ONLY_LAB | Cannot modify production — read-only | scheduler.py (research phase) |
| `edge_discovery.py` | RESEARCH_ONLY_LAB | No production path | research reports |
| `rule_discovery.py` | RESEARCH_ONLY_LAB | No production path | research reports |
| `pattern_discovery.py` | RESEARCH_ONLY_LAB | No production path | pattern_kb |
| `adaptive_learning.py` | RESEARCH_ONLY_LAB | Analysis-only layer | scheduler.py |
| `smc_rl_optimizer.py` | RESEARCH_ONLY_LAB | Optimization only; production_promoter gates output | scheduler.py |
| `walk_forward_backtester.py` | RESEARCH_ONLY_LAB | Gradient update not fed to production | scheduler.py |
| `early_buy_tracker.py` | RESEARCH_SHADOW | Shadow tracking only; no auto-promotion | daily_tracker |

---

## Recovery Instructions

To restore any archived file:

```bash
cp archive/legacy/<filename>.py <filename>.py
```

All archived files are fully intact — no content was removed.

---

## Manifest Log

| Date | Action | File | Operator |
|------|--------|------|---------|
| 2026-06-21 | ARCHIVED | `_research_allocator.py` → `archive/legacy/` | CRL V1 migration |
