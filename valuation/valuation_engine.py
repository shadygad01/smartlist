"""
valuation.valuation_engine — Orchestrates all valuation models for one ticker.

Workflow:
  1. Load financials + assumptions from valuation.db
  2. Generate forecasts
  3. Run all 7 models (DCF, DDM, RI, EPV, EV/EBITDA, P/E, P/B)
  4. Compute weighted fair value + bull/base/bear scenarios
  5. Save results to valuation.db

NEVER called during scanner execution.
"""
from __future__ import annotations

import sqlite3
from datetime import date
from pathlib import Path

from valuation.financial_parser import parse_financials
from valuation.forecast_engine import build_forecasts
from valuation.dcf_model import run_dcf
from valuation.ddm_model import run_ddm
from valuation.residual_income import run_residual_income
from valuation.epv_model import run_epv
from valuation.multiples_model import run_ev_ebitda, run_pe, run_pb
from valuation import db as _db

_DB = Path(__file__).parent.parent / "valuation.db"

# Model weights (must sum to 1.0 for models with data; rebalanced on missing models)
_WEIGHTS = {
    "dcf":            0.30,
    "ddm":            0.10,
    "residual_income": 0.15,
    "earnings_power": 0.15,
    "ev_ebitda":      0.10,
    "pe":             0.10,
    "pb":             0.10,
}


def _weighted_fair_value(results: dict) -> float | None:
    """Compute weighted intrinsic value from available model outputs."""
    total_w = 0.0
    total_v = 0.0
    for model, weight in _WEIGHTS.items():
        v = results.get(model)
        if v is not None and v > 0:
            total_v += v * weight
            total_w += weight
    if total_w < 0.15:  # too few models — unreliable
        return None
    return round(total_v / total_w, 4)


def _scenarios(fair_value: float, results: dict) -> tuple[float, float, float]:
    """Compute bear/base/bull cases from model spread."""
    valid = sorted([v for v in results.values() if v is not None and v > 0])
    if not valid:
        return fair_value * 0.70, fair_value, fair_value * 1.30

    # Bear: 10th percentile of model outputs, cap at 30% below fair value
    bear_raw = valid[0]
    bull_raw = valid[-1]

    bear = max(bear_raw, fair_value * 0.60)
    bull = min(bull_raw, fair_value * 1.60)
    base = fair_value

    return round(bear, 4), round(base, 4), round(bull, 4)


def run_valuation(ticker: str, current_price: float | None = None) -> dict | None:
    """Run full valuation for one ticker. Returns result dict or None on failure.

    This function is the only public API of the engine.
    Never called during scanner execution.
    """
    print(f"[ValuationEngine] Running models for {ticker}")
    conn = sqlite3.connect(str(_DB))
    conn.row_factory = sqlite3.Row

    try:
        raw_financials = _db.get_financials(conn, ticker)
        assumptions    = _db.get_assumptions(conn, ticker)
        company_row    = conn.execute(
            "SELECT sector FROM companies WHERE ticker=?", (ticker,)
        ).fetchone()
        sector = dict(company_row)["sector"] if company_row else None
    except Exception as e:
        conn.close()
        print(f"[ValuationEngine] DB read failed for {ticker}: {e}")
        return None

    financials = parse_financials(raw_financials)
    if not financials:
        conn.close()
        print(f"[ValuationEngine] No financial data for {ticker}")
        return None

    forecasts = build_forecasts(financials, assumptions.get("terminal_growth", 0.04))

    results = {
        "dcf":            run_dcf(financials, forecasts, assumptions, current_price),
        "ddm":            run_ddm(financials, forecasts, assumptions),
        "residual_income": run_residual_income(financials, forecasts, assumptions),
        "earnings_power": run_epv(financials, assumptions),
        "ev_ebitda":      run_ev_ebitda(financials, assumptions, sector),
        "pe":             run_pe(financials, assumptions, sector),
        "pb":             run_pb(financials, assumptions, sector),
    }

    fair_value = _weighted_fair_value(results)
    if fair_value is None:
        conn.close()
        print(f"[ValuationEngine] Insufficient models for {ticker}")
        return None

    bear, base, bull = _scenarios(fair_value, results)
    results["weighted_fair_value"] = fair_value
    results["bear_case"] = bear
    results["base_case"]  = base
    results["bull_case"]  = bull

    today = date.today().isoformat()
    try:
        _db.save_valuation_model(conn, ticker, today, results)
        if current_price:
            _db.save_valuation_history(conn, ticker, today, current_price, fair_value)
        conn.commit()
        print(f"[ValuationEngine] {ticker}: fair={fair_value:.2f} bear={bear:.2f} bull={bull:.2f}")
    except Exception as e:
        print(f"[ValuationEngine] Save failed for {ticker}: {e}")
    finally:
        conn.close()

    return results
