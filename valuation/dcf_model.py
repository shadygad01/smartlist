"""
valuation.dcf_model — FCFF Discounted Cash Flow valuation model.

Implements a 5-year explicit FCFF projection with terminal value.
Returns intrinsic value per share.
Never called during scanner execution.
"""
from __future__ import annotations
from valuation.financial_parser import latest


def run_dcf(
    financials: list[dict],
    forecasts:  list[dict],
    assumptions: dict,
    current_price: float | None = None,
) -> float | None:
    """
    FCFF DCF: PV(FCF years 1-5) + PV(Terminal Value).
    Returns intrinsic value per share, or None if inputs insufficient.

    assumptions keys used:
      wacc, terminal_growth, tax_rate
    """
    if not financials or not forecasts:
        return None

    wacc     = assumptions.get("wacc", 0.16)
    g_term   = assumptions.get("terminal_growth", 0.04)
    shares   = latest(financials, "shares")

    if not shares or shares <= 0:
        return None
    if wacc <= g_term:
        return None  # Gordon Growth terminal value undefined when wacc ≤ g

    # Discount projected FCFs
    pv_sum = 0.0
    for i, f in enumerate(forecasts, start=1):
        fcf = f.get("fcf")
        if fcf is None:
            return None
        pv_sum += fcf / ((1 + wacc) ** i)

    # Terminal value (Gordon Growth on final year FCF)
    last_fcf = forecasts[-1].get("fcf")
    if last_fcf is None:
        return None
    n = len(forecasts)
    terminal_value = (last_fcf * (1 + g_term)) / (wacc - g_term)
    pv_terminal = terminal_value / ((1 + wacc) ** n)

    # Enterprise value → equity value
    # Net cash bridge applied only when both cash and debt are known.
    # Missing cash: treat as 0 (conservative — no benefit claimed for unknown cash).
    # Missing debt: treat as 0 only when debt is genuinely unavailable; if debt
    # cannot be determined, the EV → equity bridge is unreliable.
    enterprise_value = pv_sum + pv_terminal
    cash = latest(financials, "cash")
    debt = latest(financials, "debt")
    # Use the bridge whenever at least debt is known; unknown cash → 0 (conservative).
    if debt is None:
        # No capital structure info — EV approximates equity (all-equity assumption)
        net_cash = 0.0
    else:
        net_cash = (cash or 0.0) - debt

    equity_value = enterprise_value + net_cash

    if equity_value <= 0:
        return None

    return round(equity_value / shares, 4)
