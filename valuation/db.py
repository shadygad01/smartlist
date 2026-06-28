"""
valuation.db — Unified database interface for IVE V2.

Read path (called during presentation):
  get_valuation_card(ticker) — single SELECT, zero computation, never raises.
  This is the ONLY function called during scanner/dashboard/email execution.

Write path (called only by valuation_scheduler):
  save_*() functions — used exclusively by the offline scheduler pipeline.
  init_db() — idempotent schema initialization with migration support.

data_sources table: every stored financial field is traceable to its
origin source, collection time, and validation status.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

_DB = Path(__file__).parent.parent / "valuation.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS companies (
    ticker             TEXT PRIMARY KEY,
    company_name       TEXT,
    sector             TEXT,
    industry           TEXT,
    currency           TEXT DEFAULT 'EGP',
    shares_outstanding REAL
);

CREATE TABLE IF NOT EXISTS financials (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker              TEXT NOT NULL,
    year                INTEGER NOT NULL,
    quarter             TEXT,
    revenue             REAL,
    gross_profit        REAL,
    operating_income    REAL,
    ebit                REAL,
    ebitda              REAL,
    net_income          REAL,
    operating_cash_flow REAL,
    free_cash_flow      REAL,
    cash                REAL,
    debt                REAL,
    equity              REAL,
    assets              REAL,
    liabilities         REAL,
    book_value          REAL,
    eps                 REAL,
    dividend            REAL,
    roe                 REAL,
    roic                REAL,
    capex               REAL,
    shares              REAL,
    UNIQUE(ticker, year)
);

CREATE TABLE IF NOT EXISTS forecasts (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker          TEXT NOT NULL,
    forecast_year   INTEGER NOT NULL,
    revenue         REAL,
    eps             REAL,
    fcf             REAL,
    dividend        REAL,
    growth_rate     REAL,
    UNIQUE(ticker, forecast_year)
);

CREATE TABLE IF NOT EXISTS valuation_assumptions (
    ticker              TEXT PRIMARY KEY,
    risk_free_rate      REAL DEFAULT 0.1250,
    equity_risk_premium REAL DEFAULT 0.0700,
    beta                REAL DEFAULT 1.0,
    tax_rate            REAL DEFAULT 0.2250,
    terminal_growth     REAL DEFAULT 0.0400,
    wacc                REAL DEFAULT 0.1600,
    updated_at          TEXT
);

CREATE TABLE IF NOT EXISTS valuation_models (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker              TEXT NOT NULL,
    valuation_date      TEXT NOT NULL,
    dcf                 REAL,
    ddm                 REAL,
    residual_income     REAL,
    earnings_power      REAL,
    ev_ebitda           REAL,
    pe                  REAL,
    pb                  REAL,
    weighted_fair_value REAL,
    bull_case           REAL,
    base_case           REAL,
    bear_case           REAL,
    UNIQUE(ticker, valuation_date)
);

CREATE TABLE IF NOT EXISTS analyst_consensus (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker          TEXT NOT NULL,
    source          TEXT NOT NULL,
    target_price    REAL,
    recommendation  TEXT,
    date            TEXT,
    UNIQUE(ticker, source, date)
);

CREATE TABLE IF NOT EXISTS valuation_history (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker              TEXT NOT NULL,
    date                TEXT NOT NULL,
    current_price       REAL,
    fair_value          REAL,
    discount_percentage REAL,
    UNIQUE(ticker, date)
);

CREATE TABLE IF NOT EXISTS data_sources (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker           TEXT NOT NULL,
    statement        TEXT NOT NULL,    -- 'income','balance','cashflow','derived','market','analyst','economic'
    period           TEXT NOT NULL,    -- '2024', '2024-Q1', etc.
    field_name       TEXT NOT NULL,
    source_name      TEXT NOT NULL,    -- 'yfinance', 'alpha_vantage', 'polygon', etc.
    source_priority  INTEGER NOT NULL, -- 1=official,2=structured,3=market,4=analyst,5=economic
    collection_time  TEXT NOT NULL,    -- ISO 8601 UTC
    validation_status TEXT NOT NULL,   -- 'valid','warning','rejected'
    data_version     TEXT NOT NULL,    -- e.g. 'yfinance-2025-06-28-v1'
    UNIQUE(ticker, statement, period, field_name, source_name)
);
"""

_MIGRATION_SQL = [
    # Add quarter column to financials if absent (migration for pre-V2 databases)
    "ALTER TABLE financials ADD COLUMN quarter TEXT",
    # data_sources is created by _SCHEMA above; no extra migration needed
]


def init_db() -> None:
    """Initialize valuation.db schema. Idempotent. Applies migrations for existing DBs."""
    conn = sqlite3.connect(str(_DB))
    conn.executescript(_SCHEMA)
    _apply_migrations(conn)
    conn.commit()
    conn.close()


def _apply_migrations(conn: sqlite3.Connection) -> None:
    """Apply schema migrations that cannot use CREATE IF NOT EXISTS."""
    existing_cols = {
        row[1]
        for row in conn.execute("PRAGMA table_info(financials)")
    }
    for sql in _MIGRATION_SQL:
        # Only run ADD COLUMN if column not already present
        if "ADD COLUMN" in sql:
            col = sql.split("ADD COLUMN")[1].strip().split()[0]
            if col not in existing_cols:
                try:
                    conn.execute(sql)
                except Exception:
                    pass


def get_valuation_card(ticker: str) -> dict | None:
    """Return valuation card data for ticker, or None if unavailable.

    Single lightweight DB read. Never computes anything.
    Safe to call with no valuation.db present — returns None silently.

    Returned dict keys:
        ticker, valuation_date, weighted_fair_value,
        bull_case, base_case, bear_case,
        analyst_consensus_price, last_stmt_year
    """
    if not _DB.exists():
        return None
    try:
        conn = sqlite3.connect(str(_DB))
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            """
            SELECT
                vm.ticker,
                vm.valuation_date,
                vm.weighted_fair_value,
                vm.bull_case,
                vm.base_case,
                vm.bear_case,
                (SELECT ROUND(AVG(ac.target_price), 2)
                 FROM analyst_consensus ac
                 WHERE ac.ticker = vm.ticker) AS analyst_consensus_price,
                (SELECT MAX(f.year)
                 FROM financials f
                 WHERE f.ticker = vm.ticker) AS last_stmt_year
            FROM valuation_models vm
            WHERE vm.ticker = ?
            ORDER BY vm.valuation_date DESC
            LIMIT 1
            """,
            (ticker,),
        ).fetchone()
        conn.close()
        if row is None:
            return None
        return dict(row)
    except Exception:
        return None


def save_company(conn: sqlite3.Connection, ticker: str, info: dict) -> None:
    conn.execute(
        """INSERT OR REPLACE INTO companies
           (ticker, company_name, sector, industry, currency, shares_outstanding)
           VALUES (?,?,?,?,?,?)""",
        (
            ticker,
            info.get("company_name"),
            info.get("sector"),
            info.get("industry"),
            info.get("currency", "EGP"),
            info.get("shares_outstanding"),
        ),
    )


def save_financials(conn: sqlite3.Connection, ticker: str, rows: list[dict]) -> None:
    for r in rows:
        conn.execute(
            """INSERT OR REPLACE INTO financials
               (ticker, year, quarter, revenue, gross_profit, operating_income, ebit, ebitda,
                net_income, operating_cash_flow, free_cash_flow, cash, debt, equity,
                assets, liabilities, book_value, eps, dividend, roe, roic, capex, shares)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                ticker,
                r.get("year"),
                r.get("quarter"),
                r.get("revenue"),
                r.get("gross_profit"),
                r.get("operating_income"),
                r.get("ebit"),
                r.get("ebitda"),
                r.get("net_income"),
                r.get("operating_cash_flow"),
                r.get("free_cash_flow"),
                r.get("cash"),
                r.get("debt"),
                r.get("equity"),
                r.get("assets"),
                r.get("liabilities"),
                r.get("book_value"),
                r.get("eps"),
                r.get("dividend"),
                r.get("roe"),
                r.get("roic"),
                r.get("capex"),
                r.get("shares"),
            ),
        )


def save_forecasts(conn: sqlite3.Connection, ticker: str, rows: list[dict]) -> None:
    for r in rows:
        conn.execute(
            """INSERT OR REPLACE INTO forecasts
               (ticker, forecast_year, revenue, eps, fcf, dividend, growth_rate)
               VALUES (?,?,?,?,?,?,?)""",
            (
                ticker,
                r.get("forecast_year"),
                r.get("revenue"),
                r.get("eps"),
                r.get("fcf"),
                r.get("dividend"),
                r.get("growth_rate"),
            ),
        )


def save_valuation_model(conn: sqlite3.Connection, ticker: str, date: str, result: dict) -> None:
    conn.execute(
        """INSERT OR REPLACE INTO valuation_models
           (ticker, valuation_date, dcf, ddm, residual_income, earnings_power,
            ev_ebitda, pe, pb, weighted_fair_value, bull_case, base_case, bear_case)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            ticker,
            date,
            result.get("dcf"),
            result.get("ddm"),
            result.get("residual_income"),
            result.get("earnings_power"),
            result.get("ev_ebitda"),
            result.get("pe"),
            result.get("pb"),
            result.get("weighted_fair_value"),
            result.get("bull_case"),
            result.get("base_case"),
            result.get("bear_case"),
        ),
    )


def save_analyst_consensus(
    conn: sqlite3.Connection, ticker: str, source: str, target: float, rec: str, date: str
) -> None:
    conn.execute(
        """INSERT OR REPLACE INTO analyst_consensus
           (ticker, source, target_price, recommendation, date)
           VALUES (?,?,?,?,?)""",
        (ticker, source, target, rec, date),
    )


def save_valuation_history(
    conn: sqlite3.Connection, ticker: str, date: str, current_price: float, fair_value: float
) -> None:
    discount = round((fair_value - current_price) / current_price * 100, 2) if current_price else None
    conn.execute(
        """INSERT OR REPLACE INTO valuation_history
           (ticker, date, current_price, fair_value, discount_percentage)
           VALUES (?,?,?,?,?)""",
        (ticker, date, current_price, fair_value, discount),
    )


def save_data_source(
    conn:              sqlite3.Connection,
    ticker:            str,
    statement:         str,
    period:            str,
    field_name:        str,
    source_name:       str,
    source_priority:   int,
    collection_time:   str,
    validation_status: str,
    data_version:      str,
) -> None:
    """Record provenance of a single collected data field."""
    conn.execute(
        """INSERT OR REPLACE INTO data_sources
           (ticker, statement, period, field_name, source_name,
            source_priority, collection_time, validation_status, data_version)
           VALUES (?,?,?,?,?,?,?,?,?)""",
        (ticker, statement, period, field_name, source_name,
         source_priority, collection_time, validation_status, data_version),
    )


def save_many_data_sources(conn: sqlite3.Connection, records: list[dict]) -> None:
    """Batch-insert data_sources records. Each dict must have all required keys."""
    conn.executemany(
        """INSERT OR REPLACE INTO data_sources
           (ticker, statement, period, field_name, source_name,
            source_priority, collection_time, validation_status, data_version)
           VALUES (:ticker,:statement,:period,:field_name,:source_name,
                   :source_priority,:collection_time,:validation_status,:data_version)""",
        records,
    )


def save_valuation_assumptions(
    conn:   sqlite3.Connection,
    ticker: str,
    assum:  dict,
) -> None:
    """Upsert valuation assumptions for a ticker (economic inputs layer)."""
    conn.execute(
        """INSERT OR REPLACE INTO valuation_assumptions
           (ticker, risk_free_rate, equity_risk_premium, beta, tax_rate,
            terminal_growth, wacc, updated_at)
           VALUES (?,?,?,?,?,?,?,?)""",
        (
            ticker,
            assum.get("risk_free_rate",      0.1250),
            assum.get("equity_risk_premium",  0.0700),
            assum.get("beta",                 1.0),
            assum.get("tax_rate",             0.2250),
            assum.get("terminal_growth",      0.0400),
            assum.get("wacc",                 0.1600),
            assum.get("updated_at",           ""),
        ),
    )


def get_data_sources(conn: sqlite3.Connection, ticker: str) -> list[dict]:
    """Return all data_sources records for a ticker (provenance audit)."""
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT * FROM data_sources WHERE ticker=? ORDER BY period DESC, statement, field_name",
        (ticker,),
    ).fetchall()
    return [dict(r) for r in rows]


def get_financials(conn: sqlite3.Connection, ticker: str) -> list[dict]:
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT * FROM financials WHERE ticker=? ORDER BY year ASC", (ticker,)
    ).fetchall()
    return [dict(r) for r in rows]


def get_assumptions(conn: sqlite3.Connection, ticker: str) -> dict:
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        "SELECT * FROM valuation_assumptions WHERE ticker=?", (ticker,)
    ).fetchone()
    if row:
        return dict(row)
    return {
        "risk_free_rate": 0.1250,
        "equity_risk_premium": 0.0700,
        "beta": 1.0,
        "tax_rate": 0.2250,
        "terminal_growth": 0.0400,
        "wacc": 0.1600,
    }
