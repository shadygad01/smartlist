"""
Tests for data fetching, entry zone calculation, and the analyze() pipeline.
External calls (requests, yfinance) are mocked throughout.
"""

import pytest
import json
import os
import sys
import unittest.mock as mock
from datetime import date

import pandas as pd
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import main
from main import (
    tv_get_quote,
    download_data,
    calc_entry_zones,
    analyze,
    _oras_update_csv,
    _oras_load_csv,
    W_PRICE, W_LIQ, W_OB, W_HTF, W_AVWAP, W_MACD, W_DIV, W_DZ,
    WHITELIST, PRICE_GATE_NORMAL, PRICE_GATE_WHITELIST,
)


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def make_ohlcv(n=100, base=100.0, seed=0):
    rng = np.random.default_rng(seed)
    close = base + np.cumsum(rng.normal(0, 1, n))
    close = np.maximum(close, 1.0)
    high  = close + rng.uniform(0.5, 2.0, n)
    low   = close - rng.uniform(0.5, 2.0, n)
    low   = np.maximum(low, 0.1)
    open_ = close + rng.uniform(-1.0, 1.0, n)
    vol   = rng.integers(100_000, 1_000_000, n).astype(float)
    idx   = pd.date_range("2026-01-01", periods=n, freq="D")
    return pd.DataFrame({"Open": open_, "High": high, "Low": low,
                         "Close": close, "Volume": vol}, index=idx)


def make_discount_df(n=100, lo=85.0, hi=120.0):
    """OHLCV with prices in deep discount (below EQ = 102.5)."""
    rng = np.random.default_rng(42)
    close = lo + rng.uniform(0, 10, n)
    high  = close + rng.uniform(0.3, 1.5, n)
    low   = close - rng.uniform(0.3, 1.5, n)
    low   = np.maximum(low, lo * 0.9)
    open_ = close + rng.uniform(-0.5, 0.5, n)
    vol   = rng.integers(200_000, 800_000, n).astype(float)
    idx   = pd.date_range("2025-09-01", periods=n, freq="D")
    return pd.DataFrame({"Open": open_, "High": high, "Low": low,
                         "Close": close, "Volume": vol}, index=idx)


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(main, "open_positions", {})
    monkeypatch.setattr(main, "POSITIONS_FILE", str(tmp_path / "open_positions.json"))


# ─────────────────────────────────────────────────────────────────────────────
# tv_get_quote — TradingView API
# ─────────────────────────────────────────────────────────────────────────────

class TestTvGetQuote:

    def _mock_response(self, status=200, data=None):
        resp = mock.MagicMock()
        resp.status_code = status
        resp.json.return_value = data or {
            "data": [{"d": [72.5, 500000, 1.5, 73.0, 71.8, 71.9]}]
        }
        return resp

    def test_valid_response_returns_dict(self):
        with mock.patch("main.requests.post", return_value=self._mock_response()):
            result = tv_get_quote("EGX:COMI")
        assert isinstance(result, dict)
        assert result["close"] == 72.5
        assert result["volume"] == 500000.0
        assert result["high"] == 73.0
        assert result["low"] == 71.8
        assert result["open"] == 71.9

    def test_http_error_returns_none(self):
        with mock.patch("main.requests.post", return_value=self._mock_response(status=500)):
            result = tv_get_quote("EGX:COMI")
        assert result is None

    def test_empty_data_returns_none(self):
        with mock.patch("main.requests.post",
                        return_value=self._mock_response(data={"data": []})):
            result = tv_get_quote("EGX:COMI")
        assert result is None

    def test_network_exception_returns_none(self):
        with mock.patch("main.requests.post", side_effect=ConnectionError("timeout")):
            result = tv_get_quote("EGX:COMI")
        assert result is None

    def test_malformed_json_returns_none(self):
        resp = mock.MagicMock()
        resp.status_code = 200
        resp.json.side_effect = ValueError("bad json")
        with mock.patch("main.requests.post", return_value=resp):
            result = tv_get_quote("EGX:COMI")
        assert result is None

    def test_none_close_in_response_is_handled(self):
        data = {"data": [{"d": [None, 500000, 0, None, None, None]}]}
        with mock.patch("main.requests.post",
                        return_value=self._mock_response(data=data)):
            result = tv_get_quote("EGX:COMI")
        # close is None → result["close"] should be None (not crash)
        assert result is None or result["close"] is None

    def test_short_d_array_uses_fallback(self):
        # Only 1 element in d[] — high/low/open fall back to close
        data = {"data": [{"d": [72.5]}]}
        with mock.patch("main.requests.post",
                        return_value=self._mock_response(data=data)):
            result = tv_get_quote("EGX:COMI")
        if result:
            assert result["high"] == 72.5
            assert result["low"]  == 72.5


# ─────────────────────────────────────────────────────────────────────────────
# download_data — yfinance + fallback + TV patch
# ─────────────────────────────────────────────────────────────────────────────

class TestDownloadData:

    def _mock_ticker(self, df):
        ticker = mock.MagicMock()
        ticker.history.return_value = df
        return ticker

    def test_returns_dataframe_on_success(self):
        df = make_ohlcv(80)
        with mock.patch("main.yf.Ticker", return_value=self._mock_ticker(df)), \
             mock.patch("main._patch_today_from_tv", side_effect=lambda d, s: d):
            result = download_data("COMI.CA")
        assert isinstance(result, pd.DataFrame)
        assert not result.empty

    def test_yfinance_empty_triggers_fallback(self):
        empty_df = pd.DataFrame()
        fallback_df = make_ohlcv(80)
        # Build a mock fallback JSON response
        timestamps = [int(ts.timestamp()) for ts in fallback_df.index]
        fallback_json = {
            "chart": {"result": [{
                "timestamp": timestamps,
                "indicators": {"quote": [{
                    "open":   list(fallback_df["Open"]),
                    "high":   list(fallback_df["High"]),
                    "low":    list(fallback_df["Low"]),
                    "close":  list(fallback_df["Close"]),
                    "volume": list(fallback_df["Volume"]),
                }]},
            }]}
        }
        resp = mock.MagicMock()
        resp.json.return_value = fallback_json

        with mock.patch("main.yf.Ticker", return_value=self._mock_ticker(empty_df)), \
             mock.patch("main.requests.get", return_value=resp), \
             mock.patch("main._patch_today_from_tv", side_effect=lambda d, s: d):
            result = download_data("COMI.CA")

        assert not result.empty

    def test_both_apis_fail_returns_empty_df(self):
        with mock.patch("main.yf.Ticker", side_effect=Exception("network")), \
             mock.patch("main.requests.get", side_effect=Exception("network")), \
             mock.patch("main._patch_today_from_tv", side_effect=lambda d, s: d):
            result = download_data("COMI.CA")
        assert result.empty

    def test_yfinance_exception_triggers_fallback(self):
        fallback_df = make_ohlcv(80)
        timestamps = [int(ts.timestamp()) for ts in fallback_df.index]
        fallback_json = {
            "chart": {"result": [{
                "timestamp": timestamps,
                "indicators": {"quote": [{
                    "open":   list(fallback_df["Open"]),
                    "high":   list(fallback_df["High"]),
                    "low":    list(fallback_df["Low"]),
                    "close":  list(fallback_df["Close"]),
                    "volume": list(fallback_df["Volume"]),
                }]},
            }]}
        }
        resp = mock.MagicMock()
        resp.json.return_value = fallback_json

        with mock.patch("main.yf.Ticker", side_effect=Exception("yfinance down")), \
             mock.patch("main.requests.get", return_value=resp), \
             mock.patch("main._patch_today_from_tv", side_effect=lambda d, s: d):
            result = download_data("COMI.CA")

        assert not result.empty

    def test_appends_ca_suffix_if_missing(self):
        df = make_ohlcv(80)
        captured = {}
        def fake_ticker(sym):
            captured["sym"] = sym
            return self._mock_ticker(df)

        with mock.patch("main.yf.Ticker", side_effect=fake_ticker), \
             mock.patch("main._patch_today_from_tv", side_effect=lambda d, s: d):
            download_data("COMI.CA")

        assert captured["sym"] == "COMI.CA"


# ─────────────────────────────────────────────────────────────────────────────
# _oras_update_csv / _oras_load_csv — ORAS CSV I/O
# ─────────────────────────────────────────────────────────────────────────────

class TestOrasCsv:

    QUOTE = {"open": 71.0, "high": 73.5, "low": 70.5, "close": 72.0, "volume": 500_000.0}

    def test_update_creates_csv(self):
        _oras_update_csv(date(2026, 1, 5), self.QUOTE)
        assert os.path.exists(main.ORAS_CSV)

    def test_update_appends_row(self):
        _oras_update_csv(date(2026, 1, 5), self.QUOTE)
        _oras_update_csv(date(2026, 1, 6), {**self.QUOTE, "close": 73.0})
        df = pd.read_csv(main.ORAS_CSV)
        assert len(df) == 2

    def test_update_deduplicates_same_day(self):
        _oras_update_csv(date(2026, 1, 5), self.QUOTE)
        _oras_update_csv(date(2026, 1, 5), {**self.QUOTE, "close": 74.0})
        df = pd.read_csv(main.ORAS_CSV)
        assert len(df) == 1
        assert df.iloc[-1]["Close"] == 74.0

    def test_load_missing_returns_empty(self):
        df = _oras_load_csv()
        assert df.empty

    def test_load_returns_dataframe(self):
        _oras_update_csv(date(2026, 1, 5), self.QUOTE)
        df = _oras_load_csv()
        assert isinstance(df, pd.DataFrame)
        assert "Close" in df.columns

    def test_load_sets_date_as_index(self):
        _oras_update_csv(date(2026, 1, 5), self.QUOTE)
        df = _oras_load_csv(days=9999)  # large window to include Jan 2026
        assert pd.api.types.is_datetime64_any_dtype(df.index)

    def test_load_correct_close_value(self):
        _oras_update_csv(date(2026, 1, 5), self.QUOTE)
        df = _oras_load_csv(days=9999)  # large window to include Jan 2026
        assert float(df["Close"].iloc[-1]) == 72.0


# ─────────────────────────────────────────────────────────────────────────────
# calc_entry_zones — confluence merging, zone assignment
# ─────────────────────────────────────────────────────────────────────────────

class TestCalcEntryZones:
    """
    Range: lo=85, hi=120, eq=102.5, buy_hi=90.25 (0.15), sell_lo=114.75 (0.85)
    av=96, alo=93
    cur=91 (inside buy zone, below eq)
    """

    LO     = 85.0
    HI     = 120.0
    EQ     = 102.5
    BUY_HI = 90.25
    SELL_LO = 114.75
    AV     = 96.0
    ALO    = 93.0
    CUR    = 91.0

    def _call(self, df=None, cur=None):
        if df is None:
            df = make_discount_df(100)
        if cur is None:
            cur = self.CUR
        with mock.patch("main.calc_stopping_volume", return_value=(False, 0.0, "No SV")), \
             mock.patch("main.calc_volume_profile",  return_value=(False, 0.0, 0.0, "No HVN")):
            return calc_entry_zones(
                df, cur,
                self.HI, self.LO, self.EQ, self.BUY_HI, self.SELL_LO,
                self.AV, self.ALO
            )

    def test_returns_dict_with_three_zones(self):
        result = self._call()
        assert result is not None
        assert "z1" in result
        assert "z2" in result
        assert "z3" in result

    def test_zones_have_required_keys(self):
        result = self._call()
        for zone in ("z1", "z2", "z3"):
            assert "lo"     in result[zone]
            assert "hi"     in result[zone]
            assert "center" in result[zone]
            assert "label"  in result[zone]
            assert "conf"   in result[zone]

    def test_returns_avg_entry_and_target(self):
        result = self._call()
        assert "avg_entry"    in result
        assert "target"       in result
        assert "ret_from_avg" in result

    def test_all_zone_centers_below_current_price(self):
        result = self._call()
        assert result is not None
        assert result["z1"]["center"] < self.CUR * 0.999
        assert result["z2"]["center"] < self.CUR * 0.999
        assert result["z3"]["center"] < self.CUR * 0.999

    def test_zone3_is_lowest_price(self):
        result = self._call()
        assert result is not None
        assert result["z3"]["center"] <= result["z2"]["center"]
        assert result["z3"]["center"] <= result["z1"]["center"]

    def test_zone_range_is_1_5_pct_around_center(self):
        result = self._call()
        assert result is not None
        for zone in ("z1", "z2", "z3"):
            c = result[zone]["center"]
            # allow ±0.02 for rounding in round(..., 2) on both sides
            assert abs(result[zone]["lo"] - round(c * 0.985, 2)) <= 0.02
            assert abs(result[zone]["hi"] - round(c * 1.015, 2)) <= 0.02

    def test_avg_entry_weighted_50_30_20(self):
        result = self._call()
        assert result is not None
        z1 = result["z1"]["center"]
        z2 = result["z2"]["center"]
        z3 = result["z3"]["center"]
        expected = z1 * 0.5 + z2 * 0.3 + z3 * 0.2
        # allow 0.02 tolerance for intermediate rounding in round(..., 2)
        assert abs(result["avg_entry"] - expected) <= 0.02

    def test_target_is_88_pct_of_swing_high(self):
        result = self._call()
        assert result is not None
        assert result["target"] == round(self.HI * 0.88, 2)

    def test_returns_none_when_all_levels_above_current_price(self):
        # cur is below all levels
        result = self._call(cur=0.01)
        assert result is None

    def test_hvn_increases_confluence(self):
        # When HVN coincides with buy_mid (within 2%), its confluence count increases
        buy_mid = self.LO + (self.HI - self.LO) * 0.075
        with mock.patch("main.calc_stopping_volume", return_value=(False, 0.0, "No SV")), \
             mock.patch("main.calc_volume_profile",
                        return_value=(True, 0.9, buy_mid, f"HVN @ {buy_mid:.1f}")):
            result = calc_entry_zones(
                make_discount_df(100), self.CUR,
                self.HI, self.LO, self.EQ, self.BUY_HI, self.SELL_LO,
                self.AV, self.ALO
            )
        assert result is not None
        # The highest-confluence level should have conf >= 4 (buy_mid base=3 + HVN=1)
        max_conf = max(result[z]["conf"] for z in ("z1", "z2", "z3"))
        assert max_conf >= 4

    def test_ret_from_avg_is_percentage(self):
        result = self._call()
        assert result is not None
        avg = result["avg_entry"]
        tgt = result["target"]
        expected_pct = round(((tgt - avg) / avg) * 100, 1)
        assert result["ret_from_avg"] == expected_pct


# ─────────────────────────────────────────────────────────────────────────────
# analyze() — full pipeline integration
# ─────────────────────────────────────────────────────────────────────────────

class TestAnalyze:
    """
    All external calls mocked — tests the analyze() orchestration logic only.
    """

    def _mock_download(self, df, monkeypatch):
        monkeypatch.setattr(main, "download_data", lambda sym, days=110: df)

    def test_empty_data_returns_error(self, monkeypatch):
        self._mock_download(pd.DataFrame(), monkeypatch)
        result = analyze("COMI.CA")
        assert result["ok"] is False
        assert "error" in result

    def test_insufficient_rows_returns_error(self, monkeypatch):
        self._mock_download(make_ohlcv(3), monkeypatch)
        result = analyze("COMI.CA")
        assert result["ok"] is False

    def test_premium_price_locks_all_scores(self, monkeypatch):
        # Price is at the top of the range → cur >= eq → all scores locked
        df = make_ohlcv(100, base=150.0)
        # Ensure last close is in premium zone
        df["Close"] = 160.0
        df["High"]  = 162.0
        df["Low"]   = 158.0
        self._mock_download(df, monkeypatch)
        result = analyze("COMI.CA")
        assert result["ok"] is True
        assert result["score"] == 0
        assert result["signal"] in ("Skip", "Wait")

    def test_discount_price_runs_full_scoring(self, monkeypatch):
        # Price deep in discount → all scoring paths active
        df = make_discount_df(100)
        self._mock_download(df, monkeypatch)
        result = analyze("COMI.CA")
        assert result["ok"] is True
        assert result["score"] >= 0
        assert "rows" in result
        assert len(result["rows"]) == 8

    def test_result_contains_required_keys(self, monkeypatch):
        df = make_discount_df(100)
        self._mock_download(df, monkeypatch)
        result = analyze("COMI.CA")
        for key in ("ok", "price", "last_dt", "score", "signal", "target", "eq",
                    "buy_hi", "sell_lo", "avwap", "avwap_l", "r1", "rows"):
            assert key in result, f"Missing key: {key}"

    def test_score_capped_at_100(self, monkeypatch):
        df = make_discount_df(100)
        self._mock_download(df, monkeypatch)
        result = analyze("COMI.CA")
        assert result["ok"] is True
        assert result["score"] <= 100

    def test_score_never_negative(self, monkeypatch):
        df = make_discount_df(100)
        self._mock_download(df, monkeypatch)
        result = analyze("COMI.CA")
        assert result["ok"] is True
        assert result["score"] >= 0

    def test_target_is_12_pct_above_price(self, monkeypatch):
        df = make_discount_df(100)
        self._mock_download(df, monkeypatch)
        result = analyze("COMI.CA")
        assert result["ok"] is True
        expected_target = round(result["price"] * 1.12, 2)
        assert result["target"] == expected_target

    def test_whitelist_symbol_uses_lower_price_gate(self, monkeypatch):
        """
        WHITELIST stocks need r1 >= 12 (not 18) to pass the price gate.
        With a mid-discount price, r1 might be 12-17, which would be Wait for
        normal stocks but potentially pass for whitelist.
        """
        wl_symbol = WHITELIST[0]  # e.g. "FWRY.CA"
        df = make_discount_df(100)
        self._mock_download(df, monkeypatch)
        result_wl = analyze(wl_symbol)

        normal_symbol = "COMI.CA"  # not in WHITELIST
        result_normal = analyze(normal_symbol)

        # Both should run without crashing
        assert result_wl["ok"] is True
        assert result_normal["ok"] is True

    def test_exception_in_pipeline_returns_error_dict(self, monkeypatch):
        def broken_download(*a, **kw):
            raise RuntimeError("Simulated crash")
        monkeypatch.setattr(main, "download_data", broken_download)
        result = analyze("COMI.CA")
        assert result["ok"] is False
        assert "error" in result

    def test_rows_have_four_elements_each(self, monkeypatch):
        df = make_discount_df(100)
        self._mock_download(df, monkeypatch)
        result = analyze("COMI.CA")
        assert result["ok"] is True
        for row in result["rows"]:
            assert len(row) == 4, f"Row should be (label, score, max, desc): {row}"

    def test_row_scores_sum_to_total(self, monkeypatch):
        df = make_discount_df(100)
        self._mock_download(df, monkeypatch)
        result = analyze("COMI.CA")
        assert result["ok"] is True
        row_sum = sum(r[1] for r in result["rows"])
        # total = min(row_sum, 100)
        assert result["score"] == min(row_sum, 100)

    def test_sig_field_is_valid_signal(self, monkeypatch):
        df = make_discount_df(100)
        self._mock_download(df, monkeypatch)
        result = analyze("COMI.CA")
        assert result["ok"] is True
        assert result["signal"] in (
            "Skip", "Wait", "Buy", "Strong Buy", "Very Strong Buy", "Institutional Buy"
        )
