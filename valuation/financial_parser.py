"""
valuation.financial_parser — Normalize and validate raw financial data.

Converts raw collector output into clean, consistently-typed rows
ready for model consumption. Handles missing data gracefully.
"""
from __future__ import annotations
from typing import Any


def _pct(numer: float | None, denom: float | None) -> float | None:
    if numer is None or denom is None or denom == 0:
        return None
    return round(numer / denom, 4)


def _growth(series: list[float | None]) -> list[float | None]:
    """Return YoY growth rates for a series."""
    result: list[float | None] = [None]
    for i in range(1, len(series)):
        prev, curr = series[i - 1], series[i]
        if prev is not None and curr is not None and prev != 0:
            result.append(round((curr - prev) / abs(prev), 4))
        else:
            result.append(None)
    return result


def parse_financials(raw_rows: list[dict]) -> list[dict]:
    """Validate and enrich raw financial rows."""
    cleaned: list[dict] = []
    for r in raw_rows:
        yr = r.get("year")
        if yr is None:
            continue

        # Derive missing computed fields
        equity  = r.get("equity")
        assets  = r.get("assets")
        liab    = r.get("liabilities")
        ni      = r.get("net_income")
        ebit    = r.get("ebit")
        debt    = r.get("debt")
        shares  = r.get("shares")
        eps     = r.get("eps")

        if assets is not None and liab is not None and equity is None:
            equity = assets - liab

        if equity is not None and ni is not None and r.get("roe") is None:
            r["roe"] = _pct(ni, equity)

        if equity is not None and assets is not None and r.get("roa") is None:
            r["roa"] = _pct(ni, assets)

        if ni is not None and shares and shares > 0 and eps is None:
            r["eps"] = round(ni / shares, 4)

        row = dict(r)
        row["equity"] = equity
        cleaned.append(row)
    return cleaned


def compute_growth_rates(financials: list[dict]) -> dict[str, list[float | None]]:
    """Return dict of metric → [YoY growth rates] for a list of financial rows."""
    metrics = ["revenue", "net_income", "free_cash_flow", "ebitda", "eps"]
    result: dict[str, list[float | None]] = {}
    for m in metrics:
        series = [r.get(m) for r in financials]
        result[m] = _growth(series)
    return result


def average_growth(rates: list[float | None], n: int = 3) -> float:
    """Return average of last n non-None growth rates."""
    valid = [r for r in (rates or []) if r is not None]
    if not valid:
        return 0.05  # default 5%
    tail = valid[-n:]
    return round(sum(tail) / len(tail), 4)


def latest(financials: list[dict], field: str) -> float | None:
    """Return the most recent non-None value for a field."""
    for r in reversed(financials):
        v = r.get(field)
        if v is not None:
            return v
    return None
