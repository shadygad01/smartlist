from valuation.official_interim import build_ttm_row
import sqlite3

from valuation import db as valuation_db


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
