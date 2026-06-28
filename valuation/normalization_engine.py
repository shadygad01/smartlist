"""
valuation.normalization_engine — Source-specific schema normalization for IVE V2.

Maps raw provider data to the canonical IVE schema before validation and storage.
Each data source has a dedicated normalizer class.
Extensible: add new source normalizers by subclassing BaseNormalizer.
Never called during scanner execution.
"""
from __future__ import annotations

from typing import Any

# Canonical field → statement type mapping (used by data_sources table)
FIELD_STATEMENT: dict[str, str] = {
    "revenue":             "income",
    "gross_profit":        "income",
    "operating_income":    "income",
    "ebit":                "income",
    "net_income":          "income",
    "eps":                 "income",
    "dividend":            "income",
    "cash":                "balance",
    "debt":                "balance",
    "equity":              "balance",
    "assets":              "balance",
    "liabilities":         "balance",
    "book_value":          "balance",
    "shares":              "balance",
    "operating_cash_flow": "cashflow",
    "free_cash_flow":      "cashflow",
    "capex":               "cashflow",
    "ebitda":              "derived",
    "roe":                 "derived",
    "roic":                "derived",
}


def _safe_float(val: Any) -> float | None:
    try:
        v = float(val)
        return None if (v != v) else v  # NaN guard
    except (TypeError, ValueError):
        return None


class YFinanceNormalizer:
    """
    Normalizes raw yfinance DataFrames and info dicts into canonical IVE schema.

    yfinance returns:
      .financials   → income statement DataFrame (columns=period timestamps, index=field names)
      .balance_sheet → balance sheet DataFrame
      .cashflow      → cash flow statement DataFrame
      .info          → dict of market/company metadata
    """

    # Income statement: canonical_field → [yfinance row labels in priority order]
    _INC: dict[str, list[str]] = {
        "revenue":          ["Total Revenue", "Revenue"],
        "gross_profit":     ["Gross Profit"],
        "operating_income": ["Operating Income", "Operating Profit", "EBIT"],
        "ebit":             ["EBIT", "Operating Income"],
        "net_income":       ["Net Income", "Net Income Common Stockholders"],
        "eps":              ["Basic EPS", "Diluted EPS", "EPS Basic"],
    }

    # Cash flow rows used to derive per-share annual dividend
    _DIV_CF: list[str] = [
        "Cash Dividends Paid",
        "Common Stock Dividends Paid",
        "Payment Of Dividends",
    ]

    # Balance sheet
    _BAL: dict[str, list[str]] = {
        "cash":        ["Cash And Cash Equivalents",
                        "Cash Cash Equivalents And Short Term Investments"],
        "debt":        ["Total Debt", "Long Term Debt And Capital Lease Obligation"],
        "equity":      ["Stockholders Equity", "Total Equity Gross Minority Interest",
                        "Common Stock Equity"],
        "assets":      ["Total Assets"],
        "liabilities": ["Total Liabilities Net Minority Interest", "Total Liabilities"],
        "book_value":  ["Book Value", "Common Stock Equity", "Stockholders Equity"],
        "shares":      ["Ordinary Shares Number", "Share Issued"],
    }

    # Cash flow
    _CF: dict[str, list[str]] = {
        "operating_cash_flow": ["Operating Cash Flow", "Cash Flow From Operations",
                                "Total Cash From Operating Activities"],
        "capex":               ["Capital Expenditure", "Capital Expenditures"],
    }

    # D&A rows used to compute EBITDA
    _DA: list[str] = [
        "Depreciation And Amortization",
        "Depreciation Amortization Depletion",
    ]

    def normalize_financials(
        self,
        inc_df: Any,   # pd.DataFrame or None
        bal_df: Any,   # pd.DataFrame or None
        cf_df:  Any,   # pd.DataFrame or None
    ) -> list[dict]:
        """
        Build canonical annual financial rows from yfinance DataFrames.
        Returns list sorted by year ascending.
        """
        if inc_df is None or getattr(inc_df, "empty", True):
            return []

        rows: list[dict] = []
        for col in inc_df.columns:
            try:
                yr = col.year if hasattr(col, "year") else int(str(col)[:4])
            except Exception:
                continue

            def _g(df: Any, *keys: str) -> float | None:
                for k in keys:
                    try:
                        if df is not None and k in df.index:
                            return _safe_float(df.loc[k, col])
                    except Exception:
                        pass
                return None

            # Income statement
            revenue    = _g(inc_df, *self._INC["revenue"])
            gross_p    = _g(inc_df, *self._INC["gross_profit"])
            op_income  = _g(inc_df, *self._INC["operating_income"])
            ebit       = _g(inc_df, *self._INC["ebit"])
            net_income = _g(inc_df, *self._INC["net_income"])
            eps        = _g(inc_df, *self._INC["eps"])

            # Balance sheet
            cash     = _g(bal_df, *self._BAL["cash"])
            debt     = _g(bal_df, *self._BAL["debt"])
            equity   = _g(bal_df, *self._BAL["equity"])
            assets   = _g(bal_df, *self._BAL["assets"])
            liab     = _g(bal_df, *self._BAL["liabilities"])
            book_val = _g(bal_df, *self._BAL["book_value"])
            shares   = _g(bal_df, *self._BAL["shares"])

            # Per-share annual dividend: total from CF ÷ shares (never income stmt total)
            _total_div = _g(cf_df, *self._DIV_CF)
            dividend: float | None = None
            if _total_div is not None and shares and shares > 0:
                dividend = round(abs(_total_div) / shares, 4)

            # Cash flow
            op_cf = _g(cf_df, *self._CF["operating_cash_flow"])
            capex = _g(cf_df, *self._CF["capex"])

            # Derived: FCF = operating CF + capex (capex is negative in yfinance)
            # FCF is NULL when capex is missing — never estimate from operating CF alone.
            fcf = None
            if op_cf is not None and capex is not None:
                fcf = op_cf + capex

            # Derived: EBITDA
            ebitda = None
            if op_income is not None:
                da = _g(cf_df, *self._DA)
                if da is not None:
                    ebitda = op_income + abs(da)

            # Derived: ROE
            roe = None
            if net_income is not None and equity and equity != 0:
                roe = round(net_income / equity, 4)

            # Derived: ROIC (uses 22.5% EGX tax rate as fallback)
            roic = None
            if ebit is not None and debt is not None and equity and (debt + equity) != 0:
                roic = round(ebit * (1 - 0.225) / (debt + equity), 4)

            rows.append({
                "year":                 yr,
                "quarter":              None,   # annual-only for yfinance
                "revenue":              revenue,
                "gross_profit":         gross_p,
                "operating_income":     op_income,
                "ebit":                 ebit,
                "ebitda":               ebitda,
                "net_income":           net_income,
                "operating_cash_flow":  op_cf,
                "free_cash_flow":       fcf,
                "cash":                 cash,
                "debt":                 debt,
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

    def normalize_market_data(self, info: dict) -> dict:
        """Map yfinance info dict to canonical market/company schema."""
        return {
            "company_name":        info.get("longName") or info.get("shortName") or "",
            "sector":              info.get("sector", ""),
            "industry":            info.get("industry", ""),
            "currency":            info.get("currency", "EGP"),
            "shares_outstanding":  _safe_float(info.get("sharesOutstanding")),
            "current_price":       _safe_float(
                info.get("currentPrice") or info.get("regularMarketPrice")
            ),
            "market_cap":          _safe_float(info.get("marketCap")),
            "beta":                _safe_float(info.get("beta")),
            "trailing_pe":         _safe_float(info.get("trailingPE")),
            "forward_pe":          _safe_float(info.get("forwardPE")),
            "pb_ratio":            _safe_float(info.get("priceToBook")),
            "enterprise_value":    _safe_float(info.get("enterpriseValue")),
            "ev_ebitda":           _safe_float(info.get("enterpriseToEbitda")),
            "dividend_yield":      _safe_float(info.get("dividendYield")),
            # Per-share annual dividend from info (fallback if CF statement missing)
            "dividend_rate":       _safe_float(
                info.get("dividendRate") or info.get("trailingAnnualDividendRate")
            ),
            "analyst_target":      _safe_float(info.get("targetMeanPrice")),
            "analyst_low":         _safe_float(info.get("targetLowPrice")),
            "analyst_high":        _safe_float(info.get("targetHighPrice")),
            "analyst_recs":        info.get("recommendationKey", ""),
            "analyst_count":       info.get("numberOfAnalystOpinions"),
        }

    def normalize_analyst_consensus(self, market_data: dict, date_iso: str) -> list[dict]:
        """Build canonical analyst consensus rows from normalized market data."""
        records: list[dict] = []

        if market_data.get("analyst_target"):
            records.append({
                "source":         "yfinance_mean",
                "target_price":   market_data["analyst_target"],
                "recommendation": market_data.get("analyst_recs", ""),
                "date":           date_iso,
            })

        if market_data.get("analyst_low"):
            records.append({
                "source":         "yfinance_low",
                "target_price":   market_data["analyst_low"],
                "recommendation": market_data.get("analyst_recs", ""),
                "date":           date_iso,
            })

        if market_data.get("analyst_high"):
            records.append({
                "source":         "yfinance_high",
                "target_price":   market_data["analyst_high"],
                "recommendation": market_data.get("analyst_recs", ""),
                "date":           date_iso,
            })

        return records


def get_normalizer(source_name: str) -> YFinanceNormalizer:
    """
    Return the appropriate normalizer for a given source name.
    Future: add AlphaVantageNormalizer, PolygonNormalizer, etc.
    """
    return YFinanceNormalizer()
