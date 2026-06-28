"""
valuation.ddm_model — Dividend Discount Model (Gordon Growth).

P = D1 / (Ke - g)
where D1 = next year dividend, Ke = cost of equity, g = terminal growth.
Returns intrinsic value per share, or None if inputs insufficient.
Never called during scanner execution.
"""
from __future__ import annotations
from valuation.financial_parser import latest


def run_ddm(
    financials:  list[dict],
    forecasts:   list[dict],
    assumptions: dict,
) -> float | None:
    """
    Gordon Growth DDM.
    Requires dividend-paying history or projected dividends.
    Returns intrinsic per-share value, or None if no dividend data.
    """
    rfr  = assumptions.get("risk_free_rate", 0.125)
    erp  = assumptions.get("equity_risk_premium", 0.07)
    beta = assumptions.get("beta", 1.0)
    g    = assumptions.get("terminal_growth", 0.04)

    ke = rfr + beta * erp  # CAPM cost of equity

    # D1 from forecasts, else from latest actuals
    d1 = None
    if forecasts:
        d1 = forecasts[0].get("dividend")
    if d1 is None:
        d_hist = latest(financials, "dividend")
        if d_hist and d_hist > 0:
            d1 = d_hist * (1 + g)

    if not d1 or d1 <= 0:
        return None  # Non-dividend payer — model not applicable

    if ke <= g:
        return None  # Unstable (growth exceeds cost of equity)

    return round(d1 / (ke - g), 4)
