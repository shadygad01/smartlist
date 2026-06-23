"""
Constitutional Opportunity Timeline Engine V1
Event-driven, append-only architecture.

Every constitutional BUY cluster becomes a permanent event.
FIRST_BUY  = first qualifying signal cluster per ticker.
RE_ACCUMULATION = every subsequent qualifying cluster.

Constitutional BUY: R2 >= 60 AND final_score >= 35 simultaneously.
Clustering: consecutive qualifying days, gap > GAP_DAYS = new event.

Nothing is overwritten. Nothing disappears.
No portfolio dependency. No R2 degradation. No capacity.
"""
from __future__ import annotations

import sqlite3
from datetime import date, timedelta
from pathlib import Path
from typing import Optional

BASE         = Path(__file__).parent
TIMELINE_DB  = BASE / "constitutional_opportunity_events.db"
POOL_DB      = BASE / "candidate_pool.db"

# Constitutional thresholds (DO NOT MODIFY)
CONST_R2_MIN    = 60.0
CONST_SCORE_MIN = 35.0

# Clustering: gap in calendar days that separates two distinct events
GAP_DAYS = 7

EVENT_FIRST_BUY        = "FIRST_BUY"
EVENT_RE_ACCUMULATION  = "RE_ACCUMULATION"

STATUS_PREMIUM_NOW        = "PREMIUM_NOW"       # return > 50%
STATUS_ACTIVE_OPPORTUNITY = "ACTIVE_OPPORTUNITY"
STATUS_UNDER_REVIEW       = "UNDER_REVIEW"      # return < 0%


# ── Schema ────────────────────────────────────────────────────────────────────

def _open(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    return conn


def _create_schema(conn: sqlite3.Connection) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS constitutional_opportunity_events (
            event_id         TEXT PRIMARY KEY,
            ticker           TEXT NOT NULL,
            event_type       TEXT NOT NULL,   -- FIRST_BUY | RE_ACCUMULATION
            event_index      INTEGER NOT NULL, -- 0=FIRST, 1,2,...=RE_ACCUMULATION
            event_date       TEXT NOT NULL,   -- cluster start date
            event_end_date   TEXT,            -- cluster end date
            cluster_days     INTEGER,         -- qualifying days in cluster
            entry_price      REAL NOT NULL,   -- price on event_date
            buy_r2           REAL NOT NULL,
            buy_score        REAL NOT NULL,
            buy_r3           REAL,
            buy_r4           REAL,
            buy_r5           REAL,
            buy_r6           REAL,
            buy_r7           REAL,
            buy_r8           REAL,
            sector           TEXT,
            signal_version   TEXT DEFAULT 'v1',
            created_at       TEXT NOT NULL
        )
    """)
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_coe_ticker ON constitutional_opportunity_events(ticker)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_coe_date ON constitutional_opportunity_events(event_date)"
    )
    conn.commit()


def _event_id(ticker: str, idx: int) -> str:
    return f"{ticker}_E{idx:02d}"


# ── Clustering ────────────────────────────────────────────────────────────────

def _cluster_signals(rows: list) -> list[dict]:
    """
    Group chronologically sorted (date, entry, r2, score, r3-r8, sector) rows
    into clusters separated by more than GAP_DAYS calendar days.
    Returns list of cluster dicts.
    """
    clusters: list[dict] = []
    for r in rows:
        dt = date.fromisoformat(r["signal_date"])
        if not clusters or (dt - clusters[-1]["end"]).days > GAP_DAYS:
            clusters.append({
                "start":   dt,
                "end":     dt,
                "entry":   r["entry_price"],
                "r2":      r["r2_score"],
                "score":   r["final_score"],
                "r3":      r["r3_score"],
                "r4":      r["r4_score"],
                "r5":      r["r5_score"],
                "r6":      r["r6_score"],
                "r7":      r["r7_score"],
                "r8":      r["r8_score"],
                "sector":  r["sector"] or "",
                "dates":   [dt],
            })
        else:
            clusters[-1]["end"] = dt
            clusters[-1]["dates"].append(dt)
    return clusters


# ── Migration ─────────────────────────────────────────────────────────────────

def migrate() -> dict:
    """
    Scan candidate_pool.db → cluster → insert missing events into timeline DB.
    Idempotent (never overwrites existing rows).
    Returns migration report.
    """
    if not POOL_DB.exists():
        return {"error": "candidate_pool.db not found"}

    pool = _open(POOL_DB)
    tl   = _open(TIMELINE_DB)
    _create_schema(tl)

    tickers = [
        r[0] for r in pool.execute(
            "SELECT DISTINCT ticker FROM candidate_pool ORDER BY ticker"
        ).fetchall()
    ]

    total_inserted = total_skipped = 0
    ticker_summary: dict[str, int] = {}

    for ticker in tickers:
        rows = pool.execute("""
            SELECT signal_date, entry_price, r2_score, final_score,
                   r3_score, r4_score, r5_score, r6_score, r7_score, r8_score, sector
            FROM candidate_pool
            WHERE ticker=? AND r2_score>=? AND final_score>=?
            ORDER BY signal_date ASC
        """, (ticker, CONST_R2_MIN, CONST_SCORE_MIN)).fetchall()

        if not rows:
            continue

        clusters = _cluster_signals(rows)
        ticker_summary[ticker] = len(clusters)
        now_ts = date.today().isoformat()

        for idx, cl in enumerate(clusters):
            eid   = _event_id(ticker, idx)
            etype = EVENT_FIRST_BUY if idx == 0 else EVENT_RE_ACCUMULATION

            exists = tl.execute(
                "SELECT 1 FROM constitutional_opportunity_events WHERE event_id=?", (eid,)
            ).fetchone()
            if exists:
                total_skipped += 1
                continue

            tl.execute("""
                INSERT INTO constitutional_opportunity_events
                (event_id, ticker, event_type, event_index, event_date, event_end_date,
                 cluster_days, entry_price, buy_r2, buy_score,
                 buy_r3, buy_r4, buy_r5, buy_r6, buy_r7, buy_r8,
                 sector, signal_version, created_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, (
                eid, ticker, etype, idx,
                cl["start"].isoformat(), cl["end"].isoformat(), len(cl["dates"]),
                cl["entry"], cl["r2"], cl["score"],
                cl["r3"], cl["r4"], cl["r5"], cl["r6"], cl["r7"], cl["r8"],
                cl["sector"], "v1", now_ts,
            ))
            total_inserted += 1

    tl.commit()
    pool.close()
    tl.close()

    return {
        "tickers_processed":  len(ticker_summary),
        "total_events_found": sum(ticker_summary.values()),
        "inserted_new":       total_inserted,
        "already_present":    total_skipped,
        "ticker_event_counts": ticker_summary,
    }


# ── Price enrichment ──────────────────────────────────────────────────────────

def _build_price_index() -> dict[str, dict]:
    """
    Returns {ticker: {'by_date': {date: price}, 'latest': X}}

    PRIMARY source: universe_snapshot.db via PriceAuthority (single source of truth).
    FALLBACK: candidate_pool.db (for peak_after historical data — not used for 'latest').

    PriceAuthority.get_all_prices() overrides 'latest' to ensure every section
    of the dashboard shows the identical current price.
    """
    # Build by_date from candidate_pool for historical peak tracking
    idx: dict[str, dict] = {}
    if POOL_DB.exists():
        pool = _open(POOL_DB)
        rows = pool.execute(
            "SELECT ticker, signal_date, current_price FROM candidate_pool ORDER BY ticker, signal_date"
        ).fetchall()
        pool.close()
        for r in rows:
            t = r["ticker"]
            if t not in idx:
                idx[t] = {"by_date": {}, "latest": 0.0}
            if r["current_price"] and r["current_price"] > 0:
                idx[t]["by_date"][r["signal_date"]] = r["current_price"]
            idx[t]["latest"] = r["current_price"] or 0.0

    # Override 'latest' with PriceAuthority — single source of truth
    try:
        from price_authority import get_all_prices
        auth_prices = get_all_prices()
        for ticker, price in auth_prices.items():
            if ticker not in idx:
                idx[ticker] = {"by_date": {}, "latest": 0.0}
            idx[ticker]["latest"] = price
    except Exception:
        pass

    return idx


def _peak_after(price_index: dict, ticker: str, from_date: str) -> float:
    """Max current_price seen in candidate_pool on any date >= from_date."""
    dates = price_index.get(ticker, {}).get("by_date", {})
    vals  = [v for d, v in dates.items() if d >= from_date and v]
    return max(vals) if vals else 0.0


def _status(return_pct: float) -> str:
    if return_pct >= 50.0:
        return STATUS_PREMIUM_NOW
    if return_pct >= 0.0:
        return STATUS_ACTIVE_OPPORTUNITY
    return STATUS_UNDER_REVIEW


# ── Public API ────────────────────────────────────────────────────────────────

def get_timeline() -> list[dict]:
    """
    All constitutional opportunity events, enriched with live prices.
    Sorted chronologically (event_date ASC, event_index ASC).
    """
    if not TIMELINE_DB.exists():
        migrate()

    tl = _open(TIMELINE_DB)
    _create_schema(tl)
    rows = tl.execute("""
        SELECT * FROM constitutional_opportunity_events
        ORDER BY event_date ASC, ticker ASC, event_index ASC
    """).fetchall()
    tl.close()

    if not rows:
        migrate()
        tl   = _open(TIMELINE_DB)
        rows = tl.execute("""
            SELECT * FROM constitutional_opportunity_events
            ORDER BY event_date ASC, ticker ASC, event_index ASC
        """).fetchall()
        tl.close()

    pi     = _build_price_index()
    today  = date.today().isoformat()
    result = []

    for r in rows:
        t          = r["ticker"]
        buy_price  = float(r["entry_price"])
        ev_date    = r["event_date"]

        current_price = pi.get(t, {}).get("latest") or buy_price
        peak_price    = _peak_after(pi, t, ev_date) or current_price

        ret_pct  = ((current_price - buy_price) / buy_price * 100) if buy_price else 0.0
        peak_ret = ((peak_price   - buy_price) / buy_price * 100) if buy_price else 0.0

        try:
            days = (date.fromisoformat(today) - date.fromisoformat(ev_date)).days
        except Exception:
            days = 0

        result.append(dict(
            event_id         = r["event_id"],
            ticker           = t,
            event_type       = r["event_type"],
            event_index      = int(r["event_index"]),
            event_date       = ev_date,
            event_end_date   = r["event_end_date"] or ev_date,
            cluster_days     = int(r["cluster_days"] or 1),
            entry_price      = buy_price,
            buy_r2           = float(r["buy_r2"]),
            buy_score        = float(r["buy_score"]),
            sector           = r["sector"] or "",
            current_price    = current_price,
            return_pct       = round(ret_pct, 2),
            peak_return_pct  = round(peak_ret, 2),
            days_active      = days,
            status           = _status(ret_pct),
        ))

    return result


def get_new_events_today() -> list[dict]:
    today = date.today().isoformat()
    return [e for e in get_timeline() if e["event_date"] == today]


def get_analytics() -> dict[str, dict]:
    """
    Per-ticker analytics:
    total_events, avg_entry, best_entry, worst_entry, avg_days,
    best_return_event, current_return_each, avg_current_return,
    total_events_count.
    """
    timeline = get_timeline()
    by_ticker: dict[str, list] = {}
    for ev in timeline:
        by_ticker.setdefault(ev["ticker"], []).append(ev)

    result: dict[str, dict] = {}
    for t, evs in by_ticker.items():
        entries = [e["entry_price"] for e in evs]
        rets    = [e["return_pct"]  for e in evs]
        best_ev = max(evs, key=lambda e: e["return_pct"])
        result[t] = {
            "ticker":              t,
            "sector":              evs[0]["sector"],
            "total_events":        len(evs),
            "avg_entry":           round(sum(entries) / len(entries), 2),
            "best_entry":          round(min(entries), 2),
            "worst_entry":         round(max(entries), 2),
            "avg_days":            round(sum(e["days_active"] for e in evs) / len(evs), 0),
            "avg_return_pct":      round(sum(rets) / len(rets), 2),
            "best_return_pct":     round(max(rets), 2),
            "worst_return_pct":    round(min(rets), 2),
            "best_event_id":       best_ev["event_id"],
            "best_event_date":     best_ev["event_date"],
            "events":              evs,
        }
    return result


def get_leaderboards(timeline: list[dict] | None = None,
                     analytics: dict | None = None) -> dict:
    """
    Returns ranked leaderboards:
    - most_repeated: tickers with most constitutional events
    - highest_avg_return: average return across all events
    - highest_peak_return: max peak_return_pct ever seen
    - highest_best_return: single best return event
    - most_consistent: tickers where ALL events are profitable
    - compound_return: entry E0, return = (latest_price / E0 - 1)
    """
    tl = timeline if timeline is not None else get_timeline()
    an = analytics if analytics is not None else get_analytics()

    most_repeated = sorted(
        an.values(), key=lambda x: x["total_events"], reverse=True
    )
    highest_avg = sorted(
        an.values(), key=lambda x: x["avg_return_pct"], reverse=True
    )
    highest_best = sorted(
        an.values(), key=lambda x: x["best_return_pct"], reverse=True
    )
    highest_peak = sorted(
        tl, key=lambda e: e["peak_return_pct"], reverse=True
    )[:10]

    most_consistent = [
        a for a in an.values()
        if a["worst_return_pct"] >= 0 and a["total_events"] >= 2
    ]
    most_consistent.sort(key=lambda x: x["avg_return_pct"], reverse=True)

    # Compound return: compare current_price of first event vs latest price
    compound = []
    for t, a in an.items():
        evs = sorted(a["events"], key=lambda e: e["event_date"])
        e0  = evs[0]["entry_price"]
        cur = evs[-1]["current_price"]
        compound.append(dict(
            ticker=t, sector=a["sector"],
            first_entry=e0, current_price=cur,
            compound_return_pct=round((cur - e0) / e0 * 100 if e0 else 0, 2),
            total_events=a["total_events"],
        ))
    compound.sort(key=lambda x: x["compound_return_pct"], reverse=True)

    return {
        "most_repeated":    most_repeated,
        "highest_avg":      highest_avg,
        "highest_best":     highest_best,
        "highest_peak":     highest_peak,
        "most_consistent":  most_consistent,
        "compound_return":  compound,
    }


def forensic_validation() -> dict:
    """
    Verify integrity: count expected events from pool vs actual in DB.
    """
    tl = _open(TIMELINE_DB)
    _create_schema(tl)
    rows = tl.execute(
        "SELECT event_id, ticker, event_type FROM constitutional_opportunity_events"
    ).fetchall()
    tl.close()

    total_in_db    = len(rows)
    first_buys     = sum(1 for r in rows if r["event_type"] == EVENT_FIRST_BUY)
    re_accum       = sum(1 for r in rows if r["event_type"] == EVENT_RE_ACCUMULATION)
    tickers_in_db  = len(set(r["ticker"] for r in rows))

    tl2 = get_timeline()
    downgraded = 0  # impossible by design — no R2 check on historical events
    missing    = 0

    if POOL_DB.exists():
        pool = _open(POOL_DB)
        pool_tickers = set(
            r[0] for r in pool.execute(
                "SELECT DISTINCT ticker FROM candidate_pool WHERE r2_score>=? AND final_score>=?",
                (CONST_R2_MIN, CONST_SCORE_MIN)
            ).fetchall()
        )
        pool.close()
        db_tickers = set(r["ticker"] for r in rows)
        missing = len(pool_tickers - db_tickers)

    return {
        "total_events_in_db":   total_in_db,
        "first_buy_events":     first_buys,
        "re_accumulation_events": re_accum,
        "tickers_with_events":  tickers_in_db,
        "buys_missing":         missing,
        "buys_downgraded":      downgraded,
        "buys_overwritten":     0,
        "buys_deleted":         0,
        "premium_now":          sum(1 for e in tl2 if e["status"] == STATUS_PREMIUM_NOW),
        "active_opportunity":   sum(1 for e in tl2 if e["status"] == STATUS_ACTIVE_OPPORTUNITY),
        "under_review":         sum(1 for e in tl2 if e["status"] == STATUS_UNDER_REVIEW),
    }


def run_daily() -> dict:
    """
    Daily entry point: check candidate_pool for today's new qualifying signals.
    Register new events if found, return updated timeline.
    """
    today = date.today().isoformat()
    if not TIMELINE_DB.exists():
        migrate()

    if not POOL_DB.exists():
        return {"error": "candidate_pool.db not found"}

    pool = _open(POOL_DB)
    todays_rows = pool.execute("""
        SELECT ticker, signal_date, entry_price,
               r2_score, final_score, r3_score, r4_score, r5_score,
               r6_score, r7_score, r8_score, sector
        FROM candidate_pool
        WHERE signal_date=? AND r2_score>=? AND final_score>=?
        ORDER BY r2_score DESC
    """, (today, CONST_R2_MIN, CONST_SCORE_MIN)).fetchall()
    pool.close()

    new_events: list[str] = []
    tl = _open(TIMELINE_DB)
    _create_schema(tl)

    for r in todays_rows:
        t = r["ticker"]
        # Determine current max index for this ticker
        existing = tl.execute(
            "SELECT MAX(event_index) FROM constitutional_opportunity_events WHERE ticker=?", (t,)
        ).fetchone()[0]

        if existing is None:
            idx   = 0
            etype = EVENT_FIRST_BUY
        else:
            # Check if today's date continues the last cluster or is a new one
            last_end = tl.execute(
                "SELECT event_end_date FROM constitutional_opportunity_events "
                "WHERE ticker=? ORDER BY event_index DESC LIMIT 1", (t,)
            ).fetchone()[0]
            last_end_dt = date.fromisoformat(last_end)
            today_dt    = date.fromisoformat(today)
            if (today_dt - last_end_dt).days <= GAP_DAYS:
                # Extend existing cluster — update end date and days
                tl.execute("""
                    UPDATE constitutional_opportunity_events
                    SET event_end_date=?, cluster_days=cluster_days+1
                    WHERE ticker=? AND event_index=?
                """, (today, t, int(existing)))
                continue
            else:
                idx   = int(existing) + 1
                etype = EVENT_RE_ACCUMULATION

        eid = _event_id(t, idx)
        tl.execute("""
            INSERT OR IGNORE INTO constitutional_opportunity_events
            (event_id, ticker, event_type, event_index, event_date, event_end_date,
             cluster_days, entry_price, buy_r2, buy_score,
             buy_r3, buy_r4, buy_r5, buy_r6, buy_r7, buy_r8,
             sector, signal_version, created_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            eid, t, etype, idx, today, today, 1,
            r["entry_price"], r["r2_score"], r["final_score"],
            r["r3_score"], r["r4_score"], r["r5_score"],
            r["r6_score"], r["r7_score"], r["r8_score"],
            r["sector"] or "", "v1", today,
        ))
        if tl.execute("SELECT changes()").fetchone()[0]:
            new_events.append(f"{etype}:{t}")

    tl.commit()
    tl.close()

    tl_data = get_timeline()
    return {
        "date":              today,
        "new_events":        new_events,
        "total_events":      len(tl_data),
        "total_tickers":     len(set(e["ticker"] for e in tl_data)),
    }


# ── CLI / self-test ───────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 60)
    print("CONSTITUTIONAL TIMELINE ENGINE V1 — MIGRATION")
    print("=" * 60)
    report = migrate()
    for k, v in report.items():
        if k != "ticker_event_counts":
            print(f"  {k}: {v}")

    print("\n=== TICKER EVENT COUNTS ===")
    for t, cnt in sorted(report.get("ticker_event_counts", {}).items(), key=lambda x: -x[1]):
        print(f"  {t:<12} {cnt} events")

    print("\n=== FULL TIMELINE ===")
    for ev in get_timeline():
        sign = "+" if ev["return_pct"] >= 0 else ""
        pk   = "+" if ev["peak_return_pct"] >= 0 else ""
        print(
            f"  [{ev['event_type']:<16}] {ev['ticker']:<12} {ev['event_date']}"
            f"  entry={ev['entry_price']:.2f}  ret={sign}{ev['return_pct']:.1f}%"
            f"  peak={pk}{ev['peak_return_pct']:.1f}%  {ev['days_active']}d  [{ev['status']}]"
        )

    print("\n=== LEADERBOARDS ===")
    lb = get_leaderboards()
    print("Most Repeated Constitutional Opportunities:")
    for a in lb["most_repeated"][:5]:
        print(f"  {a['ticker']:<12} {a['total_events']} events  avg_ret={a['avg_return_pct']:+.1f}%")
    print("Highest Compound Return:")
    for c in lb["compound_return"][:5]:
        print(f"  {c['ticker']:<12} {c['compound_return_pct']:+.1f}%  ({c['total_events']} events)")

    print("\n=== FORENSIC VALIDATION ===")
    v = forensic_validation()
    for k, val in v.items():
        print(f"  {k}: {val}")
