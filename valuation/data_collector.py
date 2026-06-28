"""
valuation.data_collector — Layer 1/2/3/4 data collection pipeline.

Priority:
  Layer 1 — Official financial statements (via yfinance)
  Layer 2 — Current market data (via yfinance info)
  Layer 3 — Analyst consensus (via yfinance analyst data)
  Layer 4 — Valuation assumptions (stored separately, updateable)

Never called during scanner execution.
"""
from __future__ import annotations

import sqlite3
from datetime import date
from pathlib import Path
from typing import Any

_BASE = Path(__file__).parent.parent


def _safe_float(val: Any) -> float | None:
    try:
        v = float(val)
        return None if (v != v) else v  # NaN guard
    except (TypeError, ValueError):
        return None


def collect_company_info(ticker: str) -> dict:
    """Layer 2: Fetch current market/company info from yfinance."""
    try:
        import yfinance as yf
        info = yf.Ticker(ticker).info
        return {
            "company_name":     info.get("longName") or info.get("shortName") or ticker,
            "sector":           info.get("sector", ""),
            "industry":         info.get("industry", ""),
            "currency":         info.get("currency", "EGP"),
            "shares_outstanding": _safe_float(info.get("sharesOutstanding")),
            "current_price":    _safe_float(info.get("currentPrice") or info.get("regularMarketPrice")),
            "market_cap":       _safe_float(info.get("marketCap")),
            "beta":             _safe_float(info.get("beta")),
            "trailing_pe":      _safe_float(info.get("trailingPE")),
            "forward_pe":       _safe_float(info.get("forwardPE")),
            "pb_ratio":         _safe_float(info.get("priceToBook")),
            "enterprise_value": _safe_float(info.get("enterpriseValue")),
            "ev_ebitda":        _safe_float(info.get("enterpriseToEbitda")),
            "dividend_yield":   _safe_float(info.get("dividendYield")),
            "analyst_target":   _safe_float(info.get("targetMeanPrice")),
            "analyst_low":      _safe_float(info.get("targetLowPrice")),
            "analyst_high":     _safe_float(info.get("targetHighPrice")),
            "analyst_recs":     info.get("recommendationKey", ""),
            "analyst_count":    info.get("numberOfAnalystOpinions"),
        }
    except Exception as e:
        print(f"[DataCollector] company_info failed for {ticker}: {e}")
        return {"company_name": ticker, "currency": "EGP"}


def collect_financials(ticker: str) -> list[dict]:
    """Layer 1: Parse annual financial statements from yfinance."""
    try:
        import yfinance as yf
        import pandas as pd

        t = yf.Ticker(ticker)
        inc  = t.financials           # income statement (columns=years)
        bal  = t.balance_sheet
        cf   = t.cashflow

        if inc is None or inc.empty:
            return []

        rows: list[dict] = []
        for col in inc.columns:
            try:
                yr = col.year if hasattr(col, "year") else int(str(col)[:4])
            except Exception:
                continue

            def _g(df, *keys):
                for k in keys:
                    try:
                        if df is not None and k in df.index:
                            v = df.loc[k, col]
                            return _safe_float(v)
                    except Exception:
                        pass
                return None

            revenue    = _g(inc, "Total Revenue", "Revenue")
            gross_p    = _g(inc, "Gross Profit")
            op_income  = _g(inc, "Operating Income", "Operating Profit", "EBIT")
            ebit       = _g(inc, "EBIT", "Operating Income")
            net_income = _g(inc, "Net Income", "Net Income Common Stockholders")
            op_cf      = _g(cf,  "Operating Cash Flow", "Cash Flow From Operations",
                                  "Total Cash From Operating Activities")
            capex      = _g(cf,  "Capital Expenditure", "Capital Expenditures")
            fcf        = None
            if op_cf is not None and capex is not None:
                fcf = op_cf + capex  # capex is negative in yfinance
            elif op_cf is not None:
                fcf = op_cf * 0.85   # rough estimate when capex missing

            cash       = _g(bal, "Cash And Cash Equivalents", "Cash Cash Equivalents And Short Term Investments")
            total_debt = _g(bal, "Total Debt", "Long Term Debt And Capital Lease Obligation")
            equity     = _g(bal, "Stockholders Equity", "Total Equity Gross Minority Interest",
                                  "Common Stock Equity")
            assets     = _g(bal, "Total Assets")
            liab       = _g(bal, "Total Liabilities Net Minority Interest", "Total Liabilities")
            book_val   = _g(bal, "Book Value", "Common Stock Equity", "Stockholders Equity")
            shares     = _g(bal, "Ordinary Shares Number", "Share Issued")
            eps        = _g(inc, "Basic EPS", "Diluted EPS", "EPS Basic")
            dividend   = _g(inc, "Cash Dividends Paid")
            if dividend is not None:
                dividend = abs(dividend)

            # Computed ratios
            roe = roic = ebitda = None
            if net_income is not None and equity and equity != 0:
                roe = round(net_income / equity, 4)
            if ebit is not None and total_debt is not None and equity and (total_debt + equity) != 0:
                roic = round(ebit * (1 - 0.225) / (total_debt + equity), 4)
            if op_income is not None:
                da = _g(cf, "Depreciation And Amortization", "Depreciation Amortization Depletion")
                if da is not None:
                    ebitda = op_income + abs(da)

            rows.append({
                "year":                 yr,
                "revenue":              revenue,
                "gross_profit":         gross_p,
                "operating_income":     op_income,
                "ebit":                 ebit,
                "ebitda":               ebitda,
                "net_income":           net_income,
                "operating_cash_flow":  op_cf,
                "free_cash_flow":       fcf,
                "cash":                 cash,
                "debt":                 total_debt,
                "equity":               equity,
                "assets":               assets,
                "liabilities":          liab,
                "book_value":           book_val,
                "eps":                  eps,
                "dividend":             dividend,
                "roe":                  roe,
                "roic":                 roic,
                "capex":                capex,
                "shares":               shares,
            })

        return sorted(rows, key=lambda r: r["year"])
    except Exception as e:
        print(f"[DataCollector] financials failed for {ticker}: {e}")
        return []


def collect_analyst_consensus(ticker: str, info: dict) -> list[dict]:
    """Layer 3: Collect analyst consensus from available sources.

    Primary source: yfinance analyst_target / analyst_low / analyst_high.
    Each source stored independently in analyst_consensus table.
    """
    today = date.today().isoformat()
    records: list[dict] = []

    # Source A: yfinance mean target
    if info.get("analyst_target"):
        records.append({
            "source": "yfinance_mean",
            "target_price": info["analyst_target"],
            "recommendation": info.get("analyst_recs", ""),
            "date": today,
        })

    # Source B: yfinance low target
    if info.get("analyst_low"):
        records.append({
            "source": "yfinance_low",
            "target_price": info["analyst_low"],
            "recommendation": info.get("analyst_recs", ""),
            "date": today,
        })

    # Source C: yfinance high target
    if info.get("analyst_high"):
        records.append({
            "source": "yfinance_high",
            "target_price": info["analyst_high"],
            "recommendation": info.get("analyst_recs", ""),
            "date": today,
        })

    # Future hook: add Mubasher, AlphaSpread, MarketScreener scrapers here.
    # Each must be stored independently (never averaged before storing).

    return records


def collect_all(ticker: str) -> dict:
    """Collect all data layers for one ticker. Returns consolidated dict."""
    print(f"[DataCollector] Collecting: {ticker}")
    info       = collect_company_info(ticker)
    financials = collect_financials(ticker)
    consensus  = collect_analyst_consensus(ticker, info)
    return {
        "ticker":       ticker,
        "info":         info,
        "financials":   financials,
        "consensus":    consensus,
        "current_price": info.get("current_price"),
        "beta":         info.get("beta"),
    }
