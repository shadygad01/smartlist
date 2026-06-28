"""
valuation.db — Read-only interface to valuation.db for presentation layers.

This is the ONLY valuation module imported during scanner/presentation execution.
Contract: one SELECT per ticker, zero computation, never raises.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

_DB = Path(__file__).parent.parent / "valuation.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS companies (
    ticker          TEXT PRIMARY KEY,
    company_name    TEXT,
    sector          TEXT,
    industry        TEXT,
    currency        TEXT DEFAULT 'EGP',
    shares_outstanding REAL
);

CREATE TABLE IF NOT EXISTS financials (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker              TEXT NOT NULL,
    year                INTEGER NOT NULL,
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
"""


def init_db() -> None:
    """Initialize valuation.db schema. Idempotent."""
    conn = sqlite3.connect(str(_DB))
    conn.executescript(_SCHEMA)
    conn.commit()
    conn.close()


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
               (ticker, year, revenue, gross_profit, operating_income, ebit, ebitda,
                net_income, operating_cash_flow, free_cash_flow, cash, debt, equity,
                assets, liabilities, book_value, eps, dividend, roe, roic, capex, shares)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                ticker,
                r.get("year"),
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
