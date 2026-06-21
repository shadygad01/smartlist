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

BASE = Path(__file__).parent

_POOL_DB      = BASE / "candidate_pool.db"
_RESEARCH_DB  = BASE / "egx_research.db"
_SIGNAL_HIST  = BASE / "signal_history.json"
_CBR_DB       = BASE / "constitutional_buy_registry.db"
_SNAP_DB      = BASE / "universe_snapshot.db"

_CAIRO_TZ = timezone(timedelta(hours=2))


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
               FROM candidate_pool WHERE snapshot_ts=?""",
            (latest_ts,)
        ).fetchall()
        result = {}
        for r in rows:
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


def _load_signal_history() -> dict[str, float]:
    """Latest price per ticker from signal_history.json."""
    if not _SIGNAL_HIST.exists():
        return {}
    try:
        data = json.loads(_SIGNAL_HIST.read_text())
        prices = {}
        for ticker, events in data.items():
            if isinstance(events, list) and events:
                latest = max(events, key=lambda e: e.get("date", ""))
                prices[ticker] = latest.get("price")
        return prices
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
        tl = get_timeline()
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
                   in_timeline: bool, return_pct: float | None) -> str:
    if in_timeline and return_pct is not None:
        if return_pct >= 50:
            return "PREMIUM"
        elif return_pct >= 0:
            return "ACTIVE"
        else:
            return "UNDER_REVIEW"
    if r2 is not None and r2 >= 50 and score is not None and score >= 35:
        return "APPROACHING"
    if r2 is not None:
        return "BELOW_THRESHOLD"
    return "NO_HISTORY"


def _derive_waiting_for(r2: float | None, score: float | None) -> str:
    if r2 is None:
        return "No scan data available"
    if r2 >= 50 and r2 < 55:
        return f"Waiting for Demand Confirmation (R2 {r2:.0f}/60)"
    elif r2 >= 55 and r2 < 58:
        return f"Waiting for Order Block Touch (R2 {r2:.0f}/60)"
    elif r2 >= 58 and r2 < 60:
        return f"Waiting for Constitutional Trigger (R2 {r2:.0f}/60)"
    else:
        sc_str = f" Score {score:.0f}" if score is not None else ""
        return f"Below Threshold (R2 {r2:.0f}{sc_str})"


def _derive_action(status: str, return_pct: float | None) -> str:
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
    sh_prices = _load_signal_history()
    cbr       = _load_constitutional_registry()
    timeline  = _load_timeline()

    now_str = datetime.now(_CAIRO_TZ).isoformat()
    rows: list[dict] = []

    for ticker in universe:
        # Priority: pool → research → cbr
        p = pool.get(ticker, {})
        r = research.get(ticker, {})
        c = cbr.get(ticker, {})
        t = timeline.get(ticker, {})
        in_timeline = bool(t)

        # R2 + score
        r2    = p.get("r2_score") or r.get("r2_score") or c.get("r2_score")
        score = p.get("final_score") or r.get("final_score") or c.get("final_score")

        # Current price
        current_price = (
            p.get("current_price")
            or r.get("current_price")
            or t.get("current_price")
            or sh_prices.get(ticker)
        )

        # Entry price
        entry_price = (
            p.get("entry_price")
            or c.get("entry_price")
            or t.get("entry_price")
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
        last_scan         = p.get("last_scan") or r.get("last_scan") or ""
        last_price_update = t.get("event_date") or last_scan or ""

        # Source
        source = p.get("source") if p else (r.get("source") if r else "constitutional_registry" if c else "NO_HISTORY")

        status     = _derive_status(ticker, r2, score, in_timeline, return_pct)
        reason     = _derive_waiting_for(r2, score) if not in_timeline else ""
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
