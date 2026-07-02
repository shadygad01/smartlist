# Legacy Map

**CRL Version:** 1.0  
**Generated:** 2026-06-21  
**Policy:** Archive before remove. Delete nothing.  

---

## archive/ Contents

| File | Original Path | Status | Reuse Value |
|------|-------------|--------|-------------|
| `cache_orchestrator.py` | root | ARCHIVED (pre-CRL) | HIGH — cache layer for expensive modules |
| `full_backfill_all_in_one.py` | root | ARCHIVED (pre-CRL) | MEDIUM — reference for monolithic backfill |
| `legacy/_research_allocator.py` | root (underscore-prefixed) | ARCHIVED (CRL V1) | MEDIUM — research allocation logic |

---

## archive/legacy/ Contents

| File | Archived Date | Reason | Recovery |
|------|-------------|--------|---------|
| `_research_allocator.py` | 2026-06-21 | Underscore-prefixed, no callers, superseded by candidate_pool_builder + portfolio_manager | `cp archive/legacy/_research_allocator.py _research_allocator.py` |

---

## Pre-CRL Research Artifacts (Retained, Not Moved)

These files contain legacy research that has value as reference but is no longer
actively maintained. They are retained in their original locations to preserve
import chains.

| File | Era | Content | Current Status |
|------|-----|---------|---------------|
| `gx_research_memory.json` | Pre-CRL | 23 research items (all in `?` state — metadata only) | LEGACY_STATE — superseded by knowledge_base.db |
| `gx_learning_memory.json` | Pre-CRL | GX learning ecosystem state | LEGACY_STATE |
| `knowledge_base.json` | Pre-CRL | Factor findings (r1-r8 old naming) | LEGACY_STATE — superseded by knowledge_base.db |
| `optimization_results.json` | Pre-CRL | 11 optimization history entries | RESEARCH_OUTPUT |
| `logic_analysis_results.json` | Pre-CRL | Parameter sensitivity | RESEARCH_OUTPUT |
| `adaptive_learning_results.json` | Pre-CRL | Adaptive diagnosis | RESEARCH_OUTPUT |
| `smc_rl_weights.json` | Pre-CRL | RL weight history | RESEARCH_STATE |
| `rank_history.json` | Pre-CRL | 17 bytes, nearly empty | STALE |

---

## Dead Code Analysis

| File | Evidence | % Dead |
|------|---------|--------|
| `_research_allocator.py` | No callers found | 100% (ARCHIVED) |
| `outcome_enricher.py` | No live caller found; `extended_signal_log.json` missing | ~80% |
| `extended_logger.py` | `extended_signal_log.json` does not exist | ~80% |
| `backtest_analysis.py` | No confirmed caller | ~60% |
| `edge_report.py` | Referenced in old reports, no confirmed live caller | ~60% |

**Overall dead code estimate:** ~7% of Python files (6 of 89)  

---

## Superseded Systems

| System | Superseded By | Notes |
|--------|-------------|-------|
| `full_backfill_all_in_one.py` | 7 modular backfill scripts | Monolithic → modular in prior session |
| `cache_orchestrator.py` | Direct execution without caching | Caching deemed premature optimization |
| `_research_allocator.py` | `candidate_pool_builder.py` + `portfolio_manager.py` | Constitutional portfolio layer replaced research allocator |
| `knowledge_base.json` (old format) | `research/knowledge/knowledge_base.db` | DB is more queryable, structured |
| `gx_research_memory.json` (23 placeholder items) | `research/knowledge/knowledge_base.db → experiment_registry` | Structured registry replaces JSON |

---

## Recovery Index

All archived files are recoverable. No content was deleted.

```bash
# Recover any archived file
cp archive/legacy/<filename> <original_path>
cp archive/<filename> <original_path>

# Verify git history for any file
git log --all --full-history -- <filename>
git show <commit>:<filename>
```

---

## Future Archive Candidates

The following files may be candidates for archiving in future CRL phases if
confirmed to have no callers and no research value:

| File | Risk | Recommended Action |
|------|------|-------------------|
| `outcome_enricher.py` | LOW (no live callers) | Investigate; archive in CRL V2 if confirmed dead |
| `extended_logger.py` | LOW (output file missing) | Investigate; archive in CRL V2 if confirmed dead |
| `rank_history.json` | NEGLIGIBLE (17 bytes) | Archive in CRL V2 |
| `data.json` | UNKNOWN | Investigate purpose before archiving |
