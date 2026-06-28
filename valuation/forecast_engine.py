"""
valuation.forecast_engine — Generate forward financial forecasts.

Projects revenue, EPS, FCF and dividends for valuation model inputs.
Uses historical growth rates with mean-reversion dampening.
Never called during scanner execution.
"""
from __future__ import annotations
from valuation.financial_parser import compute_growth_rates, average_growth, latest


_DEFAULT_TERMINAL_GROWTH = 0.04
_GROWTH_DAMPEN = 0.50   # blend historical rate toward terminal growth
_FORECAST_YEARS = 5


def _dampen(g_hist: float | None, g_terminal: float = _DEFAULT_TERMINAL_GROWTH) -> float:
    """Blend historical growth toward terminal growth (mean reversion).
    When no historical growth data exists, use terminal growth only — never a fabricated default.
    """
    if g_hist is None:
        return g_terminal
    return round(g_hist * (1 - _GROWTH_DAMPEN) + g_terminal * _GROWTH_DAMPEN, 4)


def build_forecasts(financials: list[dict], terminal_growth: float = _DEFAULT_TERMINAL_GROWTH) -> list[dict]:
    """Return list of year-by-year forecasts for FORECAST_YEARS forward years.

    Each row: {forecast_year, revenue, eps, fcf, dividend, growth_rate}
    """
    if not financials:
        return []

    growth_rates = compute_growth_rates(financials)

    # Compute dampened growth for each metric
    g_rev  = _dampen(average_growth(growth_rates["revenue"]),      terminal_growth)
    g_eps  = _dampen(average_growth(growth_rates["eps"]),          terminal_growth)
    g_fcf  = _dampen(average_growth(growth_rates["free_cash_flow"]), terminal_growth)

    # Base values (most recent year) — None when field is unavailable
    # Downstream `if X else None` guards turn 0.0/None into None in forecast rows
    base_rev = latest(financials, "revenue")          or 0.0
    base_eps = latest(financials, "eps")              or 0.0
    base_fcf = latest(financials, "free_cash_flow")   or 0.0
    base_div = latest(financials, "dividend")         or 0.0
    last_yr  = max(r["year"] for r in financials)

    # Dividend growth tied to EPS growth with payout stability assumption
    g_div = g_eps * 0.70 if g_eps else terminal_growth

    rows: list[dict] = []
    rev, eps, fcf, div = base_rev, base_eps, base_fcf, base_div
    for i in range(1, _FORECAST_YEARS + 1):
        rev = rev * (1 + g_rev)
        eps = eps * (1 + g_eps)
        fcf = fcf * (1 + g_fcf)
        div = div * (1 + g_div) if div else None
        rows.append({
            "forecast_year": last_yr + i,
            "revenue":       round(rev, 2) if rev else None,
            "eps":           round(eps, 4) if eps else None,
            "fcf":           round(fcf, 2) if fcf else None,
            "dividend":      round(div, 4) if div else None,
            "growth_rate":   round(g_fcf, 4),
        })

    return rows
