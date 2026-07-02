"""
PriceAuthority — Single Source of Truth for Current Prices.

get_current_price(ticker) is the ONLY public interface.
Every component MUST use this function. No direct reads from candidate_pool,
presentation_snapshot, stock_dna, sqlite legacy, or temporary dicts.

Source: universe_snapshot.db (built by universe_snapshot.py which aggregates
        signal_history > candidate_pool > timeline > egx_research in priority order).
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

BASE     = Path(__file__).parent
_SNAP_DB = BASE / "universe_snapshot.db"


def get_current_price(ticker: str) -> float | None:
    """Return current price for ticker from universe_snapshot.db, or None."""
    if not _SNAP_DB.exists():
        return None
    conn = sqlite3.connect(str(_SNAP_DB))
    try:
        row = conn.execute(
            "SELECT current_price FROM universe_snapshot WHERE ticker=?", (ticker,)
        ).fetchone()
        if row and row[0] and row[0] > 0:
            return float(row[0])
        return None
    finally:
        conn.close()


def get_all_prices() -> dict[str, float]:
    """Return {ticker: current_price} for all tickers with a valid price."""
    if not _SNAP_DB.exists():
        return {}
    conn = sqlite3.connect(str(_SNAP_DB))
    try:
        rows = conn.execute(
            "SELECT ticker, current_price FROM universe_snapshot "
            "WHERE current_price IS NOT NULL AND current_price > 0"
        ).fetchall()
        return {r[0]: float(r[1]) for r in rows}
    finally:
        conn.close()


def get_price_date(ticker: str) -> str:
    """Return last_price_update date string for ticker, or ''."""
    if not _SNAP_DB.exists():
        return ""
    conn = sqlite3.connect(str(_SNAP_DB))
    try:
        row = conn.execute(
            "SELECT last_price_update FROM universe_snapshot WHERE ticker=?", (ticker,)
        ).fetchone()
        return (row[0] or "")[:10] if row else ""
    finally:
        conn.close()


def get_data_as_of() -> str:
    """Return the most recent last_price_update date across all tickers."""
    if not _SNAP_DB.exists():
        return ""
    conn = sqlite3.connect(str(_SNAP_DB))
    try:
        row = conn.execute(
            "SELECT MAX(last_price_update) FROM universe_snapshot "
            "WHERE last_price_update IS NOT NULL AND last_price_update != ''"
        ).fetchone()
        return (row[0] or "")[:10] if row else ""
    finally:
        conn.close()
