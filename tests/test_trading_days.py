"""
Tests for EGX trading day detection and scheduling logic.
"""

import pytest
from datetime import date, timedelta
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from main import is_egx_trading_day, most_recent_trading_day, EGX_HOLIDAYS


# ─────────────────────────────────────────────────────────────────────────────
# is_egx_trading_day
# ─────────────────────────────────────────────────────────────────────────────

class TestIsEgxTradingDay:

    def test_normal_sunday_is_trading_day(self):
        # 2026-01-04 is a Sunday — weekday() == 6, EGX trades Sun–Thu
        d = date(2026, 1, 4)
        assert d.weekday() == 6
        assert is_egx_trading_day(d) is True

    def test_monday_is_trading_day(self):
        d = date(2026, 1, 5)
        assert is_egx_trading_day(d) is True

    def test_thursday_is_trading_day(self):
        # 2026-01-08 is a Thursday — last trading day of EGX week
        d = date(2026, 1, 8)
        assert d.weekday() == 3
        assert is_egx_trading_day(d) is True

    def test_friday_is_weekend(self):
        # 2026-01-02 is a Friday — weekday() == 4
        d = date(2026, 1, 2)
        assert d.weekday() == 4
        assert is_egx_trading_day(d) is False

    def test_saturday_is_weekend(self):
        # 2026-01-03 is a Saturday — weekday() == 5
        d = date(2026, 1, 3)
        assert d.weekday() == 5
        assert is_egx_trading_day(d) is False

    def test_coptic_christmas_is_holiday(self):
        # 2026-01-07 — Coptic Christmas
        assert is_egx_trading_day(date(2026, 1, 7)) is False

    def test_revolution_day_is_holiday(self):
        # 2026-01-25 is a Sunday but NOT in holidays — should trade
        # 2026-01-29 is in holidays
        assert is_egx_trading_day(date(2026, 1, 29)) is False

    def test_labour_day_is_holiday(self):
        assert is_egx_trading_day(date(2026, 5, 1)) is False

    def test_all_holidays_are_blocked(self):
        for h in EGX_HOLIDAYS:
            # Holidays should never return True (even if they fall on a weekday)
            assert is_egx_trading_day(h) is False, f"Holiday {h} should be blocked"

    def test_day_before_holiday_is_trading(self):
        # Day before Coptic Christmas (2026-01-06) — Wednesday, not a holiday
        d = date(2026, 1, 6)
        assert d.weekday() == 1  # Tuesday
        assert is_egx_trading_day(d) is True

    def test_day_after_holiday_is_trading(self):
        # Day after Coptic Christmas (2026-01-08) — Thursday, not a holiday
        d = date(2026, 1, 8)
        assert is_egx_trading_day(d) is True


# ─────────────────────────────────────────────────────────────────────────────
# most_recent_trading_day
# ─────────────────────────────────────────────────────────────────────────────

class TestMostRecentTradingDay:

    def test_trading_day_returns_itself(self):
        # A known trading day should return itself
        d = date(2026, 1, 5)  # Monday, not a holiday
        assert most_recent_trading_day(d) == d

    def test_friday_returns_thursday(self):
        # Friday 2026-01-02 → last trading day was Thursday 2026-01-01
        friday = date(2026, 1, 2)
        result = most_recent_trading_day(friday)
        assert result == date(2026, 1, 1)
        assert is_egx_trading_day(result) is True

    def test_saturday_returns_thursday(self):
        # Saturday 2026-01-03 → last trading day was Thursday 2026-01-01
        saturday = date(2026, 1, 3)
        result = most_recent_trading_day(saturday)
        assert result == date(2026, 1, 1)

    def test_holiday_skips_to_previous_trading_day(self):
        # 2026-01-07 (Coptic Christmas, Wednesday) → 2026-01-06 (Tuesday)
        result = most_recent_trading_day(date(2026, 1, 7))
        assert result == date(2026, 1, 6)
        assert is_egx_trading_day(result) is True

    def test_result_is_always_a_trading_day(self):
        # Test over a range of dates — result must always be a trading day
        start = date(2026, 1, 1)
        for i in range(60):
            d = start + timedelta(days=i)
            result = most_recent_trading_day(d)
            assert is_egx_trading_day(result) is True, (
                f"most_recent_trading_day({d}) returned {result} which is not a trading day"
            )
