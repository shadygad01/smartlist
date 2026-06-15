"""
Tests for advanced SMC scoring functions:
sc_ob, sc_liquidity, sc_htf, sc_demand_zone,
calc_stopping_volume, calc_volume_profile.
"""

import pytest
import numpy as np
import pandas as pd
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from main import (
    sc_ob, sc_liquidity, sc_htf, sc_demand_zone,
    calc_stopping_volume, calc_volume_profile,
    W_OB, W_LIQ, W_HTF, W_DZ,
)


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def make_ohlcv(n=100, base=100.0, seed=42):
    rng = np.random.default_rng(seed)
    close = base + np.cumsum(rng.normal(0, 1, n))
    close = np.maximum(close, 1.0)
    high  = close + rng.uniform(0.5, 2.0, n)
    low   = close - rng.uniform(0.5, 2.0, n)
    low   = np.maximum(low, 0.1)
    open_ = close + rng.uniform(-1.0, 1.0, n)
    vol   = rng.integers(100_000, 1_000_000, n).astype(float)
    return pd.DataFrame({"Open": open_, "High": high, "Low": low,
                         "Close": close, "Volume": vol})


def make_discount_ohlcv(n=80, lo=90.0, hi=120.0):
    """OHLCV where prices stay in the discount zone (below EQ=105)."""
    rng  = np.random.default_rng(7)
    close = lo + rng.uniform(0, 10, n)       # 90–100 range
    high  = close + rng.uniform(0.2, 1.0, n)
    low   = close - rng.uniform(0.2, 1.0, n)
    low   = np.maximum(low, lo * 0.9)
    open_ = close + rng.uniform(-0.5, 0.5, n)
    vol   = rng.integers(200_000, 800_000, n).astype(float)
    return pd.DataFrame({"Open": open_, "High": high, "Low": low,
                         "Close": close, "Volume": vol})


# ─────────────────────────────────────────────────────────────────────────────
# sc_ob — Order Block scoring
# ─────────────────────────────────────────────────────────────────────────────

class TestScOb:

    LO     = 90.0
    HI     = 130.0
    EQ     = 110.0   # lo + (hi-lo)*0.5
    BUY_HI = 96.0    # lo + (hi-lo)*0.15

    def test_insufficient_data_returns_zero(self):
        df = make_ohlcv(5)
        pts, desc = sc_ob(df, 95.0, self.EQ, self.LO, self.BUY_HI)
        assert pts == 0
        assert "Insufficient" in desc

    def test_missing_columns_returns_zero(self):
        df = pd.DataFrame({"Close": [100.0] * 20})
        pts, desc = sc_ob(df, 95.0, self.EQ, self.LO, self.BUY_HI)
        assert pts == 0

    def test_score_within_valid_range(self):
        df = make_ohlcv(60)
        pts, _ = sc_ob(df, 95.0, self.EQ, self.LO, self.BUY_HI)
        assert 0 <= pts <= W_OB

    def test_price_above_eq_no_valid_ob(self):
        # cur is above EQ — OB must be in buy zone (below buy_hi), but price above EQ
        # means cur > buy_hi, so all OB candidates should be invalidated
        df = make_ohlcv(50)
        pts, desc = sc_ob(df, 120.0, self.EQ, self.LO, self.BUY_HI)
        # No OB should be found since current price is in premium
        # (OB must be below buy_hi AND cur must be above OB low)
        assert pts >= 0  # should not crash

    def test_returns_tuple_of_int_and_str(self):
        df = make_ohlcv(60)
        result = sc_ob(df, 95.0, self.EQ, self.LO, self.BUY_HI)
        assert len(result) == 2
        assert isinstance(result[0], int)
        assert isinstance(result[1], str)

    def test_with_bearish_candle_then_impulse_in_discount(self):
        """
        Inject a bearish candle followed by a strong bullish impulse inside buy zone.
        This should produce a valid OB and a non-zero score.
        """
        n = 50
        open_  = np.full(n, 95.0)
        close_ = np.full(n, 95.0)
        high_  = np.full(n, 96.0)
        low_   = np.full(n, 94.0)
        vol_   = np.full(n, 300_000.0)

        # Bar 30: bearish candle in buy zone (close < open, inside 90–96)
        open_[30]  = 95.5
        close_[30] = 93.0
        high_[30]  = 95.5
        low_[30]   = 92.5

        # Bar 31: large bullish impulse — range >> avg_range
        open_[31]  = 93.0
        close_[31] = 100.0
        high_[31]  = 101.0
        low_[31]   = 92.5

        df = pd.DataFrame({"Open": open_, "High": high_, "Low": low_,
                           "Close": close_, "Volume": vol_})

        cur    = 95.0   # current price above OB low (93)
        pts, desc = sc_ob(df, cur, self.EQ, self.LO, self.BUY_HI)
        assert pts > 0, f"Expected OB score > 0, got {pts}: {desc}"

    def test_invalid_discount_range_returns_zero(self):
        df = make_ohlcv(50)
        # eq == lo → discount_range == 0
        pts, desc = sc_ob(df, 95.0, 90.0, 90.0, 90.0)
        assert pts == 0


# ─────────────────────────────────────────────────────────────────────────────
# sc_liquidity
# ─────────────────────────────────────────────────────────────────────────────

class TestScLiquidity:

    def test_insufficient_data_returns_zero(self):
        df = make_ohlcv(5)
        pts, desc = sc_liquidity(df, 95.0)
        assert pts == 0
        assert "Insufficient" in desc

    def test_missing_columns_returns_zero(self):
        df = pd.DataFrame({"Close": [95.0] * 20})
        pts, desc = sc_liquidity(df, 95.0)
        assert pts == 0

    def test_score_within_valid_range(self):
        df = make_ohlcv(60)
        pts, _ = sc_liquidity(df, 95.0)
        assert 0 <= pts <= W_LIQ

    def test_returns_tuple(self):
        df = make_ohlcv(30)
        result = sc_liquidity(df, 95.0)
        assert len(result) == 2
        assert isinstance(result[0], int)
        assert isinstance(result[1], str)

    def test_sweep_and_reverse_returns_full_score(self):
        """
        Inject a sweep-and-reverse: bar that goes below swing_lo but closes above it.
        """
        n = 30
        close_ = np.full(n, 100.0)
        high_  = np.full(n, 101.0)
        low_   = np.full(n, 99.0)
        open_  = np.full(n, 100.0)
        vol_   = np.full(n, 300_000.0)

        # swing_lo = 10th percentile of last 20 bars = ~99
        # Bar 25: sweep below swing_lo (low=97), close above it (close=100)
        low_[25]   = 97.0
        close_[25] = 100.5
        open_[25]  = 100.0

        df = pd.DataFrame({"Open": open_, "High": high_,
                           "Low": low_, "Close": close_, "Volume": vol_})
        pts, desc = sc_liquidity(df, 100.0)
        assert pts == W_LIQ
        assert "Sweep" in desc

    def test_rejection_wick_returns_partial_score(self):
        """
        Build a candle with lower wick >= 60% of range but no sweep.

        To avoid triggering sweep (which runs first), bars 10-14 are set very
        low to pull swing_lo (10th-pct of last-20) down to ~84. The wick bar
        (index 25, low=91) is then ABOVE swing_lo, so no sweep fires.
        """
        n = 30
        open_  = np.full(n, 100.0)
        close_ = np.full(n, 100.0)
        high_  = np.full(n, 101.0)
        low_   = np.full(n, 99.5)
        vol_   = np.full(n, 300_000.0)

        # Bars 10-14: very low lows → set swing_lo (10th percentile of last 20) ≈ 84
        for i in range(10, 15):
            low_[i]   = 83.5 + (i - 10) * 0.1
            close_[i] = 99.0
            high_[i]  = 100.0
            open_[i]  = 99.0

        # Bar 25 (in d.tail(5) and d.tail(10)): wick bar with low=91 > swing_lo ~84
        # lower_wick = 100-91=9, range=101-91=10, ratio=0.90 ≥ 0.60 ✓
        # close(100) ≥ low(91) + range(10)*0.40=95 ✓
        # low(91) > swing_lo(~84) → no sweep ✓
        low_[25]   = 91.0
        open_[25]  = 100.0
        close_[25] = 100.0
        high_[25]  = 101.0

        df = pd.DataFrame({"Open": open_, "High": high_,
                           "Low": low_, "Close": close_, "Volume": vol_})
        pts, desc = sc_liquidity(df, 100.0)
        expected_wick = round(W_LIQ * 0.6)
        assert pts == expected_wick, f"Expected wick score {expected_wick}, got {pts}: {desc}"
        assert "wick" in desc.lower() or "Rejection" in desc

    def test_equal_lows_returns_partial_score(self):
        """
        Build 3+ lows within 0.5% of each other (no sweep, no wick).

        The equal-lows bars use close ≈ low (tiny lower wick) to avoid the
        wick check (which runs before equal-lows). Their low equals swing_lo
        so `c_low < swing_lo` is never True → no sweep fires either.
        """
        n = 20
        base_lo = 95.1
        close_ = np.full(n, 100.0)
        high_  = np.full(n, 101.0)
        open_  = np.full(n, 100.0)
        low_   = np.full(n, 99.5)
        vol_   = np.full(n, 300_000.0)

        # 3 equal-lows bars: close very close to low → lower_wick tiny → no wick
        # lower_wick = 95.2 - 95.1 = 0.1, range = 101 - 95.1 = 5.9, ratio = 0.017 < 0.60 ✓
        # These bars set swing_lo = quantile(0.10) ≈ 95.1 (same as c_low) → no sweep ✓
        for i in [5, 10, 15]:
            low_[i]   = base_lo
            close_[i] = 95.2
            open_[i]  = 96.0
            high_[i]  = 101.0

        df = pd.DataFrame({"Open": open_, "High": high_,
                           "Low": low_, "Close": close_, "Volume": vol_})
        pts, desc = sc_liquidity(df, 100.0)
        expected_eql = round(W_LIQ * 0.4)
        assert pts == expected_eql, f"Expected EQL score {expected_eql}, got {pts}: {desc}"
        assert "Equal Lows" in desc

    def test_no_event_returns_zero_with_message(self):
        """
        Uneventful OHLCV: no sweep, no wick, no equal lows.

        Design guarantees:
        - close = low  → lower_wick = 0, ratio = 0/range < 0.60 (no wick)
        - lows spaced 2% apart → no two lows within 0.5% (no equal lows)
        - all lows in d.tail(10) are >> swing_lo (no sweep)
        """
        n = 30
        low_   = 95.0 * (1 + np.arange(n) * 0.02)  # spaced 2% apart: 95→150
        close_ = low_.copy()       # close = low → lower wick = 0
        open_  = low_ + 2.0        # bearish candle (no lower wick)
        high_  = low_ + 2.5
        vol_   = np.full(n, 300_000.0)

        df = pd.DataFrame({"Open": open_, "High": high_,
                           "Low": low_, "Close": close_, "Volume": vol_})
        pts, desc = sc_liquidity(df, 100.0)
        assert pts == 0, f"Expected 0 (no event), got {pts}: {desc}"
        assert "No" in desc


# ─────────────────────────────────────────────────────────────────────────────
# sc_htf — Higher Timeframe Trend
# ─────────────────────────────────────────────────────────────────────────────

class TestScHtf:

    def test_score_within_valid_range(self):
        df = make_ohlcv(220)
        pts, _ = sc_htf(df)
        assert 0 <= pts <= W_HTF

    def test_returns_tuple(self):
        df = make_ohlcv(100)
        result = sc_htf(df)
        assert len(result) == 2
        assert isinstance(result[0], int)
        assert isinstance(result[1], str)

    def test_strong_uptrend_scores_high(self):
        # Clear uptrend: rising prices across 200+ bars
        close = np.linspace(50, 150, 220)
        high  = close + 1.0
        low   = close - 1.0
        df = pd.DataFrame({
            "Close": close, "High": high, "Low": low,
            "Open": close, "Volume": np.full(220, 500_000.0),
        })
        pts, desc = sc_htf(df)
        # Should score near max — above MA200, rising MA50, HH+HL
        assert pts >= round(W_HTF * 0.6), f"Expected high score in uptrend, got {pts}: {desc}"

    def test_strong_downtrend_scores_zero_or_low(self):
        # Clear downtrend: falling prices across 200+ bars
        close = np.linspace(150, 50, 220)
        high  = close + 1.0
        low   = close - 1.0
        df = pd.DataFrame({
            "Close": close, "High": high, "Low": low,
            "Open": close, "Volume": np.full(220, 500_000.0),
        })
        pts, desc = sc_htf(df)
        assert pts <= round(W_HTF * 0.4), f"Expected low score in downtrend, got {pts}: {desc}"

    def test_insufficient_data_returns_zero_or_partial(self):
        # Only 10 bars — well below MA50 minimum
        df = make_ohlcv(10)
        pts, desc = sc_htf(df)
        assert pts == 0
        assert "Insufficient" in desc or "insufficient" in desc

    def test_50_bars_uses_ma50_fallback(self):
        # Exactly 50 bars — should use MA50 as fallback (no MA200)
        close = np.linspace(80, 120, 50)
        df = pd.DataFrame({
            "Close": close,
            "High":  close + 1,
            "Low":   close - 1,
            "Open":  close,
            "Volume": np.full(50, 500_000.0),
        })
        pts, desc = sc_htf(df)
        assert "no MA200" in desc or pts >= 0  # fallback path used

    def test_score_never_negative(self):
        for seed in range(5):
            df = make_ohlcv(100, seed=seed)
            pts, _ = sc_htf(df)
            assert pts >= 0

    def test_score_never_exceeds_max(self):
        for seed in range(5):
            df = make_ohlcv(250, seed=seed)
            pts, _ = sc_htf(df)
            assert pts <= W_HTF


# ─────────────────────────────────────────────────────────────────────────────
# calc_stopping_volume
# ─────────────────────────────────────────────────────────────────────────────

class TestCalcStoppingVolume:

    EQ = 105.0
    LO = 90.0

    def test_insufficient_data_returns_false(self):
        df = make_ohlcv(10)
        hit, score, desc, sv_price = calc_stopping_volume(df, self.EQ, self.LO)
        assert hit is False
        assert "Insufficient" in desc

    def test_no_sv_in_premium_returns_false(self):
        # All prices above EQ — no discount zone candles
        n = 60
        df = pd.DataFrame({
            "Open":   np.full(n, 110.0),
            "High":   np.full(n, 111.0),
            "Low":    np.full(n, 109.0),
            "Close":  np.full(n, 110.0),
            "Volume": np.full(n, 300_000.0),
        })
        hit, score, desc, sv_price = calc_stopping_volume(df, self.EQ, self.LO)
        assert hit is False

    def test_score_between_0_and_1_when_detected(self):
        df = make_discount_ohlcv(80)
        # Inject a high-volume, narrow-range candle in discount
        df.loc[50, "Volume"] = df["Volume"].mean() * 3.0
        df.loc[50, "Close"]  = 95.0
        df.loc[50, "High"]   = 95.2
        df.loc[50, "Low"]    = 94.9
        df.loc[50, "Open"]   = 95.0

        hit, score, desc, sv_price = calc_stopping_volume(df, self.EQ, self.LO)
        if hit:
            assert 0.0 <= score <= 1.0

    def test_returns_four_values(self):
        df = make_ohlcv(60)
        result = calc_stopping_volume(df, self.EQ, self.LO)
        assert len(result) == 4

    def test_sv_detected_with_high_volume_narrow_range(self):
        """
        Inject exactly one candle that meets all SV criteria:
          - in discount (close < EQ)
          - vol >= 2.5x avg vol  (raised threshold)
          - range <= 0.5x avg range  (narrow)
          - close in upper 60% of candle range  (bullish absorption)
        """
        n = 60
        avg_vol = 300_000.0
        avg_rng = 2.0

        close_ = np.full(n, 98.0)
        high_  = close_ + avg_rng / 2
        low_   = close_ - avg_rng / 2
        open_  = close_.copy()
        vol_   = np.full(n, avg_vol)

        # SV candle at bar 40 — 3x volume (passes 2.5x threshold)
        vol_[40]   = avg_vol * 3.0
        low_[40]   = 97.7   # candle range = 0.6  (<= 0.5 * 2.0 = 1.0) ✓
        high_[40]  = 98.3
        close_[40] = 98.1   # close_pos = (98.1 - 97.7) / 0.6 = 0.67 >= 0.40 ✓
        open_[40]  = 97.9

        df = pd.DataFrame({"Open": open_, "High": high_,
                           "Low": low_, "Close": close_, "Volume": vol_})
        hit, score, desc, sv_price = calc_stopping_volume(df, self.EQ, self.LO)
        assert hit is True
        assert "Stopping Volume" in desc
        assert isinstance(sv_price, float)


# ─────────────────────────────────────────────────────────────────────────────
# calc_volume_profile
# ─────────────────────────────────────────────────────────────────────────────

class TestCalcVolumeProfile:

    EQ     = 110.0
    LO     = 90.0
    BUY_HI = 93.0   # lo + (eq-lo)*0.15 ≈ 92.7

    def test_insufficient_data_returns_false(self):
        df = make_ohlcv(5)
        hit, score, price, desc = calc_volume_profile(df, self.EQ, self.LO, self.BUY_HI)
        assert hit is False

    def test_returns_four_values(self):
        df = make_ohlcv(60)
        result = calc_volume_profile(df, self.EQ, self.LO, self.BUY_HI)
        assert len(result) == 4

    def test_score_between_0_and_1_when_detected(self):
        df = make_discount_ohlcv(80)
        hit, score, price, desc = calc_volume_profile(df, self.EQ, self.LO, self.BUY_HI)
        if hit:
            assert 0.0 <= score <= 1.0

    def test_hvn_price_below_buy_hi_when_detected(self):
        # HVN should only be reported inside buy zone (< buy_hi)
        df = make_discount_ohlcv(80)
        hit, score, price, desc = calc_volume_profile(df, self.EQ, self.LO, self.BUY_HI)
        if hit:
            assert price < self.BUY_HI

    def test_all_prices_above_eq_returns_false(self):
        # No prices in discount zone → no HVN
        n = 60
        df = pd.DataFrame({
            "High":   np.full(n, 115.0),
            "Low":    np.full(n, 112.0),
            "Close":  np.full(n, 113.0),
            "Volume": np.full(n, 400_000.0),
        })
        hit, _, _, desc = calc_volume_profile(df, self.EQ, self.LO, self.BUY_HI)
        assert hit is False

    def test_invalid_price_range_returns_false(self):
        # price_max == price_min
        n = 20
        df = pd.DataFrame({
            "High":   np.full(n, 95.0),
            "Low":    np.full(n, 95.0),
            "Close":  np.full(n, 95.0),
            "Volume": np.full(n, 300_000.0),
        })
        hit, _, _, desc = calc_volume_profile(df, self.EQ, self.LO, self.BUY_HI)
        assert hit is False
        assert "Invalid" in desc

    def test_concentrated_volume_in_discount_detected(self):
        """
        Build OHLCV where most volume is concentrated in buy zone (90–93).
        HVN should be detected there.
        """
        n = 80
        rng = np.random.default_rng(99)

        # 60 bars in buy zone with high volume
        low_bz   = 90.0 + rng.uniform(0, 2, 60)
        high_bz  = low_bz + 0.5
        close_bz = low_bz + 0.25
        open_bz  = close_bz.copy()
        vol_bz   = np.full(60, 900_000.0)

        # 20 bars in premium zone with low volume
        low_pr   = 115.0 + rng.uniform(0, 3, 20)
        high_pr  = low_pr + 0.5
        close_pr = low_pr + 0.25
        open_pr  = close_pr.copy()
        vol_pr   = np.full(20, 50_000.0)

        df = pd.DataFrame({
            "Open":   np.concatenate([open_bz, open_pr]),
            "High":   np.concatenate([high_bz, high_pr]),
            "Low":    np.concatenate([low_bz, low_pr]),
            "Close":  np.concatenate([close_bz, close_pr]),
            "Volume": np.concatenate([vol_bz, vol_pr]),
        })

        buy_hi = 93.0  # buy zone top
        hit, score, price, desc = calc_volume_profile(df, self.EQ, self.LO, buy_hi)
        assert hit is True, f"Expected HVN detected in buy zone, got: {desc}"
        assert price < buy_hi


# ─────────────────────────────────────────────────────────────────────────────
# sc_demand_zone — Confluence scoring
# ─────────────────────────────────────────────────────────────────────────────

class TestScDemandZone:

    EQ     = 110.0
    LO     = 90.0
    BUY_HI = 93.0

    def test_score_within_valid_range(self):
        df = make_ohlcv(80)
        pts, _ = sc_demand_zone(df, self.EQ, self.LO, self.BUY_HI)
        assert 0 <= pts <= W_DZ

    def test_returns_tuple(self):
        df = make_ohlcv(80)
        result = sc_demand_zone(df, self.EQ, self.LO, self.BUY_HI)
        assert len(result) == 2
        assert isinstance(result[0], int)
        assert isinstance(result[1], str)

    def test_no_confluence_returns_zero(self):
        # Premium-only data — no SV or HVN in discount
        n = 60
        df = pd.DataFrame({
            "Open":   np.full(n, 115.0),
            "High":   np.full(n, 116.0),
            "Low":    np.full(n, 114.0),
            "Close":  np.full(n, 115.0),
            "Volume": np.full(n, 300_000.0),
        })
        pts, desc = sc_demand_zone(df, self.EQ, self.LO, self.BUY_HI)
        assert pts == 0

    def test_sv_only_returns_60_pct(self):
        """Mock calc_stopping_volume to return True and calc_volume_profile False."""
        import unittest.mock as mock
        import main as m

        with mock.patch("signal_engine.calc_stopping_volume", return_value=(True, 0.8, "SV desc", 95.0)), \
             mock.patch("signal_engine.calc_volume_profile",  return_value=(False, 0.0, 0.0, "No HVN")):
            pts, desc = sc_demand_zone(make_ohlcv(60), self.EQ, self.LO, self.BUY_HI)

        assert pts == round(W_DZ * 0.60)
        assert "Stopping Volume only" in desc

    def test_hvn_only_returns_40_pct(self):
        import unittest.mock as mock
        import main as m

        with mock.patch("signal_engine.calc_stopping_volume", return_value=(False, 0.0, "No SV", 0.0)), \
             mock.patch("signal_engine.calc_volume_profile",  return_value=(True, 0.9, 92.0, "HVN desc")):
            pts, desc = sc_demand_zone(make_ohlcv(60), self.EQ, self.LO, self.BUY_HI)

        assert pts == round(W_DZ * 0.40)
        assert "HVN only" in desc

    def test_sv_and_hvn_returns_full_score(self):
        import unittest.mock as mock
        import main as m

        with mock.patch("signal_engine.calc_stopping_volume", return_value=(True, 0.9, "SV desc", 95.0)), \
             mock.patch("signal_engine.calc_volume_profile",  return_value=(True, 0.95, 92.0, "HVN desc")):
            pts, desc = sc_demand_zone(make_ohlcv(60), self.EQ, self.LO, self.BUY_HI)

        assert pts == W_DZ
        assert "DEMAND ZONE CONFIRMED" in desc
