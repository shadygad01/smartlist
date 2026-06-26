"""
Universe Snapshot — V6.1
Builds a unified 27-ticker snapshot from all available data sources.
Writes to universe_snapshot.db. Read-only on candidate_pool.db.
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone, timedelta
from pathlib import Path
from time_authority import now_cairo as _now_cairo_ta

BASE = Path(__file__).parent

_POOL_DB      = BASE / "candidate_pool.db"
_RESEARCH_DB  = BASE / "egx_research.db"
_SIGNAL_HIST  = BASE / "signal_history.json"
_CBR_DB       = BASE / "constitutional_buy_registry.db"
_SNAP_DB      = BASE / "universe_snapshot.db"

_CAIRO_TZ = _now_cairo_ta().tzinfo


# ── Source loaders ─────────────────────────────────────────────────────────────

def _load_pool() -> dict[str, dict]:
    """Latest snapshot per ticker from candidate_pool.db (READ ONLY)."""
    if not _POOL_DB.exists():
        return {}
    conn = sqlite3.connect(str(_POOL_DB))
    conn.row_factory = sqlite3.Row
    try:
        latest_ts = conn.execute(
            "SELECT MAX(snapshot_ts) FROM candidate_pool"
        ).fetchone()[0]
        if not latest_ts:
            return {}
        rows = conn.execute(
            """SELECT ticker, r2_score, final_score, entry_price, current_price, snapshot_ts
               FROM candidate_pool WHERE snapshot_ts=? AND entry_price > 0
               ORDER BY ticker,
                 ABS(r2_score - 60) ASC,
                 r2_score DESC""",
            (latest_ts,)
        ).fetchall()
        result = {}
        for r in rows:
            # First row per ticker = zone where price is closest to entry (most relevant)
            if r["ticker"] not in result:
                result[r["ticker"]] = {
                    "r2_score":      r["r2_score"],
                    "final_score":   r["final_score"],
                    "entry_price":   r["entry_price"],
                    "current_price": r["current_price"],
                    "last_scan":     (r["snapshot_ts"] or "")[:10],
                    "source":        "candidate_pool",
                }
        return result
    finally:
        conn.close()


def _load_research() -> dict[str, dict]:
    """Latest signal per ticker from egx_research.db signals table."""
    if not _RESEARCH_DB.exists():
        return {}
    conn = sqlite3.connect(str(_RESEARCH_DB))
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            """SELECT symbol, signal_date, r2_ob, adj_score, price, avg_entry
               FROM signals ORDER BY symbol, signal_date DESC"""
        ).fetchall()
        result = {}
        for r in rows:
            sym = r["symbol"]
            if sym not in result:
                result[sym] = {
                    "r2_score":      r["r2_ob"] or 0.0,
                    "final_score":   r["adj_score"] or 0.0,
                    "current_price": r["price"],
                    "entry_price":   r["avg_entry"],
                    "last_scan":     (r["signal_date"] or "")[:10],
                    "source":        "egx_research",
                }
        return result
    finally:
        conn.close()


def _load_signal_history() -> dict[str, dict]:
    """Latest scan data per ticker from signal_history.json."""
    if not _SIGNAL_HIST.exists():
        return {}
    try:
        data = json.loads(_SIGNAL_HIST.read_text())
        result = {}
        for ticker, events in data.items():
            if isinstance(events, list) and events:
                latest = max(events, key=lambda e: e.get("date", ""))
                result[ticker] = {
                    "price":      latest.get("price"),
                    "score":      latest.get("score", 0),
                    "r1":         latest.get("r1", 0),
                    "last_scan":  latest.get("date", ""),
                    "count":      len(events),
                }
        return result
    except Exception:
        return {}


def _load_constitutional_registry() -> dict[str, dict]:
    """Entry prices and buy data from constitutional_buy_registry.db."""
    if not _CBR_DB.exists():
        return {}
    conn = sqlite3.connect(str(_CBR_DB))
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            """SELECT ticker, buy_date, buy_price, buy_r2, buy_score
               FROM constitutional_buy_registry ORDER BY ticker, buy_date"""
        ).fetchall()
        result = {}
        for r in rows:
            ticker = r["ticker"]
            if ticker not in result:
                result[ticker] = {
                    "entry_price": r["buy_price"],
                    "r2_score":    r["buy_r2"],
                    "final_score": r["buy_score"],
                    "buy_date":    r["buy_date"],
                }
        return result
    finally:
        conn.close()


def _load_timeline() -> dict[str, dict]:
    """Load constitutional timeline for return_pct per ticker."""
    try:
        import sys
        sys.path.insert(0, str(BASE))
        from constitutional_timeline_engine import get_timeline
        tl = get_timeline(production_only=True)
        result: dict[str, dict] = {}
        for e in tl:
            ticker = e["ticker"]
            if ticker not in result or e["event_date"] > result[ticker]["event_date"]:
                result[ticker] = {
                    "return_pct":    e["return_pct"],
                    "entry_price":   e["entry_price"],
                    "current_price": e["current_price"],
                    "event_date":    e["event_date"],
                    "event_type":    e["event_type"],
                }
        return result
    except Exception:
        return {}


# ── Status derivation ──────────────────────────────────────────────────────────

def _derive_status(ticker: str, r2: float | None, score: float | None,
                   in_timeline: bool, return_pct: float | None,
                   has_scan_history: bool = False) -> str:
    """Return PREMIUM/ACTIVE/UNDER_REVIEW/APPROACHING/BELOW_THRESHOLD/NO_HISTORY status label."""
    if in_timeline and return_pct is not None:
        if return_pct >= 50:
            return "PREMIUM"
        elif return_pct >= 0:
            return "ACTIVE"
        else:
            return "UNDER_REVIEW"
    if r2 is not None and r2 >= 50 and score is not None and score >= 35:
        return "APPROACHING"
    if r2 is not None or has_scan_history:
        return "BELOW_THRESHOLD"
    return "NO_HISTORY"


def _derive_waiting_for(r2: float | None, score: float | None,
                        has_scan_history: bool = False,
                        status: str = "") -> str:
    """Return human-readable reason string for why ticker is waiting for constitutional entry."""
    if r2 is None or r2 == 0:
        if has_scan_history:
            return "R1=0 — Price Zone not met (score=0)"
        return "No scan data available"
    sc = score or 0.0
    if r2 >= 60 and sc >= 35:
        if status in ("PREMIUM", "ACTIVE"):
            return "READY FOR RE-ACCUMULATION"
        return "READY NOW — R2≥60, Score≥35"
    if r2 >= 60 and sc < 35:
        return f"Waiting for Score ≥35 (Score {sc:.1f}/35)"
    if r2 >= 58:
        return f"Waiting for Constitutional Trigger (R2 {r2:.1f}/60)"
    if r2 >= 55:
        return f"Waiting for Order Block Touch (R2 {r2:.1f}/60)"
    if r2 >= 50:
        if sc >= 35:
            return f"Waiting for Demand Confirmation (R2 {r2:.1f}/60)"
        return f"Waiting for Score ≥35 and Demand Confirmation (R2 {r2:.1f}/60, Score {sc:.1f}/35)"
    return f"Below Threshold — Needs R2≥50 (R2 {r2:.1f}/60)"


def _derive_action(status: str, return_pct: float | None) -> str:
    """Return actionable instruction string (HOLD/MONITOR/WATCH) for a given status."""
    if status == "PREMIUM":
        return "HOLD — TARGET HIT"
    elif status == "ACTIVE":
        return "HOLD"
    elif status == "UNDER_REVIEW":
        return "MONITOR"
    elif status == "APPROACHING":
        return "WATCH — Entry Near"
    else:
        return "MONITOR"


# ── Main builder ───────────────────────────────────────────────────────────────

def build_universe_snapshot() -> list[dict]:
    """Build and persist full 27-ticker snapshot. Returns list of row dicts."""
    from config.scanner_config import get_constitutional_universe
    universe = get_constitutional_universe()

    pool      = _load_pool()
    research  = _load_research()
    sh_data   = _load_signal_history()
    cbr       = _load_constitutional_registry()
    timeline  = _load_timeline()

    now_str = _now_cairo_ta().isoformat()
    rows: list[dict] = []

    for ticker in universe:
        # Priority: pool → research → cbr
        p = pool.get(ticker, {})
        r = research.get(ticker, {})
        c = cbr.get(ticker, {})
        t = timeline.get(ticker, {})
        in_timeline = bool(t)

        sh = sh_data.get(ticker, {})
        has_scan_history = bool(sh)

        # R2 + score — use explicit None checks to avoid treating 0 as missing
        def _first_not_none(*vals):
            """Return first non-None value from args, or None if all are None."""
            for v in vals:
                if v is not None:
                    return v
            return None
        r2    = _first_not_none(p.get("r2_score"), r.get("r2_score"), c.get("r2_score"))
        score = _first_not_none(p.get("final_score"), r.get("final_score"), c.get("final_score"))

        # Current price
        # Priority: signal_history (live scanner, freshest EOD from yfinance)
        #           > candidate_pool (may use historical CSVs, can be 1 session behind)
        #           > timeline live price
        #           > egx_research (most stale)
        current_price = (
            sh.get("price")
            or p.get("current_price")
            or t.get("current_price")
            or r.get("current_price")
        )

        # Price scan date — prefer signal_history date (most recent scan), then pool
        price_date = sh.get("last_scan") or (p.get("last_scan") if p else "") or ""

        # Entry price — timeline first: canonical v1 event price that anchors return_pct
        entry_price = (
            t.get("entry_price")
            or p.get("entry_price")
            or c.get("entry_price")
            or r.get("entry_price")
        )

        # Return pct
        return_pct = t.get("return_pct")
        if return_pct is None and current_price and entry_price and entry_price > 0:
            return_pct = round((current_price - entry_price) / entry_price * 100, 2)

        # Distance
        distance = None
        if current_price and entry_price and entry_price > 0:
            distance = round((current_price - entry_price) / entry_price * 100, 2)

        # Last scan / last price update
        last_scan         = p.get("last_scan") or r.get("last_scan") or sh.get("last_scan") or ""
        # last_price_update = the date of the PRICE DATA, not the constitutional BUY date
        last_price_update = price_date or last_scan or ""

        # Source
        source = p.get("source") if p else (r.get("source") if r else "constitutional_registry" if c else ("signal_history" if has_scan_history else "NO_HISTORY"))

        status     = _derive_status(ticker, r2, score, in_timeline, return_pct, has_scan_history)
        reason     = _derive_waiting_for(r2, score, has_scan_history, status)
        action     = _derive_action(status, return_pct)
        memory     = 1 if in_timeline else 0

        rows.append({
            "ticker":            ticker,
            "current_price":     current_price,
            "status":            status,
            "entry_zone":        entry_price,
            "distance":          distance,
            "reason":            reason,
            "action":            action,
            "memory":            memory,
            "r2_score":          r2,
            "final_score":       score,
            "last_scan":         last_scan,
            "generated_at":      now_str,
            "source":            source,
            "last_price_update": last_price_update,
            "return_pct":        return_pct,
        })

    # Write to DB
    conn = sqlite3.connect(str(_SNAP_DB))
    conn.execute("""
        CREATE TABLE IF NOT EXISTS universe_snapshot (
            ticker TEXT PRIMARY KEY,
            current_price REAL,
            status TEXT,
            entry_zone REAL,
            distance REAL,
            reason TEXT,
            action TEXT,
            memory INTEGER DEFAULT 0,
            r2_score REAL,
            final_score REAL,
            last_scan TEXT,
            generated_at TEXT,
            source TEXT,
            last_price_update TEXT,
            return_pct REAL
        )
    """)
    conn.execute("DELETE FROM universe_snapshot")
    conn.executemany(
        """INSERT INTO universe_snapshot
           (ticker, current_price, status, entry_zone, distance, reason, action,
            memory, r2_score, final_score, last_scan, generated_at, source,
            last_price_update, return_pct)
           VALUES (:ticker, :current_price, :status, :entry_zone, :distance, :reason,
                   :action, :memory, :r2_score, :final_score, :last_scan, :generated_at,
                   :source, :last_price_update, :return_pct)""",
        rows
    )
    conn.commit()
    conn.close()
    print(f"[UniverseSnapshot] Built universe_snapshot.db — {len(rows)} tickers.")
    return rows


def load_universe_snapshot() -> list[dict]:
    """Load latest universe_snapshot.db rows. Returns up to 27 rows."""
    if not _SNAP_DB.exists():
        return []
    conn = sqlite3.connect(str(_SNAP_DB))
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute("SELECT * FROM universe_snapshot ORDER BY ticker").fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


if __name__ == "__main__":
    rows = build_universe_snapshot()
    for r in rows:
        print(f"  {r['ticker']:<12} {r['status']:<15} R2={r['r2_score'] or 0:.1f}  "
              f"Price={r['current_price'] or 0:.2f}  Return={r['return_pct'] or 0:.1f}%")
