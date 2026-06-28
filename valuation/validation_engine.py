"""
valuation.validation_engine — Data validation pipeline for IVE V2.

Every collected dataset is validated before normalization and storage.
Invalid records are rejected and never stored.
Warnings are logged but do not block storage.
Never called during scanner execution.
"""
from __future__ import annotations

from dataclasses import dataclass, field

# At least one of these must be non-null for a financial row to be accepted
_CORE_FIELDS = ("revenue", "net_income", "operating_cash_flow", "equity")

_MIN_YEAR = 1990
_MAX_YEAR = 2030
_ROE_MAX_ABS       = 10.0   # |ROE| > 1000% is suspicious
_EQUITY_ASSETS_MIN = -5.0   # equity/assets < -500% is suspicious


@dataclass
class Issue:
    field:    str
    severity: str    # 'error' | 'warning'
    message:  str


@dataclass
class RowValidation:
    is_valid: bool
    status:   str           # 'valid' | 'warning' | 'rejected'
    issues:   list[Issue] = field(default_factory=list)


# ── Per-field checkers ──────────────────────────────────────────────────────

def _chk_year(row: dict) -> list[Issue]:
    yr = row.get("year")
    if yr is None:
        return [Issue("year", "error", "Missing year")]
    if not isinstance(yr, (int, float)) or not (_MIN_YEAR <= int(yr) <= _MAX_YEAR):
        return [Issue("year", "error", f"Year {yr} outside valid range [{_MIN_YEAR}-{_MAX_YEAR}]")]
    return []


def _chk_core(row: dict) -> list[Issue]:
    if not any(row.get(f) is not None for f in _CORE_FIELDS):
        return [Issue(
            "core_data", "error",
            f"Year {row.get('year')}: revenue, net_income, operating_cash_flow "
            "and equity are all NULL — no real financial data"
        )]
    return []


def _chk_negatives(row: dict) -> list[Issue]:
    issues: list[Issue] = []
    yr = row.get("year", "?")

    if row.get("shares") is not None and row["shares"] < 0:
        issues.append(Issue("shares", "error", f"Year {yr}: negative shares_outstanding"))

    if row.get("revenue") is not None and row["revenue"] < 0:
        issues.append(Issue("revenue", "error", f"Year {yr}: negative revenue"))

    if row.get("assets") is not None and row["assets"] < 0:
        issues.append(Issue("assets", "warning", f"Year {yr}: negative total assets"))

    return issues


def _chk_ratios(row: dict) -> list[Issue]:
    issues: list[Issue] = []
    yr = row.get("year", "?")

    roe = row.get("roe")
    if roe is not None and abs(roe) > _ROE_MAX_ABS:
        issues.append(Issue("roe", "warning", f"Year {yr}: extreme |ROE| = {roe:.2f}"))

    equity = row.get("equity")
    assets = row.get("assets")
    if equity is not None and assets is not None and assets > 0:
        ratio = equity / assets
        if ratio < _EQUITY_ASSETS_MIN:
            issues.append(Issue(
                "equity", "warning",
                f"Year {yr}: extreme negative equity/assets ratio = {ratio:.2f}"
            ))

    # EPS sanity: if both reported EPS and NI+shares exist, they should be close
    eps = row.get("eps")
    ni  = row.get("net_income")
    sh  = row.get("shares")
    if eps is not None and ni is not None and sh and sh > 0:
        implied = ni / sh
        denom   = max(abs(implied), 0.001)
        if abs(eps - implied) / denom > 10.0:
            issues.append(Issue(
                "eps", "warning",
                f"Year {yr}: reported EPS ({eps:.4f}) diverges significantly "
                f"from NI/shares ({implied:.4f})"
            ))

    return issues


# ── Public API ──────────────────────────────────────────────────────────────

def validate_financial_row(row: dict) -> RowValidation:
    """Validate a single financial row. Returns RowValidation."""
    issues: list[Issue] = []
    issues.extend(_chk_year(row))

    if any(i.severity == "error" for i in issues):
        return RowValidation(False, "rejected", issues)

    issues.extend(_chk_core(row))
    issues.extend(_chk_negatives(row))
    issues.extend(_chk_ratios(row))

    errors   = [i for i in issues if i.severity == "error"]
    warnings = [i for i in issues if i.severity == "warning"]

    if errors:
        return RowValidation(False, "rejected", issues)
    if warnings:
        return RowValidation(True, "warning", issues)
    return RowValidation(True, "valid", [])


def validate_financials(rows: list[dict]) -> tuple[list[dict], list[dict]]:
    """
    Validate a list of normalized financial rows.
    Returns (valid_rows, rejected_rows).
    Attaches '_validation_status' and '_validation_issues' to every row.
    Duplicate years are rejected.
    """
    if not rows:
        return [], []

    # Count years to detect duplicates
    year_counts: dict[int, int] = {}
    for r in rows:
        yr = r.get("year")
        if yr is not None:
            year_counts[yr] = year_counts.get(yr, 0) + 1

    valid: list[dict] = []
    rejected: list[dict] = []

    for row in rows:
        row = dict(row)  # don't mutate caller's data
        yr  = row.get("year")

        if yr is not None and year_counts.get(yr, 0) > 1:
            row["_validation_status"] = "rejected"
            row["_validation_issues"] = [f"Duplicate period: year {yr}"]
            rejected.append(row)
            print(f"[Validation] Rejected duplicate year {yr}")
            continue

        vr = validate_financial_row(row)
        row["_validation_status"]  = vr.status
        row["_validation_issues"]  = [
            f"{i.severity.upper()} {i.field}: {i.message}" for i in vr.issues
        ]

        if vr.is_valid:
            valid.append(row)
            if vr.issues:
                print(
                    f"[Validation] Year {yr}: accepted with warnings — "
                    + "; ".join(i.message for i in vr.issues)
                )
        else:
            rejected.append(row)
            print(
                f"[Validation] Year {yr}: REJECTED — "
                + "; ".join(i.message for i in vr.issues)
            )

    return valid, rejected


def validate_market_data(data: dict) -> tuple[dict, list[str]]:
    """
    Validate and clean market data dict.
    Returns (cleaned_data, list_of_issues).
    Issues describe what was removed; cleaned_data has invalid fields set to None.
    """
    issues: list[str] = []
    cleaned = dict(data)

    price = cleaned.get("current_price")
    if price is not None and price <= 0:
        issues.append(f"Non-positive current_price: {price}")
        cleaned["current_price"] = None

    shares = cleaned.get("shares_outstanding")
    if shares is not None and shares <= 0:
        issues.append(f"Non-positive shares_outstanding: {shares}")
        cleaned["shares_outstanding"] = None

    beta = cleaned.get("beta")
    if beta is not None and (beta < -5.0 or beta > 10.0):
        issues.append(f"Implausible beta: {beta} (clipped to None)")
        cleaned["beta"] = None

    market_cap = cleaned.get("market_cap")
    if market_cap is not None and market_cap < 0:
        issues.append(f"Negative market_cap: {market_cap}")
        cleaned["market_cap"] = None

    return cleaned, issues


def validate_analyst_consensus(rows: list[dict]) -> tuple[list[dict], list[dict]]:
    """
    Validate analyst consensus rows.
    Returns (valid_rows, rejected_rows).
    """
    valid: list[dict] = []
    rejected: list[dict] = []

    for row in rows:
        row    = dict(row)
        target = row.get("target_price")
        issues: list[str] = []

        if not row.get("source"):
            issues.append("Missing source identifier")

        if target is None:
            issues.append("Missing target_price")
        elif not isinstance(target, (int, float)) or target <= 0:
            issues.append(f"Non-positive target_price: {target}")

        if issues:
            row["_validation_status"] = "rejected"
            row["_validation_issues"] = issues
            rejected.append(row)
        else:
            row["_validation_status"] = "valid"
            row["_validation_issues"] = []
            valid.append(row)

    return valid, rejected
