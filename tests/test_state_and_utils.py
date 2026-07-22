"""
Tests for state management, signal-change detection, position monitoring,
CSV helpers, and utility functions.
"""

import pytest
import json
import os
import csv
import sys
import unittest.mock as mock
from datetime import datetime, date
from types import SimpleNamespace

import pandas as pd
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import main
from main import (
    detect_signal_changes,
    save_scan_results,
    load_previous_results,
    save_history,
    col,
    pill,
    bar,
    is_market_hours,
    STOCKS,
    CAIRO,
)


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def isolated_state(tmp_path, monkeypatch):
    """Each test works in a clean temp directory with isolated global state."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(main, "open_positions", {})
    monkeypatch.setattr(main, "POSITIONS_FILE", str(tmp_path / "open_positions.json"))
    monkeypatch.setattr(main, "send_telegram_target_update", lambda *a, **kw: None)
    monkeypatch.setattr(main, "send_telegram_zone3_reinforcement", lambda *a, **kw: None)
    yield


# ─────────────────────────────────────────────────────────────────────────────
# col — safe column accessor
# ─────────────────────────────────────────────────────────────────────────────

class TestCol:

    def test_existing_column_returned(self):
        df = pd.DataFrame({"Close": [1.0, 2.0, 3.0], "Volume": [100, 200, 300]})
        result = col(df, "Close")
        pd.testing.assert_series_equal(result, df["Close"].dropna())

    def test_missing_column_returns_empty_series(self):
        df = pd.DataFrame({"Close": [1.0, 2.0]})
        result = col(df, "Open")
        assert isinstance(result, pd.Series)
        assert len(result) == 0

    def test_nan_values_are_dropped(self):
        df = pd.DataFrame({"Close": [1.0, float("nan"), 3.0]})
        result = col(df, "Close")
        assert len(result) == 2
        assert float("nan") not in result.values


# ─────────────────────────────────────────────────────────────────────────────
# save_scan_results / load_previous_results
# ─────────────────────────────────────────────────────────────────────────────

class TestScanResultsIO:

    def test_save_creates_file(self):
        save_scan_results({"COMI.CA": {"score": 42, "sig": "Buy"}})
        assert os.path.exists("scan_results.json")

    def test_save_and_load_roundtrip(self):
        data = {"COMI.CA": {"score": 55, "sig": "Strong Buy", "price": 72.5}}
        save_scan_results(data)
        loaded = load_previous_results()
        assert loaded["COMI.CA"]["score"] == 55
        assert loaded["COMI.CA"]["sig"] == "Strong Buy"

    def test_load_missing_file_returns_empty_dict(self):
        result = load_previous_results()
        assert result == {}

    def test_load_corrupted_json_returns_empty_dict(self):
        with open("scan_results.json", "w") as f:
            f.write("{ bad json !!!")
        result = load_previous_results()
        assert result == {}

    def test_save_multiple_stocks(self):
        data = {s: {"score": i * 10, "sig": "Skip"} for i, s in enumerate(STOCKS[:5])}
        save_scan_results(data)
        loaded = load_previous_results()
        assert len(loaded) == 5

    def test_load_preserves_types(self):
        data = {"COMI.CA": {"score": 45, "price": 72.5, "ok": True}}
        save_scan_results(data)
        loaded = load_previous_results()
        assert isinstance(loaded["COMI.CA"]["score"], int)
        assert isinstance(loaded["COMI.CA"]["price"], float)
        assert loaded["COMI.CA"]["ok"] is True


# ─────────────────────────────────────────────────────────────────────────────
# detect_signal_changes
# ─────────────────────────────────────────────────────────────────────────────

class _FixedDate:
    """Stand-in for today_cairo()'s return value — only .isoformat() is used."""
    def __init__(self, iso: str):
        self._iso = iso

    def isoformat(self) -> str:
        return self._iso


class TestDetectSignalChanges:
    """
    Regression tests for main.detect_signal_changes(snap).

    PRODUCTION API CHANGE (git: "Fix near-count mismatch by sharing one
    PresentationSnapshot with the dashboard"): the function used to take
    (current: dict, previous: dict) and compare string signals ("Buy" /
    "Wait" / "Skip" / "Strong Buy"). It now takes a single snapshot object
    (snap.universe_snapshot) and decides eligibility via the boolean
    constitutional_gate.is_constitutional_buy(r2, score, price, entry) gate,
    persisting state transitions through notifications.signal_state_store
    (idempotent NONE/CONSTITUTIONAL_BUY state machine) instead of comparing
    two in-memory dicts. The old tests called the removed two-argument form
    and have been rewritten below against the current implementation.

    Only "only_stocks_in_stocks_list_are_checked" has no direct analog: the
    new function operates on whatever universe_snapshot rows it is given, not
    a filtered global STOCKS list — the closest surviving behavior (rows
    missing a ticker are skipped) is covered by
    test_row_without_ticker_is_skipped below.

    Since the persisted state machine only ever stores NONE or
    CONSTITUTIONAL_BUY (STATE_NEAR_ENTRY is defined but never assigned
    anywhere in the codebase), the old "Skip"/"Wait"/"no previous data"
    distinctions all collapse onto the same "not currently in buy zone"
    starting state — they are intentionally represented by ONE test
    (test_new_buy_zone_entry_is_detected) rather than three near-duplicates.
    """

    TODAY = "2026-07-22"

    @pytest.fixture(autouse=True)
    def _isolate_signal_store(self, tmp_path, monkeypatch):
        import notifications.signal_state_store as sss
        monkeypatch.setattr(sss, "_DB", tmp_path / "notification_delivery.db")
        monkeypatch.setattr(main, "today_cairo", lambda: _FixedDate(self.TODAY))

    def _row(self, ticker, *, r2=70.0, score=50.0, price=100.0, entry=115.0,
              last_scan=None, **extra):
        row = {
            "ticker": ticker,
            "candidate_r2": r2,
            "expected_reward_score": score,
            "current_price": price,
            "constitutional_entry_price": entry,
            "last_scan": last_scan or self.TODAY,
            "sector": "Banks",
            "return_pct": 0.0,
            "status": "ACTIVE",
        }
        row.update(extra)
        return row

    def _snap(self, rows):
        return SimpleNamespace(universe_snapshot=rows, new_events_today=[])

    def test_new_buy_zone_entry_is_detected(self):
        """A ticker with no prior recorded state entering its buy zone -> FIRST_BUY."""
        snap = self._snap([self._row(STOCKS[0])])  # r2=70, score=50, price<=entry: qualifies
        changes = detect_signal_changes(snap)
        assert len(changes) == 1
        assert changes[0]["ticker"] == STOCKS[0]
        assert changes[0]["event_type"] == "FIRST_BUY"

    def test_not_in_buy_zone_not_detected(self):
        """Gate fails (score below CONST_SCORE_MIN) -> no event."""
        snap = self._snap([self._row(STOCKS[0], score=10.0)])
        changes = detect_signal_changes(snap)
        assert len(changes) == 0

    def test_price_above_entry_not_detected(self):
        """Gate fails on price (current_price > entry_price) -> no event."""
        snap = self._snap([self._row(STOCKS[0], price=120.0, entry=115.0)])
        changes = detect_signal_changes(snap)
        assert len(changes) == 0

    def test_exiting_buy_zone_is_not_alerted(self):
        """Deterioration (was CONST_BUY, now fails gate) must not fire an alert,
        and must silently reset persisted state to NONE."""
        import notifications.signal_state_store as sss
        sss.record_transition(STOCKS[0], sss.STATE_NONE, sss.STATE_CONST_BUY, self.TODAY)

        snap = self._snap([self._row(STOCKS[0], score=10.0)])  # now fails the gate
        changes = detect_signal_changes(snap)

        assert len(changes) == 0
        assert sss.get_current_state(STOCKS[0]) == sss.STATE_NONE

    def test_continuation_in_buy_zone_is_not_re_alerted(self):
        """
        Regression test for a real bug: a ticker already in its constitutional
        buy zone as of a PRIOR day, still in the buy zone TODAY (a pure
        continuation, not a new signal), must not generate any event.

        Root cause (fixed in notifications/signal_state_store.py): the
        "retry unnotified transitions" safety net in detect_signal_changes()
        used get_unnotified_transitions(), which — unlike the sibling
        get_stale_unnotified() — did not exclude CONST_BUY->CONST_BUY
        continuation rows. Continuation rows are legitimately never marked
        notified (by design, they're not supposed to alert), so the retry
        path was resurrecting them as spurious "RE_ACCUMULATION" alerts on
        the first scan of every day the ticker remained in its buy zone.
        Confirmed via direct reproduction before the fix; this test fails
        against the pre-fix code and passes against the fix.
        """
        import notifications.signal_state_store as sss
        sss.record_transition(STOCKS[0], sss.STATE_NONE, sss.STATE_CONST_BUY, "2026-07-21")

        snap = self._snap([self._row(STOCKS[0])])  # still qualifies today
        changes = detect_signal_changes(snap)

        assert changes == []

    def test_multiple_tickers_mixed_results(self):
        snap = self._snap([
            self._row(STOCKS[0]),                 # qualifies -> FIRST_BUY
            self._row(STOCKS[1], score=60.0),      # qualifies -> FIRST_BUY
            self._row(STOCKS[2], score=10.0),      # fails gate -> no event
        ])
        changes = detect_signal_changes(snap)
        tickers = {c["ticker"] for c in changes}
        assert tickers == {STOCKS[0], STOCKS[1]}

    def test_change_record_contains_expected_fields(self):
        snap = self._snap([self._row(
            STOCKS[0], score=42.0, price=75.0, entry=88.0, r2=65.0,
        )])
        changes = detect_signal_changes(snap)
        c = changes[0]
        assert c["ticker"] == STOCKS[0]
        assert c["event_type"] == "FIRST_BUY"
        assert c["constitutional_score"] == 42.0
        assert c["current_price"] == 75.0
        assert c["constitutional_entry_price"] == 88.0
        assert c["constitutional_r2"] == 65.0
        assert c["event_date"] == self.TODAY

    def test_row_without_ticker_is_skipped(self):
        """Malformed universe rows with no ticker must be skipped, not crash."""
        row = self._row("")
        snap = self._snap([row])
        changes = detect_signal_changes(snap)
        assert changes == []

    def test_empty_universe_falls_back_to_new_events_today(self):
        """When universe_snapshot is empty, fall back to snap.new_events_today."""
        snap = SimpleNamespace(universe_snapshot=[], new_events_today=[{"ticker": "X"}])
        changes = detect_signal_changes(snap)
        assert changes == [{"ticker": "X"}]


# ─────────────────────────────────────────────────────────────────────────────
# save_history — CSV append
# ─────────────────────────────────────────────────────────────────────────────

class TestSaveHistory:

    def _mock_result(self, price=72.5, score=45, signal="Buy", target=85.0):
        return {
            "price": price,
            "last_dt": "2026-01-05",
            "is_fresh": True,
            "signal": signal,
            "score": score,
            "target": target,
        }

    def test_creates_csv_on_first_call(self):
        save_history("COMI.CA", self._mock_result())
        assert os.path.exists("signals_history.csv")

    def test_csv_contains_correct_fields(self):
        save_history("COMI.CA", self._mock_result(price=72.5, score=45))
        df = pd.read_csv("signals_history.csv")
        assert "stock" in df.columns
        assert "score" in df.columns
        assert "price" in df.columns

    def test_csv_has_correct_values(self):
        save_history("COMI.CA", self._mock_result(price=72.5, score=45, signal="Buy"))
        df = pd.read_csv("signals_history.csv")
        assert df.iloc[0]["stock"] == "COMI.CA"
        assert df.iloc[0]["price"] == 72.5
        assert df.iloc[0]["score"] == 45
        assert df.iloc[0]["signal"] == "Buy"

    def test_appends_on_subsequent_calls(self):
        save_history("COMI.CA", self._mock_result())
        save_history("TMGH.CA", self._mock_result(price=30.0, score=55))
        df = pd.read_csv("signals_history.csv")
        assert len(df) == 2
        assert set(df["stock"].tolist()) == {"COMI.CA", "TMGH.CA"}

    def test_same_stock_multiple_days_appends(self):
        save_history("COMI.CA", self._mock_result(score=40))
        save_history("COMI.CA", self._mock_result(score=55))
        df = pd.read_csv("signals_history.csv")
        assert len(df) == 2
        assert list(df["score"]) == [40, 55]

    def test_unknown_stock_uses_symbol_as_company(self):
        save_history("FAKE.CA", self._mock_result())
        df = pd.read_csv("signals_history.csv")
        assert df.iloc[0]["company"] == "FAKE.CA"


# ─────────────────────────────────────────────────────────────────────────────
# monitor_positions — target advancement
# ─────────────────────────────────────────────────────────────────────────────

class TestMonitorPositions:

    def test_price_below_all_targets_no_update(self):
        main.add_position("COMI.CA", 100.0, "2026-01-05")
        first_target = main.open_positions["COMI.CA"]["fib_targets"][0]
        # Price well below first target
        main.monitor_positions({"COMI.CA": first_target * 0.95})
        assert main.open_positions["COMI.CA"]["current_level"] == 0

    def test_price_hits_first_target_advances_level(self):
        main.add_position("COMI.CA", 100.0, "2026-01-05")
        first_target = main.open_positions["COMI.CA"]["fib_targets"][0]
        main.monitor_positions({"COMI.CA": first_target})
        assert main.open_positions["COMI.CA"]["current_level"] == 1

    def test_price_hits_multiple_targets_advances_multiple_levels(self):
        main.add_position("COMI.CA", 100.0, "2026-01-05")
        # Price exceeds first two targets
        targets = main.open_positions["COMI.CA"]["fib_targets"]
        price_above_two = targets[1] * 1.001
        main.monitor_positions({"COMI.CA": price_above_two})
        assert main.open_positions["COMI.CA"]["current_level"] >= 2

    def test_closed_position_is_skipped(self):
        main.add_position("COMI.CA", 100.0, "2026-01-05")
        main.open_positions["COMI.CA"]["status"] = "closed"
        targets = main.open_positions["COMI.CA"]["fib_targets"]
        main.monitor_positions({"COMI.CA": targets[0] * 2})
        assert main.open_positions["COMI.CA"]["current_level"] == 0

    def test_symbol_not_in_prices_is_skipped(self):
        main.add_position("COMI.CA", 100.0, "2026-01-05")
        targets = main.open_positions["COMI.CA"]["fib_targets"]
        # Price dict is empty — no update
        main.monitor_positions({})
        assert main.open_positions["COMI.CA"]["current_level"] == 0

    def test_level_does_not_exceed_targets_length(self):
        main.add_position("COMI.CA", 100.0, "2026-01-05")
        n = len(main.open_positions["COMI.CA"]["fib_targets"])
        # Price way above all targets
        main.monitor_positions({"COMI.CA": 99999.0})
        assert main.open_positions["COMI.CA"]["current_level"] <= n - 1

    def test_multiple_positions_monitored_independently(self):
        main.add_position("COMI.CA", 100.0, "2026-01-05")
        main.add_position("TMGH.CA", 50.0, "2026-01-05")
        t_comi = main.open_positions["COMI.CA"]["fib_targets"][0]
        # Only COMI hits its target
        main.monitor_positions({"COMI.CA": t_comi, "TMGH.CA": 49.0})
        assert main.open_positions["COMI.CA"]["current_level"] == 1
        assert main.open_positions["TMGH.CA"]["current_level"] == 0


# ─────────────────────────────────────────────────────────────────────────────
# monitor_reinforcement — Zone 3 trigger
# ─────────────────────────────────────────────────────────────────────────────

class TestMonitorReinforcement:

    def _make_result_with_z3(self, z3_lo, z3_hi):
        return {
            "entry_zones": {
                "z3": {"lo": z3_lo, "hi": z3_hi, "center": (z3_lo + z3_hi) / 2}
            }
        }

    def test_price_in_z3_triggers_reinforcement(self):
        main.add_position("COMI.CA", 100.0, "2026-01-05")
        results = {"COMI.CA": self._make_result_with_z3(92.0, 95.0)}
        main.monitor_reinforcement({"COMI.CA": 93.5}, results)
        assert main.open_positions["COMI.CA"].get("reinforced") is True

    def test_price_above_z3_does_not_trigger(self):
        main.add_position("COMI.CA", 100.0, "2026-01-05")
        results = {"COMI.CA": self._make_result_with_z3(92.0, 95.0)}
        main.monitor_reinforcement({"COMI.CA": 98.0}, results)
        assert main.open_positions["COMI.CA"].get("reinforced") is None

    def test_price_below_z3_does_not_trigger(self):
        main.add_position("COMI.CA", 100.0, "2026-01-05")
        results = {"COMI.CA": self._make_result_with_z3(92.0, 95.0)}
        main.monitor_reinforcement({"COMI.CA": 90.0}, results)
        assert main.open_positions["COMI.CA"].get("reinforced") is None

    def test_already_reinforced_is_not_triggered_again(self):
        main.add_position("COMI.CA", 100.0, "2026-01-05")
        main.open_positions["COMI.CA"]["reinforced"] = True
        main.open_positions["COMI.CA"]["reinforcement_price"] = 93.0
        results = {"COMI.CA": self._make_result_with_z3(92.0, 95.0)}
        with mock.patch.object(main, "send_telegram_zone3_reinforcement") as m_send:
            main.monitor_reinforcement({"COMI.CA": 93.5}, results)
            m_send.assert_not_called()

    def test_reinforcement_records_avg_price(self):
        entry = 100.0
        cur   = 93.5
        main.add_position("COMI.CA", entry, "2026-01-05")
        results = {"COMI.CA": self._make_result_with_z3(92.0, 95.0)}
        main.monitor_reinforcement({"COMI.CA": cur}, results)
        expected_avg = round((entry + cur) / 2, 2)
        assert main.open_positions["COMI.CA"]["avg_price"] == expected_avg

    def test_reinforcement_records_current_price(self):
        main.add_position("COMI.CA", 100.0, "2026-01-05")
        results = {"COMI.CA": self._make_result_with_z3(92.0, 95.0)}
        main.monitor_reinforcement({"COMI.CA": 93.5}, results)
        assert main.open_positions["COMI.CA"]["reinforcement_price"] == 93.5

    def test_closed_position_skipped(self):
        main.add_position("COMI.CA", 100.0, "2026-01-05")
        main.open_positions["COMI.CA"]["status"] = "closed"
        results = {"COMI.CA": self._make_result_with_z3(92.0, 95.0)}
        with mock.patch.object(main, "send_telegram_zone3_reinforcement") as m_send:
            main.monitor_reinforcement({"COMI.CA": 93.5}, results)
            m_send.assert_not_called()

    def test_no_entry_zones_skipped(self):
        main.add_position("COMI.CA", 100.0, "2026-01-05")
        results = {"COMI.CA": {}}   # no entry_zones key
        main.monitor_reinforcement({"COMI.CA": 93.5}, results)
        assert main.open_positions["COMI.CA"].get("reinforced") is None


# ─────────────────────────────────────────────────────────────────────────────
# HTML helpers — pill, bar
# ─────────────────────────────────────────────────────────────────────────────

class TestHtmlHelpers:

    def test_pill_returns_string(self):
        assert isinstance(pill(7, 10), str)

    def test_pill_contains_score_fraction(self):
        result = pill(7, 10)
        assert "7/10" in result

    def test_pill_zero_max_does_not_crash(self):
        result = pill(0, 0)
        assert isinstance(result, str)

    def test_pill_high_score_green(self):
        result = pill(8, 10)   # 80% → green
        assert "#d1f0dd" in result or "#1a7340" in result

    def test_pill_low_score_red(self):
        result = pill(2, 10)   # 20% → red
        assert "#fde8e8" in result or "#a02020" in result

    def test_bar_returns_string(self):
        assert isinstance(bar(50), str)

    def test_bar_contains_score(self):
        result = bar(65)
        assert ">65<" in result
        assert "/100" in result

    def test_bar_high_score_green(self):
        result = bar(75)
        assert "#1a7340" in result

    def test_bar_low_score_red(self):
        result = bar(30)
        assert "#a02020" in result

    def test_bar_zero_does_not_crash(self):
        result = bar(0)
        assert isinstance(result, str)

    def test_bar_100_does_not_crash(self):
        result = bar(100)
        assert isinstance(result, str)


# ─────────────────────────────────────────────────────────────────────────────
# is_market_hours — time boundary checks
# ─────────────────────────────────────────────────────────────────────────────

class TestIsMarketHours:

    def _mock_time(self, hour, minute, monkeypatch):
        fake_dt = datetime(2026, 1, 5, hour, minute, tzinfo=CAIRO)
        monkeypatch.setattr(main, "now_cairo", lambda: fake_dt)

    def test_exactly_10am_is_market_hours(self, monkeypatch):
        self._mock_time(10, 0, monkeypatch)
        assert is_market_hours() is True

    def test_noon_is_market_hours(self, monkeypatch):
        self._mock_time(12, 0, monkeypatch)
        assert is_market_hours() is True

    def test_2pm_is_market_hours(self, monkeypatch):
        self._mock_time(14, 0, monkeypatch)
        assert is_market_hours() is True

    def test_exactly_2_30pm_is_market_hours(self, monkeypatch):
        self._mock_time(14, 30, monkeypatch)
        assert is_market_hours() is True

    def test_2_31pm_is_not_market_hours(self, monkeypatch):
        self._mock_time(14, 31, monkeypatch)
        assert is_market_hours() is False

    def test_9am_is_not_market_hours(self, monkeypatch):
        self._mock_time(9, 59, monkeypatch)
        assert is_market_hours() is False

    def test_midnight_is_not_market_hours(self, monkeypatch):
        self._mock_time(0, 0, monkeypatch)
        assert is_market_hours() is False

    def test_after_close_is_not_market_hours(self, monkeypatch):
        self._mock_time(15, 0, monkeypatch)
        assert is_market_hours() is False
