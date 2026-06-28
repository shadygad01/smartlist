"""
valuation.data_collector — Orchestrates the IVE V2 data acquisition pipeline.

Pipeline per ticker:
  1. SourceManager fetches raw data (priority order, retry, fallback)
  2. NormalizationEngine maps raw data to canonical schema
  3. ValidationEngine rejects invalid records
  4. Returns clean data + full provenance metadata for data_sources recording

Source priorities:
  Priority 1: Official IR / exchange disclosures (future integration hook)
  Priority 2: yfinance structured financial statements
  Priority 3: Market data (price, cap, shares) — also via yfinance
  Priority 4: Analyst consensus — also via yfinance
  Priority 5: Economic inputs (beta from yfinance; EGX defaults for rest)

Never called during scanner execution.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any

from valuation.source_manager import SourceManager, SourceResult
from valuation.normalization_engine import YFinanceNormalizer, get_normalizer
from valuation.validation_engine import (
    validate_financials,
    validate_market_data,
    validate_analyst_consensus,
)


# ── yfinance fetchers ────────────────────────────────────────────────────────

def _yf_fetch_financials(ticker: str) -> tuple | None:
    """Fetch yfinance annual financial statement DataFrames."""
    try:
        import yfinance as yf
        t   = yf.Ticker(ticker)
        inc = t.financials
        bal = t.balance_sheet
        cf  = t.cashflow
        if inc is None or getattr(inc, "empty", True):
            return None
        return (inc, bal, cf)
    except Exception as exc:
        print(f"[DataCollector] yfinance financials fetch error for {ticker}: {exc}")
        return None


def _yf_fetch_market(ticker: str) -> dict | None:
    """Fetch yfinance info dict (market + company metadata)."""
    try:
        import yfinance as yf
        info = yf.Ticker(ticker).info
        if not info or not isinstance(info, dict):
            return None
        return info
    except Exception as exc:
        print(f"[DataCollector] yfinance market fetch error for {ticker}: {exc}")
        return None


# ── SourceManager builder ────────────────────────────────────────────────────

def _build_source_manager(ticker: str) -> SourceManager:
    """
    Build and configure SourceManager with all available sources.

    Priority 1 slot is reserved for future official IR/exchange data integrations.
    Priority 2: yfinance — annual financial statements.
    Priority 3: yfinance — market and company data.
    Priority 4: yfinance — analyst consensus (derived from info dict).
    """
    sm = SourceManager(ticker)
    sm.register("financials",  "yfinance", 2, _yf_fetch_financials)
    sm.register("market_data", "yfinance", 3, _yf_fetch_market)
    return sm


# ── provenance builder ───────────────────────────────────────────────────────

def build_data_source_records(
    ticker:      str,
    fin_rows:    list[dict],
    source_meta: SourceResult | None,
) -> list[dict]:
    """
    Build data_sources records for every non-null field in every financial row.
    Called by valuation_scheduler._store_collected() before DB writes.
    """
    if not source_meta:
        return []

    from valuation.normalization_engine import FIELD_STATEMENT

    records: list[dict] = []
    for row in fin_rows:
        yr         = row.get("year")
        period     = str(yr) if yr is not None else "unknown"
        val_status = row.get("_validation_status", "valid")

        for field_name, statement in FIELD_STATEMENT.items():
            if row.get(field_name) is not None:
                records.append({
                    "ticker":            ticker,
                    "statement":         statement,
                    "period":            period,
                    "field_name":        field_name,
                    "source_name":       source_meta.source_name,
                    "source_priority":   source_meta.source_priority,
                    "collection_time":   source_meta.collection_time,
                    "validation_status": val_status,
                    "data_version":      source_meta.data_version,
                })

    return records


# ── main entry point ─────────────────────────────────────────────────────────

def collect_all(ticker: str) -> dict:
    """
    Run the full data acquisition pipeline for one ticker.

    Returns a consolidated dict consumed by valuation_scheduler._store_collected():
      ticker, info, financials, financials_rejected, consensus, current_price,
      beta, source_meta {financials: SourceResult, market_data: SourceResult}
    """
    print(f"[DataCollector] Collecting: {ticker}")
    today_iso = date.today().isoformat()

    sm = _build_source_manager(ticker)

    # ── Layer 2: financial statements ────────────────────────────────────────
    fin_result  = sm.fetch("financials")
    norm        = get_normalizer(fin_result.source_name if fin_result else "yfinance")

    financials_raw: list[dict] = []
    if fin_result:
        inc_df, bal_df, cf_df = fin_result.data
        financials_raw = norm.normalize_financials(inc_df, bal_df, cf_df)
        print(
            f"[DataCollector] {ticker}: normalized {len(financials_raw)} "
            f"annual year(s) from {fin_result.source_name}"
        )

    financials_valid, financials_rejected = validate_financials(financials_raw)
    print(
        f"[DataCollector] {ticker}: validation — "
        f"{len(financials_valid)} accepted, {len(financials_rejected)} rejected"
    )

    # ── Layer 3: market / company data ──────────────────────────────────────
    mkt_result       = sm.fetch("market_data")
    market_data_raw: dict = {}
    if mkt_result:
        market_data_raw = norm.normalize_market_data(mkt_result.data)

    market_data, mkt_issues = validate_market_data(market_data_raw)
    if mkt_issues:
        print(f"[DataCollector] {ticker}: market data issues — {mkt_issues}")

    # ── Layer 4: analyst consensus ──────────────────────────────────────────
    consensus_raw    = norm.normalize_analyst_consensus(market_data, today_iso)
    consensus_valid, consensus_rejected = validate_analyst_consensus(consensus_raw)

    return {
        "ticker":               ticker,
        "info":                 market_data,
        "financials":           financials_valid,
        "financials_rejected":  financials_rejected,
        "consensus":            consensus_valid,
        "current_price":        market_data.get("current_price"),
        "beta":                 market_data.get("beta"),
        "source_meta": {
            "financials":  fin_result,
            "market_data": mkt_result,
        },
    }
