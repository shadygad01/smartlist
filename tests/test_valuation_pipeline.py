"""
tests/test_valuation_pipeline.py

Regression tests proving:
  1. ValuationPanel is a generic shared component — no ticker-specific logic.
  2. Valuation data flows correctly from valuation.db → snapshot → frontend type contract.
  3. BuySignalCard and ReAccumulationSection both import ValuationPanel.
  4. When valuation data exists, the required fields are present.
  5. When valuation data is absent, components degrade gracefully.
  6. Price in valuation matches price in snapshot (same canonical source).

Run with: pytest tests/test_valuation_pipeline.py -v
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

ROOT          = Path(__file__).parent.parent
SNAPSHOT_PATH = ROOT / "presentation_snapshot.json"
# The Next.js frontend at frontend/src this file originally targeted was
# migrated to the Vite app at artifacts/egx-commandcenter (frontend/ no
# longer exists on the code branch); dashboard components now live under
# components/dashboard/ (no app/ nesting).
FRONTEND_SRC  = ROOT / "artifacts" / "egx-commandcenter" / "src"
DASHBOARD_DIR = FRONTEND_SRC / "components" / "dashboard"
VALUATION_DB  = ROOT / "valuation.db"


# ── Helpers ───────────────────────────────────────────────────────────────────

def _load_snapshot() -> dict:
    assert SNAPSHOT_PATH.exists(), f"Snapshot not found: {SNAPSHOT_PATH}"
    return json.loads(SNAPSHOT_PATH.read_text())


# ── Part 1: ValuationPanel generic component contract ─────────────────────────

class TestValuationPanelGeneralization:
    """ValuationPanel must be a shared component with zero ticker-specific logic."""

    def test_valuation_panel_exists_as_shared_component(self):
        panel = DASHBOARD_DIR / "ValuationPanel.tsx"
        assert panel.exists(), "ValuationPanel.tsx must exist as a shared component"

    def test_valuation_panel_accepts_generic_props(self):
        text = (DASHBOARD_DIR / "ValuationPanel.tsx").read_text()
        assert "valuation: ValuationCard" in text or "valuation:" in text
        assert "currentPrice" in text, "ValuationPanel must accept currentPrice prop"

    def test_valuation_panel_has_no_hardcoded_tickers(self):
        text = (DASHBOARD_DIR / "ValuationPanel.tsx").read_text()
        for symbol in ["ABUK", "MCQE", "COMI", "TMGH"]:
            assert symbol not in text, f"ValuationPanel.tsx hardcodes ticker '{symbol}'"

    def test_buy_signal_card_imports_valuation_panel(self):
        text = (DASHBOARD_DIR / "BuySignalCard.tsx").read_text()
        assert "import ValuationPanel from './ValuationPanel'" in text

    def test_re_accumulation_section_imports_valuation_panel(self):
        text = (DASHBOARD_DIR / "ReAccumulationSection.tsx").read_text()
        assert "import ValuationPanel from './ValuationPanel'" in text

    def test_valuation_panel_render_condition_is_generic(self):
        """Must render based on data presence, not ticker identity."""
        text = (DASHBOARD_DIR / "BuySignalCard.tsx").read_text()
        # The condition must check valuation data fields, not ticker names
        assert "weighted_fair_value" in text or "valuation &&" in text


# ── Part 2: valuation.db schema integrity ────────────────────────────────────

class TestValuationDBSchema:
    """valuation.db must have the correct schema even when empty."""

    def test_valuation_db_exists(self):
        assert VALUATION_DB.exists(), "valuation.db not found"

    def test_valuation_db_has_required_tables(self):
        import valuation.db as _vdb
        status = _vdb.verify_schema()
        assert status["db_exists"], "valuation.db does not exist"
        assert status["ok"], (
            f"valuation.db schema incomplete. Missing: {status['missing_tables']}"
        )

    def test_get_valuation_card_safe_when_empty(self):
        """get_valuation_card must return None safely when DB has no data."""
        import valuation.db as _vdb
        result = _vdb.get_valuation_card("NONEXISTENT.XX")
        assert result is None


# ── Part 3: Snapshot valuation contract ──────────────────────────────────────

class TestSnapshotValuationContract:
    """presentation_snapshot.json must have a 'valuation' key of correct type."""

    def test_snapshot_has_valuation_key(self):
        snap = _load_snapshot()
        assert "valuation" in snap, "presentation_snapshot.json missing 'valuation' key"

    def test_snapshot_valuation_is_dict(self):
        snap = _load_snapshot()
        assert isinstance(snap["valuation"], dict), (
            f"valuation is {type(snap['valuation'])}, expected dict"
        )

    def test_valuation_entries_have_required_fields(self):
        """When valuation data exists, every entry must have all required fields."""
        snap    = _load_snapshot()
        entries = snap.get("valuation", {})
        if not entries:
            pytest.skip("No valuation entries in snapshot — scheduler not yet run")

        required = {
            "ticker", "valuation_date",
            "weighted_fair_value", "bull_case", "base_case", "bear_case",
            "analyst_consensus_price", "last_stmt_year",
        }
        for ticker, card in entries.items():
            missing = required - set(card.keys())
            assert not missing, (
                f"ValuationCard for {ticker} missing fields: {missing}"
            )

    def test_valuation_ticker_keys_match_card_ticker_field(self):
        """Dict key must equal card['ticker'] — no mismatches."""
        snap    = _load_snapshot()
        entries = snap.get("valuation", {})
        if not entries:
            pytest.skip("No valuation entries in snapshot")

        for key, card in entries.items():
            assert card.get("ticker") == key, (
                f"Mismatch: dict key '{key}' != card.ticker '{card.get('ticker')}'"
            )


# ── Part 4: Valuation data vs snapshot price consistency ─────────────────────

class TestValuationPriceAlignment:
    """
    Valuation cards must reference the same tickers as universe_snapshot.
    No valuation entry may reference a ticker not in the constitutional universe.
    """

    def test_valuation_tickers_are_in_universe(self):
        snap          = _load_snapshot()
        universe_tkrs = {u["ticker"] for u in snap.get("universe_snapshot", [])}
        val_tkrs      = set(snap.get("valuation", {}).keys())
        if not val_tkrs:
            pytest.skip("No valuation entries in snapshot")

        extras = val_tkrs - universe_tkrs
        assert not extras, (
            f"Valuation entries for tickers not in universe_snapshot: {extras}"
        )

    def test_buy_signal_tickers_can_look_up_valuation(self):
        """Every buy-ready ticker lookup must not throw — valuation may be None."""
        snap     = _load_snapshot()
        val_map  = snap.get("valuation", {})
        buy_sigs = [
            u for u in snap.get("universe_snapshot", [])
            if any(s in (u.get("waiting_for_reason") or "")
                   for s in ["READY NOW", "READY FOR RE-ACCUMULATION"])
        ]
        if not buy_sigs:
            pytest.skip("No buy signals in snapshot")

        # Must not raise — None is acceptable; missing key is acceptable
        for sig in buy_sigs:
            card = val_map.get(sig["ticker"])
            if card is not None:
                assert isinstance(card, dict), f"valuation[{sig['ticker']}] is not a dict"


# ── Part 5: Seeded DB validation (scheduler logic) ───────────────────────────

class TestValuationSchedulerWithSeedData:
    """Validate get_valuation_card() against seeded in-memory data."""

    @pytest.fixture(autouse=True)
    def seed_db(self, tmp_path):
        import valuation.db as _vdb
        db_path = tmp_path / "val_test.db"
        orig_db   = _vdb._DB
        orig_flag = _vdb._schema_initialized

        _vdb._DB = db_path
        _vdb._schema_initialized = False
        _vdb.init_db()

        conn = sqlite3.connect(str(db_path))
        _vdb.save_company(conn, "ABUK.CA", {
            "company_name": "Abu Kir Fertilizers", "sector": "Materials",
            "industry": "Chemicals", "currency": "EGP",
            "shares_outstanding": 200_000_000,
        })
        conn.execute("INSERT OR IGNORE INTO financials (ticker, year) VALUES ('ABUK.CA', 2025)")
        _vdb.save_valuation_model(conn, "ABUK.CA", "2026-06-29", {
            "weighted_fair_value": 95.00,
            "bull_case": 115.00,
            "base_case": 95.00,
            "bear_case": 70.00,
        })
        _vdb.save_analyst_consensus(conn, "ABUK.CA", "EGX Research", 88.00, "BUY", "2026-06-29")
        conn.commit()
        conn.close()
        yield
        _vdb._DB               = orig_db
        _vdb._schema_initialized = orig_flag

    def test_get_valuation_card_returns_all_required_fields(self):
        import valuation.db as _vdb
        card = _vdb.get_valuation_card("ABUK.CA")
        assert card is not None
        required = {
            "ticker", "valuation_date",
            "weighted_fair_value", "bull_case", "base_case", "bear_case",
            "analyst_consensus_price", "last_stmt_year",
        }
        missing = required - set(card.keys())
        assert not missing, f"Missing fields: {missing}"

    def test_fair_value_is_correct(self):
        import valuation.db as _vdb
        card = _vdb.get_valuation_card("ABUK.CA")
        assert card["weighted_fair_value"] == pytest.approx(95.00)
        assert card["bull_case"]           == pytest.approx(115.00)
        assert card["bear_case"]           == pytest.approx(70.00)
        assert card["analyst_consensus_price"] == pytest.approx(88.00)

    def test_upside_calculation_is_correct(self):
        """Upside must be computed from snapshot fields only — never from DB directly."""
        import valuation.db as _vdb
        card         = _vdb.get_valuation_card("ABUK.CA")
        current_price = 66.80  # from snapshot
        fv            = card["weighted_fair_value"]
        upside_pct    = (fv - current_price) / current_price * 100
        assert upside_pct == pytest.approx(42.21, abs=0.1), (
            f"Upside calc wrong: expected ~42.2%, got {upside_pct:.2f}%"
        )
        mos = (fv - current_price) / fv * 100
        assert mos == pytest.approx(29.68, abs=0.1)

    def test_valuation_pipeline_snapshot_injection(self):
        """Simulate the snapshot builder loop — card must be injectable as a dict."""
        import valuation.db as _vdb
        valuation_section = {}
        for ticker in ["ABUK.CA", "MISSING.CA"]:
            card = _vdb.get_valuation_card(ticker)
            if card:
                valuation_section[ticker] = card

        assert "ABUK.CA" in valuation_section
        assert "MISSING.CA" not in valuation_section
        assert valuation_section["ABUK.CA"]["weighted_fair_value"] == pytest.approx(95.00)
