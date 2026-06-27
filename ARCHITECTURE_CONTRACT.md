# Constitutional Architecture Contract

**Status:** PRODUCTION CERTIFIED
**Issued:** 2026-06-27
**Certification scope:** All layers of the SmartList constitutional decision pipeline.

This document is the authoritative specification of the nine architectural contracts
that govern the constitutional production system. Each contract is enforced by a
regression test in `audit/assert_regression_suite.py` and verified by CI before
every deployment.

---

## Contract 1 — Single Decision Engine

**Rule:** Constitutional buy eligibility is determined by exactly one function:
`is_constitutional_buy(r2, score, current_price, entry_price)` in `constitutional_gate.py`.

**Enforcement:** R-01, R-03, R-04, R-15, R-17
**Prohibited:** Any file outside `constitutional_gate.py` may not re-implement the
threshold comparison `r2 >= CONST_R2_MIN and score >= CONST_SCORE_MIN`. All callers
must import and call `is_constitutional_buy()`.

---

## Contract 2 — Single Decision Snapshot

**Rule:** Exactly one file may write `production_decision_snapshot.json`:
`audit/build_production_decision_snapshot.py`. No other file may open this file for
writing.

**Enforcement:** R-14
**Rationale:** The production decision snapshot is the immutable source of truth for
all downstream rendering. Any mutation outside the builder breaks the replay guarantee.

---

## Contract 3 — Single Threshold Source

**Rule:** The numeric threshold constants `CONST_R2_MIN = 60.0` and
`CONST_SCORE_MIN = 35.0` are defined exactly once, in `constitutional_gate.py`.
All other files must import these constants — never redefine them.

**Enforcement:** R-01 (static scan of all `.py` files)
**Prohibited:** `CONST_R2_MIN = ...` or `CONST_SCORE_MIN = ...` outside
`constitutional_gate.py`.

---

## Contract 4 — Single Event Identity

**Rule:** For any constitutional buy event, the fields `ticker`, `event_date`,
`constitutional_entry_price`, and `event_type` must be identical across all layers:
timeline DB → production decision snapshot → presentation snapshot → dashboard HTML.
No mutation of these identity fields is permitted between pipeline stages.

**Enforcement:** `assert_event_chain_integrity.py` (Phase 4 identity checks)
**Rationale:** Identity mutation would mean the dashboard renders a different entry
price than what triggered the buy signal.

---

## Contract 5 — Single Timeline Source

**Rule:** All timeline events originate from `constitutional_opportunity_events.db`.
Every ticker that receives a `CONSTITUTIONAL_BUY` notification must have a
corresponding entry in this database.

**Enforcement:** R-11 (no orphan timeline events), R-16 (no orphan notifications)
**Prohibited:** Creating `signal_event_log` entries for `CONSTITUTIONAL_BUY`
without first recording the event in the timeline database.

---

## Contract 6 — Single Candidate Pool Policy

**Rule:** `universe_snapshot.py` must refuse to use a candidate pool that is older
than `_POOL_STALENESS_DAYS` (5 calendar days). A stale pool silently produces false
constitutional decisions.

**Enforcement:** R-05 (staleness guard exists in universe_snapshot.py)
**Rationale:** The candidate pool drives all R2/score inputs. Using stale pool data
produces phantom buy signals that cannot be traced to current market data.

---

## Contract 7 — Single Rendering Contract

**Rule:** Dashboard (`dashboard.py`), email (`egx_email.py`), and notification
(`notifications/scan_orchestrator.py`) renderers must consume pre-computed decisions
from `production_decision_snapshot.json` or `presentation_snapshot.json`. They must
not re-evaluate eligibility. Calls to `is_constitutional_buy()` in these files are
permitted only for display cross-checks, not for gating decisions.

**Enforcement:** R-15 (no inline gate in renderer files)
**Note:** R-15 permits calls to `is_constitutional_buy()` — it prohibits inline
threshold comparisons (`r2 >= 60 and score >= 35`).

---

## Contract 8 — Single Audit Contract

**Rule:** All audit scripts in `audit/` must use `AuditStatus` from
`audit/audit_status.py` exclusively. No script may define its own status enum,
exit code constants, or local `_IN_CI` logic.

**Enforcement:** R-18 (no duplicated AuditStatus class)
**Exit code contract:**
- `0 = PASS` — assertion ran, all checks passed
- `1 = FAIL` — production inconsistency detected; CI blocks
- `2 = SKIPPED` — prerequisite missing or validation skipped
- `3 = EXPECTED` — known dev-mode limitation (same condition → FAIL in CI)

---

## Contract 9 — Single Fingerprint Contract

**Rule:** Two fingerprints are maintained and committed after every successful
production scan:

1. `constitutional_fingerprint.json` — SHA256 of **data artifacts**:
   `production_decision_snapshot.json`, `presentation_snapshot.json`,
   `universe_snapshot.db`, `dashboard.html`, `candidate_pool.db`,
   `signal_history.json`.

2. `architecture_fingerprint.json` — SHA256 of **code and architectural files**:
   `constitutional_gate.py`, `audit/audit_status.py`, workflow YAMLs,
   `dashboard.py`, `egx_email.py`, `notifications/scan_orchestrator.py`.

**Enforcement:** `build_constitutional_fingerprint.py`,
`audit/build_architecture_fingerprint.py`
**Rationale:** Any code or data change between production runs is detectable by
comparing fingerprints. A divergence in the architecture fingerprint means
architectural drift — a regression must be filed.

---

## Regression Test Index

| Test | Contract | Description |
|------|----------|-------------|
| R-01 | 1, 3 | No duplicate `CONST_R2_MIN`/`CONST_SCORE_MIN` outside gate |
| R-02 | 1 | No 2% price buffer (`entry * 1.0x`) in eligibility paths |
| R-03 | 1, 7 | `dashboard._s_buy_signals()` uses `is_constitutional_buy()` |
| R-04 | 1 | `detect_signal_changes()` uses `is_constitutional_buy()` |
| R-05 | 6 | `universe_snapshot.py` has pool staleness guard |
| R-06 | — | `presentation_snapshot.json` not stale (>26h) |
| R-07 | 4 | No ticker appears in multiple presentation sections |
| R-08 | 5 | `new_events_today` tickers have timeline entries |
| R-09 | — | No duplicate rows in `signal_event_log` (idempotency) |
| R-10 | — | No `wf_v1` events in production output |
| R-11 | 5 | No orphan timeline events |
| R-12 | 1 | `main.py` and `dashboard.py` import from `constitutional_gate` |
| R-13 | 2 | `production_decision_snapshot.json` exists and has decisions |
| R-14 | 2 | Only `build_production_decision_snapshot.py` writes production snapshot |
| R-15 | 1, 7 | No inline gate logic in renderer files |
| R-16 | 5 | No orphan `CONSTITUTIONAL_BUY` notifications without timeline entry |
| R-17 | 1 | Engine files import from `constitutional_gate` |
| R-18 | 8 | No duplicated `AuditStatus` class outside `audit/audit_status.py` |
| R-19 | 1 | `is_constitutional_buy()` defined only in `constitutional_gate.py` |

---

*This contract is enforced automatically. Any change that violates a numbered contract
must be accompanied by an updated contract entry and a new regression test.*
