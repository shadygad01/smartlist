"""
signal_engine.py — EGX Scanner Signal Scoring Engine
Extracted from main.py. No logic changes — pure extraction + GateConfig wrapper.
"""

import os
import json
import pandas as pd
import numpy as np

# =========================================
# CONFIG LOADER
# =========================================

_BASE_DIR = os.path.dirname(os.path.abspath(__file__))

_DEFAULT_WEIGHTS = {
    "r1_price":     30,
    "r2_ob":        10,
    "r3_liquidity": 20,
    "r4_htf":       10,
    "r5_avwap":      8,
    "r6_macd":       4,
    "r7_div":        3,
    "r8_demand":    15,
}

_DEFAULT_GATES = {
    "sc_ob_min_quality":        0.5,
    "sc_liquidity_quantile":    0.10,
    "sc_liquidity_vol_mult":    2.5,
    "sc_htf_lookback":          80,
    "sc_htf_ma_long":           200,
    "sc_htf_ma_short":          50,
    "sc_avwap_gap_cap":         2.0,
    "sc_demand_sv_vol_mult":    2.5,
    "sc_demand_sv_range_ratio": 0.5,
    "sc_demand_sv_lookback":    30,
    "sc_demand_hvn_bins":       20,
    "sc_demand_hvn_pct":        0.70,
    "swings_lookback":          80,
    "macd_fast":                12,
    "macd_slow":                26,
    "macd_signal":               9,
}


class GateConfig:
    def __init__(self, gates_path=None, weights_path=None):
        if gates_path is None:
            gates_path = os.path.join(_BASE_DIR, "config", "gates_config.json")
        if weights_path is None:
            weights_path = os.path.join(_BASE_DIR, "config", "weights.json")

        self.gates = dict(_DEFAULT_GATES)
        self.weights = dict(_DEFAULT_WEIGHTS)

        if os.path.exists(gates_path):
            try:
                with open(gates_path) as f:
                    loaded = json.load(f)
                self.gates.update({k: v for k, v in loaded.items()
                                   if k in _DEFAULT_GATES})
            except Exception:
                pass

        if os.path.exists(weights_path):
            try:
                with open(weights_path) as f:
                    loaded = json.load(f)
                self.weights.update({k: v for k, v in loaded.items()
                                     if k in _DEFAULT_WEIGHTS})
            except Exception:
                pass

        # Convenience attributes — gates
        self.sv_vol_mult    = self.gates["sc_demand_sv_vol_mult"]
        self.sv_range_ratio = self.gates["sc_demand_sv_range_ratio"]
        self.sv_lookback    = self.gates["sc_demand_sv_lookback"]
        self.hvn_bins       = self.gates["sc_demand_hvn_bins"]
        self.hvn_pct        = self.gates["sc_demand_hvn_pct"]
        self.swings_lb      = self.gates["swings_lookback"]

        # Convenience attributes — weights
        self.w_price  = self.weights["r1_price"]
        self.w_ob     = self.weights["r2_ob"]
        self.w_liq    = self.weights["r3_liquidity"]
        self.w_htf    = self.weights["r4_htf"]
        self.w_avwap  = self.weights["r5_avwap"]
        self.w_macd   = self.weights["r6_macd"]
        self.w_div    = self.weights["r7_div"]
        self.w_dz     = self.weights["r8_demand"]


# Module-level default config instance (used when functions are called without gate_config)
_default_cfg = GateConfig()

# Module-level weight shorthands (mirroring main.py globals — updated from config)
W_PRICE = _default_cfg.w_price
W_OB    = _default_cfg.w_ob
W_LIQ   = _default_cfg.w_liq
W_HTF   = _default_cfg.w_htf
W_AVWAP = _default_cfg.w_avwap
W_MACD  = _default_cfg.w_macd
W_DIV   = _default_cfg.w_div
W_DZ    = _default_cfg.w_dz


def reload_weights(config_path: str = "config/") -> dict:
    """
    Hot-reload weights from config/weights.json into module-level globals.
    Call after production_promoter.promote() to pick up deployed weights
    without restarting the process.
    Returns dict of new weight values.
    """
    global _default_cfg, W_PRICE, W_OB, W_LIQ, W_HTF, W_AVWAP, W_MACD, W_DIV, W_DZ
    _weights_path = os.path.join(config_path, "weights.json")
    _gates_path = os.path.join(config_path, "gates_config.json")
    _default_cfg = GateConfig(gates_path=_gates_path, weights_path=_weights_path)
    W_PRICE = _default_cfg.w_price
    W_OB    = _default_cfg.w_ob
    W_LIQ   = _default_cfg.w_liq
    W_HTF   = _default_cfg.w_htf
    W_AVWAP = _default_cfg.w_avwap
    W_MACD  = _default_cfg.w_macd
    W_DIV   = _default_cfg.w_div
    W_DZ    = _default_cfg.w_dz
    return {
        "w_price": W_PRICE, "w_ob": W_OB, "w_liq": W_LIQ, "w_htf": W_HTF,
        "w_avwap": W_AVWAP, "w_macd": W_MACD, "w_div": W_DIV, "w_dz": W_DZ,
    }


# =========================================
# HELPERS
# =========================================

def col(df, name):
    if name not in df.columns:
        return pd.Series(dtype=float)
    return df[name].dropna()


# =========================================
# INDICATORS
# =========================================

def calc_macd(close):
    m = close.ewm(span=12).mean() - close.ewm(span=26).mean()
    s = m.ewm(span=9).mean()
    return m, s, m - s


def calc_avwap(df):
    """
    Anchored VWAP — anchor على آخر swing low حقيقي (أدنى نقطة في آخر 60 bar).
    بدل anchor ثابت على 1 يناير اللي بيعطي نتائج عشوائية.
    Returns: (avwap, avwap_lower_band)
    """
    d = pd.DataFrame({
        "H": col(df, "High"), "L": col(df, "Low"),
        "C": col(df, "Close"), "V": col(df, "Volume"),
    }).dropna()

    if len(d) < 5:
        v = float(d["C"].iloc[-1]) if len(d) else 0.0
        return v, v

    # anchor = آخر swing low في 60 bar
    lookback   = min(60, len(d))
    tail_low   = d["L"].tail(lookback)
    anchor_idx = int(tail_low.values.argmin())
    anchor_pos = len(d) - lookback + anchor_idx

    # لو الـ anchor هو آخر 3 bars → fallback لـ 20 bar قبله
    if anchor_pos >= len(d) - 3:
        anchor_pos = max(0, len(d) - 20)

    d_anc = d.iloc[anchor_pos:].copy()
    if len(d_anc) < 3:
        d_anc = d.copy()

    tp     = (d_anc["H"] + d_anc["L"] + d_anc["C"]) / 3
    av     = (tp * d_anc["V"]).cumsum() / d_anc["V"].cumsum()
    cum_v  = d_anc["V"].cumsum()
    var_vw = ((tp - av) ** 2 * d_anc["V"]).cumsum() / cum_v.where(cum_v > 0, 1)
    std_vw = np.sqrt(var_vw.clip(lower=0)).fillna(0)
    lo     = av - std_vw

    return float(av.iloc[-1]), float(lo.iloc[-1])


def swings(df, lb=80):
    """
    Price range levels based on custom SMC framework:
      0.00 = lo  (swing low  — best buy)
      0.15 = buy_hi  (top of buy zone)
      0.50 = eq  (equilibrium)
      0.85 = sell_lo (bottom of sell zone)
      1.00 = hi  (swing high — best sell)
    Uses actual High/Low prices for accurate range measurement.
    """
    hi      = float(df["High"].tail(lb).max())
    lo      = float(df["Low"].tail(lb).min())
    rng     = hi - lo
    eq      = lo + rng * 0.50
    buy_hi  = lo + rng * 0.15   # top of buy zone  (0.15)
    sell_lo = lo + rng * 0.85   # bottom of sell zone (0.85)
    return hi, lo, eq, buy_hi, sell_lo


# =========================================
# STOPPING VOLUME & VOLUME PROFILE
# =========================================

def calc_stopping_volume(df, eq, lo, lookback=30, vol_mult=2.5, range_ratio=0.5):
    """
    Detect Stopping Volume candles inside the discount zone (price < EQ).
    A SV candle: high volume (effort) + narrow range (no result) + in discount.
    Returns: sv_detected(bool), sv_score(0-1), sv_desc(str)
    """
    needed = ["High", "Low", "Close", "Open", "Volume"]
    if not all(c in df.columns for c in needed) or len(df) < lookback + 5:
        return False, 0.0, "Insufficient data for SV scan", 0.0

    d          = df[needed].dropna().tail(lookback + 20)
    avg_vol    = d["Volume"].rolling(lookback).mean()
    candle_rng = d["High"] - d["Low"]
    avg_rng    = candle_rng.rolling(lookback).mean()

    # extract scan-window arrays (after rolling warmup) — avoids repeated .iloc[i] overhead
    c_close = d["Close"].values[lookback:]
    c_vol   = d["Volume"].values[lookback:]
    c_low   = d["Low"].values[lookback:]
    c_rng   = candle_rng.values[lookback:]
    a_vol   = avg_vol.values[lookback:]
    a_rng   = avg_rng.values[lookback:]

    discount_range = eq - lo
    with np.errstate(invalid="ignore", divide="ignore"):
        close_pos = np.where(c_rng > 0, (c_close - c_low) / c_rng, 0.0)

    mask = (
        (a_vol > 0) & (a_rng > 0) &
        (c_close < eq) &
        (c_vol >= vol_mult * a_vol) &
        (c_rng <= range_ratio * a_rng) &
        (c_rng > 0) &
        (close_pos >= 0.40)
    )

    idx = np.where(mask)[0]
    if len(idx) == 0:
        return False, 0.0, "No Stopping Volume detected in discount zone", 0.0

    vol_ratio = c_vol[idx] / a_vol[idx]
    depth     = (eq - c_close[idx]) / discount_range if discount_range > 0 else np.zeros(len(idx))
    scores    = depth * 0.6 + np.minimum(vol_ratio / 5, 1.0) * 0.4
    best_i    = int(np.argmax(scores))

    best_close     = float(c_close[idx[best_i]])
    best_vol_ratio = float(vol_ratio[best_i])
    best_depth     = float(depth[best_i])
    score          = float(min(1.0, scores[best_i]))
    desc = (f"Stopping Volume @ {best_close:.1f} — "
            f"vol {best_vol_ratio:.1f}x avg — "
            f"depth {best_depth*100:.0f}% into discount")
    return True, score, desc, best_close


def calc_volume_profile(df, eq, lo, buy_hi, bins=20, hvn_pct=0.70):
    """
    Build volume profile over full history; find HVN inside discount zone.
    Each bar's volume is distributed proportionally across its H-L price range.
    Returns: hvn_detected(bool), hvn_score(0-1), hvn_price(float), hvn_desc(str)
    """
    needed = ["High", "Low", "Close", "Volume"]
    if not all(c in df.columns for c in needed) or len(df) < 10:
        return False, 0.0, 0.0, "Insufficient data for VP scan"

    d         = df[needed].dropna()
    price_min = float(d["Low"].min())
    price_max = float(d["High"].max())
    if price_max <= price_min:
        return False, 0.0, 0.0, "Invalid price range for VP"

    bin_size  = (price_max - price_min) / bins
    vol_bins  = np.zeros(bins)
    bin_edges = np.linspace(price_min, price_max, bins + 1)

    h_arr = d["High"].values
    l_arr = d["Low"].values
    v_arr = d["Volume"].values.astype(float)
    valid = (v_arr > 0) & (h_arr > l_arr)
    h_arr, l_arr, v_arr = h_arr[valid], l_arr[valid], v_arr[valid]
    lo_bins = np.clip(((l_arr - price_min) / bin_size).astype(int), 0, bins - 1)
    hi_bins = np.clip(((h_arr - price_min) / bin_size).astype(int), 0, bins - 1)
    for i in range(len(h_arr)):
        span = hi_bins[i] - lo_bins[i] + 1
        vol_bins[lo_bins[i]: hi_bins[i] + 1] += v_arr[i] / span

    max_vol       = np.max(vol_bins)
    threshold     = max_vol * hvn_pct
    discount_hvns = []
    for b in range(bins):
        bin_price = (bin_edges[b] + bin_edges[b + 1]) / 2
        # HVN لازم يكون في Buy Zone (0–15%) فقط
        if bin_price >= buy_hi:
            continue
        if vol_bins[b] >= threshold:
            depth = (eq - bin_price) / (eq - lo) if (eq - lo) > 0 else 0
            discount_hvns.append({"price": bin_price,
                                   "vol": vol_bins[b], "depth": depth})

    if not discount_hvns:
        return False, 0.0, 0.0, "No HVN in discount zone"

    best      = max(discount_hvns, key=lambda x: x["vol"])
    hvn_score = min(1.0, best["vol"] / max_vol)
    desc      = (f"HVN @ {best['price']:.1f} — "
                 f"{best['vol']/max_vol*100:.0f}% of peak vol — "
                 f"depth {best['depth']*100:.0f}% into discount")
    return True, hvn_score, best["price"], desc


def sc_demand_zone(df, eq, lo, buy_hi, _sv=None, _hvn=None):
    """
    Demand Zone Confluence = Stopping Volume + Volume Profile HVN, both in discount.
    SV + HVN  → full W_DZ  (true institutional demand zone)
    SV only   → 60% W_DZ   (absorption present, no volume memory)
    HVN only  → 40% W_DZ   (volume memory, no absorption candle)
    Neither   → 0
    _sv/_hvn: pre-computed tuples from calc_stopping_volume / calc_volume_profile
              to avoid recomputing when called from analyze().
    """
    sv_hit, sv_score, sv_desc, _sv_price = _sv  if _sv  is not None else calc_stopping_volume(df, eq, lo)
    hvn_hit, hvn_score, _, hvn_desc      = _hvn if _hvn is not None else calc_volume_profile(df, eq, lo, buy_hi)

    if sv_hit and hvn_hit:
        pts  = W_DZ
        desc = f"DEMAND ZONE CONFIRMED — {sv_desc} | {hvn_desc}"
    elif sv_hit:
        pts  = round(W_DZ * 0.60)
        desc = f"Stopping Volume only — {sv_desc} | No HVN: {hvn_desc}"
    elif hvn_hit:
        pts  = round(W_DZ * 0.40)
        desc = f"HVN only — {hvn_desc} | No SV: {sv_desc}"
    else:
        pts  = 0
        desc = f"No demand confluence — SV: {sv_desc} | VP: {hvn_desc}"

    return pts, desc


# =========================================
# SMC SCORING
# =========================================

def sc_price(cur, lo, hi, eq, buy_hi, sell_lo):
    """
    Score price position using custom SMC zones:
      Buy Zone   : lo  → buy_hi  (0.00–0.15) — max score, degrades toward buy_hi
      Mid Disc.  : buy_hi → eq   (0.15–0.50) — partial score, degrades toward EQ
      EQ or above: eq → hi       (0.50–1.00) — 0, gate already blocks these
    """
    rng = hi - lo
    if rng <= 0: return 0, "Invalid range"

    if cur <= buy_hi:
        # Inside buy zone (0.00–0.15): score 100% → 60% linearly
        ratio = (cur - lo) / (buy_hi - lo) if (buy_hi - lo) > 0 else 0
        pts   = max(round(W_PRICE * (1.0 - ratio * 0.40)), 0)
        dist_pct = round((cur - lo) / lo * 100, 1) if lo > 0 else 0
        return pts, f"Buy Zone @ {cur:.1f} — {dist_pct}% above Deep Discount floor — {pts}/{W_PRICE}"

    if cur < eq:
        # Mid-discount (0.15–0.50): score 60% → 0% linearly
        ratio = (cur - buy_hi) / (eq - buy_hi) if (eq - buy_hi) > 0 else 1
        pts   = max(round(W_PRICE * 0.60 * (1.0 - ratio)), 0)
        dist_to_dd = round((cur - buy_hi) / rng * 100, 1)
        return pts, f"Mid-Discount @ {cur:.1f} — {dist_to_dd}% away from Deep Discount — {pts}/{W_PRICE}"

    pct_above_eq = round((cur - eq) / rng * 100, 1)
    return 0, f"Premium Zone @ {cur:.1f} — {pct_above_eq}% above EQ — SMC setup inactive"


def sc_ob(df, cur, eq, lo, buy_hi):
    """
    Order Block Quality — OB حقيقي بناءً على:
    1. آخر bearish candle قبل move صاعد قوي (impulse ≥ 1.5x avg range)
    2. OB لازم يكون في discount zone (تحت EQ)
    3. السعر الحالي لازم يكون فوق الـ OB (مش اخترقه لتحت)

    لو مفيش OB حقيقي → يرجع 0 بدل ما يبعت رقم مضلل.
    """
    needed = ["Open", "High", "Low", "Close"]
    if not all(c in df.columns for c in needed) or len(df) < 10:
        return 0, "Insufficient data for OB detection"

    d   = df[needed].dropna()
    rng = d["High"] - d["Low"]
    avg_rng = float(rng.rolling(20).mean().iloc[-1]) if len(d) >= 20 else float(rng.mean())

    if avg_rng <= 0:
        return 0, "Invalid range data"

    discount_range = eq - lo
    if discount_range <= 0:
        return 0, "Invalid discount range"

    # ── بحث عن OB حقيقي في آخر 40 bar ───────────────────────────────────────
    ob_candidates = []
    search   = d.tail(40)
    s_open   = search["Open"].values
    s_close  = search["Close"].values
    s_low    = search["Low"].values
    s_high   = search["High"].values
    n_search = len(search)

    for i in range(n_search - 2):
        c_open  = s_open[i]
        c_close = s_close[i]
        c_low   = s_low[i]
        c_high  = s_high[i]

        # OB candle: bearish (close < open)
        if c_close >= c_open:
            continue

        # الـ 1-2 candles التالية لازم يكون فيها impulse صاعد قوي (≥ 1.5x avg range)
        has_impulse = False
        for j in range(i + 1, min(i + 3, n_search)):
            if s_high[j] - s_low[j] >= avg_rng * 1.5:
                has_impulse = True
                break
        if not has_impulse:
            continue

        # OB zone = body of the bearish candle (open → close)
        ob_top = max(c_open, c_close)   # top of bearish body
        ob_bot = min(c_open, c_close)   # bottom of bearish body (mitigation level)

        # OB zone must be in Buy Zone (0–15%)
        if ob_top >= buy_hi:
            continue

        # OB is mitigated if price closed below the body bottom
        if cur <= ob_bot:
            continue

        # quality based on zone midpoint depth in discount zone
        ob_mid  = (ob_top + ob_bot) / 2
        ratio   = (ob_mid - lo) / discount_range
        quality = max(0.0, 1.0 - ratio)

        dist = abs(cur - ob_top) / cur   # distance to OB top (natural entry point)
        ob_candidates.append({
            "top":     ob_top,
            "bot":     ob_bot,
            "quality": quality,
            "dist":    dist,
            "candle":  i,
        })

    if not ob_candidates:
        return 0, "No valid OB found in discount zone (last 40 bars)"

    # أفضل OB: أعلى quality × proximity
    best = max(ob_candidates,
               key=lambda x: x["quality"] * max(0.1, 1 - x["dist"] * 5))

    ob_top = best["top"]
    ob_bot = best["bot"]
    qual   = best["quality"]
    dist   = best["dist"]
    zone_lbl = "Buy Zone" if ob_top <= buy_hi else "Mid-Discount"

    if dist > 0.10:
        pts = round(W_OB * qual * 0.15)
        return pts, f"OB zone {ob_bot:.1f}–{ob_top:.1f} [{zone_lbl}] — far ({dist*100:.0f}% away) → {pts}/{W_OB}"
    if dist < 0.02:
        pts = round(W_OB * qual)
        return pts, f"At OB zone {ob_bot:.1f}–{ob_top:.1f} [{zone_lbl}] — quality {qual*100:.0f}% → {pts}/{W_OB}"
    if dist < 0.05:
        pts = round(W_OB * qual * 0.6)
        return pts, f"Near OB zone {ob_bot:.1f}–{ob_top:.1f} [{zone_lbl}] — quality {qual*100:.0f}% → {pts}/{W_OB}"
    pts = round(W_OB * qual * 0.30)
    return pts, f"OB zone {ob_bot:.1f}–{ob_top:.1f} [{zone_lbl}] — moderate distance → {pts}/{W_OB}"


def sc_liquidity(df, cur):
    """
    Liquidity Context — 3 أنواع من الـ liquidity events:
    1. Sweep & Reverse   : السعر اخترق swing low ثم رجع فوقه (stop hunt)
    2. Equal Lows (EQL)  : مستويات متقاربة تشير لـ liquidity pool تحت
    3. Rejection Wick    : شمعة بـ lower wick طويل (≥ 2x body) في discount

    الأعلى قيمة = Sweep & Reverse (إثبات أن السوق امتص البيع وعكس)
    """
    needed = ["High", "Low", "Close", "Open"]
    close  = df["Close"].dropna() if "Close" in df.columns else pd.Series(dtype=float)

    if not all(c in df.columns for c in needed) or len(df) < 10:
        return 0, "Insufficient data for liquidity scan"

    d     = df[needed].dropna()
    score = 0
    desc  = []

    # ── 1. Sweep & Reverse (أقوى إشارة) ──────────────────────────────────────
    if len(d) >= 10:
        recent   = d.tail(10)
        swing_lo = float(d["Low"].tail(20).quantile(0.10))  # أدنى 10% من الـ 20 bar

        for i in range(1, len(recent) - 1):
            c_low   = float(recent["Low"].iloc[i])
            c_close = float(recent["Close"].iloc[i])

            # اخترق الـ swing low ثم أقفل فوقه
            if c_low < swing_lo and c_close > swing_lo:
                score += W_LIQ
                desc.append(f"Sweep & Reverse @ {c_low:.1f} — stop hunt confirmed ✓")
                break

    # ── 2. Rejection Wick في discount ─────────────────────────────────────────
    if score == 0 and len(d) >= 5:
        last5 = d.tail(5)
        for i in range(len(last5)):
            o = float(last5["Open"].iloc[i])
            c = float(last5["Close"].iloc[i])
            l = float(last5["Low"].iloc[i])
            h = float(last5["High"].iloc[i])
            body       = abs(c - o)
            lower_wick = min(o, c) - l
            candle_rng = h - l

            if candle_rng <= 0:
                continue
            # lower wick ≥ 60% of candle range و close في upper 40%
            if lower_wick >= candle_rng * 0.60 and c >= l + candle_rng * 0.40:
                pts = round(W_LIQ * 0.6)
                score = max(score, pts)
                desc.append(f"Rejection wick @ {l:.1f} — lower wick {lower_wick/candle_rng*100:.0f}% of range")

    # ── 3. Equal Lows (liquidity pool below) ──────────────────────────────────
    if score == 0 and len(d) >= 15:
        lows = d["Low"].tail(15).values
        eql_count = 0
        base_lo   = float(d["Low"].tail(15).min())
        for lv in lows:
            if abs(lv - base_lo) / base_lo < 0.005:   # within 0.5%
                eql_count += 1
        if eql_count >= 3:
            pts = round(W_LIQ * 0.4)
            score = pts
            desc.append(f"Equal Lows x{eql_count} @ {base_lo:.1f} — liquidity pool below")

    if not desc:
        desc.append("No liquidity event detected")

    return min(score, W_LIQ), " · ".join(desc)


def _find_pivots(high_series, low_series, left=3, right=3):
    """Identify swing highs/lows using left/right bar confirmation."""
    h = high_series.values
    l = low_series.values
    n = min(len(h), len(l))
    swing_highs, swing_lows = [], []
    for i in range(left, n - right):
        if all(h[i] >= h[i - j] for j in range(1, left + 1)) and \
           all(h[i] >= h[i + j] for j in range(1, right + 1)):
            swing_highs.append(float(h[i]))
        if all(l[i] <= l[i - j] for j in range(1, left + 1)) and \
           all(l[i] <= l[i + j] for j in range(1, right + 1)):
            swing_lows.append(float(l[i]))
    return swing_highs, swing_lows


def sc_htf(df):
    """
    Higher Timeframe Trend Quality — 3 components (total W_HTF pts):
      1. MA200 position  : price vs 200-day MA         (40% of W_HTF)
      2. MA50 slope      : is 50-day MA rising?         (30% of W_HTF)
      3. HH/HL structure : Higher Highs & Higher Lows   (30% of W_HTF)
    Scoring:
      - Full score  → clear recovery signals present
      - Partial     → mixed signals
      - Zero        → deep downtrend, no structure yet
    """
    close = df["Close"].dropna()
    n = len(close)

    pts  = 0
    desc = []

    # ── 1. MA200 position ────────────────────────────────────────────────────
    w1 = round(W_HTF * 0.40)
    if n >= 200:
        ma200 = float(close.rolling(200).mean().iloc[-1])
        cur   = float(close.iloc[-1])
        if cur >= ma200:
            pts += w1
            desc.append(f"Above MA200 ({ma200:.1f}) ✓")
        else:
            gap = round((ma200 - cur) / ma200 * 100, 1)
            if gap < 5:
                pts += round(w1 * 0.5)
                desc.append(f"Near MA200 ({ma200:.1f}, -{gap}%)")
            else:
                desc.append(f"Below MA200 ({ma200:.1f}, -{gap}%)")
    elif n >= 50:
        # حساب MA50 كبديل لو مفيش 200 يوم
        ma50 = float(close.rolling(50).mean().iloc[-1])
        cur  = float(close.iloc[-1])
        if cur >= ma50:
            pts += round(w1 * 0.6)
            desc.append(f"Above MA50 ({ma50:.1f}) [no MA200] ✓")
        else:
            desc.append(f"Below MA50 ({ma50:.1f}) [no MA200]")
    else:
        desc.append("Insufficient data for MA")

    # ── 2. MA50 slope (last 10 bars) ─────────────────────────────────────────
    w2 = round(W_HTF * 0.30)
    if n >= 60:
        ma50_series = close.rolling(50).mean().dropna()
        if len(ma50_series) >= 10:
            slope = float(ma50_series.iloc[-1]) - float(ma50_series.iloc[-10])
            if slope > 0:
                pts += w2
                desc.append(f"MA50 rising (+{slope:.2f}) ✓")
            elif slope > -float(close.iloc[-1]) * 0.01:
                pts += round(w2 * 0.4)
                desc.append(f"MA50 flattening ({slope:.2f})")
            else:
                desc.append(f"MA50 falling ({slope:.2f})")
    else:
        desc.append("MA50 slope: insufficient data")

    # ── 3. HH / HL structure (last 40 bars, pivot confirmation) ─────────────
    w3 = W_HTF - w1 - w2
    if n >= 20:
        lb_tail = min(40, n)
        h_ser = df["High"].dropna().tail(lb_tail) if "High" in df.columns else close.tail(lb_tail)
        l_ser = df["Low"].dropna().tail(lb_tail)  if "Low"  in df.columns else close.tail(lb_tail)
        s_highs, s_lows = _find_pivots(h_ser, l_ser, left=3, right=3)

        if len(s_highs) >= 2 and len(s_lows) >= 2:
            hh = s_highs[-1] > s_highs[-2]
            hl = s_lows[-1]  > s_lows[-2]
            if hh and hl:
                pts += w3
                desc.append("HH+HL structure confirmed ✓")
            elif hh or hl:
                pts += round(w3 * 0.5)
                desc.append(f"Partial structure (HH:{hh}, HL:{hl})")
            else:
                desc.append("No HH/HL — downtrend structure")
        else:
            desc.append(f"Insufficient pivots ({len(s_highs)} highs, {len(s_lows)} lows) — no structure")
    else:
        desc.append("HH/HL: insufficient data")

    return pts, " | ".join(desc)


def sc_avwap(cur, av, av_lo):
    if cur <= av_lo: return W_AVWAP, f"At/below AVWAP lower band {av_lo:.1f}"
    if cur < av: return max(round(((av - cur) / (av - av_lo)) * (W_AVWAP - 1)), 1), f"Below AVWAP {av:.1f}"
    return 0, f"Above AVWAP {av:.1f}"


def sc_macd(close, _macd=None):
    if len(close) < 15: return 0, "Not enough data"
    m, sg, h = _macd if _macd is not None else calc_macd(close)
    macd_now  = m.iloc[-1]
    macd_prev = m.iloc[-2]
    sig_now   = sg.iloc[-1]
    sig_prev  = sg.iloc[-2]
    # فوق الصفر → صفر دايماً
    if macd_now >= 0:
        return 0, f"MACD above zero ({macd_now:.4f}) — no score"
    # تحت الصفر + تقاطع صاعد (crossover) → 4/4
    crossed_up = macd_prev <= sig_prev and macd_now > sig_now
    if crossed_up:
        return W_MACD, f"Bullish crossover BELOW zero ({macd_now:.4f}) — 4/4"
    # تحت الصفر بدون تقاطع → 2/4
    half = round(W_MACD / 2)
    return half, f"MACD below zero ({macd_now:.4f}), no cross yet — 2/4"


def _calc_rsi(close, period=14):
    """RSI حقيقي بـ Wilder smoothing."""
    delta = close.diff()
    gain  = delta.clip(lower=0)
    loss  = (-delta).clip(lower=0)
    avg_g = gain.ewm(alpha=1/period, min_periods=period, adjust=False).mean()
    avg_l = loss.ewm(alpha=1/period, min_periods=period, adjust=False).mean()
    # avg_l == 0 means no losses → RSI = 100; use where() to avoid NaN propagation
    rsi = avg_l.copy()
    rsi[:] = 100.0
    has_loss = avg_l > 0
    rs = avg_g[has_loss] / avg_l[has_loss]
    rsi[has_loss] = 100 - (100 / (1 + rs))
    rsi[avg_g == 0] = 0.0   # no gains either → RSI = 0 (flat price after warmup)
    return rsi


def sc_div(close, ml):
    """
    Bullish Divergence Detection — RSI + MACD:
      - Price makes Lower Low (LL)  while RSI  makes Higher Low → RSI  divergence
      - Price makes Lower Low (LL)  while MACD makes Higher Low → MACD divergence
    Lookback: last 30 bars, comparing last 2 swing lows (simple: min of halves).
    Scoring:
      Both divergences  → W_DIV      (3/3)
      RSI  only         → W_DIV * 0.7 (2/3 rounded)
      MACD only         → W_DIV * 0.5 (1-2/3)
      None              → 0
    """
    if len(close) < 30:
        return 0, "Insufficient data for divergence"

    # تقسيم آخر 30 bar لنصين — نقارن الـ swing low في كل نص
    half = 15
    tail = close.tail(30)

    price_lo1 = float(tail.iloc[:half].min())   # أول نص (قديم)
    price_lo2 = float(tail.iloc[half:].min())   # تاني نص (حديث)

    # لازم يكون في lower low في السعر عشان يبقى divergence حقيقي
    if price_lo2 >= price_lo1 * 0.998:
        return 0, f"No price LL (lo1={price_lo1:.1f}, lo2={price_lo2:.1f}) — no divergence"

    signals = []

    # ── RSI divergence ────────────────────────────────────────────────────────
    if len(close) >= 44:   # 14 period warmup + 30 tail
        rsi    = _calc_rsi(close).dropna()
        if len(rsi) >= 30:
            rsi_tail = rsi.tail(30)
            rsi_lo1  = float(rsi_tail.iloc[:half].min())
            rsi_lo2  = float(rsi_tail.iloc[half:].min())
            if rsi_lo2 > rsi_lo1 * 1.01:   # RSI higher low (+1% tolerance)
                signals.append(f"RSI div (RSI {rsi_lo1:.1f}→{rsi_lo2:.1f} ↑, price ↓)")

    # ── MACD divergence ───────────────────────────────────────────────────────
    if len(ml) >= 30:
        ml_tail = ml.tail(30)
        ml_lo1  = float(ml_tail.iloc[:half].min())
        ml_lo2  = float(ml_tail.iloc[half:].min())
        if ml_lo2 > ml_lo1 * 1.01:
            signals.append(f"MACD div (MACD {ml_lo1:.4f}→{ml_lo2:.4f} ↑, price ↓)")

    if len(signals) == 2:
        return W_DIV, "STRONG: " + " | ".join(signals)
    elif len(signals) == 1:
        if "RSI" in signals[0]:
            pts = round(W_DIV * 0.7)
        else:
            pts = round(W_DIV * 0.5)
        return pts, signals[0]
    else:
        return 0, f"No divergence (price LL confirmed: {price_lo1:.1f}→{price_lo2:.1f}, but indicators confirmed trend)"


# Alias for callers using the full name
sc_divergence = sc_div


# =========================================
# COMPOSITE SCORER
# =========================================

def score_signal(symbol, df, hi, lo, eq, buy_hi, sell_lo, gate_config=None):
    """
    Run all 8 sc_* scoring functions and return a unified result dict.

    Returns dict with keys:
      r1_price, r2_ob, r3_liquidity, r4_htf, r5_avwap, r6_macd, r7_div, r8_demand,
      raw_score,
      desc_price, desc_ob, desc_liquidity, desc_htf, desc_avwap, desc_macd, desc_div, desc_demand,
      sv_hit, sv_score, sv_price, hvn_hit, hvn_score, hvn_price,
      macd_val, rsi_val, avwap, avwap_lower, ob_quality, ob_dist, cur
    """
    cfg = gate_config if gate_config is not None else _default_cfg

    close = col(df, "Close")
    cur   = float(close.iloc[-1]) if len(close) else 0.0

    # ── pre-compute shared intermediates ─────────────────────────────────────
    avwap_val, avwap_lower = calc_avwap(df)

    macd_tuple = calc_macd(close) if len(close) >= 15 else None
    macd_line  = macd_tuple[0] if macd_tuple is not None else pd.Series(dtype=float)
    macd_val   = float(macd_line.iloc[-1]) if len(macd_line) else float("nan")

    rsi_series = _calc_rsi(close) if len(close) >= 14 else pd.Series(dtype=float)
    rsi_val    = float(rsi_series.iloc[-1]) if len(rsi_series) else float("nan")

    sv_result  = calc_stopping_volume(
        df, eq, lo,
        lookback=cfg.sv_lookback,
        vol_mult=cfg.sv_vol_mult,
        range_ratio=cfg.sv_range_ratio,
    )
    hvn_result = calc_volume_profile(
        df, eq, lo, buy_hi,
        bins=cfg.hvn_bins,
        hvn_pct=cfg.hvn_pct,
    )

    sv_hit   = sv_result[0]
    sv_score = sv_result[1]
    sv_price = sv_result[3]

    hvn_hit   = hvn_result[0]
    hvn_score = hvn_result[1]
    hvn_price = hvn_result[2]

    # ── score each gate ───────────────────────────────────────────────────────
    r1, d1 = sc_price(cur, lo, hi, eq, buy_hi, sell_lo)
    r2, d2 = sc_ob(df, cur, eq, lo, buy_hi)
    r3, d3 = sc_liquidity(df, cur)
    r4, d4 = sc_htf(df)
    r5, d5 = sc_avwap(cur, avwap_val, avwap_lower)
    r6, d6 = sc_macd(close, _macd=macd_tuple)
    r7, d7 = sc_div(close, macd_line)
    r8, d8 = sc_demand_zone(df, eq, lo, buy_hi, _sv=sv_result, _hvn=hvn_result)

    raw_score = r1 + r2 + r3 + r4 + r5 + r6 + r7 + r8

    return {
        # gate scores
        "r1_price":     r1,
        "r2_ob":        r2,
        "r3_liquidity": r3,
        "r4_htf":       r4,
        "r5_avwap":     r5,
        "r6_macd":      r6,
        "r7_div":       r7,
        "r8_demand":    r8,
        "raw_score":    raw_score,
        # gate descriptions
        "desc_price":     d1,
        "desc_ob":        d2,
        "desc_liquidity": d3,
        "desc_htf":       d4,
        "desc_avwap":     d5,
        "desc_macd":      d6,
        "desc_div":       d7,
        "desc_demand":    d8,
        # detail fields
        "sv_hit":      sv_hit,
        "sv_score":    sv_score,
        "sv_price":    sv_price,
        "hvn_hit":     hvn_hit,
        "hvn_score":   hvn_score,
        "hvn_price":   hvn_price,
        "macd_val":    macd_val,
        "rsi_val":     rsi_val,
        "avwap":       avwap_val,
        "avwap_lower": avwap_lower,
        "ob_quality":  float("nan"),
        "ob_dist":     float("nan"),
        "cur":         cur,
    }
