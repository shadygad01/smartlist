"""
Build Production Decision Snapshot — Phase 1 Constitutional Hardening.

After every scan builds ONE immutable record of the constitutional decision for every ticker.
production_decision_snapshot.json is the single production truth used by all downstream validators.

Called by: full_production_scan.yml and morning_email.yml after presentation_snapshot is built.
Consumed by: assert_cross_layer_consistency.py and run_consistency_report.py.
"""
from __future__ import annotations

import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

BASE = Path(__file__).parent.parent
sys.path.insert(0, str(BASE))

from constitutional_gate import evaluate, is_constitutional_buy

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


def _timeline_tickers() -> set[str]:
    """Return tickers with any v1 production event."""
    if not _TIMELINE_DB.exists():
        return set()
    try:
        con = sqlite3.connect(str(_TIMELINE_DB))
        rows = con.execute(
            "SELECT DISTINCT ticker FROM constitutional_opportunity_events "
            "WHERE signal_version='v1' OR signal_version IS NULL"
        ).fetchall()
        con.close()
        return {r[0] for r in rows}
    except Exception:
        return set()


def build_production_decision_snapshot() -> dict:
    """Build and write production_decision_snapshot.json. Returns snapshot dict."""
    if not _SNAP_DB.exists():
        print("WARN: universe_snapshot.db missing — production_decision_snapshot.json not built")
        return {}

    con = sqlite3.connect(str(_SNAP_DB))
    con.row_factory = sqlite3.Row
    db_rows = con.execute("SELECT * FROM universe_snapshot ORDER BY ticker").fetchall()
    con.close()

    sectors   = _sector_map()
    in_tl     = _timeline_tickers()
    gen_at    = datetime.now(timezone.utc).isoformat(timespec="seconds")
    decisions = []

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
        elif ticker in in_tl:
            event_type = "RE_ACCUMULATION"
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
        decisions.append(decision.as_dict())

    eligible_count = sum(1 for d in decisions if d["eligible"])
    snapshot = {
        "generated_at":  gen_at,
        "ticker_count":  len(decisions),
        "eligible_count": eligible_count,
        "decisions":     decisions,
    }
    OUTPUT_PATH.write_text(json.dumps(snapshot, indent=2))
    eligible_tickers = sorted(d["ticker"] for d in decisions if d["eligible"])
    print(f"production_decision_snapshot.json  tickers={len(decisions)}  eligible={eligible_count}")
    if eligible_tickers:
        print(f"  Eligible: {eligible_tickers}")
    return snapshot


if __name__ == "__main__":
    build_production_decision_snapshot()
