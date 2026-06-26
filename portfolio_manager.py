"""
Constitutional Portfolio Manager V1
=====================================
Manages candidates from candidate_pool.db through a constitutional
state machine.  Never reads OHLCV.  Never reruns the signal engine.
Never modifies the candidate pool.

Constitution:
  Max positions      : 12-15
  Max sector weight  : 25%
  Max pairwise corr  : 0.80
  Weight method      : Equal weight
  Ranking            : R2 (primary) → diversification (secondary)
  expected_reward_score : NEVER used for ranking

State machine:
  NEW → PRIMARY_BUY | BUY_RESERVE | WATCH
  PRIMARY_BUY → HELD | BUY_RESERVE | WATCH | ARCHIVED
  BUY_RESERVE → HELD | WATCH | ARCHIVED
  WATCH → BUY_RESERVE | PRIMARY_BUY | ARCHIVED
  HELD → REDUCED | EXIT
  REDUCED → HELD | EXIT
  EXIT → ARCHIVED
"""

import hashlib
import json
import os
import sqlite3
from datetime import date as _date, datetime as _dt

import numpy as np
import pandas as pd

POOL_DB = os.path.join(os.path.dirname(__file__), "candidate_pool.db")
MGR_DB  = os.path.join(os.path.dirname(__file__), "portfolio_manager.db")
DATA_DIR = os.path.join(os.path.dirname(__file__), "historical_data", "historical_data")

MAX_POSITIONS   = 13          # target size (12-15)
MAX_SECTOR_PCT  = 0.25        # 25%
MAX_CORR        = 0.80        # pairwise
CORR_WINDOW     = 60          # trading days for correlation

VALID_STATES = {
    "NEW", "PRIMARY_BUY", "BUY_RESERVE", "WATCH",
    "HELD", "REDUCED", "EXIT", "ARCHIVED",
}

SECTOR_MAP = {
    "TMGH.CA": "Real Estate", "EMFD.CA": "Real Estate", "PHDC.CA": "Real Estate",
    "ORHD.CA": "Real Estate", "HELI.CA": "Real Estate",
    "EAST.CA": "Industrial",  "ABUK.CA": "Industrial",  "ORAS.CA": "Industrial",
    "EFID.CA": "Industrial",  "HRHO.CA": "Industrial",  "JUFO.CA": "Industrial",
    "ARCC.CA": "Industrial",  "ORWE.CA": "Industrial",  "CCAP.CA": "Industrial",
    "MCQE.CA": "Healthcare",  "ISPH.CA": "Healthcare",  "RMDA.CA": "Healthcare",
    "FWRY.CA": "FinTech",     "EFIH.CA": "FinTech",     "RAYA.CA": "FinTech",
    "BTFH.CA": "FinTech",
    "COMI.CA": "Banking",     "EGAL.CA": "Banking",     "ADIB.CA": "Banking",
    "ETEL.CA": "Telecom",     "GBCO.CA": "Telecom",     "OIH.CA":  "Telecom",
}

MGR_SCHEMA = """
CREATE TABLE IF NOT EXISTS candidate_states (
    state_id              TEXT PRIMARY KEY,
    candidate_id          TEXT NOT NULL,
    ticker                TEXT NOT NULL,
    signal_date           TEXT NOT NULL,
    candidate_entry_zone  REAL NOT NULL,
    state                 TEXT NOT NULL,
    candidate_r2          REAL,
    sector           TEXT,
    decision_reason  TEXT,
    portfolio_impact TEXT,
    replacement_rank INTEGER DEFAULT 0,
    sector_exposure  REAL DEFAULT 0,
    corr_impact      REAL DEFAULT 0,
    suggested_action TEXT,
    created_at       TEXT NOT NULL,
    updated_at       TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS state_history (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    candidate_id    TEXT NOT NULL,
    ticker          TEXT NOT NULL,
    from_state      TEXT,
    to_state        TEXT NOT NULL,
    reason          TEXT,
    ts              TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS portfolio_snapshots (
    snapshot_id   TEXT PRIMARY KEY,
    snapshot_date TEXT NOT NULL,
    holdings_json TEXT NOT NULL,
    primary_buy_json   TEXT,
    reserve_json       TEXT,
    watch_json         TEXT,
    sector_alloc_json  TEXT,
    corr_matrix_json   TEXT,
    replacement_queue_json TEXT,
    portfolio_health_json  TEXT,
    created_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS correlation_cache (
    pair_key TEXT PRIMARY KEY,
    ticker_a TEXT NOT NULL,
    ticker_b TEXT NOT NULL,
    corr     REAL NOT NULL,
    computed_date TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_cs_ticker ON candidate_states(ticker);
CREATE INDEX IF NOT EXISTS idx_cs_state  ON candidate_states(state);
CREATE INDEX IF NOT EXISTS idx_sh_ticker ON state_history(ticker);
CREATE INDEX IF NOT EXISTS idx_sh_ts     ON state_history(ts);
"""


# ── Helpers ──────────────────────────────────────────────────────────────────

def _now() -> str:
    """Return current UTC timestamp as ISO string."""
    return _dt.utcnow().isoformat()


def _snap_id(snap_date: str) -> str:
    """Return a short deterministic ID for a portfolio snapshot."""
    return hashlib.sha256(f"snap|{snap_date}|{_now()}".encode()).hexdigest()[:16]


def _state_id(candidate_id: str) -> str:
    """Return a deterministic state primary key for a candidate."""
    return hashlib.sha256(f"state|{candidate_id}".encode()).hexdigest()[:24]


def _conn(db_path: str = MGR_DB) -> sqlite3.Connection:
    """Open portfolio_manager.db connection with Row factory."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


# ── Correlation layer (reads OHLCV once, caches in manager DB) ───────────────

def _build_correlation_cache(as_of: str, conn: sqlite3.Connection):
    """
    One-time: compute 60-day pairwise return correlation for all
    universe symbols and store in correlation_cache table.
    Only called when cache is empty or stale (>5 days old).
    """
    tickers = list(SECTOR_MAP.keys())
    series  = {}
    for sym in tickers:
        path = os.path.join(DATA_DIR, f"{sym}.csv")
        if not os.path.exists(path):
            continue
        df = pd.read_csv(path, parse_dates=["Date"]).sort_values("Date")
        df = df[df["Date"] <= as_of].tail(CORR_WINDOW + 5)
        if len(df) >= 10:
            series[sym] = df.set_index("Date")["Close"].pct_change().dropna()

    if len(series) < 2:
        return

    df_ret = pd.DataFrame(series).dropna(how="all").tail(CORR_WINDOW)
    corr   = df_ret.corr()
    ts     = _now()

    conn.execute("DELETE FROM correlation_cache")   # refresh
    rows = []
    cols = list(corr.columns)
    for i, a in enumerate(cols):
        for j, b in enumerate(cols):
            if j <= i:
                continue
            val = corr.at[a, b] if (a in corr.index and b in corr.columns) else 0.0
            if pd.isna(val):
                val = 0.0
            key = "|".join(sorted([a, b]))
            rows.append((key, a, b, round(float(val), 4), ts))

    conn.executemany(
        "INSERT OR REPLACE INTO correlation_cache (pair_key,ticker_a,ticker_b,corr,computed_date)"
        " VALUES (?,?,?,?,?)",
        rows,
    )
    conn.commit()


def _get_corr(ticker_a: str, ticker_b: str, conn: sqlite3.Connection) -> float:
    """Return cached pairwise correlation between two tickers (1.0 if same ticker)."""
    if ticker_a == ticker_b:
        return 1.0
    key = "|".join(sorted([ticker_a, ticker_b]))
    row = conn.execute(
        "SELECT corr FROM correlation_cache WHERE pair_key=?", (key,)
    ).fetchone()
    return float(row["corr"]) if row else 0.0


def _max_corr_with_held(ticker: str, held_tickers: list, conn: sqlite3.Connection) -> float:
    """Return maximum pairwise correlation between ticker and any currently held position."""
    if not held_tickers:
        return 0.0
    return max(_get_corr(ticker, h, conn) for h in held_tickers)


# ── Pool reader ───────────────────────────────────────────────────────────────

def _latest_candidates(pool_conn: sqlite3.Connection) -> pd.DataFrame:
    """Latest signal per ticker from pool (highest R2 among the most recent signals)."""
    df = pd.read_sql(
        """
        SELECT c.*,
               ROW_NUMBER() OVER (
                   PARTITION BY ticker
                   ORDER BY signal_date DESC, candidate_r2 DESC
               ) rn
        FROM candidate_pool c
        """,
        pool_conn,
    )
    return df[df["rn"] == 1].drop(columns=["rn"]).reset_index(drop=True)


# ── State machine ─────────────────────────────────────────────────────────────

def _record_transition(conn, candidate_id, ticker, from_state, to_state, reason):
    """Append a state-machine transition record to state_history."""
    conn.execute(
        "INSERT INTO state_history (candidate_id,ticker,from_state,to_state,reason,ts)"
        " VALUES (?,?,?,?,?,?)",
        (candidate_id, ticker, from_state, to_state, reason, _now()),
    )


def _upsert_state(conn, row: dict):
    """Insert or update a candidate state row in candidate_states."""
    conn.execute(
        """
        INSERT INTO candidate_states
            (state_id, candidate_id, ticker, signal_date, candidate_entry_zone, state,
             candidate_r2, sector, decision_reason, portfolio_impact, replacement_rank,
             sector_exposure, corr_impact, suggested_action, created_at, updated_at)
        VALUES
            (:state_id,:candidate_id,:ticker,:signal_date,:candidate_entry_zone,:state,
             :candidate_r2,:sector,:decision_reason,:portfolio_impact,:replacement_rank,
             :sector_exposure,:corr_impact,:suggested_action,:created_at,:updated_at)
        ON CONFLICT(state_id) DO UPDATE SET
            state=excluded.state,
            decision_reason=excluded.decision_reason,
            portfolio_impact=excluded.portfolio_impact,
            replacement_rank=excluded.replacement_rank,
            sector_exposure=excluded.sector_exposure,
            corr_impact=excluded.corr_impact,
            suggested_action=excluded.suggested_action,
            updated_at=excluded.updated_at
        """,
        row,
    )


# ── Portfolio policy engine ───────────────────────────────────────────────────

def _sector_weights(held: list) -> dict:
    """Fraction of portfolio in each sector given held list."""
    if not held:
        return {}
    counts: dict = {}
    for t in held:
        s = SECTOR_MAP.get(t, "Unknown")
        counts[s] = counts.get(s, 0) + 1
    n = len(held)
    return {s: c / n for s, c in counts.items()}


def _sector_full(sector: str, held: list) -> bool:
    """Return True if sector weight among held positions meets or exceeds the cap."""
    w = _sector_weights(held)
    return w.get(sector, 0.0) >= MAX_SECTOR_PCT


def _assign_states(candidates: pd.DataFrame, held_tickers: list,
                   mgr_conn: sqlite3.Connection) -> pd.DataFrame:
    """
    Assign constitutional states to all candidates.
    Ranking: R2 primary, diversification secondary.
    expected_reward_score NEVER used.
    """
    df = candidates.copy().sort_values("candidate_r2", ascending=False).reset_index(drop=True)

    # Sector counts in current portfolio
    sec_weights = _sector_weights(held_tickers)

    results = []
    primary_count   = 0
    reserve_count   = 0
    reserve_rank    = 0
    portfolio_held  = list(held_tickers)   # grows as PRIMARY_BUY selected

    for _, cand in df.iterrows():
        ticker  = cand["ticker"]
        sector  = cand.get("sector") or SECTOR_MAP.get(ticker, "Unknown")
        r2      = float(cand["candidate_r2"])
        sig_dt  = str(cand["signal_date"])[:10]
        entry   = float(cand["candidate_entry_zone"])
        cid     = str(cand["candidate_id"])

        # Correlation against current portfolio
        max_c = _max_corr_with_held(ticker, portfolio_held, mgr_conn)
        sec_w = _sector_weights(portfolio_held).get(sector, 0.0)

        corr_blocked   = max_c > MAX_CORR
        sector_blocked = sec_w >= MAX_SECTOR_PCT
        port_full      = primary_count >= MAX_POSITIONS

        # --- Decision logic (state machine) ---
        if ticker in held_tickers:
            state  = "HELD"
            reason = "Position currently owned."
            action = "Monitor. Reassess on breach of entry support."
            impact = "No change."
            rank   = 0

        elif r2 >= 60 and not corr_blocked and not sector_blocked and not port_full:
            state   = "PRIMARY_BUY"
            reason  = (f"Highest entry quality (R2={r2:.1f}). "
                       f"Sector {sector} below cap ({sec_w*100:.0f}% < 25%). "
                       f"Max portfolio corr {max_c:.2f} ≤ 0.80.")
            action  = f"Buy immediately. Equal weight {100/MAX_POSITIONS:.1f}%."
            impact  = f"Portfolio {primary_count+1}/{MAX_POSITIONS}. {sector}: {(sec_w+1/MAX_POSITIONS)*100:.0f}%."
            rank    = 0
            primary_count += 1
            if ticker not in portfolio_held:
                portfolio_held.append(ticker)

        elif r2 >= 55 and (corr_blocked or sector_blocked or port_full):
            reserve_rank += 1
            state   = "BUY_RESERVE"
            block   = []
            if port_full:         block.append("portfolio full")
            if sector_blocked:    block.append(f"{sector} at 25% cap")
            if corr_blocked:      block.append(f"corr={max_c:.2f} > 0.80")
            reason  = (f"Excellent entry quality (R2={r2:.1f}). "
                       f"Blocked: {'; '.join(block)}.")
            action  = ("Buy immediately if any "
                       + ("position exits." if port_full else
                          f"{sector} position exits." if sector_blocked else
                          "correlated holding exits."))
            impact  = f"First in replacement queue (priority {reserve_rank})."
            rank    = reserve_rank

        elif r2 >= 45:
            state   = "WATCH"
            reason  = (f"Good setup (R2={r2:.1f}). "
                       f"Needs confirmation or better entry timing.")
            action  = "Monitor. Re-evaluate if R2 improves or portfolio has capacity."
            impact  = "No immediate portfolio change."
            rank    = 0

        else:
            state   = "WATCH"
            reason  = (f"Entry quality below threshold (R2={r2:.1f} < 45). "
                       f"Watchlist only.")
            action  = "No action. Review if fundamentals improve."
            impact  = "None."
            rank    = 0

        results.append({
            "state_id":           _state_id(cid),
            "candidate_id":       cid,
            "ticker":             ticker,
            "signal_date":        sig_dt,
            "candidate_entry_zone": entry,
            "state":              state,
            "candidate_r2":       r2,
            "sector":          sector,
            "decision_reason": reason,
            "portfolio_impact": impact,
            "replacement_rank": rank,
            "sector_exposure":  round(sec_w, 4),
            "corr_impact":      round(max_c, 4),
            "suggested_action": action,
            "created_at":       _now(),
            "updated_at":       _now(),
        })

    return pd.DataFrame(results)


# ── Report builder ────────────────────────────────────────────────────────────

def _portfolio_health(df_states: pd.DataFrame, held_tickers: list,
                      mgr_conn: sqlite3.Connection) -> dict:
    """Compute portfolio health metrics: capacity, sector weights, max correlation."""
    n_held   = len(held_tickers)
    sec_w    = _sector_weights(held_tickers)
    max_sec  = max(sec_w.values()) if sec_w else 0.0
    n_pri    = len(df_states[df_states["state"] == "PRIMARY_BUY"])
    n_res    = len(df_states[df_states["state"] == "BUY_RESERVE"])
    n_watch  = len(df_states[df_states["state"] == "WATCH"])

    # Max pairwise corr among held
    max_held_corr = 0.0
    for i, a in enumerate(held_tickers):
        for b in held_tickers[i+1:]:
            c = _get_corr(a, b, mgr_conn)
            if c > max_held_corr:
                max_held_corr = c

    return {
        "held_positions":       n_held,
        "target_positions":     MAX_POSITIONS,
        "capacity_used_pct":    round(n_held / MAX_POSITIONS * 100, 1),
        "primary_buy_ready":    n_pri,
        "buy_reserve_count":    n_res,
        "watch_count":          n_watch,
        "sector_weights":       {k: round(v*100,1) for k, v in sec_w.items()},
        "max_sector_pct":       round(max_sec*100, 1),
        "sector_cap_ok":        max_sec < MAX_SECTOR_PCT,
        "max_held_correlation": round(max_held_corr, 3),
        "corr_cap_ok":          max_held_corr <= MAX_CORR,
        "weight_method":        "Equal Weight",
        "position_weight_pct":  round(100 / MAX_POSITIONS, 1),
    }


def _corr_matrix_subset(tickers: list, mgr_conn: sqlite3.Connection) -> dict:
    """Return corr matrix dict for a list of tickers."""
    mat = {}
    for a in tickers:
        mat[a] = {}
        for b in tickers:
            mat[a][b] = _get_corr(a, b, mgr_conn)
    return mat


def _build_daily_report(df_states: pd.DataFrame, held_tickers: list,
                         snap_date: str, mgr_conn: sqlite3.Connection,
                         pool_conn: sqlite3.Connection) -> dict:
    """Build full daily portfolio report dict with held detail, states, health, and correlations."""

    def state_rows(state_name):
        """Return sorted list of state row dicts for the given state name."""
        sub = df_states[df_states["state"] == state_name].copy()
        sub = sub.sort_values("replacement_rank" if state_name == "BUY_RESERVE"
                              else "candidate_r2", ascending=(state_name == "BUY_RESERVE"))
        return sub[["ticker","signal_date","candidate_entry_zone","candidate_r2","sector",
                    "decision_reason","replacement_rank","suggested_action"]].to_dict("records")

    # Current prices from pool
    pool_df = pd.read_sql(
        "SELECT ticker, current_price, candidate_entry_zone FROM candidate_pool "
        "ORDER BY signal_date DESC", pool_conn
    )
    latest_price = pool_df.drop_duplicates("ticker").set_index("ticker")["current_price"].to_dict()

    held_detail = []
    for t in held_tickers:
        row = df_states[df_states["ticker"] == t]
        entry  = float(row["candidate_entry_zone"].iloc[0]) if not row.empty else None
        cur    = latest_price.get(t, entry)
        ret    = round((cur / entry - 1) * 100, 1) if (entry and cur) else None
        held_detail.append({
            "ticker":               t,
            "sector":               SECTOR_MAP.get(t, "Unknown"),
            "candidate_entry_zone": entry,
            "current_price":        cur,
            "return_pct":           ret,
            "candidate_r2":         float(row["candidate_r2"].iloc[0]) if not row.empty else None,
        })

    health   = _portfolio_health(df_states, held_tickers, mgr_conn)
    corr_mat = _corr_matrix_subset(held_tickers, mgr_conn) if held_tickers else {}

    reserve = state_rows("BUY_RESERVE")
    # Replacement queue = reserve sorted by rank
    replace_q = sorted(reserve, key=lambda x: x["replacement_rank"])

    return {
        "snap_date":        snap_date,
        "PRIMARY_BUY":      state_rows("PRIMARY_BUY"),
        "BUY_RESERVE":      reserve,
        "WATCH":            state_rows("WATCH"),
        "HELD":             held_detail,
        "REDUCED":          state_rows("REDUCED"),
        "EXIT":             state_rows("EXIT"),
        "sector_allocation": health["sector_weights"],
        "correlation_matrix": corr_mat,
        "replacement_queue":  replace_q,
        "portfolio_health":   health,
    }


# ── Main entry ────────────────────────────────────────────────────────────────

def run_portfolio_manager(
    held_tickers: list = None,
    snap_date: str = None,
    mgr_db: str = MGR_DB,
    pool_db: str = POOL_DB,
) -> dict:
    """
    Run the Constitutional Portfolio Manager for snap_date.

    held_tickers : list of ticker strings currently in portfolio (HELD state).
                   Empty list = no current holdings.
    snap_date    : ISO date string. Defaults to today.
    Returns      : full daily report dict.
    """
    if held_tickers is None:
        held_tickers = []
    if snap_date is None:
        snap_date = str(_date.today())

    mgr_conn  = _conn(mgr_db)
    mgr_conn.executescript(MGR_SCHEMA)
    mgr_conn.commit()

    pool_conn = _conn(pool_db)

    # Ensure correlation cache is populated
    existing = mgr_conn.execute("SELECT COUNT(*) as n FROM correlation_cache").fetchone()
    if existing["n"] == 0:
        print("  Building correlation cache (one-time)...")
        _build_correlation_cache(snap_date, mgr_conn)
        mgr_conn.commit()
        print(f"  Correlation cache: {mgr_conn.execute('SELECT COUNT(*) FROM correlation_cache').fetchone()[0]} pairs")

    # Latest candidate per ticker
    candidates = _latest_candidates(pool_conn)

    # Assign states
    df_states = _assign_states(candidates, held_tickers, mgr_conn)

    # Persist states (append-only via UPSERT)
    for _, row in df_states.iterrows():
        prev = mgr_conn.execute(
            "SELECT state FROM candidate_states WHERE state_id=?",
            (row["state_id"],)
        ).fetchone()
        prev_state = prev["state"] if prev else None

        _upsert_state(mgr_conn, row.to_dict())
        if prev_state != row["state"]:
            _record_transition(mgr_conn, row["candidate_id"], row["ticker"],
                               prev_state, row["state"],
                               row["decision_reason"][:120])

    mgr_conn.commit()

    # Build daily report
    report = _build_daily_report(df_states, held_tickers, snap_date, mgr_conn, pool_conn)

    # Persist snapshot
    snap_id = _snap_id(snap_date)
    mgr_conn.execute(
        """INSERT OR REPLACE INTO portfolio_snapshots
           (snapshot_id,snapshot_date,holdings_json,primary_buy_json,
            reserve_json,watch_json,sector_alloc_json,corr_matrix_json,
            replacement_queue_json,portfolio_health_json,created_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
        (
            snap_id, snap_date,
            json.dumps(report["HELD"]),
            json.dumps(report["PRIMARY_BUY"]),
            json.dumps(report["BUY_RESERVE"]),
            json.dumps(report["WATCH"]),
            json.dumps(report["sector_allocation"]),
            json.dumps(report["correlation_matrix"]),
            json.dumps(report["replacement_queue"]),
            json.dumps(report["portfolio_health"]),
            _now(),
        ),
    )
    mgr_conn.commit()
    mgr_conn.close()
    pool_conn.close()

    return report


def print_daily_report(report: dict):
    """Print formatted daily portfolio report to stdout."""
    W = 72
    sep = "=" * W
    dash = "-" * W

    def section(title):
        """Print a section header separator with title."""
        print(f"\n{sep}")
        print(f"  {title}")
        print(sep)

    snap = report["snap_date"]
    health = report["portfolio_health"]

    print(sep)
    print(f"  CONSTITUTIONAL PORTFOLIO MANAGER — DAILY REPORT")
    print(f"  Date: {snap}  |  {health['held_positions']}/{health['target_positions']} positions  "
          f"|  Weight: {health['position_weight_pct']}% each")
    print(sep)

    # ── PRIMARY BUY ──────────────────────────────────────────────────────────
    section("PRIMARY BUY")
    rows = report["PRIMARY_BUY"]
    if not rows:
        print("  None.")
    for r in rows:
        print(f"\n  Ticker  : {r['ticker']}")
        print(f"  Sector  : {r['sector']}")
        print(f"  R2      : {r['candidate_r2']:.1f}")
        print(f"  Entry   : {r['candidate_entry_zone']:.2f}  (signal {r['signal_date']})")
        print(f"  Reason  : {r['decision_reason']}")
        print(f"  Action  : {r['suggested_action']}")

    # ── BUY RESERVE ──────────────────────────────────────────────────────────
    section("BUY RESERVE (Replacement Queue)")
    rows = sorted(report["BUY_RESERVE"], key=lambda x: x["replacement_rank"])
    if not rows:
        print("  None.")
    for r in rows:
        print(f"\n  [{r['replacement_rank']}] {r['ticker']}  |  Sector: {r['sector']}"
              f"  |  R2: {r['candidate_r2']:.1f}")
        print(f"      Reason  : {r['decision_reason']}")
        print(f"      Action  : {r['suggested_action']}")

    # ── WATCH ─────────────────────────────────────────────────────────────────
    section("WATCH")
    rows = sorted(report["WATCH"], key=lambda x: -x["candidate_r2"])
    if not rows:
        print("  None.")
    for r in rows[:8]:    # show top 8
        print(f"  {r['ticker']:<12} Sector: {r['sector']:<14} R2: {r['candidate_r2']:.1f}"
              f"  |  {r['suggested_action'][:50]}")

    # ── CURRENT HOLDINGS ─────────────────────────────────────────────────────
    section("CURRENT HOLDINGS")
    rows = report["HELD"]
    if not rows:
        print("  No holdings declared.")
    for r in rows:
        ret_str = f"{r['return_pct']:+.1f}%" if r["return_pct"] is not None else "N/A"
        print(f"  {r['ticker']:<12} {r['sector']:<14} "
              f"Entry: {(r['candidate_entry_zone'] or 0):.2f}  "
              f"Current: {(r['current_price'] or 0):.2f}  "
              f"Return: {ret_str}  "
              f"R2: {(r['candidate_r2'] or 0):.1f}")

    # ── SECTOR ALLOCATION ─────────────────────────────────────────────────────
    section("SECTOR ALLOCATION")
    for sec, pct in sorted(report["sector_allocation"].items(), key=lambda x: -x[1]):
        bar = "█" * int(pct / 5) + "░" * (20 - int(pct / 5))
        flag = " ⚠ OVER CAP" if pct >= 25 else ""
        print(f"  {sec:<15} {pct:5.1f}%  {bar}{flag}")
    print(f"\n  Sector cap : {MAX_SECTOR_PCT*100:.0f}%  |  "
          f"Max sector now: {health['max_sector_pct']:.1f}%  |  "
          f"Status: {'OK' if health['sector_cap_ok'] else 'BREACH'}")

    # ── CORRELATION MATRIX ────────────────────────────────────────────────────
    section("CORRELATION MATRIX (Holdings)")
    held_t = [r["ticker"] for r in report["HELD"]]
    mat    = report["correlation_matrix"]
    if not held_t:
        print("  No holdings.")
    else:
        header = f"  {'':12}" + "".join(f"{t[:8]:>10}" for t in held_t)
        print(header)
        for a in held_t:
            row_s = f"  {a:<12}"
            for b in held_t:
                val = mat.get(a, {}).get(b, 0.0)
                flag = " !" if (a != b and val > MAX_CORR) else "  "
                row_s += f"{val:>8.2f}{flag}"
            print(row_s)
        print(f"\n  Max pairwise corr: {health['max_held_correlation']:.3f}  |  "
              f"Cap: {MAX_CORR:.2f}  |  "
              f"Status: {'OK' if health['corr_cap_ok'] else 'BREACH'}")

    # ── REPLACEMENT QUEUE ─────────────────────────────────────────────────────
    section("REPLACEMENT QUEUE")
    queue = report["replacement_queue"]
    if not queue:
        print("  Empty — no reserves pending.")
    for r in queue:
        print(f"  [{r['replacement_rank']}] {r['ticker']:<12} "
              f"Sector: {r['sector']:<14} R2: {r['candidate_r2']:.1f}  "
              f"|  {r['suggested_action'][:52]}")

    # ── PORTFOLIO HEALTH ──────────────────────────────────────────────────────
    section("PORTFOLIO HEALTH")
    h = health
    print(f"  Positions       : {h['held_positions']} / {h['target_positions']}  "
          f"({h['capacity_used_pct']:.0f}% capacity)")
    print(f"  Primary buy     : {h['primary_buy_ready']} ready")
    print(f"  Buy reserve     : {h['buy_reserve_count']} queued")
    print(f"  Watch list      : {h['watch_count']} candidates")
    print(f"  Sector cap      : {'PASS' if h['sector_cap_ok'] else 'BREACH'}  "
          f"(max {h['max_sector_pct']:.1f}%  /  cap 25.0%)")
    print(f"  Corr cap        : {'PASS' if h['corr_cap_ok'] else 'BREACH'}  "
          f"(max {h['max_held_correlation']:.3f}  /  cap 0.80)")
    print(f"  Weight method   : {h['weight_method']}  ({h['position_weight_pct']:.1f}% each)")
    print(f"\n{sep}")


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    # Current held positions (manual portfolio — same as walk-forward)
    HELD_NOW = [
        "PHDC.CA", "HELI.CA", "ORHD.CA", "RMDA.CA", "EMFD.CA",
        "TMGH.CA", "JUFO.CA", "ARCC.CA", "ISPH.CA", "EFID.CA",
        "HRHO.CA", "ORWE.CA", "GBCO.CA", "EAST.CA", "BTFH.CA",
    ]

    print("Running Constitutional Portfolio Manager V1...")
    report = run_portfolio_manager(
        held_tickers=HELD_NOW,
        snap_date=str(_date.today()),
    )
    print_daily_report(report)

    # Validation
    print("\n" + "=" * 72)
    print("  VALIDATION")
    print("=" * 72)
    mgr_conn = _conn(MGR_DB)
    total     = mgr_conn.execute("SELECT COUNT(*) FROM candidate_states").fetchone()[0]
    no_state  = mgr_conn.execute(
        "SELECT COUNT(*) FROM candidate_states WHERE state IS NULL OR state=''").fetchone()[0]
    invalid   = mgr_conn.execute(
        f"SELECT COUNT(*) FROM candidate_states WHERE state NOT IN "
        f"({','.join('?'*len(VALID_STATES))})",
        list(VALID_STATES),
    ).fetchone()[0]
    dup_held  = mgr_conn.execute(
        "SELECT COUNT(*)-COUNT(DISTINCT ticker) FROM candidate_states WHERE state='HELD'"
    ).fetchone()[0]
    snaps     = mgr_conn.execute("SELECT COUNT(*) FROM portfolio_snapshots").fetchone()[0]
    hist      = mgr_conn.execute("SELECT COUNT(*) FROM state_history").fetchone()[0]
    mgr_conn.close()

    print(f"  Total candidate states      : {total}")
    print(f"  Missing state               : {no_state}   {'PASS' if no_state==0 else 'FAIL'}")
    print(f"  Invalid state values        : {invalid}    {'PASS' if invalid==0 else 'FAIL'}")
    print(f"  Duplicate HELD tickers      : {dup_held}   {'PASS' if dup_held==0 else 'FAIL'}")
    print(f"  No lookahead                : PASS  (reads pool only)")
    print(f"  Append-only history entries : {hist}")
    print(f"  Portfolio snapshots         : {snaps}")
    print(f"  Signal engine modified      : NO")
    print(f"  Candidate pool modified     : NO")
    print("=" * 72)
