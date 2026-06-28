"""
valuation.multiples_model — Relative valuation via market multiples.

Models: EV/EBITDA, Relative P/E, Relative P/B.
Uses sector/market medians for peer comparison when available.
Returns intrinsic value per share for each multiple.
Never called during scanner execution.
"""
from __future__ import annotations
from valuation.financial_parser import latest, average_growth, compute_growth_rates

# EGX sector median multiples (conservative estimates, Egypt market context)
_SECTOR_PE: dict[str, float] = {
    "Financial Services": 10.0,
    "Banks":              9.0,
    "Real Estate":        12.0,
    "Consumer Goods":     15.0,
    "Healthcare":         18.0,
    "Industrials":        11.0,
    "Technology":         20.0,
    "Telecommunications": 10.0,
    "Energy":             8.0,
    "Materials":          9.0,
    "default":            11.0,
}

_SECTOR_EV_EBITDA: dict[str, float] = {
    "Financial Services": 8.0,
    "Banks":              7.0,
    "Real Estate":        9.0,
    "Consumer Goods":     10.0,
    "Healthcare":         12.0,
    "Industrials":        8.0,
    "Technology":         14.0,
    "Telecommunications": 7.0,
    "Energy":             6.0,
    "Materials":          7.0,
    "default":            8.5,
}

_SECTOR_PB: dict[str, float] = {
    "Financial Services": 1.2,
    "Banks":              1.0,
    "Real Estate":        1.5,
    "Consumer Goods":     2.0,
    "Healthcare":         2.5,
    "Industrials":        1.3,
    "Technology":         3.0,
    "Telecommunications": 1.5,
    "Energy":             1.0,
    "Materials":          1.2,
    "default":            1.3,
}


def _get(mapping: dict, sector: str | None) -> float:
    if sector:
        for k in mapping:
            if k.lower() in (sector or "").lower():
                return mapping[k]
    return mapping["default"]


def run_ev_ebitda(
    financials:  list[dict],
    assumptions: dict,
    sector:      str | None = None,
) -> float | None:
    """Return EV/EBITDA implied per-share value."""
    ebitda  = latest(financials, "ebitda")
    shares  = latest(financials, "shares")
    cash    = latest(financials, "cash") or 0.0
    debt    = latest(financials, "debt") or 0.0

    if not ebitda or not shares or shares <= 0 or ebitda <= 0:
        return None

    multiple    = _get(_SECTOR_EV_EBITDA, sector)
    ev_implied  = ebitda * multiple
    equity_val  = ev_implied + cash - debt
    if equity_val <= 0:
        return None
    return round(equity_val / shares, 4)


def run_pe(
    financials:  list[dict],
    assumptions: dict,
    sector:      str | None = None,
) -> float | None:
    """Return P/E multiple implied per-share value."""
    eps    = latest(financials, "eps")
    shares = latest(financials, "shares")
    if not eps or eps <= 0 or not shares:
        return None

    multiple = _get(_SECTOR_PE, sector)
    # PEG adjustment: if growth > sector median, expand multiple slightly
    growth_rates = compute_growth_rates(financials)
    g_eps = average_growth(growth_rates["eps"])
    if g_eps and g_eps > 0.10:
        peg = multiple / (g_eps * 100)  # PEG ratio
        if peg < 1.0:
            multiple = min(multiple * 1.15, multiple + 2.0)

    return round(eps * multiple, 4)


def run_pb(
    financials:  list[dict],
    assumptions: dict,
    sector:      str | None = None,
) -> float | None:
    """Return P/B multiple implied per-share value."""
    equity = latest(financials, "equity")
    shares = latest(financials, "shares")
    if not equity or not shares or shares <= 0:
        return None

    bvps     = equity / shares
    multiple = _get(_SECTOR_PB, sector)

    # ROE-adjusted PB: higher ROE justifies higher multiple
    roe = latest(financials, "roe")
    if roe and roe > 0.15:
        multiple = min(multiple * 1.10, multiple + 0.3)

    return round(bvps * multiple, 4)
