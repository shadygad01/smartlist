"""
valuation.completeness_engine — Data completeness measurement for IVE V2.

Runs before any valuation model.
Measures which required fields are available vs missing.
Determines per-model eligibility based on field availability.
Results stored in data_completeness table.
Never called during scanner execution.
"""
from __future__ import annotations

import json

# Every field tracked for completeness reporting
REQUIRED_FIELDS: list[str] = [
    "revenue", "gross_profit", "operating_income", "ebit", "ebitda",
    "net_income", "operating_cash_flow", "free_cash_flow",
    "cash", "debt", "equity", "assets", "book_value",
    "eps", "dividend", "shares", "roe", "roic", "capex",
]

# Per-model eligibility requirements
#   required  — all must be non-null in at least one year
#   either_or — each sublist needs at least one non-null field
MODEL_REQUIREMENTS: dict[str, dict] = {
    "dcf": {
        "required":    ["free_cash_flow", "shares"],
        "either_or":   [],
        "description": "FCFF DCF — needs projected FCF and share count",
    },
    "ddm": {
        "required":    ["dividend", "shares"],
        "either_or":   [],
        "description": "Gordon Growth DDM — needs per-share annual dividend",
    },
    "residual_income": {
        "required":    ["equity", "shares", "eps"],
        "either_or":   [],
        "description": "Ohlson RI — needs book value per share and EPS",
    },
    "earnings_power": {
        "required":    ["shares"],
        "either_or":   [["ebit", "operating_income"]],
        "description": "EPV — needs normalised EBIT/EBIT and share count",
    },
    "ev_ebitda": {
        "required":    ["ebitda", "shares"],
        "either_or":   [],
        "description": "EV/EBITDA — needs EBITDA and share count",
    },
    "pe": {
        "required":    ["eps"],
        "either_or":   [],
        "description": "P/E — needs earnings per share",
    },
    "pb": {
        "required":    ["equity", "shares"],
        "either_or":   [],
        "description": "P/B — needs book value per share",
    },
}


def _field_available(financials: list[dict], field: str) -> bool:
    """Return True if field is non-null in at least one financial year."""
    return any(r.get(field) is not None for r in financials)


def measure_completeness(financials: list[dict]) -> dict:
    """
    Measure data completeness across all financial years for a ticker.

    A field is 'available' if it is non-null in at least one year.
    Returns a storage-ready dict plus internal sets for eligibility checks.
    """
    available = [f for f in REQUIRED_FIELDS if _field_available(financials, f)]
    missing   = [f for f in REQUIRED_FIELDS if f not in available]
    pct       = round(len(available) / len(REQUIRED_FIELDS) * 100, 1)

    return {
        "required_fields":      json.dumps(REQUIRED_FIELDS),
        "available_fields":     json.dumps(available),
        "missing_fields":       json.dumps(missing),
        "completeness_percent": pct,
        "_available_set":       set(available),   # internal — not stored to DB
        "_missing_set":         set(missing),      # internal — not stored to DB
    }


def check_model_eligibility(
    model_name: str,
    financials: list[dict],
) -> tuple[bool, str]:
    """
    Determine whether a valuation model has enough data to run.

    Returns (is_eligible: bool, reason: str).
    reason is 'OK' on success, or a human-readable explanation on failure.
    """
    spec = MODEL_REQUIREMENTS.get(model_name)
    if spec is None:
        return False, f"Unknown model '{model_name}'"

    for field in spec.get("required", []):
        if not _field_available(financials, field):
            return False, (
                f"Required field '{field}' is NULL in all years "
                f"({spec['description']})"
            )

    for group in spec.get("either_or", []):
        if not any(_field_available(financials, f) for f in group):
            return False, (
                f"Need at least one of {group} — all are NULL "
                f"({spec['description']})"
            )

    return True, "OK"


def eligibility_summary(financials: list[dict]) -> dict[str, tuple[bool, str]]:
    """Return eligibility status for all models. Useful for logging."""
    return {
        name: check_model_eligibility(name, financials)
        for name in MODEL_REQUIREMENTS
    }
