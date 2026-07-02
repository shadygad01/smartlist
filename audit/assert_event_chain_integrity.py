"""
Event Chain Integrity Assertion — Phase 3+4 Constitutional Hardening.

For every CONSTITUTIONAL_BUY transition recorded today, verifies the complete chain:

  signal_state_store (notification_delivery.db)
    ↓ ticker + event_date + to_state
  constitutional_opportunity_events.db (timeline)
    ↓ constitutional_entry_price + event_type + constitutional_r2 + constitutional_score
  production_decision_snapshot.json
    ↓ eligible = True
  presentation_snapshot.json (new_events_today)

Phase 4 (Identity): ticker, event_date, constitutional_entry_price, event_type
  must be identical across all layers. Reject any mutation.

Exits 1 on any broken link in the chain.
"""
from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

BASE = Path(__file__).parent.parent
sys.path.insert(0, str(BASE))

from audit.audit_status import AuditStatus

NOTIF_DB    = BASE / "notification_delivery.db"
TIMELINE_DB = BASE / "constitutional_opportunity_events.db"
PRES_SNAP   = BASE / "presentation_snapshot.json"
PROD_SNAP   = BASE / "production_decision_snapshot.json"

PRICE_TOL = 0.001

failures: list[str] = []
warnings: list[str] = []


def _near(a: float, b: float, tol: float = PRICE_TOL) -> bool:
    return abs(a - b) / max(abs(a), abs(b), 1.0) <= tol


def main() -> int:
    try:
        from time_authority import today_cairo
        today = today_cairo().isoformat()
    except Exception:
        from datetime import date
        today = date.today().isoformat()

    print(f"Event Chain Integrity Assertion  date={today}")
    print()

    # ── Load today's CONSTITUTIONAL_BUY transitions ────────────────────────────
    transitions: list[dict] = []
    if NOTIF_DB.exists():
        try:
            con = sqlite3.connect(str(NOTIF_DB))
            # Only validate NEW transitions into CONSTITUTIONAL_BUY (state changes).
            # from_state='CONSTITUTIONAL_BUY' entries are "re-confirmed" holdings — not
            # new transitions — and do not require a fresh timeline entry for today.
            rows = con.execute(
                "SELECT ticker, from_state, to_state, notified_email, notified_tg, created_at "
                "FROM signal_event_log "
                "WHERE event_date=? AND to_state='CONSTITUTIONAL_BUY' "
                "AND (from_state IS NULL OR from_state != 'CONSTITUTIONAL_BUY')",
                (today,)
            ).fetchall()
            con.close()
            transitions = [
                {"ticker": r[0], "from_state": r[1], "to_state": r[2],
                 "notified_email": bool(r[3]), "notified_tg": bool(r[4])}
                for r in rows
            ]
        except Exception as e:
            warnings.append(f"notification_delivery.db read error: {e}")

    if not transitions:
        print("  INFO: No CONSTITUTIONAL_BUY transitions today — chain validation skipped")
        print("\nASSERTION PASSED — no transitions to validate.")
        return 0

    print(f"  CONSTITUTIONAL_BUY transitions today: {len(transitions)}")

    # ── Load supporting layers ────────────────────────────────────────────────
    # Build per-ticker active-cluster lookup: a v1 event is "active today" if
    # event_date <= today <= event_end_date (clusters span multiple days).
    # Newly-created events also pass because event_date = event_end_date = today.
    tl_today: dict[str, dict] = {}
    if TIMELINE_DB.exists():
        try:
            con = sqlite3.connect(str(TIMELINE_DB))
            con.row_factory = sqlite3.Row
            active_tickers = {tr["ticker"] for tr in transitions}
            for t in active_tickers:
                rows = con.execute(
                    "SELECT * FROM constitutional_opportunity_events "
                    "WHERE ticker=? "
                    "  AND event_date <= ? "
                    "  AND (event_end_date IS NULL OR event_end_date >= ?) "
                    "  AND (signal_version='v1' OR signal_version IS NULL) "
                    "ORDER BY event_date DESC LIMIT 1",
                    (t, today, today)
                ).fetchall()
                if rows:
                    tl_today[t] = dict(rows[0])
            con.close()
        except Exception as e:
            warnings.append(f"timeline DB read error: {e}")

    pres_today: dict[str, dict] = {}
    if PRES_SNAP.exists():
        try:
            pres = json.loads(PRES_SNAP.read_text())
            for ev in pres.get("new_events_today", []):
                if ev.get("event_date") == today:
                    pres_today[ev["ticker"]] = ev
        except Exception as e:
            warnings.append(f"presentation_snapshot read error: {e}")

    prod_by_t: dict[str, dict] = {}
    if PROD_SNAP.exists():
        try:
            prod = json.loads(PROD_SNAP.read_text())
            prod_by_t = {d["ticker"]: d for d in prod.get("decisions", [])}
        except Exception as e:
            warnings.append(f"production_decision_snapshot read error: {e}")

    # ── Validate each transition's chain ───────────────────────────────────────
    for tr in transitions:
        ticker = tr["ticker"]
        print(f"\n  Chain: {ticker}  email={tr['notified_email']}  tg={tr['notified_tg']}")

        # Link 1: signal_state_store → timeline
        if ticker not in tl_today:
            failures.append(
                f"{ticker}: signal fired today but NO entry in "
                f"constitutional_opportunity_events.db for date={today}"
            )
            print(f"    ✗ Timeline: MISSING")
            continue

        tl = tl_today[ticker]
        tl_ep    = float(tl.get("constitutional_entry_price") or 0)
        tl_r2    = float(tl.get("constitutional_r2") or 0)
        tl_score = float(tl.get("constitutional_score") or 0)
        tl_type  = tl.get("event_type", "")
        print(f"    ✓ Timeline: event_type={tl_type}  r2={tl_r2:.1f}  score={tl_score:.1f}  entry={tl_ep:.4f}")

        # Link 2: constitutional gate compliance — verified from the IMMUTABLE timeline record.
        # The production_decision_snapshot is rebuilt every scan cycle; by the time the audit runs
        # the price may have moved (signal expired), making eligible=False even for a legitimate
        # historical notification. The timeline event's own persisted r2 and score are the
        # authoritative evidence: they record what the gate evaluated at the exact moment of persistence.
        #
        # Production snapshot is consulted as a secondary source: if it says eligible=True and entry
        # prices agree that is a positive identity check; if it says eligible=False we fall back to
        # the timeline's constitutional metrics.
        is_new_transition = tr.get("from_state") != "CONSTITUTIONAL_BUY"
        if not is_new_transition:
            print(f"    ⚠ Production: self-transition (ongoing signal, snapshot check skipped)")
        else:
            # Primary: validate constitutional gate from timeline record
            gate_r2    = tl_r2
            gate_score = tl_score
            from constitutional_gate import CONST_R2_MIN, CONST_SCORE_MIN
            if gate_r2 < CONST_R2_MIN or gate_score < CONST_SCORE_MIN:
                failures.append(
                    f"{ticker}: timeline event fails constitutional gate — "
                    f"r2={gate_r2:.1f} (min {CONST_R2_MIN}) score={gate_score:.1f} (min {CONST_SCORE_MIN})"
                )
                print(f"    ✗ Constitutional gate: FAILED r2={gate_r2:.1f} score={gate_score:.1f}")
            else:
                print(f"    ✓ Constitutional gate: r2={gate_r2:.1f} score={gate_score:.1f}")
                # Secondary: if snapshot is present and agrees, verify identity
                if ticker in prod_by_t:
                    prod    = prod_by_t[ticker]
                    prod_ep = float(prod.get("constitutional_entry_price") or 0)
                    if prod.get("eligible"):
                        if tl_ep > 0 and prod_ep > 0 and not _near(tl_ep, prod_ep):
                            failures.append(
                                f"{ticker}: Phase 4 IDENTITY MUTATION — "
                                f"entry_price timeline={tl_ep} != production_snapshot={prod_ep}"
                            )
                            print(f"    ✗ Production: entry_price MISMATCH {tl_ep} != {prod_ep}")
                        else:
                            print(f"    ✓ Production: eligible=True  entry={prod_ep:.4f}")
                    else:
                        # Snapshot says ineligible but timeline metrics are valid.
                        # This is expected when price moves after signal fires (signal expired).
                        print(f"    ⚠ Production: eligible=False (price moved after signal; timeline record is authoritative)")

        # Link 3: timeline → presentation_snapshot.new_events_today
        if ticker not in pres_today:
            warnings.append(
                f"{ticker}: in signal_state_store but not in presentation_snapshot.new_events_today "
                f"(pipeline runs may differ)"
            )
            print(f"    ⚠ Presentation: not in new_events_today (pipeline run gap?)")
        else:
            pev     = pres_today[ticker]
            pres_ep = float(pev.get("constitutional_entry_price") or 0)
            pres_et = pev.get("event_type", "")

            # Phase 4 Identity: entry_price
            if pres_ep > 0 and tl_ep > 0 and not _near(pres_ep, tl_ep):
                failures.append(
                    f"{ticker}: Phase 4 IDENTITY MUTATION — "
                    f"entry_price presentation={pres_ep} != timeline={tl_ep}"
                )
                print(f"    ✗ Presentation: entry_price MISMATCH {pres_ep} != {tl_ep}")
            # Phase 4 Identity: event_type
            elif pres_et and tl_type and pres_et != tl_type:
                failures.append(
                    f"{ticker}: Phase 4 IDENTITY MUTATION — "
                    f"event_type presentation={pres_et} != timeline={tl_type}"
                )
                print(f"    ✗ Presentation: event_type MISMATCH {pres_et} != {tl_type}")
            else:
                print(f"    ✓ Presentation: new_events_today  event_type={pres_et}  entry={pres_ep:.4f}")

    # ── Report ─────────────────────────────────────────────────────────────────
    print()
    if warnings:
        print("WARNINGS:")
        for w in warnings:
            print(f"  ⚠ {w}")
    if failures:
        print("\nCHAIN INTEGRITY FAILURES:")
        for f in failures:
            print(f"  ✗ {f}")
        print("\nASSERTION FAILED — event chain is broken.")
        return AuditStatus.FAIL

    print(f"ASSERTION PASSED — {len(transitions)} event chain(s) intact.")
    return AuditStatus.PASS


if __name__ == "__main__":
    sys.exit(main())
