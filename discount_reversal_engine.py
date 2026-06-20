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

def r2_discount_quality(close: float, eq: float, discount_bottom: float,
                         premium_top: float) -> tuple[float, float, float, float]:
    """
    Returns (quality_score 0-100, dist_to_bottom, dist_to_eq, discount_depth).
    """
    if eq <= 0 or discount_bottom <= 0 or premium_top <= discount_bottom:
        return 0.0, 0.0, 0.0, 0.0

    dist_to_bottom = (close - discount_bottom) / close if close > 0 else 0
    dist_to_eq = (eq - close) / close if close > 0 else 0
    discount_depth = (eq - discount_bottom) / eq if eq > 0 else 0

    # Score: reward being close to bottom, having deep discount zone
    # Closer to bottom = higher quality; deeper discount zone = better opportunity
    proximity_score = max(0, 1 - dist_to_bottom / 0.30) * 50   # up to 50 pts
    depth_score = min(discount_depth / 0.20, 1.0) * 30          # up to 30 pts
    upside_score = min(dist_to_eq / 0.10, 1.0) * 20             # up to 20 pts

    quality = proximity_score + depth_score + upside_score

    return (round(quality, 2), round(dist_to_bottom, 4),
            round(max(dist_to_eq, 0), 4), round(discount_depth, 4))


# ─── R3: Discount Residency Engine ───────────────────────────────────────────

def r3_discount_residency(days_in_discount: int) -> tuple[int, float]:
    """
    Returns (days, residency_score 0-100).
    Sweet spot: 5-30 days. Too short = not established. Too long = stale.
    """
    if days_in_discount <= 0:
        return 0, 0.0
    if days_in_discount < 3:
        score = days_in_discount / 3 * 40
    elif days_in_discount <= 30:
        # Peak at 10-20 days
        if days_in_discount <= 20:
            score = 40 + (days_in_discount - 3) / 17 * 60
        else:
            score = 100.0
    elif days_in_discount <= 60:
        score = 100 - (days_in_discount - 30) / 30 * 30  # decay to 70
    else:
        score = max(0, 70 - (days_in_discount - 60) / 40 * 70)

    return days_in_discount, round(score, 2)


# ─── R4: Base Formation Engine (MOST IMPORTANT) ───────────────────────────────

def r4_base_formation(highs: list, lows: list, closes: list, volumes: list,
                       atr_period: int = 14) -> tuple[float, float, float, int]:
    """
    Returns (base_score 0-100, range_compression, atr_compression, base_duration).
    Uses last N candles to measure consolidation quality.
    """
    if len(closes) < 10:
        return 0.0, 0.0, 0.0, 0

    closes_arr = np.array(closes, dtype=float)
    highs_arr = np.array(highs, dtype=float)
    lows_arr = np.array(lows, dtype=float)

    # Range compression: recent range vs prior range
    lookback = min(20, len(closes_arr))
    half = lookback // 2

    recent_highs = highs_arr[-half:]
    recent_lows = lows_arr[-half:]
    prior_highs = highs_arr[-lookback:-half]
    prior_lows = lows_arr[-lookback:-half]

    recent_range = (recent_highs.max() - recent_lows.min()) / closes_arr[-1]
    prior_range = (prior_highs.max() - prior_lows.min()) / closes_arr[-half - 1] if len(prior_highs) > 0 else recent_range

    range_compression = 1 - (recent_range / prior_range) if prior_range > 0 else 0
    range_compression = max(0, min(range_compression, 1))

    # ATR compression: current ATR vs prior ATR
    def compute_atr(h, l, c, period=14):
        tr = np.maximum(h[1:] - l[1:],
             np.maximum(abs(h[1:] - c[:-1]), abs(l[1:] - c[:-1])))
        if len(tr) < period:
            return tr.mean() if len(tr) > 0 else 0
        return tr[-period:].mean()

    if len(closes_arr) >= 20:
        recent_atr = compute_atr(highs_arr[-14:], lows_arr[-14:], closes_arr[-14:])
        prior_atr  = compute_atr(highs_arr[-28:-14], lows_arr[-28:-14], closes_arr[-28:-14])
        atr_compression = 1 - (recent_atr / prior_atr) if prior_atr > 0 else 0
        atr_compression = max(0, min(atr_compression, 1))
    else:
        atr_compression = range_compression  # fallback

    # Base duration: count candles in tight range (within 5% band)
    base_high = closes_arr[-1] * 1.05
    base_low  = closes_arr[-1] * 0.95
    duration = 0
    for i in range(len(closes_arr) - 1, -1, -1):
        if lows_arr[i] >= base_low and highs_arr[i] <= base_high:
            duration += 1
        else:
            break

    # Score components (30% most important station)
    range_comp_score = range_compression * 40   # up to 40 pts
    atr_comp_score   = atr_compression * 35     # up to 35 pts
    duration_score   = min(duration / 15, 1.0) * 25  # up to 25 pts; sweet spot ~15 days

    base_score = range_comp_score + atr_comp_score + duration_score

    return (round(base_score, 2), round(range_compression, 4),
            round(atr_compression, 4), duration)


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

def r6_recovery(highs: list, lows: list, closes: list,
                 choch_present: bool = False, bos_present: bool = False) -> tuple[float, bool, float]:
    """
    Returns (recovery_score 0-100, higher_low, recovery_pct).
    CHOCH/BOS are supporting signals only — not mandatory.
    """
    if len(lows) < 6:
        return 0.0, False, 0.0

    lows_arr = np.array(lows, dtype=float)
    highs_arr = np.array(highs, dtype=float)
    closes_arr = np.array(closes, dtype=float)

    # Higher low: last pivot low > previous pivot low
    recent_low = lows_arr[-3:].min()
    prior_low  = lows_arr[-10:-3].min() if len(lows_arr) >= 10 else lows_arr[:-3].min()
    higher_low = recent_low > prior_low * 0.99

    # Recovery leg: how much has price recovered from the low
    period_low = lows_arr[-20:].min() if len(lows_arr) >= 20 else lows_arr.min()
    recovery_pct = (closes_arr[-1] - period_low) / period_low if period_low > 0 else 0
    recovery_pct = max(0, min(recovery_pct, 0.30))  # cap at 30%

    score = 0.0
    if higher_low:
        score += 45.0
    # Recovery leg score (up to 35 pts, sweet spot 3-15%)
    if recovery_pct >= 0.03:
        score += min(recovery_pct / 0.15, 1.0) * 35
    # Supporting signals (NOT mandatory — bonus only)
    if choch_present:
        score = min(score + 10, 100)
    if bos_present:
        score = min(score + 10, 100)

    return round(score, 2), bool(higher_low), round(recovery_pct, 4)


# ─── R7: MACD Phase Engine ───────────────────────────────────────────────────

def r7_macd_phase(macd_val: float, macd_hist: float, macd_signal_val: float = 0.0) -> float:
    """
    Returns macd_score 0-100.
    Preferred: MACD below zero. Acceptable: near zero. Reject: strongly extended above zero.
    Acts as constitutional filter — strongly negative MACD is ideal (early phase).
    """
    # Ideal: macd_val < 0 (below zero line)
    # Acceptable: -0.5 to +0.5 normalized
    # Reject: macd_val strongly positive

    # Normalize by using macd_hist sign and magnitude
    if macd_val is None:
        return 50.0

    if macd_val < 0:
        # Below zero — most preferred
        if macd_hist < 0 and abs(macd_hist) < abs(macd_val) * 0.5:
            # Histogram shrinking negative → bullish divergence forming
            score = 90.0
        elif macd_hist >= 0:
            # MACD below zero but histogram positive → curling up
            score = 85.0
        else:
            score = 75.0
    elif macd_val < abs(macd_val) * 0.20:
        # Near zero
        score = 60.0 if macd_hist >= 0 else 50.0
    else:
        # Above zero — penalize based on extension
        # Reject strongly extended
        score = max(0, 40 - macd_val * 10)

    return round(min(100, max(0, score)), 2)


# ─── R8: Volume Behaviour Engine ─────────────────────────────────────────────

def r8_volume_behaviour(volumes: list, lookback: int = 20) -> tuple[float, bool, bool]:
    """
    Returns (volume_score 0-100, vol_dry_up, vol_expansion).
    Dry-up during consolidation + expansion on recovery = best setup.
    Neutral volume acceptable.
    """
    if len(volumes) < 5:
        return 50.0, False, False

    vols = np.array(volumes, dtype=float)
    avg_vol = vols[-lookback:].mean() if len(vols) >= lookback else vols.mean()

    recent_vol = vols[-5:].mean()
    prior_vol  = vols[-15:-5].mean() if len(vols) >= 15 else avg_vol

    # Dry-up: recent volume < 70% of average
    vol_dry_up = recent_vol < avg_vol * 0.70

    # Expansion: last 3 bars above average
    vol_expansion = vols[-1] > avg_vol * 1.5 or vols[-3:].mean() > avg_vol * 1.3

    score = 50.0  # neutral baseline
    if vol_dry_up:
        score = 80.0  # dry-up during base = constructive
    if vol_expansion and not vol_dry_up:
        score = 75.0  # expansion on recovery
    if vol_dry_up and len(vols) >= 2 and vols[-1] > avg_vol:
        score = 90.0  # dry-up followed by expansion = ideal

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

        # R2
        r2_score, dist_bot, dist_eq, depth = r2_discount_quality(close, eq, discount_bottom, premium_top)

        # R3
        r3_days, r3_score = r3_discount_residency(days_in_discount)

        # R4
        r4_score, range_comp, atr_comp, base_dur = r4_base_formation(highs, lows, closes, volumes)

        # R5
        r5_score, no_new_low, failed_bd = r5_low_protection(lows, closes)

        # R6
        choch = bool(price_data.get('snap_choch', pd.Series([0])).iloc[-1]) if 'snap_choch' in price_data.columns else False
        bos   = bool(price_data.get('snap_bos', pd.Series([0])).iloc[-1]) if 'snap_bos' in price_data.columns else False
        r6_score, higher_low, recovery_pct = r6_recovery(highs, lows, closes, choch, bos)

        # R7
        r7_score = r7_macd_phase(macd_val, macd_hist)

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
