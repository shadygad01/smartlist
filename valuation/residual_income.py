"""
valuation.residual_income — Residual Income (RI) valuation model.

Value = Book Value + PV(Residual Incomes)
Residual Income(t) = Net Income(t) - Ke * Equity(t-1)
Uses 5-year explicit period + terminal RI.
Never called during scanner execution.
"""
from __future__ import annotations
from valuation.financial_parser import latest


def run_residual_income(
    financials:  list[dict],
    forecasts:   list[dict],
    assumptions: dict,
) -> float | None:
    """
    Ohlson Residual Income Model.
    Returns intrinsic value per share, or None if inputs insufficient.
    """
    rfr  = assumptions.get("risk_free_rate", 0.125)
    erp  = assumptions.get("equity_risk_premium", 0.07)
    beta = assumptions.get("beta", 1.0)
    g    = assumptions.get("terminal_growth", 0.04)

    ke = rfr + beta * erp

    # Starting book value per share
    equity = latest(financials, "equity")
    shares = latest(financials, "shares")
    if not equity or not shares or shares <= 0:
        return None

    bvps = equity / shares  # book value per share

    pv_ri = 0.0
    bv = bvps
    for i, f in enumerate(forecasts, start=1):
        eps = f.get("eps")
        if eps is None:
            return None
        ri = eps - ke * bv
        pv_ri += ri / ((1 + ke) ** i)
        # BV grows by retained earnings (EPS - DPS); unknown dividend → full retention
        div_actual = latest(financials, "dividend") or 0.0
        bv = bv + eps - div_actual

    # Terminal RI: persistence factor 0.5 means RI fades toward zero at (ke-g)
    # last_eps=None means no terminal RI contribution (zero terminal)
    if forecasts:
        last_eps = forecasts[-1].get("eps")
        if last_eps is not None and ke > g:
            terminal_ri = (last_eps - ke * bv) * 0.5 / (ke - g)
        else:
            terminal_ri = 0.0
        pv_terminal = terminal_ri / ((1 + ke) ** len(forecasts))
        pv_ri += pv_terminal

    return round(bvps + pv_ri, 4)
