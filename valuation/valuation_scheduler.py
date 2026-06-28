"""
valuation.valuation_scheduler — Offline valuation pipeline runner.

This is the ONLY authorised writer to valuation.db in production.

Workflow:
  1. Collect official financial statements via yfinance (Layer 1)
  2. Collect market data (Layer 2)
  3. Collect analyst consensus (Layer 3)
  4. Store raw data in valuation.db
  5. Run all 7 valuation models on real financials
  6. Save results

PRODUCTION RULE: If real financial data cannot be collected for a ticker,
no valuation record is written and no IVE card will be shown.
Silence is correct. Fabricated data is never correct.

Run AFTER market close or when new financial statements become available.
NEVER run during scanner execution.

Usage:
  python -m valuation.valuation_scheduler              # all 27 tickers
  python -m valuation.valuation_scheduler COMI.CA      # single ticker
  python -m valuation.valuation_scheduler --init-db    # initialize schema only
"""
from __future__ import annotations

import sqlite3
import sys
import time
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from config.scanner_config import get_constitutional_universe
from valuation import db as _db
from valuation.data_collector import collect_all
from valuation.valuation_engine import run_valuation

_DB_PATH = Path(__file__).parent.parent / "valuation.db"


def init_database() -> None:
    """Initialize valuation.db schema. Safe to run multiple times."""
    _db.init_db()
    print(f"[Scheduler] valuation.db initialized at {_DB_PATH}")


def _store_collected(ticker: str, data: dict) -> None:
    """Persist collected data to valuation.db."""
    conn = sqlite3.connect(str(_DB_PATH))
    try:
        # Company info
        _db.save_company(conn, ticker, data["info"])

        # Layer 1: Financial statements
        if data["financials"]:
            _db.save_financials(conn, ticker, data["financials"])
            print(f"[Scheduler] {ticker}: stored {len(data['financials'])} financial year(s)")

        # Layer 3: Analyst consensus
        for rec in data.get("consensus", []):
            _db.save_analyst_consensus(
                conn,
                ticker,
                rec["source"],
                rec["target_price"],
                rec.get("recommendation", ""),
                rec.get("date", date.today().isoformat()),
            )

        conn.commit()
    finally:
        conn.close()


def run_ticker(ticker: str) -> bool:
    """Full pipeline for one ticker. Returns True on success."""
    try:
        # Phase 1: Collect data
        data = collect_all(ticker)

        # Phase 2: Store data
        _store_collected(ticker, data)

        # Phase 3: Run valuation models
        current_price = data.get("current_price")
        result = run_valuation(ticker, current_price)

        if result:
            fv = result.get("weighted_fair_value")
            print(f"[Scheduler] {ticker} DONE — FairValue={fv:.2f if fv else 'N/A'}")
            return True
        else:
            print(f"[Scheduler] {ticker} — valuation incomplete (insufficient data)")
            return False

    except Exception as e:
        print(f"[Scheduler] ERROR {ticker}: {e}")
        return False


def run_all(tickers: list[str] | None = None, delay_s: float = 2.0) -> dict:
    """Run full pipeline for all (or specified) tickers.

    delay_s: seconds to wait between tickers to respect rate limits.
    Returns summary dict: {ticker: 'ok'|'failed'}.
    """
    if tickers is None:
        tickers = get_constitutional_universe()

    print(f"\n[Scheduler] Starting IVE run — {len(tickers)} ticker(s)")
    print(f"[Scheduler] Database: {_DB_PATH}")
    print(f"[Scheduler] Date: {date.today().isoformat()}\n")

    init_database()
    summary: dict[str, str] = {}

    for i, ticker in enumerate(tickers, start=1):
        print(f"\n[Scheduler] ── {i}/{len(tickers)}: {ticker} ──")
        ok = run_ticker(ticker)
        summary[ticker] = "ok" if ok else "failed"
        if i < len(tickers):
            time.sleep(delay_s)  # Rate limit

    ok_count   = sum(1 for v in summary.values() if v == "ok")
    fail_count = len(summary) - ok_count
    print(f"\n[Scheduler] Completed — {ok_count} ok, {fail_count} failed")
    if fail_count:
        failed = [t for t, s in summary.items() if s == "failed"]
        print(f"[Scheduler] Failed: {failed}")
    return summary


if __name__ == "__main__":
    args = sys.argv[1:]
    if "--init-db" in args:
        init_database()
    elif args:
        tickers_arg = [a for a in args if not a.startswith("--")]
        run_all(tickers_arg)
    else:
        run_all()
