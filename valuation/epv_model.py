"""
valuation.epv_model — Earnings Power Value (EPV) model.

EPV = Normalized EBIT × (1 - tax) / WACC
No growth assumed. Conservative floor valuation.
Never called during scanner execution.
"""
from __future__ import annotations
from valuation.financial_parser import latest


def _average(financials: list[dict], field: str, n: int = 3) -> float | None:
    """Return trailing-n average of a field."""
    vals = [r.get(field) for r in financials[-n:] if r.get(field) is not None]
    if not vals:
        return None
    return sum(vals) / len(vals)


def run_epv(
    financials:  list[dict],
    assumptions: dict,
) -> float | None:
    """
    Earnings Power Value.
    EPV = Normalized EBIT(1-T) / WACC
    Returns intrinsic value per share, or None if inputs insufficient.
    """
    wacc  = assumptions.get("wacc", 0.16)
    tax   = assumptions.get("tax_rate", 0.225)
    shares = latest(financials, "shares")

    if not shares or shares <= 0:
        return None

    # Normalize EBIT: 3-year average
    ebit_avg = _average(financials, "ebit", 3)
    if ebit_avg is None:
        # Fall back to operating income
        ebit_avg = _average(financials, "operating_income", 3)
    if ebit_avg is None:
        return None

    nopat = ebit_avg * (1 - tax)
    if nopat <= 0:
        return None

    # EPV equity value = NOPAT / WACC + Net Cash
    cash = latest(financials, "cash") or 0.0
    debt = latest(financials, "debt") or 0.0
    epv_firm = nopat / wacc
    epv_equity = epv_firm + cash - debt

    if epv_equity <= 0:
        return None

    return round(epv_equity / shares, 4)
