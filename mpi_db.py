"""
Market Psychology Intelligence — Database Layer.

Single source of truth for behavioral snapshots.
Append-only: historical records are never rewritten.
New engine versions create new records alongside old ones.
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Optional

BASE = Path(__file__).parent
_DB  = str(BASE / "mpi_snapshots.db")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS mpi_snapshots (
    id                       INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker                   TEXT    NOT NULL,
    signal_type              TEXT    NOT NULL,
    analysis_date            TEXT    NOT NULL,
    engine_version           TEXT    NOT NULL DEFAULT '1.0',
    schema_version           TEXT    NOT NULL DEFAULT '1',
    phase                    TEXT    NOT NULL,
    confidence               REAL    NOT NULL,
    confidence_label         TEXT    NOT NULL,
    institutional_interpretation TEXT,
    retail_interpretation        TEXT,
    buying_pressure              TEXT,
    selling_pressure             TEXT,
    supply_absorption            TEXT,
    distribution_probability     TEXT,
    key_drivers                  TEXT,
    evidence_json                TEXT,
    historical_cases             INTEGER DEFAULT 0,
    similarity_score             REAL    DEFAULT 0.0,
    avg_mfe40                    REAL    DEFAULT 0.0,
    avg_drawdown                 REAL    DEFAULT 0.0,
    avg_holding_days             REAL    DEFAULT 0.0,
    historical_confidence        TEXT    DEFAULT 'LOW',
    explanation                  TEXT    NOT NULL,
    explanation_compact          TEXT    NOT NULL,
    created_at                   TEXT    NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_mpi_ticker_date_type
    ON mpi_snapshots(ticker, analysis_date, signal_type);

CREATE INDEX IF NOT EXISTS idx_mpi_date
    ON mpi_snapshots(analysis_date);
"""


def _conn(db_path: str = _DB) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(db_path: str = _DB) -> None:
    conn = _conn(db_path)
    conn.executescript(_SCHEMA)
    conn.commit()
    conn.close()


def upsert_snapshot(snap: dict, db_path: str = _DB) -> None:
    """Insert or replace a behavioral snapshot (upsert by ticker+date+signal_type)."""
    init_db(db_path)
    conn = _conn(db_path)
    try:
        conn.execute(
            """
            INSERT INTO mpi_snapshots (
                ticker, signal_type, analysis_date, engine_version, schema_version,
                phase, confidence, confidence_label,
                institutional_interpretation, retail_interpretation,
                buying_pressure, selling_pressure, supply_absorption,
                distribution_probability, key_drivers, evidence_json,
                historical_cases, similarity_score, avg_mfe40,
                avg_drawdown, avg_holding_days, historical_confidence,
                explanation, explanation_compact, created_at
            ) VALUES (
                :ticker, :signal_type, :analysis_date, :engine_version, :schema_version,
                :phase, :confidence, :confidence_label,
                :institutional_interpretation, :retail_interpretation,
                :buying_pressure, :selling_pressure, :supply_absorption,
                :distribution_probability, :key_drivers, :evidence_json,
                :historical_cases, :similarity_score, :avg_mfe40,
                :avg_drawdown, :avg_holding_days, :historical_confidence,
                :explanation, :explanation_compact, :created_at
            )
            ON CONFLICT(ticker, analysis_date, signal_type) DO UPDATE SET
                engine_version           = excluded.engine_version,
                phase                    = excluded.phase,
                confidence               = excluded.confidence,
                confidence_label         = excluded.confidence_label,
                institutional_interpretation = excluded.institutional_interpretation,
                retail_interpretation    = excluded.retail_interpretation,
                buying_pressure          = excluded.buying_pressure,
                selling_pressure         = excluded.selling_pressure,
                supply_absorption        = excluded.supply_absorption,
                distribution_probability = excluded.distribution_probability,
                key_drivers              = excluded.key_drivers,
                evidence_json            = excluded.evidence_json,
                historical_cases         = excluded.historical_cases,
                similarity_score         = excluded.similarity_score,
                avg_mfe40                = excluded.avg_mfe40,
                avg_drawdown             = excluded.avg_drawdown,
                avg_holding_days         = excluded.avg_holding_days,
                historical_confidence    = excluded.historical_confidence,
                explanation              = excluded.explanation,
                explanation_compact      = excluded.explanation_compact,
                created_at               = excluded.created_at
            """,
            snap,
        )
        conn.commit()
    finally:
        conn.close()


def load_snapshot(ticker: str, date_str: str, signal_type: str,
                  db_path: str = _DB) -> Optional[dict]:
    """Load a stored behavioral snapshot. Returns None if not found."""
    if not Path(db_path).exists():
        return None
    conn = _conn(db_path)
    try:
        row = conn.execute(
            "SELECT * FROM mpi_snapshots WHERE ticker=? AND analysis_date=? AND signal_type=?",
            (ticker, date_str, signal_type),
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def load_snapshots_for_date(date_str: str, db_path: str = _DB) -> list[dict]:
    """Load all behavioral snapshots for a given date."""
    if not Path(db_path).exists():
        return []
    conn = _conn(db_path)
    try:
        rows = conn.execute(
            "SELECT * FROM mpi_snapshots WHERE analysis_date=?", (date_str,)
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def load_snapshots_for_tickers(tickers: list[str], date_str: str,
                                db_path: str = _DB) -> dict[str, dict]:
    """Return {ticker: snapshot} dict for the given tickers and date."""
    if not tickers or not Path(db_path).exists():
        return {}
    conn = _conn(db_path)
    try:
        placeholders = ",".join("?" * len(tickers))
        rows = conn.execute(
            f"SELECT * FROM mpi_snapshots WHERE ticker IN ({placeholders}) AND analysis_date=?",
            (*tickers, date_str),
        ).fetchall()
        result: dict[str, dict] = {}
        for r in rows:
            d = dict(r)
            key = d["ticker"]
            existing = result.get(key)
            if existing is None or d["signal_type"] in ("FIRST_BUY", "RE_ACCUMULATION"):
                result[key] = d
        return result
    finally:
        conn.close()
