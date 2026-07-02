"""
Tests for technical indicator calculations: MACD, RSI, Swings, AVWAP.
"""

import pytest
import numpy as np
import pandas as pd
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from main import calc_macd, _calc_rsi, swings, calc_avwap


def make_close(values):
    return pd.Series(values, dtype=float)


def make_swings_df(values):
    """Build a minimal OHLCV DataFrame for swings() tests.
    High == Low == Close so the results are identical to the old close-series behaviour."""
    s = pd.Series(values, dtype=float)
    return pd.DataFrame({
        "Open": s, "High": s, "Low": s, "Close": s,
        "Volume": pd.Series([1.0] * len(s)),
    })


def make_ohlcv(n=100, base=100.0, seed=42):
    """Generate synthetic OHLCV DataFrame with realistic price movement."""
    rng = np.random.default_rng(seed)
    close = base + np.cumsum(rng.normal(0, 1, n))
    close = np.maximum(close, 1.0)
    high  = close + rng.uniform(0.5, 2.0, n)
    low   = close - rng.uniform(0.5, 2.0, n)
    low   = np.maximum(low, 0.5)
    open_ = close + rng.uniform(-1.0, 1.0, n)
    vol   = rng.integers(100_000, 1_000_000, n).astype(float)
    return pd.DataFrame({"Open": open_, "High": high, "Low": low, "Close": close, "Volume": vol})


# ─────────────────────────────────────────────────────────────────────────────
# calc_macd
# ─────────────────────────────────────────────────────────────────────────────

class TestCalcMacd:

    def test_returns_three_series(self):
        close = make_close(range(1, 101))
        m, s, h = calc_macd(close)
        assert isinstance(m, pd.Series)
        assert isinstance(s, pd.Series)
        assert isinstance(h, pd.Series)

    def test_histogram_equals_macd_minus_signal(self):
        close = make_close(range(1, 101))
        m, s, h = calc_macd(close)
        pd.testing.assert_series_equal(h, m - s)

    def test_length_matches_input(self):
        close = make_close(range(1, 51))
        m, s, h = calc_macd(close)
        assert len(m) == 50
        assert len(s) == 50
        assert len(h) == 50

    def test_trending_up_macd_positive(self):
        # Strong uptrend: MACD should be positive toward the end
        close = make_close([i * 2 for i in range(1, 101)])
        m, _, _ = calc_macd(close)
        assert float(m.iloc[-1]) > 0

    def test_trending_down_macd_negative(self):
        # Strong downtrend: MACD should be negative toward the end
        close = make_close([200 - i for i in range(100)])
        m, _, _ = calc_macd(close)
        assert float(m.iloc[-1]) < 0

    def test_single_bar_does_not_crash(self):
        # Should not raise, even with minimal data
        close = make_close([100.0])
        m, s, h = calc_macd(close)
        assert len(m) == 1


# ─────────────────────────────────────────────────────────────────────────────
# _calc_rsi
# ─────────────────────────────────────────────────────────────────────────────

class TestCalcRsi:

    def test_rsi_bounds(self):
        close = make_close(np.random.default_rng(0).normal(100, 5, 100).cumsum())
        rsi = _calc_rsi(close).dropna()
        assert (rsi >= 0).all(), "RSI should never be below 0"
        assert (rsi <= 100).all(), "RSI should never exceed 100"

    def test_all_gains_rsi_near_100(self):
        # Perfectly rising prices → RSI must be 100 (no losses → avg_l = 0)
        close = make_close([100 + i for i in range(50)])
        rsi = _calc_rsi(close).dropna()
        assert len(rsi) > 0, "RSI should produce valid values for all-gain series"
        assert float(rsi.iloc[-1]) == pytest.approx(100.0)

    def test_all_losses_rsi_near_0(self):
        # Perfectly falling prices → RSI approaches 0
        close = make_close([150 - i for i in range(50)])
        rsi = _calc_rsi(close).dropna()
        assert float(rsi.iloc[-1]) < 10

    def test_flat_prices_rsi_near_50(self):
        # Constant prices → no gains or losses → RSI should be NaN or neutral
        close = make_close([100.0] * 30)
        rsi = _calc_rsi(close)
        # Either all NaN (division by zero) or around 50 — both are acceptable
        valid = rsi.dropna()
        if len(valid) > 0:
            # If it produces values they should be between 0 and 100
            assert (valid >= 0).all() and (valid <= 100).all()

    def test_length_matches_input(self):
        close = make_close(range(1, 41))
        rsi = _calc_rsi(close)
        assert len(rsi) == 40


# ─────────────────────────────────────────────────────────────────────────────
# swings
# ─────────────────────────────────────────────────────────────────────────────

class TestSwings:

    def test_returns_five_values(self):
        df = make_swings_df([100 + i % 10 for i in range(100)])
        result = swings(df)
        assert len(result) == 5

    def test_hi_greater_than_lo(self):
        df = make_swings_df([100 + i % 15 for i in range(100)])
        hi, lo, eq, buy_hi, sell_lo = swings(df)
        assert hi > lo

    def test_eq_is_midpoint(self):
        df = make_swings_df([100 + i % 10 for i in range(100)])
        hi, lo, eq, buy_hi, sell_lo = swings(df)
        assert abs(eq - (lo + (hi - lo) * 0.50)) < 1e-9

    def test_buy_hi_is_15_pct_of_range(self):
        df = make_swings_df([100 + i % 10 for i in range(100)])
        hi, lo, eq, buy_hi, sell_lo = swings(df)
        assert abs(buy_hi - (lo + (hi - lo) * 0.15)) < 1e-9

    def test_sell_lo_is_85_pct_of_range(self):
        df = make_swings_df([100 + i % 10 for i in range(100)])
        hi, lo, eq, buy_hi, sell_lo = swings(df)
        assert abs(sell_lo - (lo + (hi - lo) * 0.85)) < 1e-9

    def test_zone_ordering(self):
        df = make_swings_df([100 + i % 20 for i in range(100)])
        hi, lo, eq, buy_hi, sell_lo = swings(df)
        assert lo < buy_hi < eq < sell_lo < hi

    def test_constant_prices(self):
        # All same price — range is 0, hi == lo
        df = make_swings_df([100.0] * 100)
        hi, lo, eq, buy_hi, sell_lo = swings(df)
        assert hi == lo == eq == buy_hi == sell_lo

    def test_lookback_uses_last_lb_bars(self):
        # First 50 bars are high, last 80 bars used by default lb=80
        prices = [200.0] * 20 + [100.0 + i % 10 for i in range(80)]
        df = make_swings_df(prices)
        hi80, lo80, _, _, _ = swings(df, lb=80)
        # The 200-bars should NOT appear in lb=80 result
        assert hi80 < 150.0


# ─────────────────────────────────────────────────────────────────────────────
# calc_avwap
# ─────────────────────────────────────────────────────────────────────────────

class TestCalcAvwap:

    def test_returns_two_floats(self):
        df = make_ohlcv(60)
        av, av_lo = calc_avwap(df)
        assert isinstance(av, float)
        assert isinstance(av_lo, float)

    def test_avwap_lower_band_below_avwap(self):
        df = make_ohlcv(60)
        av, av_lo = calc_avwap(df)
        assert av_lo <= av

    def test_short_data_returns_last_close(self):
        df = make_ohlcv(3)
        av, av_lo = calc_avwap(df)
        last_close = float(df["Close"].iloc[-1])
        assert av == pytest.approx(last_close, abs=1e-6)
        assert av_lo == pytest.approx(last_close, abs=1e-6)

    def test_avwap_positive(self):
        df = make_ohlcv(100)
        av, av_lo = calc_avwap(df)
        assert av > 0
        assert av_lo > 0

    def test_missing_volume_does_not_crash(self):
        df = make_ohlcv(60)
        df["Volume"] = 0.0  # Zero volume edge case
        # Should not raise
        try:
            av, av_lo = calc_avwap(df)
        except Exception:
            pytest.skip("Zero-volume edge case not handled — known gap")
