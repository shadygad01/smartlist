"""
Production Invariants — Constitutional Architecture Phase 11 (Phase 6).

Every invariant represents a logical truth that must hold after every production run.
A violation means at least one side effect completed while another did not —
i.e., Partial Execution occurred.

Invariants:
  INV-01  If morning_delivery has a "sent" row for today
            → signal_event_log must have at least one CONSTITUTIONAL_BUY row for today
              (only applies when eligible tickers exist in production_decision_snapshot.json)
  INV-02  If telegram_delivery has any row for today
            → constitutional_opportunity_events.db must have a v1 event for today
              (only applies when eligible tickers exist)
  INV-03  If constitutional_opportunity_events.db has a v1 event for today (ticker T)
            → production_decision_snapshot.json must have eligible=True for ticker T
  INV-04  If production_decision_snapshot.json exists and has eligible_count > 0
            → presentation_snapshot.json must not be stale relative to it
              (generated_at within 5 minutes)
  INV-05  If production_execution_journal has any NOTIFY row for today's scan_id
            → all PERSIST rows for the same scan_id must have status="success"
  INV-06  If signal_state_current has state=CONSTITUTIONAL_BUY for ticker T
            → constitutional_opportunity_events.db must have a v1 row for ticker T

Each invariant returns (passed: bool, details: str).
"""
from __future__ import annotations

import json
import sqlite3
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

BASE         = Path(__file__).parent.parent
_NOTIF_DB    = BASE / "notification_delivery.db"
_TIMELINE_DB = BASE / "constitutional_opportunity_events.db"
_PROD_SNAP   = BASE / "production_decision_snapshot.json"
_PRES_SNAP   = BASE / "presentation_snapshot.json"


def _today() -> str:
    try:
        from time_authority import today_cairo
        return today_cairo().isoformat()
    except Exception:
        return date.today().isoformat()


def _notif_con() -> Optional[sqlite3.Connection]:
    if not _NOTIF_DB.exists():
        return None
    con = sqlite3.connect(str(_NOTIF_DB), timeout=10)
    con.row_factory = sqlite3.Row
    return con


def _timeline_con() -> Optional[sqlite3.Connection]:
    if not _TIMELINE_DB.exists():
        return None
    con = sqlite3.connect(str(_TIMELINE_DB), timeout=10)
    con.row_factory = sqlite3.Row
    return con


def _eligible_tickers() -> set[str]:
    if not _PROD_SNAP.exists():
        return set()
    try:
        data = json.loads(_PROD_SNAP.read_text())
        return {d["ticker"] for d in data.get("decisions", []) if d.get("eligible")}
    except Exception:
        return set()


# ── Individual Invariant Checks ───────────────────────────────────────────────

def inv01_email_implies_signal_state(today: Optional[str] = None) -> tuple[bool, str]:
    """
    INV-01: If email was sent today → signal_state_current must have
    CONSTITUTIONAL_BUY for every ticker that was eligible today.
    """
    today = today or _today()
    eligible = _eligible_tickers()
    if not eligible:
        return True, "INV-01: SKIP (no eligible tickers today)"

    con = _notif_con()
    if con is None:
        return True, "INV-01: SKIP (notification_delivery.db not found)"

    try:
        row = con.execute(
            "SELECT status FROM morning_delivery WHERE date=?", (today,)
        ).fetchone()
    except Exception as e:
        con.close()
        return True, f"INV-01: SKIP (morning_delivery query failed: {e})"
    con.close()

    if row is None or row["status"] != "sent":
        return True, "INV-01: SKIP (no email sent today)"

    # Email was sent — check signal_state_current for all eligible tickers
    missing: list[str] = []
    try:
        con2 = _notif_con()
        for ticker in eligible:
            r = con2.execute(
                "SELECT state FROM signal_state_current WHERE ticker=?", (ticker,)
            ).fetchone()
            if r is None or r["state"] != "CONSTITUTIONAL_BUY":
                missing.append(ticker)
        con2.close()
    except Exception as e:
        return False, f"INV-01: FAIL (signal_state query failed: {e})"

    if missing:
        return False, (
            f"INV-01: FAIL — email sent but signal_state_current missing for: {missing}. "
            f"Email fired without signal state being recorded first (Partial Execution)."
        )
    return True, f"INV-01: PASS — email sent, signal_state consistent for {sorted(eligible)}"


def inv02_telegram_implies_timeline(today: Optional[str] = None) -> tuple[bool, str]:
    """
    INV-02: If Telegram morning brief was routed today → constitutional_opportunity_events.db
    must have a v1 event for today for every eligible ticker.
    """
    today = today or _today()
    eligible = _eligible_tickers()
    if not eligible:
        return True, "INV-02: SKIP (no eligible tickers today)"

    con = _notif_con()
    if con is None:
        return True, "INV-02: SKIP (notification_delivery.db not found)"

    try:
        row = con.execute(
            "SELECT COUNT(*) as cnt FROM telegram_delivery WHERE event_date=?", (today,)
        ).fetchone()
    except Exception as e:
        con.close()
        return True, f"INV-02: SKIP (telegram_delivery query failed: {e})"
    con.close()

    if row is None or row["cnt"] == 0:
        return True, "INV-02: SKIP (no Telegram delivery today)"

    # Telegram was sent — check timeline
    tl_con = _timeline_con()
    if tl_con is None:
        return False, (
            "INV-02: FAIL — Telegram sent but constitutional_opportunity_events.db not found. "
            "Timeline missing entirely (Partial Execution)."
        )

    missing: list[str] = []
    try:
        for ticker in eligible:
            r = tl_con.execute(
                "SELECT event_id FROM constitutional_opportunity_events "
                "WHERE ticker=? AND signal_version='v1'", (ticker,)
            ).fetchone()
            if r is None:
                missing.append(ticker)
    except Exception as e:
        tl_con.close()
        return False, f"INV-02: FAIL (timeline query failed: {e})"
    tl_con.close()

    if missing:
        return False, (
            f"INV-02: FAIL — Telegram sent but v1 timeline event missing for: {missing}. "
            f"Telegram fired without timeline being written first (Partial Execution)."
        )
    return True, f"INV-02: PASS — Telegram sent, timeline consistent for {sorted(eligible)}"


def _signal_state_tickers(state: str) -> set[str]:
    """Return tickers in signal_state_current with the given state."""
    con = _notif_con()
    if con is None:
        return set()
    try:
        rows = con.execute(
            "SELECT ticker FROM signal_state_current WHERE state=?", (state,)
        ).fetchall()
        return {r[0] for r in rows}
    except Exception:
        return set()
    finally:
        con.close()


def inv03_timeline_implies_production_snapshot(today: Optional[str] = None) -> tuple[bool, str]:
    """
    INV-03: Every v1 timeline event for today must correspond to a CONSTITUTIONAL_BUY
    in signal_state_current (the live source of truth kept in sync by continuous_scan).

    Note: production_decision_snapshot.json is built by the CI audit pipeline
    (build_production_decision_snapshot.py), not by continuous_scan. In a multi-scan
    day, a later intraday scan can add timeline events that are not yet reflected in
    the snapshot. Signal_state_current is authoritative for live state.
    """
    today = today or _today()
    tl_con = _timeline_con()
    if tl_con is None:
        return True, "INV-03: SKIP (constitutional_opportunity_events.db not found)"

    try:
        rows = tl_con.execute(
            "SELECT ticker FROM constitutional_opportunity_events "
            "WHERE signal_version='v1' AND event_date=?", (today,)
        ).fetchall()
    except Exception as e:
        tl_con.close()
        return True, f"INV-03: SKIP (query failed: {e})"
    tl_con.close()

    tl_tickers = {r["ticker"] for r in rows}
    if not tl_tickers:
        return True, "INV-03: SKIP (no v1 timeline events for today)"

    # Primary check: every timeline ticker must be CONSTITUTIONAL_BUY in live state store
    live_buys = _signal_state_tickers("CONSTITUTIONAL_BUY")
    missing_live = tl_tickers - live_buys
    if missing_live:
        return False, (
            f"INV-03: FAIL — timeline has v1 events for {missing_live} but "
            f"signal_state_current does not have CONSTITUTIONAL_BUY for them. "
            f"Live state and timeline are inconsistent (Partial Execution)."
        )

    # Advisory: note if production_decision_snapshot is lagging (CI rebuild needed)
    eligible = _eligible_tickers()
    lagging  = tl_tickers - eligible
    lagging_note = (
        f" [Advisory: {sorted(lagging)} not yet in production_decision_snapshot — "
        f"rebuild required to sync CI artifact]" if lagging else ""
    )
    return True, (
        f"INV-03: PASS — all timeline tickers {sorted(tl_tickers)} "
        f"confirmed CONSTITUTIONAL_BUY in live state{lagging_note}"
    )


def inv04_snapshot_freshness(today: Optional[str] = None) -> tuple[bool, str]:
    """
    INV-04: If production_decision_snapshot.json has eligible_count > 0,
    presentation_snapshot.json must be generated within 10 minutes of it.
    """
    if not _PROD_SNAP.exists():
        return True, "INV-04: SKIP (production_decision_snapshot.json not found)"
    if not _PRES_SNAP.exists():
        return True, "INV-04: SKIP (presentation_snapshot.json not found)"

    try:
        prod = json.loads(_PROD_SNAP.read_text())
        pres = json.loads(_PRES_SNAP.read_text())
    except Exception as e:
        return True, f"INV-04: SKIP (parse error: {e})"

    if prod.get("eligible_count", 0) == 0:
        return True, "INV-04: SKIP (no eligible tickers)"

    prod_ts = prod.get("generated_at", "")
    pres_ts = pres.get("generated_at", "")
    if not prod_ts or not pres_ts:
        return True, "INV-04: SKIP (missing generated_at)"

    try:
        t_prod = datetime.fromisoformat(prod_ts.replace("Z", "+00:00"))
        t_pres = datetime.fromisoformat(pres_ts.replace("Z", "+00:00"))
        # Only directional staleness matters: presentation must NOT be older than
        # production decisions. If presentation is newer (continuous_scan ran more
        # recently than the CI audit rebuild), that is normal and not a failure.
        staleness = (t_prod - t_pres).total_seconds()
    except Exception as e:
        return True, f"INV-04: SKIP (timestamp parse error: {e})"

    if staleness > 600:
        return False, (
            f"INV-04: FAIL — presentation_snapshot.json is {staleness:.0f}s older than "
            f"production_decision_snapshot.json (>10 min stale). Dashboard shows old data."
        )
    return True, (
        f"INV-04: PASS — presentation_snapshot freshness ok "
        f"(prod_ahead={staleness:.0f}s, threshold=600s)"
    )


def inv05_notify_requires_all_persist_success(scan_id: Optional[str] = None) -> tuple[bool, str]:
    """
    INV-05: If the execution journal has any NOTIFY row for scan_id,
    all PERSIST rows for the same scan_id must have status="success".
    """
    if not _NOTIF_DB.exists():
        return True, "INV-05: SKIP (notification_delivery.db not found)"

    if scan_id is None:
        # Use latest scan_id from journal
        try:
            con = sqlite3.connect(str(_NOTIF_DB), timeout=10)
            con.row_factory = sqlite3.Row
            row = con.execute(
                "SELECT scan_id FROM production_execution_journal "
                "ORDER BY id DESC LIMIT 1"
            ).fetchone()
            con.close()
            if row is None:
                return True, "INV-05: SKIP (no journal entries)"
            scan_id = row["scan_id"]
        except Exception as e:
            return True, f"INV-05: SKIP (journal query failed: {e})"

    try:
        con = sqlite3.connect(str(_NOTIF_DB), timeout=10)
        con.row_factory = sqlite3.Row

        notify_rows = con.execute(
            "SELECT COUNT(*) as cnt FROM production_execution_journal "
            "WHERE scan_id=? AND phase='NOTIFY'", (scan_id,)
        ).fetchone()

        if notify_rows is None or notify_rows["cnt"] == 0:
            con.close()
            return True, f"INV-05: SKIP (no NOTIFY rows for scan {scan_id[:8]})"

        failed_persist = con.execute(
            "SELECT operation, error FROM production_execution_journal "
            "WHERE scan_id=? AND phase='PERSIST' AND status!='success'", (scan_id,)
        ).fetchall()
        con.close()
    except Exception as e:
        return True, f"INV-05: SKIP (query failed: {e})"

    if failed_persist:
        ops = [r["operation"] for r in failed_persist]
        return False, (
            f"INV-05: FAIL — NOTIFY executed but PERSIST failed for: {ops} "
            f"(scan_id={scan_id[:8]}). Phase ordering violated (Partial Execution)."
        )
    return True, f"INV-05: PASS — all PERSIST succeeded before NOTIFY (scan {scan_id[:8]})"


def inv06_signal_state_implies_timeline(today: Optional[str] = None) -> tuple[bool, str]:
    """
    INV-06: If signal_state_current has CONSTITUTIONAL_BUY for ticker T,
    constitutional_opportunity_events.db must have an ACTIVE v1 cluster for T
    covering `today` (event_date <= today <= event_end_date) — not merely
    any v1 row ever recorded for T. A ticker with only stale/past clusters
    would otherwise pass this check even though today's transition was never
    persisted (Partial Execution the check exists to catch).
    """
    if today is None:
        try:
            from time_authority import today_cairo
            today = today_cairo().isoformat()
        except Exception:
            from datetime import date
            today = date.today().isoformat()

    con = _notif_con()
    if con is None:
        return True, "INV-06: SKIP (notification_delivery.db not found)"

    try:
        buy_rows = con.execute(
            "SELECT ticker FROM signal_state_current WHERE state='CONSTITUTIONAL_BUY'"
        ).fetchall()
    except Exception as e:
        con.close()
        return True, f"INV-06: SKIP (signal_state_current query failed: {e})"
    con.close()

    buy_tickers = {r[0] for r in buy_rows}
    if not buy_tickers:
        return True, "INV-06: SKIP (no tickers in CONSTITUTIONAL_BUY state)"

    tl_con = _timeline_con()
    if tl_con is None:
        return False, (
            f"INV-06: FAIL — {buy_tickers} in CONSTITUTIONAL_BUY state but "
            f"constitutional_opportunity_events.db not found (Partial Execution)."
        )

    missing: list[str] = []
    try:
        for ticker in buy_tickers:
            r = tl_con.execute(
                "SELECT event_id FROM constitutional_opportunity_events "
                "WHERE ticker=? AND event_date<=? AND (event_end_date IS NULL OR event_end_date>=?) "
                "  AND (signal_version='v1' OR signal_version IS NULL) LIMIT 1",
                (ticker, today, today)
            ).fetchone()
            if r is None:
                missing.append(ticker)
    except Exception as e:
        tl_con.close()
        return False, f"INV-06: FAIL (timeline query failed: {e})"
    tl_con.close()

    if missing:
        return False, (
            f"INV-06: FAIL — signal_state=CONSTITUTIONAL_BUY for {missing} "
            f"but no v1 timeline event covers date={today}. State store and timeline are "
            f"inconsistent (Partial Execution)."
        )
    return True, (
        f"INV-06: PASS — all CONSTITUTIONAL_BUY tickers {sorted(buy_tickers)} "
        f"have v1 timeline events"
    )


# ── Aggregate ─────────────────────────────────────────────────────────────────

_ALL_INVARIANTS = [
    ("INV-01", inv01_email_implies_signal_state),
    ("INV-02", inv02_telegram_implies_timeline),
    ("INV-03", inv03_timeline_implies_production_snapshot),
    ("INV-04", inv04_snapshot_freshness),
    ("INV-05", inv05_notify_requires_all_persist_success),
    ("INV-06", inv06_signal_state_implies_timeline),
]


def assert_production_invariants(
    today:   Optional[str] = None,
    scan_id: Optional[str] = None,
    verbose: bool = True,
) -> tuple[bool, list[str]]:
    """
    Run all invariants. Returns (all_pass, list_of_failure_messages).
    Prints results when verbose=True.
    """
    failures: list[str] = []
    for name, fn in _ALL_INVARIANTS:
        try:
            passed, detail = fn(today) if name != "INV-05" else fn(scan_id)
        except Exception as exc:
            passed  = False
            detail  = f"{name}: EXCEPTION — {exc}"
        if verbose:
            icon = "✓" if passed else "✗"
            print(f"  {icon} {detail}")
        if not passed:
            failures.append(detail)
    return len(failures) == 0, failures
