"""
Universe Snapshot — V6.2
Builds a unified 27-ticker snapshot from all available data sources.
Writes to universe_snapshot.db. Read-only on candidate_pool.db.

Pool freshness: candidate_pool.db is the primary source of constitutional R2.
If pool is stale (latest signal_date > POOL_STALENESS_DAYS old), it is rebuilt
automatically via build_candidate_pool() before snapshot construction.
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, date as _date, timezone, timedelta
from pathlib import Path
from time_authority import now_cairo as _now_cairo_ta, today_cairo as _today_cairo_ta

BASE = Path(__file__).parent

_POOL_DB      = BASE / "candidate_pool.db"
_RESEARCH_DB  = BASE / "egx_research.db"
_SIGNAL_HIST  = BASE / "signal_history.json"
_CBR_DB       = BASE / "constitutional_buy_registry.db"
_SNAP_DB      = BASE / "universe_snapshot.db"

_CAIRO_TZ = _now_cairo_ta().tzinfo

# Pool older than this many calendar days is considered stale.
# 5 days = tolerate a full work week gap (e.g. holiday), but reject anything older.
_POOL_STALENESS_DAYS = 5


def _pool_latest_signal_date() -> str | None:
    """Return the MAX(signal_date) across the latest snapshot_ts, or None."""
    if not _POOL_DB.exists():
        return None
    conn = sqlite3.connect(str(_POOL_DB))
    try:
        row = conn.execute(
            """SELECT MAX(signal_date) FROM candidate_pool
               WHERE snapshot_ts = (SELECT MAX(snapshot_ts) FROM candidate_pool)"""
        ).fetchone()
        return row[0] if row else None
    finally:
        conn.close()


def _rebuild_pool_if_stale() -> bool:
    """
    Rebuild candidate_pool for the last 3 calendar days if the pool is missing or stale.
    Returns True if a rebuild was triggered, False otherwise.
    Uses INSERT OR IGNORE so rebuilds are safe to call repeatedly.
    """
    latest_sig = _pool_latest_signal_date()
    _today     = _today_cairo_ta()
    today_str  = _today.isoformat()

    if latest_sig is None:
        needs_rebuild = True
    else:
        days_stale = (_today - _date.fromisoformat(latest_sig)).days
        needs_rebuild = days_stale > _POOL_STALENESS_DAYS

    if not needs_rebuild:
        return False

    print(f"[UniverseSnapshot] Pool stale (latest signal_date={latest_sig}) — rebuilding...")
    try:
        from candidate_pool_builder import build_candidate_pool
        start = (_today - timedelta(days=7)).isoformat()
        build_candidate_pool(start_date=start, end_date=today_str)
        print(f"[UniverseSnapshot] Pool rebuilt for {start} to {today_str}.")
        return True
    except Exception as e:
        print(f"[UniverseSnapshot] Pool rebuild non-fatal: {e}")
        return False


# ── Source loaders ─────────────────────────────────────────────────────────────

def _load_pool() -> dict[str, dict]:
    """
    Latest signal per ticker from candidate_pool.db (READ ONLY).

    Returns the most recent signal_date row per ticker from the latest snapshot.
    Returns {} if pool is missing or stale (latest signal_date > _POOL_STALENESS_DAYS old).
    Stale pool data must not drive constitutional signal detection — callers should
    trigger _rebuild_pool_if_stale() before calling this.
    """
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

        # Staleness guard: reject pool data older than _POOL_STALENESS_DAYS.
        # Stale R2 values from candidate_pool would drive false constitutional signals.
        latest_sig = conn.execute(
            "SELECT MAX(signal_date) FROM candidate_pool WHERE snapshot_ts=?", (latest_ts,)
        ).fetchone()[0]
        if latest_sig:
            days_stale = (_date.today() - _date.fromisoformat(latest_sig)).days
            if days_stale > _POOL_STALENESS_DAYS:
                print(f"[UniverseSnapshot] Pool stale ({days_stale}d, latest={latest_sig}) — "
                      f"skipping pool for R2 sourcing.")
                return {}

        # Most recent signal_date per ticker — avoids serving historical high-R2 rows
        # from past qualifying windows as if they represent today's market state.
        rows = conn.execute(
            """SELECT ticker, candidate_r2, expected_reward_score, candidate_entry_zone,
                      current_price, snapshot_ts, signal_date
               FROM candidate_pool WHERE snapshot_ts=? AND candidate_entry_zone > 0
               ORDER BY ticker, signal_date DESC, candidate_r2 DESC""",
            (latest_ts,)
        ).fetchall()
        result = {}
        for r in rows:
            if r["ticker"] not in result:
                result[r["ticker"]] = {
                    "candidate_r2":          r["candidate_r2"],
                    "expected_reward_score": r["expected_reward_score"],
                    "candidate_entry_zone":  r["candidate_entry_zone"],
                    "current_price":         r["current_price"],
                    "last_scan":             (r["signal_date"] or "")[:10],
                    "source":                "candidate_pool",
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
                    "candidate_r2":          r["r2_ob"] or 0.0,
                    "expected_reward_score": r["adj_score"] or 0.0,
                    "current_price":         r["price"],
                    "research_entry_zone":   r["avg_entry"],
                    "last_scan":             (r["signal_date"] or "")[:10],
                    "source":                "egx_research",
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
            """SELECT ticker, buy_date, constitutional_entry_price, constitutional_r2, constitutional_score
               FROM constitutional_buy_registry ORDER BY ticker, buy_date"""
        ).fetchall()
        result = {}
        for r in rows:
            ticker = r["ticker"]
            if ticker not in result:
                result[ticker] = {
                    "constitutional_entry_price": r["constitutional_entry_price"],
                    "candidate_r2":              r["constitutional_r2"],
                    "constitutional_score":      r["constitutional_score"],
                    "buy_date":                  r["buy_date"],
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
                    "return_pct":                e["return_pct"],
                    "constitutional_entry_price": e["constitutional_entry_price"],
                    "current_price":             e["current_price"],
                    "event_date":                e["event_date"],
                    "event_type":                e["event_type"],
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

    # Auto-rebuild pool if stale so constitutional R2 reflects current market state.
    # Runs before all other source loaders so _load_pool() sees fresh data.
    _rebuild_pool_if_stale()

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
        r2    = _first_not_none(p.get("candidate_r2"), r.get("candidate_r2"), c.get("candidate_r2"))
        score = _first_not_none(p.get("expected_reward_score"), r.get("expected_reward_score"), c.get("constitutional_score"))

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
        constitutional_entry_price = (
            t.get("constitutional_entry_price")
            or p.get("candidate_entry_zone")
            or c.get("constitutional_entry_price")
            or r.get("research_entry_zone")
        )

        # Return pct
        return_pct = t.get("return_pct")
        if return_pct is None and current_price and constitutional_entry_price and constitutional_entry_price > 0:
            return_pct = round((current_price - constitutional_entry_price) / constitutional_entry_price * 100, 2)

        # Distance
        distance = None
        if current_price and constitutional_entry_price and constitutional_entry_price > 0:
            distance = round((current_price - constitutional_entry_price) / constitutional_entry_price * 100, 2)

        # Last scan / last price update
        last_scan         = p.get("last_scan") or r.get("last_scan") or sh.get("last_scan") or ""
        # last_price_update = the date of the PRICE DATA, not the constitutional BUY date
        last_price_update = price_date or last_scan or ""

        # Source
        source = p.get("source") if p else (r.get("source") if r else "constitutional_registry" if c else ("signal_history" if has_scan_history else "NO_HISTORY"))

        status               = _derive_status(ticker, r2, score, in_timeline, return_pct, has_scan_history)
        waiting_for_reason   = _derive_waiting_for(r2, score, has_scan_history, status)
        action               = _derive_action(status, return_pct)
        constitutional_memory = 1 if in_timeline else 0

        rows.append({
            "ticker":                   ticker,
            "current_price":            current_price,
            "status":                   status,
            "constitutional_entry_price": constitutional_entry_price,
            "distance":                 distance,
            "waiting_for_reason":       waiting_for_reason,
            "action":                   action,
            "constitutional_memory":    constitutional_memory,
            "candidate_r2":             r2,
            "expected_reward_score":    score,
            "last_scan":                last_scan,
            "generated_at":             now_str,
            "source":                   source,
            "last_price_update":        last_price_update,
            "return_pct":               return_pct,
        })

    # Write to DB
    conn = sqlite3.connect(str(_SNAP_DB))
    conn.execute("""
        CREATE TABLE IF NOT EXISTS universe_snapshot (
            ticker TEXT PRIMARY KEY,
            current_price REAL,
            status TEXT,
            constitutional_entry_price REAL,
            distance REAL,
            waiting_for_reason TEXT,
            action TEXT,
            constitutional_memory INTEGER DEFAULT 0,
            candidate_r2 REAL,
            expected_reward_score REAL,
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
           (ticker, current_price, status, constitutional_entry_price, distance,
            waiting_for_reason, action, constitutional_memory, candidate_r2,
            expected_reward_score, last_scan, generated_at, source,
            last_price_update, return_pct)
           VALUES (:ticker, :current_price, :status, :constitutional_entry_price, :distance,
                   :waiting_for_reason, :action, :constitutional_memory, :candidate_r2,
                   :expected_reward_score, :last_scan, :generated_at,
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
        print(f"  {r['ticker']:<12} {r['status']:<15} R2={r['candidate_r2'] or 0:.1f}  "
              f"Price={r['current_price'] or 0:.2f}  Return={r['return_pct'] or 0:.1f}%")
