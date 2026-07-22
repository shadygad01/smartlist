"""
Regression tests for notifications/signal_state_store.py and
notifications/delivery_store.py — the idempotent alert state machine and the
append-only delivery log.

Guards against the connection-leak regression where a raised exception mid
function skipped `con.close()` (fixed by wrapping the connection lifetime in
try/finally), and against delivery_store.recent() silently dropping rows due
to its redundant/dead connection-reopening logic.
"""
from __future__ import annotations

import sqlite3

import pytest

from notifications import signal_state_store as sss
from notifications import delivery_store as ds


@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    db_path = tmp_path / "notification_delivery.db"
    monkeypatch.setattr(sss, "_DB", db_path)
    monkeypatch.setattr(ds, "_DB_PATH", db_path)
    yield db_path


class TestSignalStateStore:
    def test_record_transition_is_idempotent(self):
        first = sss.record_transition("COMI", sss.STATE_NONE, sss.STATE_CONST_BUY, "2026-07-22")
        second = sss.record_transition("COMI", sss.STATE_NONE, sss.STATE_CONST_BUY, "2026-07-22")
        assert first is True
        assert second is False

    def test_get_current_state_reflects_last_transition(self):
        sss.record_transition("COMI", sss.STATE_NONE, sss.STATE_CONST_BUY, "2026-07-22")
        assert sss.get_current_state("COMI") == sss.STATE_CONST_BUY

    def test_get_current_state_defaults_to_none(self):
        assert sss.get_current_state("UNKNOWN") == sss.STATE_NONE

    def test_mark_notified_and_has_notified_today(self):
        sss.record_transition("COMI", sss.STATE_NONE, sss.STATE_CONST_BUY, "2026-07-22")
        assert sss.has_notified_today("COMI", sss.STATE_CONST_BUY, "2026-07-22") is False
        sss.mark_notified("COMI", sss.STATE_CONST_BUY, "2026-07-22")
        assert sss.has_notified_today("COMI", sss.STATE_CONST_BUY, "2026-07-22") is True

    def test_get_todays_events_returns_recorded_transition(self):
        sss.record_transition("COMI", sss.STATE_NONE, sss.STATE_CONST_BUY, "2026-07-22")
        events = sss.get_todays_events("2026-07-22")
        assert len(events) == 1
        assert events[0]["ticker"] == "COMI"

    def test_connection_does_not_leak_on_db_error(self, monkeypatch):
        """A failure inside the try body must still close the connection (regression guard).

        Uses a fake connection (real sqlite3.Connection objects reject
        per-instance attribute overrides) whose execute() explodes on the
        first business-logic call, so we can assert close() still fires.
        """

        class FakeConn:
            def __init__(self):
                self.closed = False

            def execute(self, *a, **k):
                raise sqlite3.OperationalError("simulated failure")

            def commit(self):
                pass

            def close(self):
                self.closed = True

        fake = FakeConn()
        monkeypatch.setattr(sss, "_conn", lambda: fake)

        result = sss.record_transition("COMI", sss.STATE_NONE, sss.STATE_CONST_BUY, "2026-07-22")

        assert result is False
        assert fake.closed is True


class TestDeliveryStore:
    def test_record_attempt_success_roundtrip(self):
        rid = ds.record_attempt("telegram", recipient="chat1", subject="Buy signal")
        ds.record_success(rid, retry_count=1)
        rows = ds.recent(limit=10)
        assert len(rows) == 1
        assert rows[0]["id"] == rid
        assert rows[0]["status"] == "sent"
        assert rows[0]["retry_count"] == 1

    def test_record_failure_sets_error(self):
        rid = ds.record_attempt("email", recipient="a@b.com", subject="x")
        ds.record_failure(rid, "SMTP timeout", retry_count=2)
        rows = ds.recent(limit=10)
        assert rows[0]["status"] == "failed"
        assert rows[0]["error"] == "SMTP timeout"
        assert rows[0]["retry_count"] == 2

    def test_recent_respects_limit_and_order(self):
        ids = [ds.record_attempt("telegram", subject=f"msg{i}") for i in range(3)]
        rows = ds.recent(limit=2)
        assert len(rows) == 2
        # newest first
        assert rows[0]["id"] == ids[-1]
