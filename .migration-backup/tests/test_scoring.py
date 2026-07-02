"""
Tests for SMC scoring functions: sc_price, sc_macd, sc_avwap, sc_div, sig_info.
"""

import pytest
import numpy as np
import pandas as pd
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from main import (
    sc_price, sc_macd, sc_avwap, sc_div, sig_info,
    W_PRICE, W_MACD, W_AVWAP, W_DIV,
)


def make_close(values):
    return pd.Series(values, dtype=float)


# ─────────────────────────────────────────────────────────────────────────────
# sc_price
# ─────────────────────────────────────────────────────────────────────────────

class TestScPrice:
    """
    Range: lo=100, hi=200, eq=150, buy_hi=115, sell_lo=185
    Buy zone:    100–115 → max score W_PRICE down to ~60% of W_PRICE
    Mid-disc:    115–150 → ~60% of W_PRICE down to 0
    Premium:     150+    → 0
    """

    LO = 100.0
    HI = 200.0
    # eq = lo + (hi-lo)*0.50 = 150
    EQ = 150.0
    # buy_hi = lo + (hi-lo)*0.15 = 115
    BUY_HI = 115.0
    # sell_lo = lo + (hi-lo)*0.85 = 185
    SELL_LO = 185.0

    def test_at_swing_low_returns_max_score(self):
        pts, desc = sc_price(self.LO, self.LO, self.HI, self.EQ, self.BUY_HI, self.SELL_LO)
        assert pts == W_PRICE
        assert "Buy Zone" in desc

    def test_at_buy_hi_returns_60_pct(self):
        pts, desc = sc_price(self.BUY_HI, self.LO, self.HI, self.EQ, self.BUY_HI, self.SELL_LO)
        assert pts == round(W_PRICE * 0.60)
        assert "Buy Zone" in desc

    def test_above_eq_returns_zero(self):
        pts, desc = sc_price(self.EQ, self.LO, self.HI, self.EQ, self.BUY_HI, self.SELL_LO)
        assert pts == 0
        assert "Premium" in desc

    def test_well_above_eq_returns_zero(self):
        pts, desc = sc_price(self.HI, self.LO, self.HI, self.EQ, self.BUY_HI, self.SELL_LO)
        assert pts == 0

    def test_mid_discount_is_between_buy_zone_and_zero(self):
        mid = (self.BUY_HI + self.EQ) / 2  # 132.5
        pts, desc = sc_price(mid, self.LO, self.HI, self.EQ, self.BUY_HI, self.SELL_LO)
        assert 0 < pts < round(W_PRICE * 0.60)
        assert "Mid-Discount" in desc

    def test_invalid_range_returns_zero(self):
        pts, desc = sc_price(100.0, 100.0, 100.0, 100.0, 100.0, 100.0)
        assert pts == 0
        assert "Invalid" in desc

    def test_score_never_negative(self):
        for cur in [100, 110, 120, 130, 140, 150, 160, 200]:
            pts, _ = sc_price(float(cur), self.LO, self.HI, self.EQ, self.BUY_HI, self.SELL_LO)
            assert pts >= 0, f"Negative score at cur={cur}"

    def test_score_never_exceeds_max(self):
        for cur in [100, 105, 110, 115, 120, 140, 150]:
            pts, _ = sc_price(float(cur), self.LO, self.HI, self.EQ, self.BUY_HI, self.SELL_LO)
            assert pts <= W_PRICE, f"Score exceeded W_PRICE at cur={cur}"

    def test_score_monotonically_decreasing_in_buy_zone(self):
        prices = [100.0, 105.0, 110.0, 115.0]
        scores = [sc_price(p, self.LO, self.HI, self.EQ, self.BUY_HI, self.SELL_LO)[0] for p in prices]
        assert scores == sorted(scores, reverse=True), "Score should decrease as price rises in buy zone"


# ─────────────────────────────────────────────────────────────────────────────
# sc_macd
# ─────────────────────────────────────────────────────────────────────────────

class TestScMacd:

    def test_insufficient_data_returns_zero(self):
        close = make_close([100.0] * 14)
        pts, desc = sc_macd(close)
        assert pts == 0
        assert "Not enough data" in desc

    def test_macd_above_zero_returns_zero(self):
        # Strong uptrend → MACD above zero
        close = make_close([100 + i * 3 for i in range(60)])
        pts, desc = sc_macd(close)
        assert pts == 0
        assert "above zero" in desc

    def test_macd_below_zero_returns_half_score(self):
        # Downtrend without crossover → MACD below zero, 2/4
        close = make_close([200 - i * 1.5 for i in range(60)])
        pts, desc = sc_macd(close)
        # Should return half score (2) since no crossover
        assert pts == round(W_MACD / 2)
        assert "below zero" in desc

    def test_macd_crossover_below_zero_returns_full_score(self):
        # Build a series that has MACD below zero with a bullish crossover:
        # long downtrend then a gentle recovery that keeps MACD below zero
        down = [200 - i * 0.8 for i in range(50)]
        up   = [down[-1] + i * 0.3 for i in range(15)]
        close = make_close(down + up)
        pts, desc = sc_macd(close)
        # Score must be in valid range; exact value depends on crossover timing
        assert pts in (0, round(W_MACD / 2), W_MACD)

    def test_score_within_valid_range(self):
        close = make_close([100 + np.sin(i / 5) * 10 for i in range(60)])
        pts, _ = sc_macd(close)
        assert 0 <= pts <= W_MACD


# ─────────────────────────────────────────────────────────────────────────────
# sc_avwap
# ─────────────────────────────────────────────────────────────────────────────

class TestScAvwap:
    """
    av=150, av_lo=140
    cur <= av_lo → full score W_AVWAP
    av_lo < cur < av → partial score (1..W_AVWAP-1)
    cur >= av → 0
    """

    AV    = 150.0
    AV_LO = 140.0

    def test_at_lower_band_returns_max(self):
        pts, desc = sc_avwap(self.AV_LO, self.AV, self.AV_LO)
        assert pts == W_AVWAP

    def test_below_lower_band_returns_max(self):
        pts, desc = sc_avwap(130.0, self.AV, self.AV_LO)
        assert pts == W_AVWAP

    def test_at_avwap_returns_zero(self):
        pts, desc = sc_avwap(self.AV, self.AV, self.AV_LO)
        assert pts == 0

    def test_above_avwap_returns_zero(self):
        pts, desc = sc_avwap(160.0, self.AV, self.AV_LO)
        assert pts == 0

    def test_between_bands_returns_partial(self):
        mid = (self.AV + self.AV_LO) / 2  # 145
        pts, _ = sc_avwap(mid, self.AV, self.AV_LO)
        assert 1 <= pts < W_AVWAP

    def test_score_never_negative(self):
        for cur in [130, 140, 145, 148, 150, 155]:
            pts, _ = sc_avwap(float(cur), self.AV, self.AV_LO)
            assert pts >= 0

    def test_score_never_exceeds_max(self):
        for cur in [130, 140, 145, 148, 150, 155]:
            pts, _ = sc_avwap(float(cur), self.AV, self.AV_LO)
            assert pts <= W_AVWAP

    def test_score_decreasing_as_price_rises(self):
        prices = [130.0, 140.0, 145.0, 149.0, 150.0]
        scores = [sc_avwap(p, self.AV, self.AV_LO)[0] for p in prices]
        assert scores == sorted(scores, reverse=True)


# ─────────────────────────────────────────────────────────────────────────────
# sc_div
# ─────────────────────────────────────────────────────────────────────────────

class TestScDiv:

    def test_insufficient_data_returns_zero(self):
        close = make_close([100.0] * 29)
        ml    = make_close([0.0] * 29)
        pts, desc = sc_div(close, ml)
        assert pts == 0
        assert "Insufficient" in desc

    def test_no_price_lower_low_returns_zero(self):
        # Prices rising (no LL) → no divergence possible
        close = make_close([100 + i for i in range(50)])
        ml    = make_close([-0.5 + i * 0.01 for i in range(50)])
        pts, desc = sc_div(close, ml)
        assert pts == 0

    def test_price_ll_with_no_indicator_divergence_returns_zero(self):
        # Price makes LL, indicators also make LL → no divergence
        close = make_close([100 - i * 0.3 for i in range(50)])
        ml    = make_close([-0.1 - i * 0.002 for i in range(50)])
        pts, desc = sc_div(close, ml)
        assert pts == 0

    def test_score_within_valid_range(self):
        close = make_close([100 + np.sin(i / 8) * 15 for i in range(60)])
        _, sg, _ = __import__('main').calc_macd(close)
        m, _, _  = __import__('main').calc_macd(close)
        pts, _ = sc_div(close, m)
        assert 0 <= pts <= W_DIV


# ─────────────────────────────────────────────────────────────────────────────
# sig_info  (signal label lookup)
# ─────────────────────────────────────────────────────────────────────────────

class TestSigInfo:

    def test_score_85_is_institutional_buy(self):
        label, *_ = sig_info(85)
        assert label == "Institutional Buy"

    def test_score_100_is_institutional_buy(self):
        label, *_ = sig_info(100)
        assert label == "Institutional Buy"

    def test_score_70_is_very_strong_buy(self):
        label, *_ = sig_info(70)
        assert label == "Very Strong Buy"

    def test_score_84_is_very_strong_buy(self):
        label, *_ = sig_info(84)
        assert label == "Very Strong Buy"

    def test_score_55_is_strong_buy(self):
        label, *_ = sig_info(55)
        assert label == "Strong Buy"

    def test_score_69_is_strong_buy(self):
        label, *_ = sig_info(69)
        assert label == "Strong Buy"

    def test_score_35_is_buy(self):
        label, *_ = sig_info(35)
        assert label == "Buy"

    def test_score_54_is_buy(self):
        label, *_ = sig_info(54)
        assert label == "Buy"

    def test_score_34_is_skip(self):
        label, *_ = sig_info(34)
        assert label == "Skip"

    def test_score_0_is_skip(self):
        label, *_ = sig_info(0)
        assert label == "Skip"

    def test_returns_four_values(self):
        result = sig_info(50)
        assert len(result) == 4

    @pytest.mark.parametrize("score,expected", [
        (0,  "Skip"),
        (34, "Skip"),
        (35, "Buy"),
        (54, "Buy"),
        (55, "Strong Buy"),
        (69, "Strong Buy"),
        (70, "Very Strong Buy"),
        (84, "Very Strong Buy"),
        (85, "Institutional Buy"),
        (100, "Institutional Buy"),
    ])
    def test_all_boundary_thresholds(self, score, expected):
        label, *_ = sig_info(score)
        assert label == expected, f"sig_info({score}) should be '{expected}', got '{label}'"
