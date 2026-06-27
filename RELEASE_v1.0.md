# SmartList v1.0 — Constitutional Production Release

**Release date:** 2026-06-27
**Tag:** `constitutional-v1.0-certified`
**Branch:** `main`
**Certification:** PASS — 11 PASS | 0 FAIL | 1 EXPECTED (dev-mode staleness only)

---

## Architecture Completed

This release formalizes the Constitutional Production Architecture — a set of nine
inviolable contracts that govern every constitutional buy decision from data ingestion
through signal delivery.

**Constitutional Gate:** A single function `is_constitutional_buy(r2, score, current_price, entry_price)`
in `constitutional_gate.py` is the sole arbiter of buy eligibility. Thresholds are
`CONST_R2_MIN = 60.0` and `CONST_SCORE_MIN = 35.0` with zero price buffer.

**Production Decision Snapshot:** `production_decision_snapshot.json` is the single
immutable record of all 27 constitutional decisions per run. Only
`audit/build_production_decision_snapshot.py` may write it.

**Shared Audit Contract:** `audit/audit_status.py` defines the single `AuditStatus` enum
(PASS=0, FAIL=1, SKIPPED=2, EXPECTED=3). All 16 audit scripts import from it. No local
implementations exist anywhere in the codebase.

---

## Major Fixes (Phases 1–10 constitutional hardening)

- **Inline gate violation fixed** — `presentation/presentation_snapshot.py` was
  re-implementing `r2 >= 60 and score >= 35` inline; replaced with
  `is_constitutional_buy()` call
- **Stale candidate pool guard** — `universe_snapshot.py` now refuses pools older
  than 5 days, eliminating phantom buy signals from stale data
- **Signal state false positives** — `detect_signal_changes()` and dashboard
  `_s_buy_signals()` now call the gate function, not inline thresholds
- **Event chain integrity** — assertion now correctly distinguishes new state
  transitions from re-confirmed holdings (from_state != to_state filter)
- **2% price buffer removed** — entry price tolerance set to zero (strict)
- **UTC+2 vs UTC+3 timezone** — time authority unified under `time_authority.py`
  (`Africa/Cairo` via `ZoneInfo`); all cron offsets corrected to UTC+3

---

## Production Certification

**Certification runner:** `audit/run_consistency_report.py`

| Assertion | Status |
|-----------|--------|
| Decision Consistency | PASS |
| Full Universe Replay (27/27) | PASS |
| Cross-Layer Consistency | PASS |
| Rendered Output Validation | PASS |
| Event Chain Integrity | PASS |
| Data Freshness | EXPECTED (dev-mode staleness) |
| Workflow Completeness | PASS |
| Decision Replay | PASS |
| Regression Suite (19/19) | PASS |
| Presentation Consistency | PASS |
| Price Consistency | PASS |
| CI Protection Gate | PASS |

CI strict mode: in production GitHub Actions, EXPECTED and SKIPPED are promoted
to FAIL — no production run may deploy with skipped validations.

---

## Known Limitations

- `candidate_pool` is rebuilt by the full production scan. Between scans (>5 days),
  `Data Freshness` returns EXPECTED in dev mode and FAIL in CI. This is expected and
  intentional — stale pools must be refreshed before CI passes.
- No current eligible buy signals (`eligible=0`). All 27 universe tickers have prices
  above constitutional entry (typical outside a market correction).

---

## Repository Structure

```
smartlist/
├── constitutional_gate.py          # Single decision engine — DO NOT modify thresholds
├── constitutional_timeline_engine.py
├── constitutional_opportunity_engine.py
├── candidate_pool_builder.py
├── universe_snapshot.py
├── time_authority.py
├── price_authority.py
├── dashboard.py
├── egx_email.py
├── main.py
├── signal_db.py
├── signal_engine.py
├── audit/
│   ├── audit_status.py             # Single AuditStatus enum — Contract 8
│   ├── run_consistency_report.py   # Constitutional Production Certification
│   ├── assert_*.py                 # 12 constitutional assertions
│   ├── build_*.py                  # Snapshot / fingerprint builders
│   └── golden_master/              # Golden master fixtures
├── notifications/
├── operations/
├── presentation/
├── .github/workflows/
│   ├── morning_email.yml           # 07:30 Cairo (04:30 UTC) Sun–Thu
│   └── full_production_scan.yml    # Full pipeline on dispatch
├── ARCHITECTURE_CONTRACT.md        # 9 architectural contracts (authoritative)
├── CONSTITUTION_VERSION.md         # Constitution versioning
└── SOURCE_OF_TRUTH.md             # Data provenance documentation
```

---

## Certification Artifacts

All committed to `main` and fingerprinted:

| File | Purpose |
|------|---------|
| `constitutional_fingerprint.json` | SHA256 of all data artifacts |
| `architecture_fingerprint.json` | SHA256 of all code/architectural files |
| `consistency_report.json` | Machine-readable certification results |
| `production_decision_snapshot.json` | Immutable 27-ticker decision record |
| `ARCHITECTURE_CONTRACT.md` | 9 architectural contracts with enforcement index |

---

## Regression Protection Summary

19 regression tests (`R-01` through `R-19`) permanently enforce every bug that was
previously fixed. CI fails on any regression before deployment.

Key regressions guarded:
- No inline gate logic outside `constitutional_gate.py` (R-01, R-15, R-19)
- No price buffer in eligibility paths (R-02)
- No stale candidate pool driving decisions (R-05)
- No duplicate tickers in presentation sections (R-07)
- No orphan notifications without timeline entry (R-16)
- No duplicated `AuditStatus` class (R-18)

---

## Migration Summary

| Area | Before | After |
|------|--------|-------|
| Gate function | Inline in multiple files | Single `is_constitutional_buy()` in `constitutional_gate.py` |
| Thresholds | Defined in 3+ places | Single `CONST_R2_MIN` / `CONST_SCORE_MIN` in gate |
| Audit exit codes | Inconsistent (0/1 only) | Standardized 0/1/2/3 via `AuditStatus` |
| CI mode detection | Local `_IN_CI` in each file | Single `is_ci()` in `audit/audit_status.py` |
| Stale data in dev | FAIL | EXPECTED (non-blocking) |
| Stale data in CI | — | FAIL (blocking) |
| Price tolerance | 2% buffer | Zero (strict) |
| Timezone | UTC+2 hardcoded | UTC+3 via `ZoneInfo("Africa/Cairo")` |

---

*This release freezes the constitutional production baseline. All future research and
feature development branches from this certified state.*
