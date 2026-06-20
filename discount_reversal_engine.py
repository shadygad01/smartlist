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

# EGX30 universe — only these symbols are eligible
EGX30_SYMBOLS = {
    'COMI.CA', 'EKHW.CA', 'HRHO.CA', 'EGCH.CA', 'ESRS.CA',
    'PHDC.CA', 'SWDY.CA', 'TMGH.CA', 'AMER.CA', 'EFIC.CA',
    'FWRY.CA', 'GBCO.CA', 'ALCN.CA', 'ORWE.CA', 'ABUK.CA',
    'ARCC.CA', 'EAST.CA', 'EFID.CA', 'JUFO.CA', 'MNHD.CA',
    'OCDI.CA', 'ORHD.CA', 'ISPH.CA', 'HELI.CA', 'ACGC.CA',
    'AURS.CA', 'MOIL.CA', 'SPMD.CA', 'AMOC.CA', 'AUTO.CA',
}

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
    """
    if len(lows) < lookback:
        lookback = len(lows)
    if lookback < 3:
        return 0.0, False, False

    lows_arr = np.array(lows[-lookback:], dtype=float)
    closes_arr = np.array(closes[-lookback:], dtype=float)

    # No new low: recent lows not breaking below earlier lows
    first_half_low = lows_arr[:lookback//2].min()
    second_half_low = lows_arr[lookback//2:].min()
    no_new_low = second_half_low >= first_half_low * 0.99  # 1% tolerance

    # Failed breakdown: close recovered above a breached low
    all_time_low = lows_arr.min()
    current_close = closes_arr[-1]
    failed_breakdown = current_close > all_time_low * 1.02  # closed 2%+ above lowest low

    score = 0.0
    if no_new_low:
        score += 60.0
    if failed_breakdown:
        score += 40.0
    # Bonus: if recent lows are rising
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

def r7_macd_phase(macd_val: float, macd_hist: float,
                   macd_signal_val: float = 0.0, price: float = 0.0) -> float:
    """
    Returns macd_score 0-100.
    Preferred: MACD below zero. Acceptable: near zero. Reject: strongly extended above zero.

    Normalization: MACD values are in price units. Normalize by dividing by price (as %)
    so thresholds are symbol-agnostic.
    near_zero band: abs(macd_val_pct) < 0.005 (±0.5% of price)
    """
    if macd_val is None:
        return 50.0

    # Normalize to % of price so thresholds are symbol-agnostic
    if price and price > 0:
        macd_pct = macd_val / price
        hist_pct = macd_hist / price if macd_hist else 0.0
    else:
        # Fallback: use raw values with ±0.5 as near-zero band estimate
        macd_pct = macd_val
        hist_pct = macd_hist if macd_hist else 0.0

    NEAR_ZERO = 0.005  # ±0.5% of price

    if macd_pct < -NEAR_ZERO:
        # Below zero — most preferred early phase
        if hist_pct < 0 and abs(hist_pct) < abs(macd_pct) * 0.5:
            # Histogram shrinking (less negative) → bullish curl forming
            score = 90.0
        elif hist_pct >= 0:
            # MACD below zero, histogram already positive → curling up
            score = 85.0
        else:
            # MACD below zero, histogram still falling
            score = 75.0
    elif abs(macd_pct) <= NEAR_ZERO:
        # Near zero — acceptable, not ideal
        if hist_pct >= 0:
            score = 65.0  # crossing up through zero
        else:
            score = 55.0  # crossing down through zero
    else:
        # Above zero — penalize proportional to extension
        # Linear decay: 0% extension → 45, 3% extension → 0
        extension = macd_pct - NEAR_ZERO
        score = max(0.0, 45.0 - (extension / 0.03) * 45.0)

    return round(min(100.0, max(0.0, score)), 2)


# ─── R8: Volume Behaviour Engine ─────────────────────────────────────────────

def r8_volume_behaviour(volumes: list, lookback: int = 20) -> tuple[float, bool, bool]:
    """
    Returns (volume_score 0-100, vol_dry_up, vol_expansion).
    Continuous scoring across three components:
      - Dry-Up Strength   (0-40 pts): how far below historical avg recent volume is
      - Expansion Strength (0-40 pts): how far above historical avg the latest bar is
      - Trend Component    (0-20 pts): recent vs prior window ratio (improving direction)
    Neutral volume scores ~50. Dry-up scores 60-80. Expansion after dry-up scores 80-100.
    """
    if len(volumes) < 5:
        return 50.0, False, False

    vols = np.array(volumes, dtype=float)
    hist_avg  = vols[-lookback:].mean() if len(vols) >= lookback else vols.mean()
    if hist_avg <= 0:
        return 50.0, False, False

    recent_5  = vols[-5:].mean()
    prior_10  = vols[-15:-5].mean() if len(vols) >= 15 else hist_avg
    last_bar  = float(vols[-1])

    # --- Dry-Up Strength (0-40 pts) ---
    # ratio < 1.0 means drying up; ratio > 1.0 means above average
    dry_ratio = recent_5 / hist_avg          # 1.0 = neutral, 0.0 = zero volume
    # Score: 40 pts at ratio=0, 20 pts at ratio=0.70, 0 pts at ratio=1.0+
    dry_score = max(0.0, min(40.0, (1.0 - dry_ratio) * 40.0 / 0.30))
    # Clamp: no dry-up credit if ratio >= 1.0
    dry_score = 0.0 if dry_ratio >= 1.0 else dry_score
    vol_dry_up = dry_ratio < 0.70

    # --- Expansion Strength (0-40 pts) ---
    # Expansion on last bar relative to historical avg
    exp_ratio = last_bar / hist_avg           # 1.0 = neutral, 2.0 = double avg
    # Score: 0 pts at ratio=1.0, 40 pts at ratio=2.5+
    exp_score = max(0.0, min(40.0, (exp_ratio - 1.0) * 40.0 / 1.5))
    vol_expansion = exp_ratio >= 1.5

    # --- Trend Component (0-20 pts) ---
    # recent_5 vs prior_10: is volume improving in the right direction?
    # For dry-up phase: recent < prior = constructive (drying up = good)
    # For expansion phase: recent > prior = constructive (expanding = good)
    trend_ratio = recent_5 / prior_10 if prior_10 > 0 else 1.0
    if vol_dry_up:
        # Drying up: lower recent than prior = better (ratio < 1 is good)
        trend_score = max(0.0, min(20.0, (1.0 - trend_ratio) * 20.0 / 0.5))
    else:
        # Expanding: higher recent than prior = better (ratio > 1 is good)
        trend_score = max(0.0, min(20.0, (trend_ratio - 1.0) * 20.0 / 0.5))

    # Combine: neutral baseline is 50
    # Pure neutral (no dry-up, no expansion): dry=0, exp=0, trend~0 → raw=0
    # Map raw [0,100] to output [50,100] when signal present; [0,50] when adverse
    raw_score = dry_score + exp_score + trend_score  # 0-100

    if not vol_dry_up and not vol_expansion:
        # Neutral volume: score near 50
        score = 45.0 + trend_score * 0.25
    elif vol_dry_up and vol_expansion:
        # Dry-up then expansion on last bar = ideal setup
        score = 70.0 + dry_score * 0.30 + trend_score * 0.20
        score = min(100.0, score)
    elif vol_dry_up:
        score = 50.0 + dry_score * 0.75 + trend_score * 0.25
        score = min(90.0, score)
    else:
        # Expansion only (no prior dry-up)
        score = 40.0 + exp_score * 0.75 + trend_score * 0.25
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

        # R6
        r6_score, higher_low, recovery_pct = r6_recovery(highs, lows, closes)

        # R7
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
