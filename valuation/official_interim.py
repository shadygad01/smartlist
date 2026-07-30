"""Curated official interim filings used to build honest TTM rows."""
from __future__ import annotations

from copy import deepcopy


OFFICIAL_INTERIM_FILINGS: dict[str, dict] = {
    "ABUK.CA": {
        "period_end": "2026-03-31",
        "label": "TTM Q1 2026",
        "annual_base_year": 2025,
        "source_name": "abuqir_official_q1_2026",
        "source_url": "https://abuqir.net/financial-statement/41015/",
        "current": {
            "revenue": 9_533_430_000.0,
            "net_income": 5_633_180_000.0,
            "eps": 3.81,
        },
        "comparable": {
            "revenue": 6_644_380_000.0,
            "net_income": 2_783_140_000.0,
            "eps": 1.89,
        },
    },
}


def build_ttm_row(ticker: str, annual_rows: list[dict]) -> tuple[dict | None, dict | None]:
    """Return an official trailing-twelve-month row and its filing metadata."""
    filing = OFFICIAL_INTERIM_FILINGS.get(ticker)
    if not filing:
        return None, None

    base = next(
        (row for row in annual_rows if row.get("year") == filing["annual_base_year"]),
        None,
    )
    if base is None:
        return None, filing

    row = deepcopy(base)
    row["year"] = int(filing["period_end"][:4])
    row["quarter"] = filing["label"]
    for field, current_value in filing["current"].items():
        annual_value = base.get(field)
        comparable_value = filing["comparable"].get(field)
        row[field] = (
            round(annual_value - comparable_value + current_value, 4)
            if annual_value is not None and comparable_value is not None
            else None
        )

    # Never carry stale annual flow metrics into a TTM-labelled row.
    for field in (
        "gross_profit", "operating_income", "ebit", "ebitda",
        "operating_cash_flow", "free_cash_flow", "capex", "roic",
    ):
        row[field] = None

    equity = row.get("equity")
    if equity and row.get("net_income") is not None:
        row["roe"] = round(row["net_income"] / equity, 4)
    return row, filing


def build_source_records(ticker: str, filing: dict, collected_at: str) -> list[dict]:
    """Build provenance for fields sourced from the official filing."""
    period = filing["period_end"]
    version = f"{filing['source_name']}-{period}-v1"
    return [
        {
            "ticker": ticker,
            "statement": "income",
            "period": period,
            "field_name": field,
            "source_name": filing["source_name"],
            "source_priority": 1,
            "collection_time": collected_at,
            "validation_status": "valid",
            "data_version": version,
        }
        for field in filing["current"]
    ]
