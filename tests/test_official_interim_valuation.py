from valuation.official_interim import build_ttm_row
import sqlite3
import pandas as pd

from valuation import db as valuation_db
from valuation.forecast_engine import _dampen
from valuation.normalization_engine import YFinanceNormalizer
from valuation.valuation_engine import _weighted_fair_value


def test_abuk_official_q1_builds_ttm_without_carrying_stale_flows():
    annual = [{
        "year": 2025,
        "quarter": None,
        "revenue": 22_915_657_021.0,
        "net_income": 9_352_763_248.0,
        "eps": 6.32,
        "operating_income": 8_162_886_025.0,
        "ebit": 11_982_530_403.0,
        "equity": 32_135_051_656.0,
        "shares": 1_261_875_720.0,
    }]

    row, filing = build_ttm_row("ABUK.CA", annual)

    assert filing["period_end"] == "2026-03-31"
    assert row["quarter"] == "TTM Q1 2026"
    assert row["revenue"] == 25_804_707_021.0
    assert row["net_income"] == 12_202_803_248.0
    assert row["eps"] == 8.24
    assert row["operating_income"] is None
    assert row["ebit"] is None
    assert row["roe"] == 0.3797


def test_unknown_ticker_has_no_curated_override():
    assert build_ttm_row("UNKNOWN.CA", [{"year": 2025}]) == (None, None)


def test_card_excludes_synthetic_consensus_and_exposes_ttm_label(tmp_path, monkeypatch):
    db_path = tmp_path / "valuation.db"
    conn = sqlite3.connect(db_path)
    conn.executescript(valuation_db._SCHEMA)
    conn.execute(
        "INSERT INTO valuation_models "
        "(ticker, valuation_date, weighted_fair_value, bull_case, base_case, bear_case) "
        "VALUES ('ABUK.CA', '2026-07-30', 45.33, 72.53, 45.33, 27.20)"
    )
    conn.execute(
        "INSERT INTO financials (ticker, year, quarter) "
        "VALUES ('ABUK.CA', 2026, 'TTM Q1 2026')"
    )
    conn.execute(
        "INSERT INTO analyst_consensus (ticker, source, target_price, date) "
        "VALUES ('ABUK.CA', 'ive_estimate', 102.07, '2026-06-30')"
    )
    conn.commit()
    conn.close()

    monkeypatch.setattr(valuation_db, "_DB", db_path)
    monkeypatch.setattr(valuation_db, "_schema_initialized", True)
    card = valuation_db.get_valuation_card("ABUK.CA")

    assert card["analyst_consensus_price"] is None
    assert card["last_stmt_year"] == 2026
    assert card["last_stmt_quarter"] == "TTM Q1 2026"


def test_yfinance_ttm_uses_annual_plus_comparable_quarter_delta():
    annual_date = pd.Timestamp("2025-06-30")
    current = pd.Timestamp("2026-03-31")
    comparable = pd.Timestamp("2025-03-31")
    annual_inc = pd.DataFrame({annual_date: [22_915.0, 9_353.0, 6.32]}, index=[
        "Total Revenue", "Net Income", "Basic EPS",
    ])
    quarterly_inc = pd.DataFrame({
        current: [9_533.0, 5_633.0, 3.81],
        comparable: [6_644.0, 2_783.0, 1.89],
    }, index=["Total Revenue", "Net Income", "Basic EPS"])
    quarterly_bal = pd.DataFrame({current: [1_262.0, 32_135.0]}, index=[
        "Ordinary Shares Number", "Stockholders Equity",
    ])
    annual_rows = [{
        "year": 2025, "revenue": 22_915.0, "net_income": 9_353.0,
        "eps": 6.32, "shares": 1_262.0, "equity": 32_000.0,
    }]

    row = YFinanceNormalizer().normalize_ttm(
        annual_rows, annual_inc, quarterly_inc, quarterly_bal, pd.DataFrame()
    )

    assert row["quarter"] == "TTM 2026-03-31"
    assert row["revenue"] == 25_804.0
    assert row["net_income"] == 12_203.0
    assert row["eps"] == 8.24
    assert row["shares"] == 1_262.0


def test_growth_and_aggregation_reject_explosive_outliers():
    assert _dampen(8.0, 0.04) == 0.12
    values = {
        "dcf": 4_900.0,
        "ddm": 22.0,
        "residual_income": 70.0,
        "earnings_power": 68.0,
        "ev_ebitda": 60.0,
        "pe": 75.0,
        "pb": 53.0,
    }
    fair = _weighted_fair_value(values)
    assert fair is not None
    assert fair < 100.0
