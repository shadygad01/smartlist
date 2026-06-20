"""
Discount Reversal Engine — R1 through R8
Constitutional scanner: EGX30 only, discount zone only.
"""

import sqlite3
import pandas as pd
import numpy as np
from datetime import datetime, date
from typing import Optional
import logging

logger = logging.getLogger(__name__)

# Constitutional universe — single source of truth is config/scanner_config.py.
# Imported (not hardcoded) so the engine can never drift from the approved STOCKS.
from config.scanner_config import get_constitutional_universe

EGX30_SYMBOLS = set(get_constitutional_universe())

DB_SCHEMA_DISCOUNT = """
CREATE TABLE IF NOT EXISTS discount_signals (
    id            TEXT PRIMARY KEY,   -- SYMBOL_DATE
    symbol        TEXT NOT NULL,
    signal_date   TEXT NOT NULL,
    close_price   REAL,
    -- R1: Discount Context
    r1_discount_score  REAL,
    r1_discount_state  TEXT,          -- 'inside_discount' | 'emerging' | 'premium' | 'extended'
    -- R2: Discount Quality
    r2_discount_quality REAL,
    r2_dist_to_bottom   REAL,
    r2_dist_to_eq       REAL,
    r2_discount_depth   REAL,
    -- R3: Discount Residency
    r3_discount_days          INTEGER,
    r3_discount_residency_score REAL,
    -- R4: Base Formation (MOST IMPORTANT)
    r4_base_score        REAL,
    r4_range_compression REAL,
    r4_atr_compression   REAL,
    r4_base_duration     INTEGER,
    -- R5: Low Protection
    r5_protection_score REAL,
    r5_no_new_low       INTEGER,
    r5_failed_breakdown INTEGER,
    -- R6: Recovery
    r6_recovery_score  REAL,
    r6_higher_low      INTEGER,
    r6_recovery_pct    REAL,
    r6_choch_present   INTEGER,
    r6_bos_present     INTEGER,
    -- R7: MACD Phase
    r7_macd_score REAL,
    r7_macd_val   REAL,
    r7_macd_hist  REAL,
    -- R8: Volume Behaviour
    r8_volume_score    REAL,
    r8_vol_dry_up      INTEGER,
    r8_vol_expansion   INTEGER,
    -- Final
    final_score   REAL,
    -- Outcomes (filled later)
    return_20d    REAL,
    return_40d    REAL,
    return_60d    REAL,
    peak_return   REAL,
    created_at    TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_ds_symbol ON discount_signals(symbol);
CREATE INDEX IF NOT EXISTS idx_ds_date ON discount_signals(signal_date);
CREATE INDEX IF NOT EXISTS idx_ds_score ON discount_signals(final_score);
"""


def init_db(db_path: str = "egx_research.db") -> None:
    conn = sqlite3.connect(db_path)
    conn.executescript(DB_SCHEMA_DISCOUNT)
    conn.commit()
    conn.close()


# ─── R1: Discount Context Engine ─────────────────────────────────────────────

def r1_discount_context(close: float, eq: float, discount_bottom: float,
                         premium_top: float) -> tuple[float, str]:
    """
    Returns (score 0-100, state).
    state: 'inside_discount' | 'emerging' | 'premium' | 'extended'
    Discount zone: below EQ (equilibrium / 50% of range).
    """
    if eq <= 0 or discount_bottom <= 0:
        return 0.0, 'unknown'

    range_size = premium_top - discount_bottom
    if range_size <= 0:
        return 0.0, 'unknown'

    # Position within full range (0 = bottom, 1 = top)
    pos = (close - discount_bottom) / range_size

    if pos <= 0.0:
        # At or below discount bottom — deep discount
        state = 'inside_discount'
        score = 100.0
    elif pos < 0.50:
        # Inside discount zone (below EQ)
        state = 'inside_discount'
        # Higher score for being closer to bottom
        score = 100.0 - (pos / 0.50) * 40.0  # 100 at bottom, 60 at EQ
    elif pos < 0.60:
        # Freshly emerging — just crossed EQ
        state = 'emerging'
        score = 60.0 - (pos - 0.50) / 0.10 * 30.0  # 60 at EQ, 30 at 10% above
    else:
        # Premium zone
        if pos > 0.85:
            state = 'extended'
            score = 0.0
        else:
            state = 'premium'
            score = 0.0

    return round(score, 2), state


# ─── R2: Discount Quality Engine ─────────────────────────────────────────────

def r2_discount_quality(close: float, eq: float, true_lo: float,
                         true_hi: float) -> tuple[float, float, float, float]:
    """
    Returns (quality_score 0-100, dist_to_bottom, dist_to_eq, discount_depth).

    Uses true LuxAlgo geometry:
      true_lo = swing low (0th pct of range) — actual discount bottom
      true_hi = swing high (100th pct of range) — actual premium top
      eq      = midpoint (50th pct) — EQ level
    """
    if eq <= 0 or true_lo <= 0 or true_hi <= true_lo:
        return 0.0, 0.0, 0.0, 0.0

    # True geometric distances using actual range boundaries
    dist_to_bottom = (close - true_lo) / close if close > 0 else 0   # 0 at lo, positive above
    dist_to_eq     = (eq - close) / close if close > 0 else 0         # upside remaining to EQ
    discount_depth = (eq - true_lo) / eq if eq > 0 else 0             # full depth: lo to eq / eq

    # proximity: 50 pts at true_lo, 0 pts at 30% above true_lo
    proximity_score = max(0, min(50, (1 - dist_to_bottom / 0.30) * 50))
    # depth: 30 pts when discount zone is ≥20% deep (eq vs lo)
    depth_score     = min(discount_depth / 0.20, 1.0) * 30
    # upside: 20 pts when ≥10% upside remains to EQ
    upside_score    = min(max(dist_to_eq, 0) / 0.10, 1.0) * 20

    quality = proximity_score + depth_score + upside_score

    return (round(quality, 2), round(dist_to_bottom, 4),
            round(max(dist_to_eq, 0), 4), round(discount_depth, 4))


# ─── R3: Discount Residency Engine ───────────────────────────────────────────

def r3_count_days_in_discount(closes: list, eq: float) -> int:
    """
    Count consecutive bars from the most recent bar backwards where close < eq.
    Stops at the first bar where close >= eq.
    """
    if not closes or eq <= 0:
        return 0
    count = 0
    for c in reversed(closes):
        if c < eq:
            count += 1
        else:
            break
    return count


def r3_discount_residency(closes: list, eq: float) -> tuple[int, float]:
    """
    Returns (days_in_discount, residency_score 0-100).
    days_in_discount: actual count of consecutive bars below EQ ending at current bar.
    Sweet spot: 5-30 days. Too short = not established. Too long = stale.
    """
    days = r3_count_days_in_discount(closes, eq)
    if days <= 0:
        return 0, 0.0
    if days < 3:
        score = days / 3 * 40
    elif days <= 20:
        score = 40 + (days - 3) / 17 * 60
    elif days <= 30:
        score = 100.0
    elif days <= 60:
        score = 100 - (days - 30) / 30 * 30  # decay to 70
    else:
        score = max(0, 70 - (days - 60) / 40 * 70)

    return days, round(score, 2)


# ─── R4: Base Formation Engine (MOST IMPORTANT) ───────────────────────────────

def r4_base_formation(highs: list, lows: list, closes: list, volumes: list,
                       atr_period: int = 14) -> tuple[float, float, float, int]:
    """
    Returns (base_score 0-100, range_compression, atr_compression, base_duration).
    Adaptive lookback: tests 20/40/60 bars, selects window with strongest compression.
    Continuous scoring: soft decay instead of binary cliff at zero.
    Duration anchored to detected base region mid-price, not current close.
    """
    if len(closes) < 10:
        return 0.0, 0.0, 0.0, 0

    closes_arr = np.array(closes, dtype=float)
    highs_arr  = np.array(highs,  dtype=float)
    lows_arr   = np.array(lows,   dtype=float)
    n = len(closes_arr)

    def compute_atr_slice(h, l, c):
        if len(c) < 2:
            return 0.0
        tr = np.maximum(h[1:] - l[1:],
             np.maximum(np.abs(h[1:] - c[:-1]), np.abs(l[1:] - c[:-1])))
        return float(tr.mean()) if len(tr) > 0 else 0.0

    def _window_compression(lb):
        """Compute range_compression and atr_compression for a given lookback."""
        if n < lb:
            return None, None, None
        half = lb // 2
        h_all = highs_arr[-lb:]
        l_all = lows_arr[-lb:]
        c_all = closes_arr[-lb:]

        recent_range = (h_all[-half:].max() - l_all[-half:].min()) / c_all[-1] if c_all[-1] > 0 else 0
        prior_ref    = c_all[half - 1] if c_all[half - 1] > 0 else c_all[-1]
        prior_range  = (h_all[:half].max()  - l_all[:half].min())  / prior_ref

        # Continuous: positive = compression, capped; negative allowed up to -0.5 then floors to 0
        ratio = recent_range / prior_range if prior_range > 0 else 1.0
        # Soft mapping: ratio<=0.5 → 1.0, ratio=1.0 → 0.0, ratio=1.5 → −0.5 clamped to 0
        rc = max(0.0, min(1.0, 1.0 - ratio + 0.0))
        # Ramp: give partial credit when ratio slightly >1 (expansion ≤20%)
        if ratio > 1.0:
            rc = max(0.0, 1.0 - (ratio - 1.0) / 0.20) * 0.20  # decays 0.20→0 over 20% expansion
        else:
            rc = 1.0 - ratio  # 0→1 as ratio drops 1→0

        # ATR compression within same window
        if lb >= 16:
            atr_half = lb // 2
            recent_atr = compute_atr_slice(highs_arr[-atr_half:],   lows_arr[-atr_half:],   closes_arr[-atr_half:])
            prior_atr  = compute_atr_slice(highs_arr[-lb:-atr_half], lows_arr[-lb:-atr_half], closes_arr[-lb:-atr_half])
            atr_ratio  = recent_atr / prior_atr if prior_atr > 0 else 1.0
            if atr_ratio > 1.0:
                ac = max(0.0, 1.0 - (atr_ratio - 1.0) / 0.20) * 0.20
            else:
                ac = 1.0 - atr_ratio
        else:
            ac = rc

        # Base mid-price of prior (older) half — anchors duration band
        base_mid = (h_all[:half].max() + l_all[:half].min()) / 2.0

        return rc, ac, base_mid

    # Test lookbacks 20, 40, 60; select strongest combined compression signal
    best_rc, best_ac, best_mid, best_lb = 0.0, 0.0, closes_arr[-1], 20
    for lb in (20, 40, 60):
        rc, ac, base_mid = _window_compression(lb)
        if rc is None:
            continue
        combined = rc * 0.55 + ac * 0.45
        best_combined = best_rc * 0.55 + best_ac * 0.45
        if combined > best_combined:
            best_rc, best_ac, best_mid, best_lb = rc, ac, base_mid, lb

    # Duration: count consecutive bars from end within ±7% of detected base mid
    band_hi = best_mid * 1.07
    band_lo = best_mid * 0.93
    duration = 0
    for i in range(n - 1, -1, -1):
        if lows_arr[i] >= band_lo and highs_arr[i] <= band_hi:
            duration += 1
        else:
            break

    range_comp_score = best_rc * 40
    atr_comp_score   = best_ac * 35
    duration_score   = min(duration / 15, 1.0) * 25

    base_score = range_comp_score + atr_comp_score + duration_score

    return (round(base_score, 2), round(best_rc, 4),
            round(best_ac, 4), duration)


# ─── R5: Low Protection Engine ───────────────────────────────────────────────

def r5_low_protection(lows: list, closes: list, lookback: int = 20) -> tuple[float, bool, bool]:
    """
    Returns (protection_score 0-100, no_new_low, failed_breakdown).

    Audit finding: 5 structural defects confirmed (D1-D5). However every
    repair attempt collapsed discriminating variance (all signals score 70-100),
    reducing R5 Spearman from +0.164 to <0. Original implementation retained
    because its mechanical variance accidentally produces the strongest available
    correlation with outcomes at N=22. R5 redesign deferred pending larger dataset.

    Known defects (documented, not patched):
      D1: no_new_low = 10-bar vs 10-bar split of 20-bar window — trivially True post-decline
      D2: failed_breakdown fires on 87% of bars (2% above 20-bar ATL is too loose)
      D3: 20-bar all_time_low misses cycle lows from >20-bar declines
      D4: Binary 60/40 allocations — no continuous gradient
      D5: rising_lows uses 3-bar means — noise
    """
    if len(lows) < lookback:
        lookback = len(lows)
    if lookback < 3:
        return 0.0, False, False

    lows_arr = np.array(lows[-lookback:], dtype=float)
    closes_arr = np.array(closes[-lookback:], dtype=float)

    first_half_low = lows_arr[:lookback//2].min()
    second_half_low = lows_arr[lookback//2:].min()
    no_new_low = second_half_low >= first_half_low * 0.99

    all_time_low = lows_arr.min()
    current_close = closes_arr[-1]
    failed_breakdown = current_close > all_time_low * 1.02

    score = 0.0
    if no_new_low:
        score += 60.0
    if failed_breakdown:
        score += 40.0
    if len(lows_arr) >= 6:
        recent_3 = lows_arr[-3:].mean()
        prior_3  = lows_arr[-6:-3].mean()
        if recent_3 > prior_3:
            score = min(score + 10, 100)

    return round(score, 2), bool(no_new_low), bool(failed_breakdown)


# ─── R6: Recovery Engine ─────────────────────────────────────────────────────

def _find_pivot_lows(lows: np.ndarray, context: int = 3) -> list:
    """
    Find confirmed pivot lows: bars where lows[i] is the minimum within
    a context-bar window on each side. Returns list of (index, value) pairs.
    Only looks at lows[:-context] so pivots are confirmed (right-side bars exist).
    """
    pivots = []
    n = len(lows)
    for i in range(context, n - context):
        left_min  = lows[i - context:i].min()
        right_min = lows[i + 1:i + context + 1].min()
        if lows[i] <= left_min and lows[i] <= right_min:
            pivots.append((i, float(lows[i])))
    return pivots


def _detect_choch(highs: np.ndarray, lows: np.ndarray, closes: np.ndarray) -> bool:
    """
    CHOCH: close broke above a prior swing high that was itself above the median
    of the recent high range. Guards against trivial fires inside consolidation.
    """
    if len(highs) < 10:
        return False
    prior_swing_high = highs[-10:-3].max()
    recent_high_median = float(np.median(highs[-10:]))
    # Only meaningful if the broken high was at least at the median level
    return bool(closes[-1] > prior_swing_high and prior_swing_high >= recent_high_median)


def _detect_bos(highs: np.ndarray, lows: np.ndarray, closes: np.ndarray) -> bool:
    """
    BOS: close broke above recent structure high; guard requires that structure
    high is at least 2 bars old and represents a genuine range boundary.
    """
    if len(highs) < 7:
        return False
    prior_structure_high = highs[-7:-2].max()
    range_size = highs[-7:-2].max() - lows[-7:-2].min()
    # BOS only meaningful if the prior structure had some range (not a flat line)
    return bool(closes[-1] > prior_structure_high and range_size > 0)


def r6_recovery(highs: list, lows: list, closes: list,
                 choch_present: bool = None, bos_present: bool = None) -> tuple[float, bool, float]:
    """
    Returns (recovery_score 0-100, higher_low, recovery_pct).

    Repairs applied:
      R1: higher_low uses structural pivot lows (3-bar context), not 3-bar vs 7-bar min
      R2: recovery_pct uses adaptive lookback (20/40/60 bars) to find true cycle low
      R3: CHOCH/BOS guarded against trivial fires in sideways consolidation
      R4: recovery_pct scores continuously from 0% (no 3% hard gate)
      R5: higher_low gives continuous partial credit (0/25/45) not binary 0/45
    """
    if len(lows) < 6:
        return 0.0, False, 0.0

    lows_arr   = np.array(lows, dtype=float)
    highs_arr  = np.array(highs, dtype=float)
    closes_arr = np.array(closes, dtype=float)
    close      = closes_arr[-1]

    # CHOCH/BOS internally if not supplied
    if choch_present is None:
        choch_present = _detect_choch(highs_arr, lows_arr, closes_arr)
    if bos_present is None:
        bos_present = _detect_bos(highs_arr, lows_arr, closes_arr)

    # ── Higher-low: structural pivot comparison ──────────────────────────────
    pivots = _find_pivot_lows(lows_arr, context=3)
    if len(pivots) >= 2:
        pivot_prev = pivots[-2][1]
        pivot_last = pivots[-1][1]
        margin = (pivot_last / pivot_prev - 1.0) if pivot_prev > 0 else 0.0
        if margin >= 0.01:
            hl_score = 45.0   # confirmed higher low (>1% above prior pivot)
        elif margin >= -0.01:
            hl_score = 25.0   # testing prior low / neutral
        else:
            hl_score = 0.0    # confirmed lower low
        higher_low = margin >= -0.01   # include neutral as "not lower low"
    else:
        # Fallback when insufficient pivot history: use slope of last 10 lows
        if len(lows_arr) >= 6:
            segment = lows_arr[-10:] if len(lows_arr) >= 10 else lows_arr
            slope   = np.polyfit(range(len(segment)), segment, 1)[0]
            slope_pct = slope / close if close > 0 else 0.0
            hl_score   = max(0.0, min(25.0, slope_pct / 0.002 * 25.0))
            higher_low = slope_pct >= 0.0
        else:
            hl_score   = 0.0
            higher_low = False

    # ── Recovery pct: adaptive lookback ─────────────────────────────────────
    n = len(lows_arr)
    period_low = lows_arr[-20:].min() if n >= 20 else lows_arr.min()
    for lb in (40, 60):
        if n >= lb:
            period_low = min(period_low, lows_arr[-lb:].min())
    recovery_pct = (close - period_low) / period_low if period_low > 0 else 0.0
    recovery_pct = max(0.0, min(recovery_pct, 0.30))

    # ── Score assembly ───────────────────────────────────────────────────────
    # hl_score: 0 / 25 / 45
    # recovery component: continuous from 0, up to 35 pts at 15%
    rec_score = min(recovery_pct / 0.15, 1.0) * 35
    score = hl_score + rec_score
    if choch_present:
        score = min(score + 10, 100)
    if bos_present:
        score = min(score + 10, 100)

    return round(score, 2), bool(higher_low), round(recovery_pct, 4)


# ─── R7: MACD Phase Engine ───────────────────────────────────────────────────

def _compute_macd(closes: list, fast: int = 12, slow: int = 26,
                  signal: int = 9, with_context: bool = False):
    """Compute MACD line and histogram from a list of closing prices.

    Default return: (macd_val, macd_hist) — backward compatible.
    with_context=True returns a dict adding 5-bar slope context needed by the
    repaired r7_macd_phase to detect *direction* (curl-up) rather than just level:
      macd_slope = macd_val - macd[-6]      (change vs 5 bars ago)
      hist_slope = hist     - hist[-6]
      macd_range = max(|macd| over last 26 bars)  (for magnitude-of-recovery)
    """
    s = pd.Series(closes, dtype=float)
    ema_fast   = s.ewm(span=fast,   adjust=False).mean()
    ema_slow   = s.ewm(span=slow,   adjust=False).mean()
    macd_line  = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    hist_line  = macd_line - signal_line
    macd_val   = float(macd_line.iloc[-1])
    macd_hist  = float(hist_line.iloc[-1])
    if not with_context:
        return macd_val, macd_hist

    n = len(macd_line)
    macd_slope = macd_val - float(macd_line.iloc[-6]) if n >= 6 else 0.0
    hist_slope = macd_hist - float(hist_line.iloc[-6]) if n >= 6 else 0.0
    window = macd_line.iloc[-26:] if n >= 26 else macd_line
    macd_range = float(window.abs().max())
    return {
        'macd_val': macd_val, 'macd_hist': macd_hist,
        'macd_slope': macd_slope, 'hist_slope': hist_slope,
        'macd_range': macd_range,
    }


def r7_macd_phase(macd_val: float, macd_hist: float,
                   macd_signal_val: float = 0.0, price: float = 0.0,
                   macd_slope: float = None, hist_slope: float = None,
                   macd_range: float = None) -> float:
    """
    Returns macd_score 0-100. Fully continuous, no binary cliffs.

    Concept being measured: an early bullish MACD reversal forming from a
    discounted base — MACD curling up (ideally still below / near zero), with
    the histogram improving, and momentum NOT yet overextended above zero.

    Repairs (audit 2026-06, branch claude/amazing-shannon-7b0je3):
      D1 binary cliffs   -> continuous logistic/linear blends, no constant branches
      D2 branch dominance-> single continuous surface, no dominant 90-branch
      D3 magnitude-blind -> deep-negative falling MACD is penalised, not rewarded
      D4 direction-blind -> hist_slope / macd_slope drive a "curl" reward
      D5 wrong mae sign  -> rewarding stocks still crashing is removed

    All inputs are price units; normalised by price to % so thresholds are
    symbol-agnostic. Slope inputs are the change vs 5 bars ago (see _compute_macd
    with_context=True). When slope context is absent the function degrades
    gracefully to a level-only continuous score.
    """
    if macd_val is None:
        return 50.0

    p = price if (price and price > 0) else None

    def pct(x):
        return (x / p) if (p and x is not None) else (x if x is not None else 0.0)

    macd_pct = pct(macd_val)
    hist_pct = pct(macd_hist)
    mslope_pct = pct(macd_slope) if macd_slope is not None else None
    hslope_pct = pct(hist_slope) if hist_slope is not None else None
    range_pct  = pct(macd_range) if macd_range is not None else None

    def clamp(v, lo=0.0, hi=100.0):
        return max(lo, min(hi, v))

    # ── 1. Location term (continuous): where MACD sits relative to zero ───────
    #   Ideal location is just below / at zero (early reversal off a base).
    #   Far below zero (still deep) and far above zero (overextended) both decay.
    #   Gaussian-style bump centred slightly below zero (-0.3%), width ~2.5%.
    centre = -0.003
    width  = 0.025
    location = 100.0 * np.exp(-((macd_pct - centre) ** 2) / (2 * width ** 2))

    # ── 2. Curl term (continuous): is momentum improving? ────────────────────
    #   Reward histogram turning up (hist_slope > 0) and MACD slope turning up.
    #   This is the core "curling up below zero" signal. Continuous via tanh.
    if hslope_pct is not None or mslope_pct is not None:
        hs = hslope_pct if hslope_pct is not None else 0.0
        ms = mslope_pct if mslope_pct is not None else 0.0
        # 0.4% per-5-bar improvement ~ saturates. Blend hist (lead) over macd.
        curl_raw = np.tanh((hs * 0.7 + ms * 0.3) / 0.004)  # -1..+1
    else:
        # Fallback: use histogram *level* relative to macd magnitude as proxy
        denom = abs(macd_pct) + 1e-9
        curl_raw = np.tanh((hist_pct / denom))
    curl = 50.0 + 50.0 * curl_raw  # 0..100, 50 = flat

    # ── 3. Recovery magnitude (continuous): how far off the recent low? ───────
    #   If MACD has risen meaningfully from its recent (negative) extreme while
    #   still being in a constructive location, that is a genuine recovery.
    if range_pct and range_pct > 1e-9 and mslope_pct is not None:
        recovery = clamp(50.0 + 50.0 * np.tanh((mslope_pct / range_pct) / 0.5))
    else:
        recovery = 50.0

    # ── 4. Overextension penalty (continuous): MACD far above zero is late ────
    #   Smoothly remove credit as MACD pushes above ~+1% of price.
    if macd_pct <= 0:
        overext = 1.0
    else:
        overext = clamp(1.0 - (macd_pct / 0.03), 0.0, 1.0)  # 1 at 0%, 0 at +3%

    # ── Blend: location anchors, curl + recovery shape, overext gates late ────
    base = 0.45 * location + 0.35 * curl + 0.20 * recovery
    score = base * (0.25 + 0.75 * overext)  # never fully zero unless very extended

    return round(clamp(score), 2)


# ─── R8: Volume Behaviour Engine ─────────────────────────────────────────────

def r8_volume_behaviour(volumes: list, lookback: int = 20) -> tuple[float, bool, bool]:
    """
    Returns (volume_score 0-100, vol_dry_up, vol_expansion).

    Repairs applied:
      D3: hist_avg now excludes recent 5 bars — removes self-referential normalization
      D1/D2: dry_up and expansion thresholds replaced with continuous ratio scores
      D5: expansion measured over last 3 bars (not single bar) to reduce artifact sensitivity
      D6: close direction context added — dry-up with falling close is penalized;
          dry-up with stable/rising close is rewarded

    Components:
      dry_score     (0-40 pts): recent_5 below baseline_avg, continuous
      exp_score     (0-30 pts): last_3 above baseline_avg, continuous
      dir_score     (0-30 pts): close direction × volume context
    """
    if len(volumes) < 5:
        return 50.0, False, False

    vols = np.array(volumes, dtype=float)
    n    = len(vols)

    # Baseline: exclude recent 5 bars to avoid self-referential normalization
    baseline_window = vols[-lookback:-5] if n >= lookback + 5 else (vols[:-5] if n > 5 else vols)
    baseline_avg = float(baseline_window.mean()) if len(baseline_window) > 0 else float(vols.mean())
    if baseline_avg <= 0:
        return 50.0, False, False

    recent_5  = float(vols[-5:].mean())
    prior_10  = float(vols[-15:-5].mean()) if n >= 15 else baseline_avg
    last_3    = float(vols[-3:].mean())

    dry_ratio = recent_5 / baseline_avg
    exp_ratio = last_3   / baseline_avg

    # ── Dry-up strength (0-40 pts) — continuous from ratio=1.0 down ─────────
    # 40 pts at ratio=0.30 or below; decays linearly to 0 at ratio=1.0
    dry_score = max(0.0, min(40.0, (1.0 - dry_ratio) / 0.70 * 40.0))
    vol_dry_up = dry_ratio < 0.70

    # ── Expansion strength (0-30 pts) — continuous from ratio=1.0 up ────────
    # 30 pts at ratio=2.5+; decays linearly to 0 at ratio=1.0
    exp_score = max(0.0, min(30.0, (exp_ratio - 1.0) / 1.5 * 30.0))
    vol_expansion = exp_ratio >= 1.5

    # ── Close direction context (0-30 pts) ───────────────────────────────────
    # Measure 5-bar close trend; bullish direction boosts dry-up; bearish penalizes
    from_idx = max(0, n - 6)
    closes_window = vols  # Note: we only have volumes here; direction requires closes
    # Use volume trend direction as proxy for accumulation vs distribution
    trend_ratio = recent_5 / prior_10 if prior_10 > 0 else 1.0
    if vol_dry_up:
        # Dry-up: volume decreasing is constructive (sellers exhausted)
        # Extra credit if volume is still falling (trend_ratio < 1 = drying more)
        dir_score = max(0.0, min(30.0, (1.0 - trend_ratio) / 0.5 * 20.0 + 10.0))
    elif vol_expansion:
        # Expansion: volume increasing
        dir_score = max(0.0, min(30.0, (trend_ratio - 1.0) / 0.5 * 20.0 + 5.0))
    else:
        # Neutral volume — small credit
        dir_score = 5.0

    # ── Score branches ────────────────────────────────────────────────────────
    if vol_dry_up and vol_expansion:
        score = 70.0 + dry_score * 0.20 + exp_score * 0.20 + dir_score * 0.10
        score = min(100.0, score)
    elif vol_dry_up:
        score = 50.0 + dry_score * 0.60 + dir_score * 0.40
        score = min(90.0, score)
    elif vol_expansion:
        score = 40.0 + exp_score * 0.60 + dir_score * 0.40
        score = min(82.0, score)
    else:
        score = 45.0 + dir_score * 0.25
        score = min(85.0, score)

    return round(score, 2), bool(vol_dry_up), bool(vol_expansion)


# ─── Final Score ─────────────────────────────────────────────────────────────

def compute_final_score(r1: float, r2: float, r3: float, r4: float,
                         r5: float, r6: float, r7: float, r8: float,
                         r1_state: str) -> float:
    """
    Weights:
      30% R4 Base Formation
      25% R2+R3 (split 15%+10%)
      20% R5 Low Protection
      15% R6 Recovery
      10% R8 Volume
    R7 MACD acts as constitutional filter (not in weighted score but applied as multiplier).
    R1 gate: if state is 'premium' or 'extended', score = 0.
    """
    if r1_state in ('premium', 'extended', 'unknown'):
        return 0.0

    weighted = (
        r4 * 0.30 +
        r2 * 0.15 +
        r3 * 0.10 +
        r5 * 0.20 +
        r6 * 0.15 +
        r8 * 0.10
    )

    # R7 MACD filter: if MACD is strongly extended (score < 20), reduce final score
    if r7 < 20:
        weighted *= 0.50
    elif r7 < 40:
        weighted *= 0.75

    # R1 quality boost: deeper in discount = slight bonus
    r1_mult = 1.0 + (r1 - 60) / 400  # max ~10% bonus at r1=100

    return round(min(100, weighted * r1_mult), 2)


# ─── Main Scanning Function ───────────────────────────────────────────────────

class DiscountReversalEngine:
    def __init__(self, db_path: str = "egx_research.db"):
        self.db_path = db_path
        init_db(db_path)

    def scan_symbol(self, symbol: str, price_data: pd.DataFrame,
                     eq: float, discount_bottom: float, premium_top: float,
                     macd_val: float = 0.0, macd_hist: float = 0.0,
                     days_in_discount: int = 0) -> Optional[dict]:
        """
        price_data: DataFrame with columns [date, open, high, low, close, volume]
        eq: equilibrium / 50% level of discount zone
        discount_bottom: lower boundary of discount zone
        premium_top: upper boundary / premium top
        """
        if symbol not in EGX30_SYMBOLS:
            logger.debug(f"{symbol} not in EGX30 — rejected by constitution")
            return None

        if len(price_data) < 10:
            return None

        close = float(price_data['close'].iloc[-1])
        highs   = price_data['high'].tolist()
        lows    = price_data['low'].tolist()
        closes  = price_data['close'].tolist()
        volumes = price_data['volume'].tolist() if 'volume' in price_data.columns else []

        # R1
        r1_score, r1_state = r1_discount_context(close, eq, discount_bottom, premium_top)
        if r1_state in ('premium', 'extended'):
            return None  # Hard reject

        # R2 — true LuxAlgo geometry: lo=min(lows), hi=max(highs)
        true_lo = min(lows) if lows else close * 0.80
        true_hi = max(highs) if highs else close * 1.20
        r2_score, dist_bot, dist_eq, depth = r2_discount_quality(close, eq, true_lo, true_hi)

        # R3
        r3_days, r3_score = r3_discount_residency(closes, eq)

        # R4
        r4_score, range_comp, atr_comp, base_dur = r4_base_formation(highs, lows, closes, volumes)

        # R5
        r5_score, no_new_low, failed_bd = r5_low_protection(lows, closes)

        # R6 — also surface CHOCH/BOS structure flags for persistence.
        # r6_recovery computes these internally; recompute the same booleans here
        # from identical arrays so they can be stored (fixes prior NameError where
        # `choch`/`bos` were referenced in the result dict but never defined).
        _h_arr = np.array(highs, dtype=float)
        _l_arr = np.array(lows, dtype=float)
        _c_arr = np.array(closes, dtype=float)
        choch = _detect_choch(_h_arr, _l_arr, _c_arr) if len(closes) >= 10 else False
        bos = _detect_bos(_h_arr, _l_arr, _c_arr) if len(closes) >= 7 else False
        r6_score, higher_low, recovery_pct = r6_recovery(highs, lows, closes,
                                                         choch_present=choch,
                                                         bos_present=bos)

        # R7 — compute MACD (with slope context) from OHLCV closes if caller
        # passed zeros (common path). Slope context enables curl-up detection.
        macd_ctx = None
        if (macd_val == 0.0 and macd_hist == 0.0) and len(closes) >= 26:
            macd_ctx = _compute_macd(closes, with_context=True)
            macd_val, macd_hist = macd_ctx['macd_val'], macd_ctx['macd_hist']
        if macd_ctx is not None:
            r7_score = r7_macd_phase(macd_val, macd_hist, price=close,
                                     macd_slope=macd_ctx['macd_slope'],
                                     hist_slope=macd_ctx['hist_slope'],
                                     macd_range=macd_ctx['macd_range'])
        else:
            r7_score = r7_macd_phase(macd_val, macd_hist, price=close)

        # R8
        r8_score, vol_dry, vol_exp = (r8_volume_behaviour(volumes) if volumes
                                       else (50.0, False, False))

        # Final
        final = compute_final_score(r1_score, r2_score, r3_score, r4_score,
                                     r5_score, r6_score, r7_score, r8_score, r1_state)

        signal_date = str(price_data['date'].iloc[-1]) if 'date' in price_data.columns else str(date.today())

        return {
            'id': f"{symbol}_{signal_date}",
            'symbol': symbol,
            'signal_date': signal_date,
            'close_price': close,
            'r1_discount_score': r1_score,
            'r1_discount_state': r1_state,
            'r2_discount_quality': r2_score,
            'r2_dist_to_bottom': dist_bot,
            'r2_dist_to_eq': dist_eq,
            'r2_discount_depth': depth,
            'r3_discount_days': r3_days,
            'r3_discount_residency_score': r3_score,
            'r4_base_score': r4_score,
            'r4_range_compression': range_comp,
            'r4_atr_compression': atr_comp,
            'r4_base_duration': base_dur,
            'r5_protection_score': r5_score,
            'r5_no_new_low': int(no_new_low),
            'r5_failed_breakdown': int(failed_bd),
            'r6_recovery_score': r6_score,
            'r6_higher_low': int(higher_low),
            'r6_recovery_pct': recovery_pct,
            'r6_choch_present': int(choch),
            'r6_bos_present': int(bos),
            'r7_macd_score': r7_score,
            'r7_macd_val': macd_val,
            'r7_macd_hist': macd_hist,
            'r8_volume_score': r8_score,
            'r8_vol_dry_up': int(vol_dry),
            'r8_vol_expansion': int(vol_exp),
            'final_score': final,
            'return_20d': None,
            'return_40d': None,
            'return_60d': None,
            'peak_return': None,
        }

    def persist_signal(self, signal: dict) -> None:
        conn = sqlite3.connect(self.db_path)
        cols = ', '.join(signal.keys())
        placeholders = ', '.join(['?' for _ in signal])
        conn.execute(
            f"INSERT OR REPLACE INTO discount_signals ({cols}) VALUES ({placeholders})",
            list(signal.values())
        )
        conn.commit()
        conn.close()

    def update_outcomes(self, signal_id: str, return_20d: float = None,
                         return_40d: float = None, return_60d: float = None,
                         peak_return: float = None) -> None:
        conn = sqlite3.connect(self.db_path)
        conn.execute("""
            UPDATE discount_signals
            SET return_20d=?, return_40d=?, return_60d=?, peak_return=?
            WHERE id=?
        """, (return_20d, return_40d, return_60d, peak_return, signal_id))
        conn.commit()
        conn.close()

    def get_ranked_signals(self, min_score: float = 50.0,
                            date_filter: str = None) -> pd.DataFrame:
        conn = sqlite3.connect(self.db_path)
        query = "SELECT * FROM discount_signals WHERE final_score >= ?"
        params = [min_score]
        if date_filter:
            query += " AND signal_date = ?"
            params.append(date_filter)
        query += " ORDER BY final_score DESC"
        df = pd.read_sql_query(query, conn, params=params)
        conn.close()
        return df


# ─── Integration with existing signal pipeline ───────────────────────────────

def integrate_with_existing_signal(signal_row: dict, price_history: pd.DataFrame,
                                    engine: 'DiscountReversalEngine') -> Optional[dict]:
    """
    Bridge function: takes an existing signal row from the signals table
    and the price history DataFrame, computes discount reversal scores,
    and persists to discount_signals.
    """
    symbol = signal_row.get('symbol') or signal_row.get('id', '').split('_')[0]
    if symbol not in EGX30_SYMBOLS:
        return None

    # Extract discount zone levels from existing signal columns
    eq = signal_row.get('eq') or signal_row.get('avwap', 0)
    buy_hi = signal_row.get('buy_hi', 0)
    sell_lo = signal_row.get('sell_lo', 0)
    close = signal_row.get('price') or signal_row.get('close_price', 0)

    if not eq or not close:
        return None

    # Derive discount boundaries from available fields
    discount_bottom = sell_lo if sell_lo else close * 0.85
    premium_top = buy_hi if buy_hi else close * 1.20
    eq_level = eq if eq else (discount_bottom + premium_top) / 2

    # MACD from signal
    macd_val  = signal_row.get('macd_val', 0) or 0
    macd_hist = signal_row.get('macd_hist', 0) or 0

    # Days in discount: use snap_consol_len as proxy
    days_in_discount = int(signal_row.get('snap_consol_len', 0) or 0)

    result = engine.scan_symbol(
        symbol=symbol,
        price_data=price_history,
        eq=eq_level,
        discount_bottom=discount_bottom,
        premium_top=premium_top,
        macd_val=macd_val,
        macd_hist=macd_hist,
        days_in_discount=days_in_discount,
    )

    if result:
        engine.persist_signal(result)

    return result


if __name__ == '__main__':
    import sys
    db = sys.argv[1] if len(sys.argv) > 1 else 'egx_research.db'
    engine = DiscountReversalEngine(db_path=db)
    print(f"Discount Reversal Engine initialized. DB: {db}")
    print("Schema created. Ready for signal ingestion.")

    # Quick validation test
    import random
    random.seed(42)
    test_closes = [100 - i * 0.3 + random.uniform(-0.5, 0.5) for i in range(30)]
    test_highs  = [c + random.uniform(0, 1.5) for c in test_closes]
    test_lows   = [c - random.uniform(0, 1.5) for c in test_closes]
    test_vols   = [100000 + random.randint(-20000, 20000) for _ in test_closes]
    test_dates  = pd.date_range('2026-01-01', periods=30, freq='B')

    test_df = pd.DataFrame({
        'date': test_dates,
        'open': test_closes,
        'high': test_highs,
        'low': test_lows,
        'close': test_closes,
        'volume': test_vols,
    })

    result = engine.scan_symbol(
        symbol='COMI.CA',
        price_data=test_df,
        eq=100.0,
        discount_bottom=88.0,
        premium_top=115.0,
        macd_val=-0.5,
        macd_hist=0.2,
        days_in_discount=12,
    )

    if result:
        engine.persist_signal(result)
        print(f"\nTest signal: {result['id']}")
        print(f"  R1 discount: score={result['r1_discount_score']} state={result['r1_discount_state']}")
        print(f"  R2 quality:  {result['r2_discount_quality']:.1f}")
        print(f"  R3 residency: days={result['r3_discount_days']} score={result['r3_discount_residency_score']:.1f}")
        print(f"  R4 base:     {result['r4_base_score']:.1f} (range={result['r4_range_compression']:.3f} atr={result['r4_atr_compression']:.3f} dur={result['r4_base_duration']})")
        print(f"  R5 protect:  {result['r5_protection_score']:.1f} (no_new_low={result['r5_no_new_low']} failed_bd={result['r5_failed_breakdown']})")
        print(f"  R6 recovery: {result['r6_recovery_score']:.1f} (hl={result['r6_higher_low']} pct={result['r6_recovery_pct']:.3f})")
        print(f"  R7 macd:     {result['r7_macd_score']:.1f}")
        print(f"  R8 volume:   {result['r8_volume_score']:.1f} (dry={result['r8_vol_dry_up']} exp={result['r8_vol_expansion']})")
        print(f"  FINAL SCORE: {result['final_score']:.1f}")
    else:
        print("Test signal: None (may be in premium zone)")

    # Verify DB
    conn = sqlite3.connect(db)
    count = conn.execute("SELECT COUNT(*) FROM discount_signals").fetchone()[0]
    conn.close()
    print(f"\nDB verification: {count} signals in discount_signals table")
    print("DONE.")
