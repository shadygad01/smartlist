"""
Snapshot Engine — EGX Research Platform
=========================================
يحسب الخصائص الرقمية الكاملة للـ Bottom لحظة الإشارة.
لا يُعيد حساب بيانات مستقبلية — Snapshot صادق 100%.

الخصائص المحسوبة (14 متغير):
  snap_atr          : ATR raw value (14 period)
  snap_wick_ratio   : lower wick / total range of signal candle
  snap_compression  : recent range / (ATR × lookback) — أقل من 1 = compression
  snap_consol_len   : عدد الشموع في حالة تماسك قبل الإشارة
  snap_bos          : Break of Structure (bullish)
  snap_bos_dist     : distance from BOS level (%)
  snap_choch        : Change of Character (higher low)
  snap_pivot_str    : قوة مستوى الدعم (عدد التلامسات / 5)
  snap_num_touches  : عدد التلامسات عند مستوى الـ Swing Low
  snap_sweep_size   : حجم اختراق الـ Liquidity Sweep (%)
  snap_vol_exp      : Volume Expansion ratio (last bar / 20-bar avg)
  snap_reclaim_spd  : سرعة استعادة EQ (1 / عدد الشموع)
  snap_dist_lo      : distance from current price to swing low (%)
  snap_prem_disc    : position within discount zone (0=low, 1=EQ)
"""
import numpy as np
import pandas as pd
from typing import Optional, Tuple


# ── Private Helpers ─────────────────────────────────────────────────────────────

def _atr(df: pd.DataFrame, period: int = 14) -> Optional[float]:
    if len(df) < period + 1:
        return None
    h = df["High"].values.astype(float)
    l = df["Low"].values.astype(float)
    c = df["Close"].values.astype(float)
    tr = np.maximum(h[1:] - l[1:],
         np.maximum(np.abs(h[1:] - c[:-1]), np.abs(l[1:] - c[:-1])))
    if len(tr) < period:
        return None
    return round(float(np.mean(tr[-period:])), 4)


def _swing_lows(low_s: pd.Series, left: int = 3, right: int = 3) -> list:
    lows = low_s.values.astype(float)
    pivots = []
    for i in range(left, len(lows) - right):
        if all(lows[i] <= lows[i - j] for j in range(1, left + 1)) and \
           all(lows[i] <= lows[i + j] for j in range(1, right + 1)):
            pivots.append((i, float(lows[i])))
    return pivots


def _swing_highs(high_s: pd.Series, left: int = 3, right: int = 3) -> list:
    highs = high_s.values.astype(float)
    pivots = []
    for i in range(left, len(highs) - right):
        if all(highs[i] >= highs[i - j] for j in range(1, left + 1)) and \
           all(highs[i] >= highs[i + j] for j in range(1, right + 1)):
            pivots.append((i, float(highs[i])))
    return pivots


def _wick_ratio(df: pd.DataFrame) -> Optional[float]:
    row = df.iloc[-1]
    o, h, l, c = float(row["Open"]), float(row["High"]), float(row["Low"]), float(row["Close"])
    rng = h - l
    if rng <= 0:
        return 0.0
    lower_wick = min(o, c) - l
    return round(max(0.0, float(lower_wick / rng)), 4)


def _compression_ratio(df: pd.DataFrame, lookback: int = 10,
                        atr_val: Optional[float] = None) -> Optional[float]:
    if len(df) < lookback or atr_val is None or atr_val <= 0:
        return None
    recent = df.tail(lookback)
    rng = float(recent["High"].max() - recent["Low"].min())
    expected = atr_val * lookback
    return round(rng / expected, 4) if expected > 0 else None


def _consolidation_len(df: pd.DataFrame, atr_val: Optional[float] = None) -> int:
    if atr_val is None or atr_val <= 0 or len(df) < 5:
        return 0
    threshold = atr_val * 1.5
    closes = df["Close"].values.astype(float)
    base = closes[-1]
    count = 0
    for i in range(len(closes) - 2, max(0, len(closes) - 40), -1):
        if abs(closes[i] - base) <= threshold:
            count += 1
        else:
            break
    return count


def _bos_choch(df: pd.DataFrame) -> Tuple[bool, float, bool]:
    """Returns: (bos_detected, bos_distance_pct, choch_detected)"""
    if len(df) < 15:
        return False, 0.0, False
    sub = df.tail(60)
    sh  = _swing_highs(sub["High"], left=3, right=3)
    sl  = _swing_lows(sub["Low"],   left=3, right=3)
    cur_close = float(df["Close"].iloc[-1])

    bos_det, bos_dist = False, 0.0
    for idx, price in reversed(sh):
        if idx < len(sub) - 3 and cur_close > price > 0:
            bos_det  = True
            bos_dist = round((cur_close - price) / price * 100, 4)
            break

    choch = False
    if len(sl) >= 2:
        sorted_sl = sorted(sl, key=lambda x: x[0])
        choch = sorted_sl[-1][1] > sorted_sl[-2][1]

    return bos_det, bos_dist, choch


def _pivot_strength(df: pd.DataFrame, lo: float) -> float:
    if lo <= 0 or len(df) < 10:
        return 0.0
    tol = lo * 0.005
    touches = sum(1 for l in df["Low"].values.astype(float) if abs(l - lo) <= tol)
    return round(min(1.0, touches / 5.0), 4)


def _num_touches(df: pd.DataFrame, lo: float, tol_pct: float = 0.005) -> int:
    if lo <= 0 or len(df) < 5:
        return 0
    tol = lo * tol_pct
    return int(sum(1 for l in df["Low"].values.astype(float) if abs(l - lo) <= tol))


def _sweep_size(df: pd.DataFrame, lo: float) -> float:
    if lo <= 0 or len(df) < 10:
        return 0.0
    min_low = float(df.tail(20)["Low"].min())
    if min_low >= lo:
        return 0.0
    return round((lo - min_low) / lo, 4)


def _vol_expansion(df: pd.DataFrame, lookback: int = 20) -> Optional[float]:
    if "Volume" not in df.columns or len(df) < lookback + 1:
        return None
    vols = df["Volume"].values.astype(float)
    avg_vol = float(np.mean(vols[-(lookback + 1):-1]))
    if avg_vol <= 0 or vols[-1] <= 0:
        return None
    return round(float(vols[-1] / avg_vol), 4)


def _reclaim_speed(df: pd.DataFrame, eq: float) -> Optional[float]:
    if eq <= 0 or len(df) < 5:
        return None
    closes = df["Close"].values.astype(float)
    below_idx = None
    for i in range(len(closes) - 2, max(0, len(closes) - 30), -1):
        if closes[i] < eq:
            below_idx = i
            break
    if below_idx is None:
        return None
    bars = len(closes) - 1 - below_idx
    return round(1.0 / bars, 4) if bars > 0 else None


# ── Public API ──────────────────────────────────────────────────────────────────

def compute_snapshot_features(
    df: pd.DataFrame,
    cur: float,
    eq: float,
    lo: float,
    hi: float,
) -> dict:
    """
    يحسب 14 خاصية رقمية للـ Bottom لحظة الإشارة.
    يُستدعى من analyze() في main.py فقط عند cur < eq.
    لا يستخدم أي بيانات مستقبلية.

    Args:
        df:  OHLCV DataFrame حتى لحظة الإشارة
        cur: سعر الإغلاق الحالي
        eq:  مستوى Equilibrium
        lo:  Swing Low
        hi:  Swing High
    """
    if df is None or len(df) < 10:
        return {}
    try:
        atr_val = _atr(df, 14)
        bos_det, bos_dist, choch = _bos_choch(df)
        rng = (hi - lo) if hi > lo else 1.0

        return {
            "snap_atr":         atr_val,
            "snap_wick_ratio":  _wick_ratio(df),
            "snap_compression": _compression_ratio(df, 10, atr_val),
            "snap_consol_len":  _consolidation_len(df, atr_val),
            "snap_bos":         int(bos_det),
            "snap_bos_dist":    bos_dist,
            "snap_choch":       int(choch),
            "snap_pivot_str":   _pivot_strength(df, lo),
            "snap_num_touches": _num_touches(df, lo),
            "snap_sweep_size":  _sweep_size(df, lo),
            "snap_vol_exp":     _vol_expansion(df, 20),
            "snap_reclaim_spd": _reclaim_speed(df, eq),
            "snap_dist_lo":     round(abs(cur - lo) / lo, 4) if lo > 0 else None,
            "snap_prem_disc":   round((cur - lo) / rng, 4),
        }
    except Exception:
        return {}
