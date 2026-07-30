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

import json
import sqlite3
import sys
import time
from datetime import date, datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from config.scanner_config import get_constitutional_universe
from valuation import db as _db
from valuation.data_collector import collect_all, build_data_source_records
from valuation.official_interim import build_ttm_row, build_source_records
from valuation.valuation_engine import run_valuation

_DB_PATH = Path(__file__).parent.parent / "valuation.db"

# EGX-calibrated economic defaults (stored in DB at init, never hardcoded in model code)
# NOTE: 'wacc' stores CAPM cost of equity (Ke = rfr + beta*erp), NOT true WACC.
# True WACC requires per-company D/E ratio and cost of debt which are not available.
# Using Ke as discount rate is the conservative (all-equity) assumption.
# At beta=1.0: Ke = 0.19 + 1.0×0.07 = 0.26.
_EGX_DEFAULTS = {
    # CBE overnight deposit rate confirmed by the 2026-07-09 MPC release.
    # It is the transparent local nominal risk-free proxy until an automated
    # sovereign yield-curve source is available.
    "risk_free_rate":      0.1900,
    "equity_risk_premium": 0.0700,   # EGX equity risk premium 7%
    "beta":                1.0,      # market-neutral default; overridden per-ticker from yfinance
    "tax_rate":            0.2250,   # Egypt corporate tax 22.5%
    "terminal_growth":     0.0400,   # 4% long-run nominal terminal growth
    "wacc":                0.2600,   # Ke default = rfr(19%) + beta(1.0)×erp(7%) = 26%
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

        # Add the latest official interim result as a TTM row, after annual
        # storage, so models consume the freshest comparable period.
        ttm_row, filing = build_ttm_row(ticker, fin_rows)
        if ttm_row is not None:
            _db.save_financials(conn, ticker, [ttm_row])
            print(f"[Scheduler] {ticker}: stored official {filing['label']} row")

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

        # Entry-price-derived seed targets are model outputs, not independent
        # analyst research, and must never be labelled as consensus.
        conn.execute(
            "DELETE FROM analyst_consensus WHERE ticker=? AND source='ive_estimate'",
            (ticker,),
        )

        # ── Economic assumptions (beta from live source) ─────────────────────
        live_beta  = data.get("beta")
        now        = datetime.now(timezone.utc).isoformat()
        assumptions = dict(_EGX_DEFAULTS)
        assumptions["updated_at"] = now
        if live_beta is not None:
            assumptions["beta"] = live_beta
            # Note: stored as 'wacc' but formula is CAPM Ke = rfr + beta*erp.
            # This assumes all-equity financing (no leverage adjustment).
            # True WACC would require per-company D/E ratio and cost of debt,
            # which are not available from the current data sources.
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
        if ttm_row is not None:
            official_records = build_source_records(ticker, filing, now)
            _db.save_many_data_sources(conn, official_records)
            print(f"[Scheduler] {ticker}: recorded {len(official_records)} official filing fields")

        conn.commit()
    finally:
        conn.close()


def run_ticker(ticker: str) -> tuple[bool, dict]:
    """
    Full pipeline for one ticker.
    Returns (success, stats) where stats carries per-ticker metrics for the quality report.
    """
    stats: dict = {
        "has_financials":   False,
        "has_dividend":     False,
        "has_analyst":      False,
        "validation_fails": 0,
        "sources":          set(),
        "model_successes":  {},
    }
    try:
        # Phase 1–3: Collect, normalize, validate
        data = collect_all(ticker)

        fin_valid    = data.get("financials", [])
        fin_rejected = data.get("financials_rejected", [])
        consensus    = data.get("consensus", [])

        stats["has_financials"]  = len(fin_valid) > 0
        stats["has_dividend"]    = any(r.get("dividend") is not None for r in fin_valid)
        stats["has_analyst"]     = len(consensus) > 0
        stats["validation_fails"] = len(fin_rejected)

        src_meta = data.get("source_meta", {})
        for sm in src_meta.values():
            if sm:
                stats["sources"].add(sm.source_name)

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
            # Collect per-model success flags
            for ms in result.get("_model_statuses", []):
                stats["model_successes"][ms["model"]] = ms["success"]
            return True, stats
        else:
            print(f"[Scheduler] {ticker} — valuation incomplete (insufficient validated data)")
            return False, stats

    except Exception as exc:
        print(f"[Scheduler] ERROR {ticker}: {exc}")
        return False, stats


def _build_quality_report(
    run_date:   str,
    run_time_s: float,
    tickers:    list[str],
    results:    list[tuple[bool, dict]],
) -> dict:
    """Aggregate per-ticker stats into a single quality report dict."""
    n = len(tickers)
    ok_count   = sum(1 for ok, _ in results if ok)
    with_data  = sum(1 for _, s in results if s.get("has_financials"))
    with_div   = sum(1 for _, s in results if s.get("has_dividend"))
    with_cons  = sum(1 for _, s in results if s.get("has_analyst"))
    val_fails  = sum(s.get("validation_fails", 0) for _, s in results)
    all_sources: set = set()
    for _, s in results:
        all_sources |= s.get("sources", set())

    model_names = ["dcf", "ddm", "residual_income", "earnings_power",
                   "ev_ebitda", "pe", "pb"]
    model_counts = {
        m: sum(1 for _, s in results if s.get("model_successes", {}).get(m))
        for m in model_names
    }

    db_size = _DB_PATH.stat().st_size if _DB_PATH.exists() else 0

    return {
        "run_date":            run_date,
        "run_time_s":          round(run_time_s, 2),
        "companies_processed": n,
        "companies_with_data": with_data,
        "companies_valued":    ok_count,
        "financial_coverage":  round(with_data / n, 4) if n else 0,
        "dividend_coverage":   round(with_div  / n, 4) if n else 0,
        "analyst_coverage":    round(with_cons  / n, 4) if n else 0,
        "dcf_success":         model_counts["dcf"],
        "ddm_success":         model_counts["ddm"],
        "ri_success":          model_counts["residual_income"],
        "epv_success":         model_counts["earnings_power"],
        "ev_ebitda_success":   model_counts["ev_ebitda"],
        "pe_success":          model_counts["pe"],
        "pb_success":          model_counts["pb"],
        "validation_failures": val_fails,
        "sources_used":        json.dumps(sorted(all_sources)),
        "db_size_bytes":       db_size,
    }


def _print_scheduler_summary(report: dict, summary: dict[str, str]) -> None:
    """Print the end-of-run scheduler summary to stdout."""
    n    = report["companies_processed"]
    ok   = report["companies_valued"]
    fail = n - ok
    failed_tickers = [t for t, s in summary.items() if s == "failed"]

    print("\n" + "═" * 60)
    print(f"  IVE V2 Scheduler Summary — {report['run_date']}")
    print("═" * 60)
    print(f"  Runtime         : {report['run_time_s']}s")
    print(f"  Tickers         : {n} processed  |  {ok} valued  |  {fail} failed")
    print(f"  Financial data  : {report['companies_with_data']}/{n} ({report['financial_coverage']*100:.1f}%)")
    print(f"  Dividend data   : {int(report['dividend_coverage']*n)}/{n} ({report['dividend_coverage']*100:.1f}%)")
    print(f"  Analyst targets : {int(report['analyst_coverage']*n)}/{n} ({report['analyst_coverage']*100:.1f}%)")
    print(f"  Validation rej  : {report['validation_failures']} years rejected")
    print(f"  Sources used    : {report['sources_used']}")
    print(f"  DB size         : {report['db_size_bytes'] / 1024:.1f} KB")
    print("  Model successes :")
    for col, label in [
        ("dcf_success", "DCF"), ("ddm_success", "DDM"), ("ri_success", "RI"),
        ("epv_success", "EPV"), ("ev_ebitda_success", "EV/EBITDA"),
        ("pe_success", "P/E"), ("pb_success", "P/B"),
    ]:
        print(f"    {label:<10}: {report[col]}/{n}")
    if failed_tickers:
        print(f"  Failed          : {failed_tickers}")
    print("═" * 60 + "\n")


def run_all(tickers: list[str] | None = None, delay_s: float = 2.0) -> dict:
    """
    Run the full IVE V2 pipeline for all (or specified) tickers.

    delay_s: seconds to wait between tickers (yfinance rate-limit courtesy).
    Returns summary dict: {ticker: 'ok' | 'failed'}.
    """
    if tickers is None:
        tickers = get_constitutional_universe()

    today = date.today().isoformat()
    print(f"\n[Scheduler] Starting IVE V2 run — {len(tickers)} ticker(s)")
    print(f"[Scheduler] Database: {_DB_PATH}")
    print(f"[Scheduler] Date:     {today}\n")

    init_database()
    summary: dict[str, str] = {}
    results: list[tuple[bool, dict]] = []
    t_start = time.perf_counter()

    for i, ticker in enumerate(tickers, start=1):
        print(f"\n[Scheduler] ── {i}/{len(tickers)}: {ticker} ──")
        ok, stats = run_ticker(ticker)
        summary[ticker] = "ok" if ok else "failed"
        results.append((ok, stats))
        if i < len(tickers):
            time.sleep(delay_s)

    run_time_s = time.perf_counter() - t_start
    report     = _build_quality_report(today, run_time_s, tickers, results)

    # Persist quality report
    conn = sqlite3.connect(str(_DB_PATH))
    try:
        _db.save_quality_report(conn, report)
        conn.commit()
    finally:
        conn.close()

    _print_scheduler_summary(report, summary)
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
