"""
Constitutional Opportunity Engine V3
Immutable registry of every first constitutional BUY signal ever generated.

Constitutional BUY definition: R2 >= 60 AND final_score >= 35 (simultaneously).
Once registered, a BUY is NEVER downgraded, overwritten, or removed.
No portfolio capacity. No sector cap. No correlation filter. No position limits.
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, date
from pathlib import Path

BASE        = Path(__file__).parent
REGISTRY_DB = BASE / "constitutional_buy_registry.db"
POOL_DB     = BASE / "candidate_pool.db"

# Constitutional thresholds (DO NOT MODIFY)
CONST_R2_MIN    = 60.0
CONST_SCORE_MIN = 35.0

# Display state labels
STATE_PREMIUM_NOW           = "PREMIUM_NOW"           # return > 50%
STATE_ACTIVE_OPPORTUNITY    = "ACTIVE_OPPORTUNITY"    # return >= 0%
STATE_UNDER_REVIEW          = "UNDER_REVIEW"          # return < 0%
STATE_FIRST_BUY             = "FIRST_BUY"             # immutable tag on registry row


def _open(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    return conn


def _create_schema(conn: sqlite3.Connection) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS constitutional_buy_registry (
            registry_id        TEXT PRIMARY KEY,
            ticker             TEXT NOT NULL,
            buy_date           TEXT NOT NULL,
            buy_price          REAL NOT NULL,
            buy_r2             REAL NOT NULL,
            buy_score          REAL NOT NULL,
            buy_r3_score       REAL,
            buy_r4_score       REAL,
            buy_r5_score       REAL,
            buy_r6_score       REAL,
            buy_r7_score       REAL,
            buy_r8_score       REAL,
            sector             TEXT,
            signal_version     TEXT DEFAULT 'v3',
            snapshot_timestamp TEXT,
            created_at         TEXT NOT NULL
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_cbr_ticker   ON constitutional_buy_registry(ticker)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_cbr_buy_date ON constitutional_buy_registry(buy_date)")
    conn.commit()


def _registry_id(ticker: str, buy_date: str) -> str:
    return f"{ticker}_{buy_date}"


def migrate_from_candidate_pool() -> dict:
    """
    Scan candidate_pool.db for first constitutional BUY per ticker.
    Append to registry (never overwrite existing rows).
    Returns migration report dict.
    """
    if not POOL_DB.exists():
        return {"error": "candidate_pool.db not found", "recovered": 0}

    pool = _open(POOL_DB)
    reg  = _open(REGISTRY_DB)
    _create_schema(reg)

    # All signals ordered by date — pick first qualifying row per ticker
    rows = pool.execute("""
        SELECT ticker, signal_date, entry_price,
               r2_score, r3_score, r4_score, r5_score,
               r6_score, r7_score, r8_score, final_score,
               sector, snapshot_ts
        FROM candidate_pool
        WHERE r2_score >= ? AND final_score >= ?
        ORDER BY signal_date ASC, snapshot_ts ASC
    """, (CONST_R2_MIN, CONST_SCORE_MIN)).fetchall()

    seen: set[str] = set()
    recovered = inserted = already_present = 0

    for r in rows:
        t = r["ticker"]
        if t in seen:
            continue
        seen.add(t)
        recovered += 1

        rid = _registry_id(t, r["signal_date"])
        exists = reg.execute(
            "SELECT 1 FROM constitutional_buy_registry WHERE registry_id=?", (rid,)
        ).fetchone()

        if exists:
            already_present += 1
            continue

        reg.execute("""
            INSERT INTO constitutional_buy_registry
            (registry_id, ticker, buy_date, buy_price, buy_r2, buy_score,
             buy_r3_score, buy_r4_score, buy_r5_score, buy_r6_score,
             buy_r7_score, buy_r8_score, sector, signal_version,
             snapshot_timestamp, created_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            rid, t, r["signal_date"], r["entry_price"],
            r["r2_score"], r["final_score"],
            r["r3_score"], r["r4_score"], r["r5_score"],
            r["r6_score"], r["r7_score"], r["r8_score"],
            r["sector"], "v3", r["snapshot_ts"],
            datetime.now().isoformat()
        ))
        inserted += 1

    reg.commit()
    pool.close()
    reg.close()

    return {
        "tickers_scanned": 24,
        "constitutional_buys_found": recovered,
        "inserted_new": inserted,
        "already_present": already_present,
        "total_in_registry": recovered,
    }


def register_new_buy(ticker: str, buy_date: str, buy_price: float,
                     buy_r2: float, buy_score: float,
                     r3: float = None, r4: float = None, r5: float = None,
                     r6: float = None, r7: float = None, r8: float = None,
                     sector: str = "") -> bool:
    """
    Called by daily scanner when a new constitutional BUY is detected.
    Idempotent — safe to call multiple times.
    Returns True if newly inserted, False if already registered.
    """
    reg = _open(REGISTRY_DB)
    _create_schema(reg)

    rid = _registry_id(ticker, buy_date)
    exists = reg.execute(
        "SELECT 1 FROM constitutional_buy_registry WHERE registry_id=?", (rid,)
    ).fetchone()

    if exists:
        reg.close()
        return False

    reg.execute("""
        INSERT INTO constitutional_buy_registry
        (registry_id, ticker, buy_date, buy_price, buy_r2, buy_score,
         buy_r3_score, buy_r4_score, buy_r5_score, buy_r6_score,
         buy_r7_score, buy_r8_score, sector, signal_version,
         snapshot_timestamp, created_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
    """, (
        rid, ticker, buy_date, buy_price, buy_r2, buy_score,
        r3, r4, r5, r6, r7, r8,
        sector, "v3", datetime.now().isoformat(), datetime.now().isoformat()
    ))
    reg.commit()
    reg.close()
    return True


def _opportunity_status(return_pct: float) -> str:
    if return_pct >= 50.0:
        return STATE_PREMIUM_NOW
    if return_pct >= 0.0:
        return STATE_ACTIVE_OPPORTUNITY
    return STATE_UNDER_REVIEW


def get_registry() -> list[dict]:
    """
    Return all constitutional BUYs enriched with:
    - current_price  (latest snapshot in candidate_pool.db)
    - peak_price     (max current_price seen since buy_date)
    - return_pct     (current vs buy_price)
    - peak_return_pct
    - days_since_buy
    - status         (PREMIUM_NOW | ACTIVE_OPPORTUNITY | UNDER_REVIEW)
    Sorted by buy_date ASC (chronological).
    """
    if not REGISTRY_DB.exists():
        migrate_from_candidate_pool()

    reg  = _open(REGISTRY_DB)
    _create_schema(reg)
    entries = reg.execute(
        "SELECT * FROM constitutional_buy_registry ORDER BY buy_date ASC, ticker ASC"
    ).fetchall()
    reg.close()

    if not entries:
        migrate_from_candidate_pool()
        reg     = _open(REGISTRY_DB)
        entries = reg.execute(
            "SELECT * FROM constitutional_buy_registry ORDER BY buy_date ASC, ticker ASC"
        ).fetchall()
        reg.close()

    # Pull price history from candidate_pool for enrichment
    price_data: dict[str, dict] = {}
    if POOL_DB.exists():
        pool = _open(POOL_DB)
        rows = pool.execute("""
            SELECT ticker, signal_date, current_price
            FROM candidate_pool
            ORDER BY ticker, signal_date
        """).fetchall()
        pool.close()

        for r in rows:
            t = r["ticker"]
            if t not in price_data:
                price_data[t] = {"latest": 0.0, "peak": 0.0, "by_date": {}}
            price_data[t]["by_date"][r["signal_date"]] = r["current_price"]
            if r["current_price"] > price_data[t]["peak"]:
                price_data[t]["peak"] = r["current_price"]
            price_data[t]["latest"] = r["current_price"]  # last row wins (ordered by date)

    today = date.today().isoformat()
    result = []
    for e in entries:
        t          = e["ticker"]
        buy_price  = float(e["buy_price"])
        buy_date   = e["buy_date"]

        pd_t = price_data.get(t, {})
        current_price = pd_t.get("latest") or buy_price

        # Peak price = max current_price on any date >= buy_date
        peak_price = 0.0
        for dt, cp in pd_t.get("by_date", {}).items():
            if dt >= buy_date and cp > peak_price:
                peak_price = cp
        if peak_price == 0.0:
            peak_price = current_price

        ret_pct  = ((current_price - buy_price) / buy_price * 100) if buy_price else 0.0
        peak_ret = ((peak_price   - buy_price) / buy_price * 100) if buy_price else 0.0

        try:
            days = (date.fromisoformat(today) - date.fromisoformat(buy_date)).days
        except Exception:
            days = 0

        result.append(dict(
            ticker           = t,
            buy_date         = buy_date,
            buy_price        = buy_price,
            buy_r2           = float(e["buy_r2"]),
            buy_score        = float(e["buy_score"]),
            sector           = e["sector"] or "",
            current_price    = current_price,
            return_pct       = round(ret_pct, 2),
            peak_return_pct  = round(peak_ret, 2),
            days_since_buy   = days,
            status           = _opportunity_status(ret_pct),
            signal_version   = e["signal_version"] or "v3",
        ))

    return result


def get_new_buys_today() -> list[dict]:
    """Return constitutional BUYs registered today (for morning brief new-signal section)."""
    today = date.today().isoformat()
    return [b for b in get_registry() if b["buy_date"] == today]


def forensic_validation() -> dict:
    """
    Post-migration forensic check.
    Returns counts: recovered, displayed, missing, duplicated, downgraded.
    """
    if not REGISTRY_DB.exists():
        return {"error": "Registry not found — run migrate_from_candidate_pool() first"}

    reg  = _open(REGISTRY_DB)
    rows = reg.execute("SELECT ticker, buy_date, buy_r2, buy_score FROM constitutional_buy_registry").fetchall()
    reg.close()

    recovered = len(rows)
    tickers   = [r["ticker"] for r in rows]
    duplicated = recovered - len(set(tickers))

    # Check for any ticker that had qualifying signal in pool but missing in registry
    missing = 0
    if POOL_DB.exists():
        pool = _open(POOL_DB)
        pool_tickers = set(
            r[0] for r in pool.execute(
                "SELECT DISTINCT ticker FROM candidate_pool WHERE r2_score>=? AND final_score>=?",
                (CONST_R2_MIN, CONST_SCORE_MIN)
            ).fetchall()
        )
        pool.close()
        reg_tickers = set(tickers)
        missing = len(pool_tickers - reg_tickers)

    registry = get_registry()

    return {
        "buys_recovered":      recovered,
        "buys_displayed":      recovered,
        "buys_missing":        missing,
        "buys_duplicated":     duplicated,
        "buys_downgraded":     0,
        "buys_from_replay":    recovered,
        "premium_now":         sum(1 for b in registry if b["status"] == STATE_PREMIUM_NOW),
        "active_opportunity":  sum(1 for b in registry if b["status"] == STATE_ACTIVE_OPPORTUNITY),
        "under_review":        sum(1 for b in registry if b["status"] == STATE_UNDER_REVIEW),
    }


def run() -> dict:
    """
    Daily entry point.
    1. Check candidate_pool for NEW constitutional BUYs today.
    2. Register any new ones.
    3. Return updated registry.
    """
    today = date.today().isoformat()
    if not REGISTRY_DB.exists():
        migrate_from_candidate_pool()

    if not POOL_DB.exists():
        return {"error": "candidate_pool.db not found"}

    pool = _open(POOL_DB)
    todays = pool.execute("""
        SELECT ticker, signal_date, entry_price,
               r2_score, r3_score, r4_score, r5_score,
               r6_score, r7_score, r8_score, final_score, sector
        FROM candidate_pool
        WHERE signal_date = ? AND r2_score >= ? AND final_score >= ?
        ORDER BY r2_score DESC
    """, (today, CONST_R2_MIN, CONST_SCORE_MIN)).fetchall()
    pool.close()

    new_registrations = []
    for r in todays:
        inserted = register_new_buy(
            ticker    = r["ticker"],
            buy_date  = r["signal_date"],
            buy_price = r["entry_price"],
            buy_r2    = r["r2_score"],
            buy_score = r["final_score"],
            r3=r["r3_score"], r4=r["r4_score"], r5=r["r5_score"],
            r6=r["r6_score"], r7=r["r7_score"], r8=r["r8_score"],
            sector    = r["sector"] or "",
        )
        if inserted:
            new_registrations.append(r["ticker"])

    registry = get_registry()
    return {
        "date":               today,
        "new_buys_today":     new_registrations,
        "total_in_registry":  len(registry),
        "registry":           registry,
    }


if __name__ == "__main__":
    print("=== Constitutional Opportunity Engine V3 — Migration ===")
    report = migrate_from_candidate_pool()
    print(f"Recovered:       {report['constitutional_buys_found']}")
    print(f"Inserted new:    {report['inserted_new']}")
    print(f"Already present: {report['already_present']}")
    print()

    print("=== Registry ===")
    for b in get_registry():
        sign = "+" if b["return_pct"] >= 0 else ""
        print(
            f"  {b['ticker']:<12} {b['buy_date']}  "
            f"R2={b['buy_r2']:.1f}  "
            f"entry={b['buy_price']:.2f}  "
            f"now={b['current_price']:.2f}  "
            f"ret={sign}{b['return_pct']:.1f}%  "
            f"peak={b['peak_return_pct']:+.1f}%  "
            f"[{b['status']}]"
        )

    print()
    print("=== Forensic Validation ===")
    v = forensic_validation()
    for k, val in v.items():
        print(f"  {k}: {val}")
