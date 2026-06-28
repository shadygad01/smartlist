"""
valuation.valuation_scheduler — IVE V2 offline pipeline runner.

This is the ONLY authorised writer to valuation.db in production.

Pipeline per ticker:
  Phase 1 — Collect     : SourceManager fetches raw data (priority 2 yfinance; future: priority 1 IR)
  Phase 2 — Normalize   : NormalizationEngine maps raw schema → canonical schema
  Phase 3 — Validate    : ValidationEngine rejects invalid records
  Phase 4 — Store Raw   : financials, companies, analyst_consensus, data_sources, assumptions
  Phase 5 — Model       : Run 7 valuation models on validated data
  Phase 6 — Store Result: valuation_models, valuation_history

PRODUCTION RULES:
  • If validated financials are empty → no valuation record written → no IVE card shown.
  • Silence is correct. Fabricated data is never correct.
  • Economic assumptions are persisted to valuation_assumptions table (never hardcoded).
  • Every stored financial field is traceable through data_sources.

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
from datetime import date, datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from config.scanner_config import get_constitutional_universe
from valuation import db as _db
from valuation.data_collector import collect_all, build_data_source_records
from valuation.valuation_engine import run_valuation

_DB_PATH = Path(__file__).parent.parent / "valuation.db"

# EGX-calibrated economic defaults (stored in DB at init, never hardcoded in model code)
_EGX_DEFAULTS = {
    "risk_free_rate":      0.1250,   # Egypt 10Y T-bill ~12.5%
    "equity_risk_premium": 0.0700,   # EGX equity risk premium 7%
    "beta":                1.0,      # market-neutral default; overridden per-ticker from yfinance
    "tax_rate":            0.2250,   # Egypt corporate tax 22.5%
    "terminal_growth":     0.0400,   # 4% long-run nominal terminal growth
    "wacc":                0.1600,   # 16% WACC for EGX (rfr + beta*erp ≈ 0.125 + 1.0*0.07)
}


def init_database() -> None:
    """Initialize valuation.db schema and seed EGX defaults. Safe to run repeatedly."""
    _db.init_db()
    _seed_assumptions()
    print(f"[Scheduler] valuation.db initialized at {_DB_PATH}")


def _seed_assumptions() -> None:
    """
    Seed valuation_assumptions with EGX defaults for all universe tickers.
    Uses INSERT OR IGNORE so existing per-ticker overrides are preserved.
    """
    tickers = get_constitutional_universe()
    conn    = sqlite3.connect(str(_DB_PATH))
    today   = date.today().isoformat()
    try:
        conn.executemany(
            """INSERT OR IGNORE INTO valuation_assumptions
               (ticker, risk_free_rate, equity_risk_premium, beta, tax_rate,
                terminal_growth, wacc, updated_at)
               VALUES (?,?,?,?,?,?,?,?)""",
            [
                (
                    t,
                    _EGX_DEFAULTS["risk_free_rate"],
                    _EGX_DEFAULTS["equity_risk_premium"],
                    _EGX_DEFAULTS["beta"],
                    _EGX_DEFAULTS["tax_rate"],
                    _EGX_DEFAULTS["terminal_growth"],
                    _EGX_DEFAULTS["wacc"],
                    today,
                )
                for t in tickers
            ],
        )
        conn.commit()
    finally:
        conn.close()


def _store_collected(ticker: str, data: dict) -> None:
    """
    Persist collected and validated data to valuation.db.

    Writes:
      • companies        — company/market metadata
      • financials       — validated annual statements only
      • analyst_consensus — validated analyst targets
      • valuation_assumptions — live beta from source, EGX defaults for rest
      • data_sources     — provenance record for every stored financial field
    """
    conn = sqlite3.connect(str(_DB_PATH))
    try:
        # ── Company info ─────────────────────────────────────────────────────
        _db.save_company(conn, ticker, data["info"])

        # ── Validated financials ─────────────────────────────────────────────
        fin_rows = data.get("financials", [])
        if fin_rows:
            _db.save_financials(conn, ticker, fin_rows)
            print(f"[Scheduler] {ticker}: stored {len(fin_rows)} validated financial year(s)")

        rejected = data.get("financials_rejected", [])
        if rejected:
            print(f"[Scheduler] {ticker}: skipped {len(rejected)} rejected year(s)")

        # ── Analyst consensus ────────────────────────────────────────────────
        for rec in data.get("consensus", []):
            _db.save_analyst_consensus(
                conn,
                ticker,
                rec["source"],
                rec["target_price"],
                rec.get("recommendation", ""),
                rec.get("date", date.today().isoformat()),
            )

        # ── Economic assumptions (beta from live source) ─────────────────────
        live_beta  = data.get("beta")
        now        = datetime.now(timezone.utc).isoformat()
        assumptions = dict(_EGX_DEFAULTS)
        assumptions["updated_at"] = now
        if live_beta is not None:
            assumptions["beta"] = live_beta
            # Recompute WACC with live beta: rfr + beta*erp
            assumptions["wacc"] = round(
                assumptions["risk_free_rate"]
                + assumptions["beta"] * assumptions["equity_risk_premium"],
                4,
            )
        _db.save_valuation_assumptions(conn, ticker, assumptions)

        # ── data_sources provenance ──────────────────────────────────────────
        fin_meta    = data.get("source_meta", {}).get("financials")
        ds_records  = build_data_source_records(ticker, fin_rows, fin_meta)
        if ds_records:
            _db.save_many_data_sources(conn, ds_records)
            print(f"[Scheduler] {ticker}: recorded {len(ds_records)} data_sources entries")

        conn.commit()
    finally:
        conn.close()


def run_ticker(ticker: str) -> bool:
    """Full pipeline for one ticker. Returns True on success."""
    try:
        # Phase 1–3: Collect, normalize, validate
        data = collect_all(ticker)

        # Phase 4: Store raw validated data
        _store_collected(ticker, data)

        # Phase 5–6: Run valuation models, store result
        current_price = data.get("current_price")
        result = run_valuation(ticker, current_price)

        if result:
            fv = result.get("weighted_fair_value")
            print(
                f"[Scheduler] {ticker} DONE — "
                f"FairValue={'%.2f' % fv if fv else 'N/A'}"
            )
            return True
        else:
            print(f"[Scheduler] {ticker} — valuation incomplete (insufficient validated data)")
            return False

    except Exception as exc:
        print(f"[Scheduler] ERROR {ticker}: {exc}")
        return False


def run_all(tickers: list[str] | None = None, delay_s: float = 2.0) -> dict:
    """
    Run the full IVE V2 pipeline for all (or specified) tickers.

    delay_s: seconds to wait between tickers (yfinance rate-limit courtesy).
    Returns summary dict: {ticker: 'ok' | 'failed'}.
    """
    if tickers is None:
        tickers = get_constitutional_universe()

    print(f"\n[Scheduler] Starting IVE V2 run — {len(tickers)} ticker(s)")
    print(f"[Scheduler] Database: {_DB_PATH}")
    print(f"[Scheduler] Date:     {date.today().isoformat()}\n")

    init_database()
    summary: dict[str, str] = {}

    for i, ticker in enumerate(tickers, start=1):
        print(f"\n[Scheduler] ── {i}/{len(tickers)}: {ticker} ──")
        ok = run_ticker(ticker)
        summary[ticker] = "ok" if ok else "failed"
        if i < len(tickers):
            time.sleep(delay_s)

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
