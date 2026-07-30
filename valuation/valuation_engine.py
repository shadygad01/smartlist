"""
valuation.valuation_engine — Orchestrates all valuation models for one ticker.

Workflow:
  1. Load financials + assumptions from valuation.db
  2. Measure data completeness (completeness_engine)
  3. Check per-model eligibility before running each model
  4. Generate forecasts
  5. Run eligible models; time each; record status
  6. Compute weighted fair value + bull/base/bear scenarios
  7. Save results to valuation.db (models, completeness, model_status, history)

NEVER called during scanner execution.
"""
from __future__ import annotations

import sqlite3
import time
from datetime import date
from pathlib import Path

from valuation.financial_parser import parse_financials
from valuation.forecast_engine import build_forecasts
from valuation.dcf_model import run_dcf
from valuation.ddm_model import run_ddm
from valuation.residual_income import run_residual_income
from valuation.epv_model import run_epv
from valuation.multiples_model import run_ev_ebitda, run_pe, run_pb
from valuation.completeness_engine import measure_completeness, check_model_eligibility
from valuation import db as _db

_DB = Path(__file__).parent.parent / "valuation.db"

# Model weights (rebalanced automatically on missing models)
_WEIGHTS = {
    "dcf":             0.30,
    "ddm":             0.10,
    "residual_income": 0.15,
    "earnings_power":  0.15,
    "ev_ebitda":       0.10,
    "pe":              0.10,
    "pb":              0.10,
}


def _weighted_fair_value(results: dict) -> float | None:
    """Compute a robust weighted value from at least three valid models.

    A single explosive DCF or residual-income result must not dominate the
    aggregate.  Values outside 1/3×–3× the model median are treated as model
    failures for this run and excluded before weights are rebalanced.
    """
    candidates = {
        model: value
        for model, value in results.items()
        if model in _WEIGHTS and value is not None and value > 0
    }
    if len(candidates) < 3:
        return None

    ordered = sorted(candidates.values())
    mid = len(ordered) // 2
    median = (
        ordered[mid]
        if len(ordered) % 2
        else (ordered[mid - 1] + ordered[mid]) / 2
    )
    lower, upper = median / 3.0, median * 3.0
    candidates = {
        model: value
        for model, value in candidates.items()
        if lower <= value <= upper
    }
    if len(candidates) < 3:
        return None

    total_w = 0.0
    total_v = 0.0
    for model, weight in _WEIGHTS.items():
        v = candidates.get(model)
        if v is not None:
            total_v += v * weight
            total_w += weight
    return round(total_v / total_w, 4)


def _scenarios(fair_value: float, results: dict) -> tuple[float, float, float]:
    """Compute bear/base/bull cases from model spread."""
    valid = sorted([v for v in results.values() if v is not None and v > 0])
    if not valid:
        return round(fair_value * 0.70, 4), fair_value, round(fair_value * 1.30, 4)

    bear = max(valid[0],  fair_value * 0.60)
    bull = min(valid[-1], fair_value * 1.60)
    return round(bear, 4), fair_value, round(bull, 4)


def _run_model(name: str, fn, *args) -> tuple[float | None, bool, str, float]:
    """
    Execute one valuation model function, returning (value, success, reason, ms).
    Catches all exceptions so one bad model never aborts the pipeline.
    """
    t0 = time.perf_counter()
    try:
        value = fn(*args)
        ms = round((time.perf_counter() - t0) * 1000, 2)
        if value is not None and value > 0:
            return value, True, "OK", ms
        return None, False, "model returned None or non-positive", ms
    except Exception as exc:
        ms = round((time.perf_counter() - t0) * 1000, 2)
        return None, False, str(exc)[:200], ms


def run_valuation(ticker: str, current_price: float | None = None) -> dict | None:
    """Run full valuation for one ticker. Returns result dict or None on failure.

    This function is the only public API of the engine.
    Never called during scanner execution.
    """
    print(f"[ValuationEngine] Running models for {ticker}")
    conn = sqlite3.connect(str(_DB))
    conn.row_factory = sqlite3.Row

    try:
        try:
            raw_financials = _db.get_financials(conn, ticker)
            assumptions    = _db.get_assumptions(conn, ticker)
            company_row    = conn.execute(
                "SELECT sector FROM companies WHERE ticker=?", (ticker,)
            ).fetchone()
            sector = dict(company_row)["sector"] if company_row else None
        except Exception as e:
            print(f"[ValuationEngine] DB read failed for {ticker}: {e}")
            return None

        financials = parse_financials(raw_financials)
        if not financials:
            print(f"[ValuationEngine] No financial data for {ticker}")
            return None

        latest_year = max(r["year"] for r in financials)
        if latest_year < date.today().year - 1:
            print(
                f"[ValuationEngine] {ticker}: latest statement year {latest_year} is stale — "
                "refusing to publish a fair value"
            )
            return None

        # Minimum data quality gate: at least one core financial statement field must
        # be non-NULL. EPS alone is insufficient — it could be synthetic.
        _CORE_FIELDS = ("revenue", "net_income", "operating_cash_flow", "equity")
        has_real_data = any(
            r.get(f) is not None
            for r in financials
            for f in _CORE_FIELDS
        )
        if not has_real_data:
            print(
                f"[ValuationEngine] {ticker}: financials contain no core income/balance data — "
                f"refusing to write valuation"
            )
            return None

        today = date.today().isoformat()

        # ── Data Completeness ────────────────────────────────────────────────────
        completeness = measure_completeness(financials)
        print(
            f"[ValuationEngine] {ticker}: completeness={completeness['completeness_percent']}% "
            f"available={len(completeness['_available_set'])}/{len(completeness['_available_set']) + len(completeness['_missing_set'])}"
        )

        # ── Per-model eligibility + execution ────────────────────────────────────
        forecasts = build_forecasts(financials, assumptions.get("terminal_growth", 0.04))

        _MODEL_FNS = {
            "dcf":             (run_dcf,          financials, forecasts, assumptions, current_price),
            "ddm":             (run_ddm,          financials, forecasts, assumptions),
            "residual_income": (run_residual_income, financials, forecasts, assumptions),
            "earnings_power":  (run_epv,          financials, assumptions),
            "ev_ebitda":       (run_ev_ebitda,    financials, assumptions, sector),
            "pe":              (run_pe,           financials, assumptions, sector),
            "pb":              (run_pb,           financials, assumptions, sector),
        }

        results: dict[str, float | None] = {}
        model_statuses: list[dict] = []

        for name, (fn, *args) in _MODEL_FNS.items():
            eligible, eligibility_reason = check_model_eligibility(name, financials)

            if not eligible:
                results[name] = None
                model_statuses.append({
                    "model":             name,
                    "executed":          False,
                    "success":           False,
                    "reason":            f"skipped: {eligibility_reason}",
                    "execution_time_ms": None,
                })
                print(f"[ValuationEngine] {ticker}/{name}: SKIP — {eligibility_reason}")
                continue

            value, success, reason, ms = _run_model(name, fn, *args)
            results[name] = value
            model_statuses.append({
                "model":             name,
                "executed":          True,
                "success":           success,
                "reason":            reason,
                "execution_time_ms": ms,
            })
            status_str = f"OK={value:.2f}" if success and value else "FAIL"
            print(f"[ValuationEngine] {ticker}/{name}: {status_str} ({ms}ms)")

        # ── Fair value + scenarios ───────────────────────────────────────────────
        fair_value = _weighted_fair_value(results)
        if fair_value is None:
            # Save completeness and model statuses even when valuation fails
            _flush_metadata(conn, ticker, today, completeness, model_statuses)
            conn.commit()
            print(f"[ValuationEngine] Insufficient models for {ticker}")
            return None

        bear, base, bull = _scenarios(fair_value, results)
        results["weighted_fair_value"] = fair_value
        results["bear_case"] = bear
        results["base_case"]  = base
        results["bull_case"]  = bull

        # ── Persist ──────────────────────────────────────────────────────────────
        try:
            _db.save_valuation_model(conn, ticker, today, results)
            if current_price:
                _db.save_valuation_history(conn, ticker, today, current_price, fair_value)
            _flush_metadata(conn, ticker, today, completeness, model_statuses)
            conn.commit()
            print(
                f"[ValuationEngine] {ticker}: fair={fair_value:.2f} "
                f"bear={bear:.2f} bull={bull:.2f}"
            )
        except Exception as e:
            print(f"[ValuationEngine] Save failed for {ticker}: {e}")

        results["_model_statuses"] = model_statuses
        results["_completeness"]   = completeness
        return results
    finally:
        conn.close()


def _flush_metadata(
    conn:            sqlite3.Connection,
    ticker:          str,
    today:           str,
    completeness:    dict,
    model_statuses:  list[dict],
) -> None:
    """Persist completeness measurement and model status rows."""
    _db.save_data_completeness(conn, ticker, today, completeness)
    for ms in model_statuses:
        _db.save_model_status(
            conn, ticker, today,
            ms["model"],
            ms["executed"],
            ms["success"],
            ms["reason"],
            ms["execution_time_ms"],
        )
