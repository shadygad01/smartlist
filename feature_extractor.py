"""
Feature Extractor — EGX Bottom Pattern Research
================================================
يحسب features تقنية من OHLCV التاريخية لكل إشارة دخول.
يُستدعى أثناء الـ backfill وأثناء تسجيل إشارات جديدة.

الفئات:
1. Structure     — بنية السوق (BOS, Swing Lows, Dealing Range)
2. Liquidity     — السيولة والاستهداف (Sweeps, Equal Lows, Accumulation)
3. Exhaustion    — استنفاد الزخم (ATR Compression, Consecutive Reds, Distance Lows)
4. Institutional — المؤسسي (VWAP Distance)
5. Market Context— سياق السوق (EGX30 Relative Strength)
6. Snap Recompute— إعادة حساب snap_* للـ backfilled signals
"""

import numpy as np
import pandas as pd
from typing import Optional

# ── Feature columns added to signals table (for _migrate_schema) ─────────────
FEAT_COLS_SCHEMA = {
    # Structure
    "feat_dist_swing_low":       "REAL",
    "feat_dealing_range_pos":    "REAL",
    "feat_candles_since_bos":    "INTEGER",
    "feat_dist_last_bos":        "REAL",
    # Liquidity
    "feat_sweep_depth_pct":      "REAL",
    "feat_equal_lows_count":     "INTEGER",
    "feat_vol_spike_ratio":      "REAL",
    "feat_candles_since_sweep":  "INTEGER",
    "feat_accumulation_score":   "REAL",
    # Exhaustion
    "feat_consec_red":           "INTEGER",
    "feat_down_days_pct":        "REAL",
    "feat_atr_compression":      "REAL",
    "feat_vol_contraction":      "REAL",
    "feat_dist_20d_low":         "REAL",
    "feat_dist_50d_low":         "REAL",
    "feat_dist_52w_low":         "REAL",
    # Institutional
    "feat_vwap_dist":            "REAL",
    # Market Context
    "feat_rs_vs_egx30":          "REAL",
    "feat_egx30_trend_val":      "REAL",
}

# snap_* columns we recompute from OHLCV for backfilled signals
SNAP_RECOMPUTE = [
    "snap_atr", "snap_wick_ratio", "snap_compression", "snap_consol_len",
    "snap_bos", "snap_choch", "snap_pivot_str", "snap_num_touches",
    "snap_sweep_size", "snap_vol_exp", "snap_dist_lo", "snap_prem_disc",
    "snap_reclaim_spd",
]

# All feature cols for ML (feat_* + snap_*)
ALL_EXTRACTED_COLS = list(FEAT_COLS_SCHEMA.keys()) + SNAP_RECOMPUTE

ATR_PERIOD     = 14
SWING_LOOKBACK = 40
BOS_LOOKBACK   = 60
SWEEP_LOOKBACK = 30
ACCUM_BARS     = 15
RANGE_BARS     = 20


# ── Helpers ───────────────────────────────────────────────────────────────────

def _safe_atr(highs: np.ndarray, lows: np.ndarray, closes: np.ndarray,
              period: int = ATR_PERIOD) -> float:
    """Average True Range — safe for short arrays."""
    if len(highs) < 2:
        return float(np.mean(highs - lows)) if len(highs) > 0 else 0.0
    tr = np.maximum(
        highs[1:] - lows[1:],
        np.maximum(np.abs(highs[1:] - closes[:-1]),
                   np.abs(lows[1:]  - closes[:-1]))
    )
    return float(np.mean(tr[-period:])) if len(tr) >= period else float(np.mean(tr))


def _pivot_lows(lows: np.ndarray, window: int = 3) -> list:
    """Returns list of (idx, value) for pivot lows."""
    result = []
    for i in range(window, len(lows) - window):
        segment = lows[max(0, i - window): i + window + 1]
        if float(lows[i]) == float(np.min(segment)):
            result.append((i, float(lows[i])))
    return result


# ── Main entry point ──────────────────────────────────────────────────────────

def compute_entry_features(
    sig: dict,
    df: pd.DataFrame,
    egx30_df: Optional[pd.DataFrame] = None,
) -> dict:
    """
    Computes all entry features for a signal from historical OHLCV.

    Args:
        sig:       signal dict with at least 'signal_date', 'price'
        df:        OHLCV DataFrame (tz-naive DatetimeIndex), covering history
                   before (and including) signal_date
        egx30_df:  optional EGX30 OHLCV for relative-strength features

    Returns:
        dict of feature_name -> value  (None when insufficient data)
    """
    signal_date = sig.get("signal_date", "")
    entry_price = float(sig.get("price", 0) or 0)
    if not entry_price or not signal_date:
        return {}

    sig_ts = pd.Timestamp(signal_date)
    pre    = df[df.index <= sig_ts].copy()
    if len(pre) < 20:
        return {}

    closes  = pre["Close"].values.astype(float)
    highs   = pre["High"].values.astype(float)
    lows    = pre["Low"].values.astype(float)
    opens   = pre["Open"].values.astype(float)  if "Open"   in pre.columns else closes.copy()
    volumes = pre["Volume"].values.astype(float) if "Volume" in pre.columns else None
    n       = len(closes)
    out: dict = {}

    # ── 1. Structure ─────────────────────────────────────────────────────────

    # Distance to last swing low (% below entry price)
    sw      = min(SWING_LOOKBACK, n)
    pivots  = _pivot_lows(lows[-sw:], window=3)
    last_pl = pivots[-1][1] if pivots else float(np.min(lows[-sw:]))
    out["feat_dist_swing_low"] = round((entry_price - last_pl) / entry_price, 4)

    # Dealing range position: 0 = at range low, 1 = at range high (20-bar)
    rb     = min(RANGE_BARS, n)
    rng_hi = float(np.max(highs[-rb:]))
    rng_lo = float(np.min(lows[-rb:]))
    span   = rng_hi - rng_lo
    out["feat_dealing_range_pos"] = round((entry_price - rng_lo) / span, 4) if span > 0 else 0.5

    # BOS: last candle where close crossed above 20-bar rolling max (bullish structure break)
    bos_bars = min(BOS_LOOKBACK, n)
    c_sl     = closes[-bos_bars:]
    rm20     = pd.Series(c_sl).rolling(20, min_periods=20).max().values
    csbos    = None
    dlbos    = None
    for i in range(len(c_sl) - 1, 1, -1):
        prev_rm = rm20[i - 1]
        if prev_rm is not None and not np.isnan(float(prev_rm)):
            if float(c_sl[i]) > float(prev_rm):
                csbos = len(c_sl) - i
                dlbos = round((entry_price - float(prev_rm)) / entry_price, 4)
                break
    out["feat_candles_since_bos"] = csbos
    out["feat_dist_last_bos"]     = dlbos

    # ── 2. Liquidity ─────────────────────────────────────────────────────────

    # Sweep depth: how far below prev 10-day low did entry day go
    prev_lo10 = float(np.min(lows[-11:-1])) if n >= 11 else float(np.min(lows[:-1]))
    entry_lo  = float(lows[-1])
    out["feat_sweep_depth_pct"] = round((prev_lo10 - entry_lo) / prev_lo10, 4) if prev_lo10 > 0 else 0.0

    # Equal lows: count lows within ±0.8% of entry price in last 30 bars (excluding entry)
    eq_bars = min(30, n - 1)
    tol     = entry_price * 0.008
    out["feat_equal_lows_count"] = int(np.sum(np.abs(lows[-eq_bars - 1:-1] - entry_price) <= tol))

    # Volume spike ratio: max(vol[-5:]) / mean(vol[-20:])
    if volumes is not None and n >= 20:
        va = float(np.mean(volumes[-20:]))
        vm = float(np.max(volumes[-min(5, n):])) if n >= 5 else va
        out["feat_vol_spike_ratio"] = round(vm / va, 3) if va > 0 else 1.0
    else:
        out["feat_vol_spike_ratio"] = None

    # Candles since last liquidity sweep (low < prev 10d low)
    sw_sl = lows[-min(SWEEP_LOOKBACK, n):]
    csw   = None
    for j in range(len(sw_sl) - 2, 9, -1):
        p10lo = float(np.min(sw_sl[max(0, j - 10):j]))
        if float(sw_sl[j]) < p10lo:
            csw = len(sw_sl) - 1 - j
            break
    out["feat_candles_since_sweep"] = csw

    # Accumulation score (0–10): declining volume + inside bars + range compression
    accum = 0.0
    if volumes is not None and n >= ACCUM_BARS + 5:
        av = volumes[-ACCUM_BARS:]
        if float(np.mean(av[-5:])) < float(np.mean(av[:5])):
            accum += 3.0
        inside = int(np.sum([1 for k in range(1, min(10, n))
                              if highs[-k] <= highs[-k - 1] and lows[-k] >= lows[-k - 1]]))
        accum += min(4.0, float(inside))
        rr = float(np.mean(highs[-5:] - lows[-5:]))
        ro = float(np.mean(highs[-ACCUM_BARS:-ACCUM_BARS + 5] - lows[-ACCUM_BARS:-ACCUM_BARS + 5]))
        if ro > 0 and rr < ro * 0.8:
            accum += 3.0
    out["feat_accumulation_score"] = round(accum, 2)

    # ── 3. Momentum Exhaustion ────────────────────────────────────────────────

    # Consecutive red candles immediately before entry
    cr = 0
    for k in range(1, min(15, n)):
        if closes[-k] < opens[-k]:
            cr += 1
        else:
            break
    out["feat_consec_red"] = cr

    # % down days in last 20 trading days
    dn  = min(21, n)
    rets = np.diff(closes[-dn:])
    out["feat_down_days_pct"] = round(float(np.sum(rets < 0)) / max(len(rets), 1), 3)

    # ATR compression: current 14d ATR / ATR 40 days prior
    if n >= 55:
        atr_now  = _safe_atr(highs[-14:],    lows[-14:],    closes[-14:])
        atr_prev = _safe_atr(highs[-55:-41], lows[-55:-41], closes[-55:-41])
        out["feat_atr_compression"] = round(atr_now / atr_prev, 4) if atr_prev > 0 else 1.0
    else:
        out["feat_atr_compression"] = None

    # Volume contraction: normalised slope of last 10 bars of volume
    if volumes is not None and n >= 10:
        v10   = volumes[-10:]
        slope = float(np.polyfit(np.arange(len(v10), dtype=float), v10, 1)[0])
        vm    = float(np.mean(v10))
        out["feat_vol_contraction"] = round(slope / vm, 4) if vm > 0 else 0.0
    else:
        out["feat_vol_contraction"] = None

    # Distance from recent lows (as fraction of entry price)
    out["feat_dist_20d_low"]  = round((entry_price - float(np.min(lows[-20:])))  / entry_price, 4) if n >= 20  else None
    out["feat_dist_50d_low"]  = round((entry_price - float(np.min(lows[-50:])))  / entry_price, 4) if n >= 50  else None
    out["feat_dist_52w_low"]  = round((entry_price - float(np.min(lows[-252:]))) / entry_price, 4) if n >= 252 else None

    # ── 4. Institutional ─────────────────────────────────────────────────────

    if volumes is not None and n >= 20:
        v20  = volumes[-20:]
        c20  = closes[-20:]
        svol = float(np.sum(v20))
        vwap = float(np.sum(c20 * v20) / svol) if svol > 0 else entry_price
        out["feat_vwap_dist"] = round((entry_price - vwap) / vwap, 4) if vwap > 0 else 0.0
    else:
        out["feat_vwap_dist"] = None

    # ── 5. Market Context ─────────────────────────────────────────────────────

    if egx30_df is not None and not egx30_df.empty:
        egx_pre = egx30_df[egx30_df.index <= sig_ts]
        if len(egx_pre) >= 21:
            ec       = egx_pre["Close"].values.astype(float)
            egx_ret  = (ec[-1] - ec[-21]) / ec[-21] if float(ec[-21]) > 0 else 0.0
            stk_ret  = (closes[-1] - closes[-21]) / closes[-21] if n >= 21 and float(closes[-21]) > 0 else 0.0
            out["feat_rs_vs_egx30"]     = round(stk_ret / egx_ret, 3) if abs(egx_ret) > 0.001 else 0.0
            egx_ma20 = float(np.mean(ec[-20:]))
            out["feat_egx30_trend_val"] = round((ec[-1] - egx_ma20) / egx_ma20, 4) if egx_ma20 > 0 else 0.0
        else:
            out["feat_rs_vs_egx30"]     = None
            out["feat_egx30_trend_val"] = None
    else:
        out["feat_rs_vs_egx30"]     = None
        out["feat_egx30_trend_val"] = None

    # ── 6. Snap Features (recomputed from OHLCV for backfilled signals) ───────

    out["snap_atr"] = round(_safe_atr(highs[-ATR_PERIOD:], lows[-ATR_PERIOD:], closes[-ATR_PERIOD:]), 4)

    body  = abs(float(closes[-1]) - float(opens[-1]))
    rng_e = float(highs[-1]) - float(lows[-1])
    out["snap_wick_ratio"] = round((rng_e - body) / rng_e, 4) if rng_e > 0 else 0.0

    out["snap_compression"] = out.get("feat_atr_compression")

    if n >= 10:
        atr_ref = _safe_atr(highs[-20:], lows[-20:], closes[-20:])
        consol  = 0
        for k in range(1, min(20, n)):
            if (float(highs[-k]) - float(lows[-k])) <= 2.0 * atr_ref:
                consol += 1
            else:
                break
        out["snap_consol_len"] = consol
    else:
        out["snap_consol_len"] = 0

    out["snap_bos"] = int(
        n >= 26 and bool(np.any(closes[-5:] > float(np.max(closes[-26:-5]))))
    )

    out["snap_choch"] = int(
        n >= 15 and bool(float(highs[-1]) > float(np.mean(highs[-8:-2])))
    ) if n >= 15 else 0

    piv_bars  = min(20, n)
    piv_lows2 = _pivot_lows(lows[-piv_bars:], window=2)
    if piv_lows2:
        depth = (entry_price - piv_lows2[-1][1]) / entry_price
        out["snap_pivot_str"] = round(min(float(depth) * 100.0, 20.0), 2)
    else:
        out["snap_pivot_str"] = 0.0

    out["snap_num_touches"] = out["feat_equal_lows_count"]
    out["snap_sweep_size"]  = out["feat_sweep_depth_pct"]

    if volumes is not None and n >= 21:
        vol_avg20 = float(np.mean(volumes[-21:-1]))
        out["snap_vol_exp"] = round(float(volumes[-1]) / vol_avg20, 3) if vol_avg20 > 0 else 1.0
    else:
        out["snap_vol_exp"] = None

    out["snap_dist_lo"]   = out.get("feat_dist_20d_low")
    out["snap_prem_disc"] = out["feat_dealing_range_pos"]

    if n >= 20:
        ema20 = float(pd.Series(closes).ewm(span=20, adjust=False).mean().iloc[-1])
        out["snap_reclaim_spd"] = round((float(closes[-1]) - ema20) / ema20, 4) if ema20 > 0 else 0.0
    else:
        out["snap_reclaim_spd"] = None

    return out
