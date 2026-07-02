"""
Tests for position management: add_position, close_position,
update_position_target, load/save_open_positions.
"""

import pytest
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import main


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def isolated_positions(tmp_path, monkeypatch):
    """Each test starts with an empty positions dict and a temp file."""
    pos_file = str(tmp_path / "open_positions.json")
    monkeypatch.setattr(main, "POSITIONS_FILE", pos_file)
    monkeypatch.setattr(main, "open_positions", {})
    # Silence Telegram/print side-effects from update_position_target
    monkeypatch.setattr(main, "send_telegram_target_update", lambda *a, **kw: None)
    yield
    # Cleanup handled by tmp_path


# ─────────────────────────────────────────────────────────────────────────────
# load / save
# ─────────────────────────────────────────────────────────────────────────────

class TestLoadSavePositions:

    def test_load_missing_file_returns_empty_dict(self):
        result = main.load_open_positions()
        assert result == {}

    def test_save_then_load_roundtrip(self):
        main.open_positions["TEST.CA"] = {"entry_price": 50.0, "status": "open"}
        main.save_open_positions()
        main.open_positions = {}
        result = main.load_open_positions()
        assert "TEST.CA" in result
        assert result["TEST.CA"]["entry_price"] == 50.0

    def test_load_corrupted_file_returns_empty_dict(self):
        with open(main.POSITIONS_FILE, "w") as f:
            f.write("{ not valid json }")
        result = main.load_open_positions()
        assert result == {}

    def test_save_creates_file(self):
        main.open_positions["SYM.CA"] = {"entry_price": 10.0}
        main.save_open_positions()
        assert os.path.exists(main.POSITIONS_FILE)


# ─────────────────────────────────────────────────────────────────────────────
# add_position
# ─────────────────────────────────────────────────────────────────────────────

class TestAddPosition:

    def test_position_is_created(self):
        main.add_position("COMI.CA", 100.0, "2026-01-05")
        assert "COMI.CA" in main.open_positions

    def test_status_is_open(self):
        main.add_position("COMI.CA", 100.0, "2026-01-05")
        assert main.open_positions["COMI.CA"]["status"] == "open"

    def test_entry_price_is_stored(self):
        main.add_position("COMI.CA", 75.5, "2026-01-05")
        assert main.open_positions["COMI.CA"]["entry_price"] == 75.5

    def test_current_level_starts_at_zero(self):
        main.add_position("COMI.CA", 100.0, "2026-01-05")
        assert main.open_positions["COMI.CA"]["current_level"] == 0

    def test_fib_targets_are_generated(self):
        main.add_position("COMI.CA", 100.0, "2026-01-05")
        targets = main.open_positions["COMI.CA"]["fib_targets"]
        assert len(targets) >= 2

    def test_first_target_is_min_volatility(self):
        entry = 100.0
        vol   = 0.12
        main.add_position("COMI.CA", entry, "2026-01-05", volatility_min_target=vol)
        first_target = main.open_positions["COMI.CA"]["fib_targets"][0]
        assert first_target == pytest.approx(entry * (1 + vol))

    def test_all_fib_targets_above_min_target(self):
        entry = 100.0
        vol   = 0.12
        min_tgt = entry * (1 + vol)
        main.add_position("COMI.CA", entry, "2026-01-05", volatility_min_target=vol)
        for t in main.open_positions["COMI.CA"]["fib_targets"]:
            assert t >= min_tgt, f"Target {t} is below min_target {min_tgt}"

    def test_fib_targets_are_sorted_ascending(self):
        main.add_position("COMI.CA", 100.0, "2026-01-05")
        targets = main.open_positions["COMI.CA"]["fib_targets"]
        assert targets == sorted(targets)

    def test_entry_score_stored(self):
        main.add_position("COMI.CA", 100.0, "2026-01-05", entry_score=42)
        assert main.open_positions["COMI.CA"]["entry_score"] == 42

    def test_adding_same_symbol_overwrites(self):
        main.add_position("COMI.CA", 100.0, "2026-01-05")
        main.add_position("COMI.CA", 200.0, "2026-01-06")
        assert main.open_positions["COMI.CA"]["entry_price"] == 200.0

    def test_multiple_symbols_independent(self):
        main.add_position("COMI.CA", 100.0, "2026-01-05")
        main.add_position("TMGH.CA", 50.0, "2026-01-05")
        assert "COMI.CA" in main.open_positions
        assert "TMGH.CA" in main.open_positions
        assert main.open_positions["COMI.CA"]["entry_price"] == 100.0
        assert main.open_positions["TMGH.CA"]["entry_price"] == 50.0


# ─────────────────────────────────────────────────────────────────────────────
# close_position
# ─────────────────────────────────────────────────────────────────────────────

class TestClosePosition:

    def test_close_unknown_symbol_returns_false(self):
        assert main.close_position("UNKNOWN.CA", 100.0) is False

    def test_close_sets_status_to_closed(self):
        main.add_position("COMI.CA", 100.0, "2026-01-05")
        main.close_position("COMI.CA", 115.0)
        assert main.open_positions["COMI.CA"]["status"] == "closed"

    def test_close_records_exit_price(self):
        main.add_position("COMI.CA", 100.0, "2026-01-05")
        main.close_position("COMI.CA", 120.0)
        assert main.open_positions["COMI.CA"]["exit_price"] == 120.0

    def test_close_calculates_pnl(self):
        main.add_position("COMI.CA", 100.0, "2026-01-05")
        main.close_position("COMI.CA", 115.0)
        assert main.open_positions["COMI.CA"]["pnl"] == pytest.approx(15.0)

    def test_close_calculates_pnl_pct(self):
        main.add_position("COMI.CA", 100.0, "2026-01-05")
        main.close_position("COMI.CA", 115.0)
        assert main.open_positions["COMI.CA"]["pnl_pct"] == pytest.approx(15.0)

    def test_close_with_loss_has_negative_pnl(self):
        main.add_position("COMI.CA", 100.0, "2026-01-05")
        main.close_position("COMI.CA", 85.0)
        assert main.open_positions["COMI.CA"]["pnl"] < 0
        assert main.open_positions["COMI.CA"]["pnl_pct"] == pytest.approx(-15.0)

    def test_close_stores_reason(self):
        main.add_position("COMI.CA", 100.0, "2026-01-05")
        main.close_position("COMI.CA", 115.0, reason="target_hit")
        assert main.open_positions["COMI.CA"]["exit_reason"] == "target_hit"

    def test_close_returns_true_on_success(self):
        main.add_position("COMI.CA", 100.0, "2026-01-05")
        result = main.close_position("COMI.CA", 115.0)
        assert result is True


# ─────────────────────────────────────────────────────────────────────────────
# update_position_target
# ─────────────────────────────────────────────────────────────────────────────

class TestUpdatePositionTarget:

    def test_update_unknown_symbol_returns_false(self):
        assert main.update_position_target("UNKNOWN.CA", 1, 110.0) is False

    def test_update_out_of_bounds_level_returns_false(self):
        main.add_position("COMI.CA", 100.0, "2026-01-05")
        n_targets = len(main.open_positions["COMI.CA"]["fib_targets"])
        assert main.update_position_target("COMI.CA", n_targets + 5, 110.0) is False

    def test_update_advances_current_level(self):
        main.add_position("COMI.CA", 100.0, "2026-01-05")
        main.update_position_target("COMI.CA", 1, 110.0)
        assert main.open_positions["COMI.CA"]["current_level"] == 1

    def test_update_changes_target_price(self):
        main.add_position("COMI.CA", 100.0, "2026-01-05")
        targets = main.open_positions["COMI.CA"]["fib_targets"]
        main.update_position_target("COMI.CA", 1, 110.0)
        assert main.open_positions["COMI.CA"]["target"] == targets[1]

    def test_update_returns_true_on_success(self):
        main.add_position("COMI.CA", 100.0, "2026-01-05")
        result = main.update_position_target("COMI.CA", 1, 110.0)
        assert result is True
