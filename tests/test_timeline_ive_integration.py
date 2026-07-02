"""
tests/test_timeline_ive_integration.py — End-to-end integration tests for
Event Timeline and Institutional Valuation Engine (IVE) pipeline.

Each test proves one stage of the data path. CI fails if any stage breaks.

Timeline pipeline:
  DB (constitutional_opportunity_events) → backend timeline builder
  → presentation_snapshot.json → React (TimelineSection) → visible DOM

IVE pipeline:
  valuation scheduler → valuation.db (valuation_models)
  → get_valuation_card() → presentation_snapshot.json
  → React (ValuationSection) → visible DOM
"""
from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

SNAPSHOT_PATH  = ROOT / "presentation_snapshot.json"
EVENTS_DB_PATH = ROOT / "constitutional_opportunity_events.db"

import valuation.db as _vdb


# ── Timeline: Stage 1 — Events exist in database ─────────────────────────────

class TestTimelineDatabase:
    def test_events_table_has_rows(self):
        """constitutional_opportunity_events.db must contain at least one row."""
        conn = sqlite3.connect(str(EVENTS_DB_PATH))
        count = conn.execute(
            "SELECT COUNT(*) FROM constitutional_opportunity_events"
        ).fetchone()[0]
        conn.close()
        assert count > 0, (
            f"constitutional_opportunity_events is empty — "
            f"timeline engine has never run or wrote no events."
        )

    def test_events_have_required_columns(self):
        """Every event must have ticker, event_type, event_date."""
        conn = sqlite3.connect(str(EVENTS_DB_PATH))
        rows = conn.execute(
            "SELECT ticker, event_type, event_date FROM constitutional_opportunity_events LIMIT 10"
        ).fetchall()
        conn.close()
        assert len(rows) > 0
        for ticker, event_type, event_date in rows:
            assert ticker, "ticker is NULL or empty"
            assert event_type in ("FIRST_BUY", "RE_ACCUMULATION"), f"Unexpected event_type: {event_type}"
            assert event_date, "event_date is NULL"

    def test_constitutional_buy_types_present(self):
        """At least one FIRST_BUY and one RE_ACCUMULATION must exist."""
        conn = sqlite3.connect(str(EVENTS_DB_PATH))
        types = {
            r[0] for r in conn.execute(
                "SELECT DISTINCT event_type FROM constitutional_opportunity_events"
            ).fetchall()
        }
        conn.close()
        assert "FIRST_BUY" in types, "No FIRST_BUY events found in DB"
        assert "RE_ACCUMULATION" in types, "No RE_ACCUMULATION events found in DB"


# ── Timeline: Stage 2 — Backend builds timeline objects ──────────────────────

class TestTimelineGeneration:
    def test_get_timeline_returns_list(self):
        """constitutional_timeline_engine.get_timeline() must return a non-empty list."""
        from constitutional_timeline_engine import get_timeline
        result = get_timeline()
        assert isinstance(result, list), f"get_timeline() returned {type(result)}"
        assert len(result) > 0, "get_timeline() returned empty list"

    def test_timeline_events_have_required_fields(self):
        """Every timeline event dict must carry the fields TimelineSection.tsx reads."""
        from constitutional_timeline_engine import get_timeline
        events = get_timeline()
        required = {"ticker", "event_type", "event_date", "constitutional_entry_price", "constitutional_r2"}
        for evt in events[:10]:
            missing = required - set(evt.keys())
            assert not missing, f"Event {evt.get('event_id')} missing fields: {missing}"


# ── Timeline: Stage 3 — Snapshot contains timeline ───────────────────────────

class TestTimelineSnapshot:
    def _load(self) -> dict:
        assert SNAPSHOT_PATH.exists(), f"Snapshot not found: {SNAPSHOT_PATH}"
        return json.loads(SNAPSHOT_PATH.read_text())

    def test_snapshot_has_timeline_key(self):
        snap = self._load()
        assert "timeline" in snap, "presentation_snapshot.json missing 'timeline' key"

    def test_snapshot_timeline_is_non_empty_list(self):
        snap = self._load()
        tl = snap["timeline"]
        assert isinstance(tl, list), f"timeline is {type(tl)}, expected list"
        assert len(tl) > 0, "timeline list is empty in snapshot"

    def test_snapshot_timeline_events_have_display_fields(self):
        """Fields consumed by TimelineSection.tsx must be present in every event."""
        snap = self._load()
        required = {"ticker", "event_type", "event_date", "constitutional_entry_price"}
        for evt in snap["timeline"]:
            missing = required - set(evt.keys())
            assert not missing, f"Snapshot event {evt.get('event_id')} missing: {missing}"

    def test_snapshot_statistics_reflect_timeline(self):
        """statistics.total_timeline_events must match len(timeline)."""
        snap = self._load()
        declared = snap.get("statistics", {}).get("total_timeline_events", -1)
        actual    = len(snap["timeline"])
        assert declared == actual, (
            f"statistics.total_timeline_events={declared} but timeline has {actual} events"
        )


# ── IVE: Stage 1 — valuation.db schema initialized ──────────────────────────

class TestIVEDatabase:
    def test_valuation_db_exists(self):
        db = ROOT / "valuation.db"
        assert db.exists(), "valuation.db not found — run valuation scheduler to create it"

    def test_valuation_db_schema_complete(self):
        status = _vdb.verify_schema()
        assert status["db_exists"], "valuation.db does not exist"
        assert status["ok"], (
            f"valuation.db schema incomplete. Missing tables: {status['missing_tables']}"
        )

    def test_get_valuation_card_does_not_raise(self):
        """get_valuation_card() must be safe to call even when DB is empty."""
        result = _vdb.get_valuation_card("NONEXISTENT.TICKER")
        assert result is None, f"Expected None for unknown ticker, got {result}"


# ── IVE: Stage 2 — Snapshot contains valuation key ──────────────────────────

class TestIVESnapshot:
    def _load(self) -> dict:
        assert SNAPSHOT_PATH.exists(), f"Snapshot not found: {SNAPSHOT_PATH}"
        return json.loads(SNAPSHOT_PATH.read_text())

    def test_snapshot_has_valuation_key(self):
        snap = self._load()
        assert "valuation" in snap, "presentation_snapshot.json missing 'valuation' key"

    def test_snapshot_valuation_is_dict(self):
        snap = self._load()
        val = snap["valuation"]
        assert isinstance(val, dict), f"valuation is {type(val)}, expected dict"


# ── IVE: Stage 3 — ValuationCard shape (when data present) ──────────────────

class TestIVEValuationCard:
    """Test the card shape using an in-memory seeded DB (does not require
    the live valuation scheduler to have run)."""

    @pytest.fixture(autouse=True)
    def seed_db(self, tmp_path):
        db_path = tmp_path / "valuation_test.db"
        original_db   = _vdb._DB
        original_flag = _vdb._schema_initialized

        _vdb._DB = db_path
        _vdb._schema_initialized = False
        _vdb.init_db()

        conn = sqlite3.connect(str(db_path))
        _vdb.save_company(conn, "TEST.CA", {
            "company_name": "Test Co", "sector": "Tech",
            "industry": "Software", "currency": "EGP",
            "shares_outstanding": 10_000_000,
        })
        conn.execute("INSERT OR IGNORE INTO financials (ticker, year) VALUES ('TEST.CA', 2025)")
        _vdb.save_valuation_model(conn, "TEST.CA", "2026-06-29", {
            "weighted_fair_value": 100.00,
            "bull_case": 130.00,
            "base_case": 100.00,
            "bear_case":  70.00,
        })
        _vdb.save_analyst_consensus(conn, "TEST.CA", "Broker A", 95.00, "BUY", "2026-06-29")
        conn.commit()
        conn.close()

        yield

        _vdb._DB               = original_db
        _vdb._schema_initialized = original_flag

    def test_get_valuation_card_returns_dict(self):
        card = _vdb.get_valuation_card("TEST.CA")
        assert card is not None, "get_valuation_card returned None for seeded ticker"
        assert isinstance(card, dict)

    def test_valuation_card_has_required_fields(self):
        """Fields consumed by ValuationSection.tsx must be present."""
        card = _vdb.get_valuation_card("TEST.CA")
        required = {
            "ticker", "valuation_date",
            "weighted_fair_value", "bull_case", "base_case", "bear_case",
            "analyst_consensus_price", "last_stmt_year",
        }
        missing = required - set(card.keys())
        assert not missing, f"ValuationCard missing fields: {missing}"

    def test_valuation_card_values_correct(self):
        card = _vdb.get_valuation_card("TEST.CA")
        assert card["weighted_fair_value"] == pytest.approx(100.00)
        assert card["bull_case"]           == pytest.approx(130.00)
        assert card["base_case"]           == pytest.approx(100.00)
        assert card["bear_case"]           == pytest.approx(70.00)
        assert card["analyst_consensus_price"] == pytest.approx(95.00)
        assert card["last_stmt_year"]      == 2025


# ── IVE: Stage 4 — Snapshot valuation key structure is correct ───────────────

class TestIVESnapshotStructure:
    """When valuation data IS present, verify per-ticker structure.
    This test re-generates a snapshot section with seeded data."""

    @pytest.fixture(autouse=True)
    def seed_db(self, tmp_path):
        db_path = tmp_path / "valuation_snap_test.db"
        original_db   = _vdb._DB
        original_flag = _vdb._schema_initialized

        _vdb._DB = db_path
        _vdb._schema_initialized = False
        _vdb.init_db()

        conn = sqlite3.connect(str(db_path))
        _vdb.save_company(conn, "SNAP.CA", {
            "company_name": "Snap Co", "sector": "Finance",
            "industry": "Banking", "currency": "EGP",
            "shares_outstanding": 5_000_000,
        })
        conn.execute("INSERT OR IGNORE INTO financials (ticker, year) VALUES ('SNAP.CA', 2025)")
        _vdb.save_valuation_model(conn, "SNAP.CA", "2026-06-29", {
            "weighted_fair_value": 55.00,
            "bull_case": 70.00,
            "base_case": 55.00,
            "bear_case": 40.00,
        })
        conn.commit()
        conn.close()

        yield

        _vdb._DB               = original_db
        _vdb._schema_initialized = original_flag

    def test_valuation_card_included_in_snapshot_dict(self):
        """Simulates the presentation_snapshot loop: card must be retrievable."""
        card = _vdb.get_valuation_card("SNAP.CA")
        valuation_section = {}
        if card:
            valuation_section["SNAP.CA"] = card

        assert "SNAP.CA" in valuation_section
        assert valuation_section["SNAP.CA"]["weighted_fair_value"] == pytest.approx(55.00)
