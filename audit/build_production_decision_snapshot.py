"""
Build Production Decision Snapshot — Phase 1 Constitutional Hardening.

After every scan builds ONE immutable record of the constitutional decision for every ticker.
production_decision_snapshot.json is the single production truth used by all downstream validators.

Called by: full_production_scan.yml and morning_email.yml after presentation_snapshot is built.
Consumed by: assert_cross_layer_consistency.py and run_consistency_report.py.

Phase 1 Enhancement — Decision Provenance:
Each decision record now includes:
  - scan_id         : UUID linking this decision to its scan
  - gate_version    : hash fingerprint of is_constitutional_buy / evaluate source
  - git_commit      : code version that produced the decision
  - workflow_run    : CI run ID (or 'local')
  - rules_evaluated : per-rule pass/fail audit trail
      r2_gate       : r2 >= CONST_R2_MIN
      score_gate    : score >= CONST_SCORE_MIN
      price_gate    : current_price <= entry_price  (or entry_price <= 0)
"""
from __future__ import annotations

import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

BASE = Path(__file__).parent.parent
sys.path.insert(0, str(BASE))

from constitutional_gate import evaluate, is_constitutional_buy, CONST_R2_MIN, CONST_SCORE_MIN
from scan_context import build_lineage, read_scan_context, compute_producer_version

_SNAP_DB     = BASE / "universe_snapshot.db"
_TIMELINE_DB = BASE / "constitutional_opportunity_events.db"
_POOL_DB     = BASE / "candidate_pool.db"
OUTPUT_PATH  = BASE / "production_decision_snapshot.json"


def _sector_map() -> dict[str, str]:
    """Get sector per ticker: timeline first (most authoritative), then pool."""
    sectors: dict[str, str] = {}
    if _TIMELINE_DB.exists():
        try:
            con = sqlite3.connect(str(_TIMELINE_DB))
            rows = con.execute(
                "SELECT ticker, sector FROM constitutional_opportunity_events "
                "WHERE sector IS NOT NULL AND sector != '' "
                "GROUP BY ticker ORDER BY MAX(created_at) DESC"
            ).fetchall()
            con.close()
            for ticker, sector in rows:
                sectors[ticker] = sector
        except Exception:
            pass
    if _POOL_DB.exists():
        try:
            con = sqlite3.connect(str(_POOL_DB))
            rows = con.execute(
                "SELECT ticker, sector FROM candidate_pool "
                "WHERE sector IS NOT NULL AND sector != '' "
                "GROUP BY ticker ORDER BY MAX(signal_date) DESC"
            ).fetchall()
            con.close()
            for ticker, sector in rows:
                if ticker not in sectors:
                    sectors[ticker] = sector
        except Exception:
            pass
    return sectors


def _timeline_event_types() -> dict[str, str]:
    """
    Return the event_type of each ticker's most recent v1 constitutional cluster.

    The timeline engine assigns event_type at write time using the cluster-index
    logic: event_index=0 → FIRST_BUY, event_index>0 → RE_ACCUMULATION. That
    assignment is authoritative and immutable. Reading it directly here avoids
    the re-derivation bug where a presence-only check would see a freshly-written
    FIRST_BUY event and misclassify it as RE_ACCUMULATION.
    """
    if not _TIMELINE_DB.exists():
        return {}
    try:
        con = sqlite3.connect(str(_TIMELINE_DB))
        # MAX(event_index) gives the most recent cluster's index for each ticker.
        # index=0 means first-ever → FIRST_BUY; index>0 → RE_ACCUMULATION.
        rows = con.execute(
            "SELECT ticker, MAX(event_index) as max_idx "
            "FROM constitutional_opportunity_events "
            "WHERE signal_version='v1' OR signal_version IS NULL "
            "GROUP BY ticker"
        ).fetchall()
        con.close()
        return {
            r[0]: ("FIRST_BUY" if (r[1] or 0) == 0 else "RE_ACCUMULATION")
            for r in rows
        }
    except Exception:
        return {}


def _sync_eligible_to_timeline(decisions: list[dict]) -> None:
    """
    Register eligible tickers in constitutional_opportunity_events.db via
    the register_alert_events pathway.

    daily_scan() is the normal entry point for this pathway.  When the
    production build pipeline rebuilds universe_snapshot and candidate_pool
    without running daily_scan() (e.g. after a manual refresh mid-day), newly-
    eligible tickers pass the constitutional gate and appear in
    production_decision_snapshot.json but are never written to the timeline DB.
    This function closes that gap.

    Idempotent: signal_state_store.record_transition() uses INSERT OR IGNORE
    on UNIQUE(ticker, event_date, to_state); register_alert_events() uses
    INSERT OR IGNORE on PRIMARY KEY and UNIQUE INDEX.
    """
    from constitutional_timeline_engine import register_alert_events
    from notifications.signal_state_store import (
        get_current_state, record_transition,
        STATE_CONST_BUY,
    )

    from time_authority import today_cairo
    event_date = today_cairo().isoformat()

    alert_events: list[dict] = []
    for d in decisions:
        if not d.get("eligible"):
            continue
        ticker     = d["ticker"]
        from_state = get_current_state(ticker)
        is_new     = record_transition(ticker, from_state, STATE_CONST_BUY, event_date)
        if is_new:
            alert_events.append({
                "ticker":                     ticker,
                "event_type":                 d.get("event_type", "FIRST_BUY"),
                "event_date":                 event_date,
                "constitutional_entry_price": float(d.get("constitutional_entry_price") or 0),
                "constitutional_r2":          float(d.get("constitutional_r2") or 0),
                "constitutional_score":       float(d.get("constitutional_score") or 0),
                "sector":                     d.get("sector", ""),
            })

    if alert_events:
        registered = register_alert_events(alert_events)
        if registered:
            print(f"  Timeline synced (new): {registered}")
        else:
            print(f"  Timeline sync: {len(alert_events)} event(s) already registered (idempotent)")
    else:
        eligible_in = [d["ticker"] for d in decisions if d.get("eligible")]
        if eligible_in:
            print(f"  Timeline sync: state already current for {eligible_in}")


def _build_rules_evaluated(r2: float, score: float, cp: float, ep: float) -> list[dict]:
    """
    Build per-rule audit trail decomposing the three gate conditions.
    This is provenance data only — the authoritative eligibility result
    comes from is_constitutional_buy() / evaluate() in constitutional_gate.py.
    """
    price_gate_pass = (ep <= 0) or (cp <= ep)
    pct_vs_entry = round((cp - ep) / ep * 100, 4) if ep > 0 else None

    return [
        {
            "rule":      "r2_gate",
            "name":      "Discount Quality (R2)",
            "threshold": CONST_R2_MIN,
            "value":     round(r2, 4),
            "pass":      r2 >= CONST_R2_MIN,
        },
        {
            "rule":      "score_gate",
            "name":      "Expected Reward Score",
            "threshold": CONST_SCORE_MIN,
            "value":     round(score, 4),
            "pass":      score >= CONST_SCORE_MIN,
        },
        {
            "rule":          "price_gate",
            "name":          "Price At/Below Entry Zone",
            "expression":    "current_price <= entry_price  (or entry_price <= 0)",
            "current_price": round(cp, 4),
            "entry_price":   round(ep, 4),
            "pct_vs_entry":  pct_vs_entry,
            "pass":          price_gate_pass,
            "note":          "gate passes when entry_price <= 0 (entry zone not yet established)",
        },
    ]


def build_production_decision_snapshot() -> dict:
    """Build and write production_decision_snapshot.json. Returns snapshot dict."""
    if not _SNAP_DB.exists():
        print("WARN: universe_snapshot.db missing — production_decision_snapshot.json not built")
        return {}

    scan_ctx      = read_scan_context()
    scan_id       = scan_ctx.get("scan_id", "unknown")
    gate_ver      = scan_ctx.get("gate_version", "unknown")
    arch_ver      = scan_ctx.get("architecture_version", "unknown")
    git_commit    = scan_ctx.get("git_commit", "unknown")
    workflow      = scan_ctx.get("workflow_run", "local")
    producer_ver  = compute_producer_version(__file__)

    con = sqlite3.connect(str(_SNAP_DB))
    con.row_factory = sqlite3.Row
    db_rows = con.execute("SELECT * FROM universe_snapshot ORDER BY ticker").fetchall()
    con.close()

    sectors      = _sector_map()
    tl_etype_map = _timeline_event_types()   # ticker → event_type from timeline
    gen_at       = datetime.now(timezone.utc).isoformat(timespec="seconds")
    decisions    = []

    for row in db_rows:
        r      = dict(row)
        ticker = r["ticker"]
        r2     = float(r.get("candidate_r2") or 0)
        score  = float(r.get("expected_reward_score") or 0)
        cp     = float(r.get("current_price") or 0)
        ep     = float(r.get("constitutional_entry_price") or 0)

        eligible = is_constitutional_buy(r2, score, cp, ep)
        if not eligible:
            event_type = "NONE"
        elif ticker in tl_etype_map:
            # Use the event_type the timeline engine already assigned at write time.
            # event_index=0 → FIRST_BUY; event_index>0 → RE_ACCUMULATION.
            event_type = tl_etype_map[ticker]
        else:
            event_type = "FIRST_BUY"

        decision = evaluate(
            ticker=ticker,
            r2=r2,
            score=score,
            current_price=cp,
            entry_price=ep,
            event_type=event_type,
            sector=sectors.get(ticker, ""),
            return_pct=float(r.get("return_pct") or 0),
            status=r.get("status", ""),
            generated_at=gen_at,
        )
        d = decision.as_dict()

        # Phase 1 + Phase 3 — Decision Provenance + Versioning
        d["scan_id"]              = scan_id
        d["gate_version"]         = gate_ver
        d["architecture_version"] = arch_ver
        d["producer_version"]     = producer_ver
        d["git_commit"]           = git_commit
        d["workflow_run"]         = workflow
        d["rules_evaluated"]      = _build_rules_evaluated(r2, score, cp, ep)

        decisions.append(d)

    eligible_count = sum(1 for d in decisions if d["eligible"])
    lineage = build_lineage(
        producer=__file__,
        parents=[_SNAP_DB, _TIMELINE_DB, _POOL_DB, BASE / "constitutional_gate.py"],
    )
    snapshot = {
        "scan_id":              scan_id,
        "generated_at":         gen_at,
        "ticker_count":         len(decisions),
        "eligible_count":       eligible_count,
        "gate_version":         gate_ver,
        "architecture_version": arch_ver,
        "producer_version":     producer_ver,
        "git_commit":           git_commit,
        "workflow_run":         workflow,
        "_lineage":             lineage,
        "decisions":            decisions,
    }
    OUTPUT_PATH.write_text(json.dumps(snapshot, indent=2))
    eligible_tickers = sorted(d["ticker"] for d in decisions if d["eligible"])
    print(f"production_decision_snapshot.json  tickers={len(decisions)}  eligible={eligible_count}")
    if eligible_tickers:
        print(f"  Eligible: {eligible_tickers}")

    print(f"  scan_id={scan_id}  gate_version={gate_ver}")
    _sync_eligible_to_timeline(decisions)


    return snapshot


if __name__ == "__main__":
    build_production_decision_snapshot()
