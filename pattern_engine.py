"""
Pattern Recognition Engine — v2
=================================
المؤشرات: 6 مؤشرات مختارة بناءً على ROC-AUC study
الطريقة:  Threshold Scoring بدل Cosine Similarity

لكل مؤشر، النظام يتعلم من التاريخ:
  "في أي نطاق كان هذا المؤشر عند الارتدادات الناجحة؟"
ثم يقيس مدى قرب الوضع الحالي من هذا النطاق.

المؤشرات واتجاهاتها (من الدراسة):
  stoch_rsi  → منخفض = إشارة (oversold)       AUC=0.632
  p_vs_ma20  → منخفض = إشارة (تحت المتوسط)   AUC=0.653  ← الأقوى
  mom_10d    → سلبي  = إشارة (نزل كفاية)      AUC=0.647
  mom_5d     → سلبي  = إشارة                  AUC=0.604
  atr_ratio  → مرتفع = إشارة (تقلب متزايد)    AUC=0.614
  vol_trend  → منخفض = إشارة (الحجم يخف)      AUC=0.592
"""

import numpy as np
import pandas as pd
import json
import os
from egx_context import is_ramadan, get_season


# ── Constants ─────────────────────────────────────────────────────────────────
FORWARD_DAYS  = 60   # days to confirm bounce quality (was 30 — extended for no-SL strategy)
BOUNCE_MIN    = 0.05  # minimum bounce from the low to count as real demand (5%)
VOL_THRESHOLD = 0.80  # volume on low day must be > 80% of 20-day average
BREAK_BUFFER  = 0.02  # low must be broken by > 2% to count as a real loss
MIN_HISTORY   = 80    # 50 for indicators + 30 for confirmation window
MIN_REVERSALS = 3
MIN_DECIDED   = 100   # أقل عدد إشارات محسومة لتحديث الأوزان

# حدود الارتداد لتصنيف قوة الإشارة
BOUNCE_LARGE  = 0.20  # >= 20% ارتداد كبير
BOUNCE_MEDIUM = 0.10  # 10-20% ارتداد متوسط
BOUNCE_SMALL  = 0.04  # 4-10%  ارتداد صغير
# < 4%  → flat

LEARNED_WEIGHTS_FILE = "learned_weights.json"

# الأوزان الافتراضية من AUC study
DEFAULT_WEIGHTS = {
    "p_vs_ma20": 0.21,
    "mom_10d":   0.20,
    "stoch_rsi": 0.18,
    "atr_ratio": 0.15,
    "mom_5d":    0.14,
    "vol_trend": 0.12,
}

DIRECTION = {
    "stoch_rsi": "lower",
    "p_vs_ma20": "lower",
    "mom_10d":   "lower",
    "mom_5d":    "lower",
    "atr_ratio": "higher",
    "vol_trend": "lower",
}


def _load_weights():
    """يحمّل الأوزان المحدّثة لو موجودة، وإلا يرجع الافتراضية."""
    if os.path.exists(LEARNED_WEIGHTS_FILE):
        try:
            with open(LEARNED_WEIGHTS_FILE) as f:
                data = json.load(f)
            w = data.get("weights", {})
            if set(w.keys()) == set(DEFAULT_WEIGHTS.keys()):
                return w
        except Exception:
            pass
    return DEFAULT_WEIGHTS.copy()


WEIGHTS = _load_weights()


def _outcome_is_positive(sig):
    """هل الإشارة انتهت بارتداد حقيقي؟ (يدعم التصنيفات القديمة والجديدة)"""
    o = sig.get("outcome", "")
    return o in ("win", "large", "medium")


def _get_peak_gain(sig):
    """يُرجع أقصى ارتداد مسجّل للإشارة — يدعم الحقلين القديم والجديد."""
    g = sig.get("peak_gain")
    if g is None:
        g = sig.get("outcome_gain")
    return float(g) if g is not None else None


def _calc_weights_from_signals(decided, min_count=30):
    """
    Point-Biserial Correlation — يصنّف الإشارات إلى ناجح/غير ناجح.
    يدعم تصنيفات win/loss (قديمة) و large/medium/small/flat (جديدة).
    """
    if len(decided) < min_count:
        return None

    features = list(DEFAULT_WEIGHTS.keys())
    correlations = {}

    for feat in features:
        vals, labels = [], []
        for s in decided:
            v = s["indicators"].get(feat)
            if v is None:
                continue
            vals.append(float(v))
            labels.append(1 if _outcome_is_positive(s) else 0)

        if len(vals) < min_count:
            correlations[feat] = DEFAULT_WEIGHTS[feat]
            continue

        vals_arr   = np.array(vals)
        labels_arr = np.array(labels)
        n  = len(vals_arr)
        n1 = int(labels_arr.sum())
        n0 = n - n1
        if n1 == 0 or n0 == 0:
            correlations[feat] = DEFAULT_WEIGHTS[feat]
            continue

        m1  = vals_arr[labels_arr == 1].mean()
        m0  = vals_arr[labels_arr == 0].mean()
        std = vals_arr.std() + 1e-9
        rpb = abs((m1 - m0) / std * np.sqrt(n1 * n0 / n**2))
        correlations[feat] = float(rpb)

    total = sum(correlations.values()) + 1e-9
    return {k: round(v / total, 4) for k, v in correlations.items()}


def _calc_gain_weights(signals, min_count=30):
    """
    Pearson Correlation بين كل مؤشر وحجم الارتداد الفعلي (peak_gain).
    يتعلم أي مؤشرات ترتبط بأكبر ارتداد — مش بس الاحتمال.
    """
    if len(signals) < min_count:
        return None

    features = list(DEFAULT_WEIGHTS.keys())
    correlations = {}

    for feat in features:
        gains, feat_vals = [], []
        for s in signals:
            g = _get_peak_gain(s)
            if g is None:
                continue
            v = s["indicators"].get(feat)
            if v is None:
                continue
            gains.append(max(0.0, g))
            feat_vals.append(float(v))

        if len(gains) < min_count:
            correlations[feat] = DEFAULT_WEIGHTS[feat]
            continue

        g_arr = np.array(gains)
        f_arr = np.array(feat_vals)
        corr  = np.corrcoef(f_arr, g_arr)[0, 1]
        correlations[feat] = float(abs(corr)) if not np.isnan(corr) else DEFAULT_WEIGHTS[feat]

    total = sum(correlations.values()) + 1e-9
    return {k: round(v / total, 4) for k, v in correlations.items()}


def _is_signal_ramadan(sig):
    """يحدد إذا كانت الإشارة في رمضان من الـ context أو من تاريخها."""
    ctx = sig.get("context", {})
    if ctx.get("is_ramadan") is not None:
        return bool(ctx["is_ramadan"])
    try:
        import datetime
        d = datetime.date.fromisoformat(sig["signal_date"])
        return is_ramadan(d)
    except Exception:
        return False


def update_weights_from_log(log_file="signal_log.json"):
    """
    يحسب أوزان من signal_log.json:
      - global      : كل الإشارات المحسومة
      - normal      : خارج رمضان
      - ramadan     : داخل رمضان (لو >= 30 إشارة)
      - per_stock   : لكل سهم (لو >= 30 إشارة)
    يحفظ النتيجة في learned_weights.json.
    """
    if not os.path.exists(log_file):
        return None

    try:
        with open(log_file) as f:
            data = json.load(f)
    except Exception:
        return None

    decided = [s for s in data.get("signals", [])
               if s.get("outcome") in ("win", "loss", "large", "medium", "small", "flat")
               and s.get("indicators")]

    if len(decided) < MIN_DECIDED:
        return None

    # ── Global weights ────────────────────────────────────────────────
    global_weights = _calc_weights_from_signals(decided, min_count=MIN_DECIDED)
    if global_weights is None:
        return None

    # ── Context-aware weights: رمضان vs عادي ─────────────────────────
    ramadan_sigs = [s for s in decided if _is_signal_ramadan(s)]
    normal_sigs  = [s for s in decided if not _is_signal_ramadan(s)]

    weights_ramadan = _calc_weights_from_signals(ramadan_sigs, min_count=30)
    weights_normal  = _calc_weights_from_signals(normal_sigs,  min_count=MIN_DECIDED // 2)

    # ── Gain-magnitude weights (Pearson) ──────────────────────────────
    gain_sigs    = [s for s in decided if _get_peak_gain(s) is not None]
    weights_gain = _calc_gain_weights(gain_sigs, min_count=MIN_DECIDED)

    # ── Per-stock weights ─────────────────────────────────────────────
    from collections import defaultdict
    by_symbol = defaultdict(list)
    for s in decided:
        by_symbol[s["symbol"]].append(s)

    per_stock = {}
    for sym, sigs in by_symbol.items():
        w = _calc_weights_from_signals(sigs, min_count=30)
        if w:
            per_stock[sym] = {"weights": w, "based_on": len(sigs)}

    # ── حفظ ──────────────────────────────────────────────────────────
    import datetime
    out = {
        "weights":         global_weights,
        "weights_normal":  weights_normal,
        "weights_ramadan": weights_ramadan,
        "weights_gain":    weights_gain,
        "per_stock":       per_stock,
        "based_on":        len(decided),
        "ramadan_signals": len(ramadan_sigs),
        "normal_signals":  len(normal_sigs),
        "gain_signals":    len(gain_sigs),
        "updated_at":      str(datetime.date.today()),
    }
    with open(LEARNED_WEIGHTS_FILE, "w") as f:
        json.dump(out, f, indent=2)

    print(f"  🔄 Global weights updated from {len(decided)} signals "
          f"(ramadan={len(ramadan_sigs)}, normal={len(normal_sigs)}):")
    for k, v in sorted(global_weights.items(), key=lambda x: -x[1]):
        old = DEFAULT_WEIGHTS[k]
        arrow = "↑" if v > old else "↓" if v < old else "="
        print(f"     {k:<12} {old:.2f} → {v:.4f} {arrow}")
    if weights_ramadan:
        print(f"  🌙 Ramadan weights learned from {len(ramadan_sigs)} signals")
    if weights_gain:
        print(f"  📈 Gain-magnitude weights learned from {len(gain_sigs)} signals")
    print(f"  🔄 Per-stock weights learned for {len(per_stock)} stocks")

    return global_weights


def _load_per_stock_weights(symbol, context=None):
    """
    يُرجع الأوزان المناسبة بترتيب الأولوية:
      per-stock  →  ramadan/normal global  →  global  →  default
    context: dict من get_signal_context (اختياري)
    """
    is_ram = (context or {}).get("is_ramadan", False)

    if os.path.exists(LEARNED_WEIGHTS_FILE):
        try:
            with open(LEARNED_WEIGHTS_FILE) as f:
                data = json.load(f)

            # 1. per-stock (أعلى أولوية)
            per_stock = data.get("per_stock", {})
            if symbol in per_stock:
                return per_stock[symbol]["weights"]

            # 2. context-aware global
            if is_ram and data.get("weights_ramadan"):
                w = data["weights_ramadan"]
                if set(w.keys()) == set(DEFAULT_WEIGHTS.keys()):
                    return w

            if not is_ram and data.get("weights_normal"):
                w = data["weights_normal"]
                if set(w.keys()) == set(DEFAULT_WEIGHTS.keys()):
                    return w

            # 3. global
            w = data.get("weights", {})
            if set(w.keys()) == set(DEFAULT_WEIGHTS.keys()):
                return w
        except Exception:
            pass
    return DEFAULT_WEIGHTS.copy()


# ── Helpers ───────────────────────────────────────────────────────────────────

def _rsi_series(close, period=14):
    delta = close.diff()
    ag = delta.clip(lower=0).ewm(alpha=1/period, min_periods=period, adjust=False).mean()
    al = (-delta).clip(lower=0).ewm(alpha=1/period, min_periods=period, adjust=False).mean()
    rsi = pd.Series(100.0, index=close.index)
    mask = al > 0
    rsi[mask] = 100 - (100 / (1 + ag[mask] / al[mask]))
    rsi[ag == 0] = 0.0
    return rsi

def _stoch_rsi(close, period=14, smooth=3):
    rsi = _rsi_series(close, period)
    lo  = rsi.rolling(period).min()
    hi  = rsi.rolling(period).max()
    k   = (rsi - lo) / (hi - lo + 1e-9)
    return k.rolling(smooth).mean()

def _atr(df, period=14):
    tr = pd.concat([
        df["High"] - df["Low"],
        (df["High"] - df["Close"].shift()).abs(),
        (df["Low"]  - df["Close"].shift()).abs(),
    ], axis=1).max(axis=1)
    return tr.ewm(alpha=1/period, adjust=False).mean()


# ── Extract 6 indicators at index i ───────────────────────────────────────────

def _extract(df, idx):
    if idx < 50 or idx >= len(df):
        return None

    close  = df["Close"]
    volume = df["Volume"]

    p0  = float(close.iloc[idx])
    p5  = float(close.iloc[idx - 5])
    p10 = float(close.iloc[idx - 10])

    # Stochastic RSI
    sr = float(_stoch_rsi(close).iloc[idx])
    stoch_rsi = np.clip(sr, 0.0, 1.0)

    # Price vs MA20
    ma20 = float(close.iloc[idx-20:idx].mean())
    p_vs_ma20 = (p0 / ma20) if ma20 > 0 else 1.0

    # Momentum 10d
    mom_10d = (p0 - p10) / p10 if p10 > 0 else 0.0

    # Momentum 5d
    mom_5d = (p0 - p5) / p5 if p5 > 0 else 0.0

    # ATR Ratio (current ATR vs 20-day avg ATR)
    atr     = _atr(df)
    atr_now = float(atr.iloc[idx])
    atr_avg = float(atr.iloc[idx-20:idx].mean())
    atr_ratio = (atr_now / atr_avg) if atr_avg > 0 else 1.0

    # Volume Trend (avg last 5 days vs avg prior 10 days)
    v5  = float(volume.iloc[idx-5:idx].mean())
    v15 = float(volume.iloc[idx-15:idx-5].mean())
    vol_trend = (v5 / v15) if v15 > 0 else 1.0

    return {
        "stoch_rsi": stoch_rsi,
        "p_vs_ma20": p_vs_ma20,
        "mom_10d":   mom_10d,
        "mom_5d":    mom_5d,
        "atr_ratio": atr_ratio,
        "vol_trend": vol_trend,
    }


# ── Find historical reversals ─────────────────────────────────────────────────

def _find_reversals(df):
    """
    Returns (wins, losses) at historical local lows.
    win  = low held (no close below within FORWARD_DAYS)
           + bounced >= BOUNCE_MIN from the low
           + volume on low day > 20-day average volume
    loss = at least one close below the low within FORWARD_DAYS
    neutral (held but weak bounce or low volume) = ignored
    """
    close  = df["Close"].values
    volume = df["Volume"].values
    n      = len(close)
    wins   = []
    losses = []

    for i in range(50, n - FORWARD_DAYS):
        if close[i] > min(close[max(0, i-5):i+1]) * 1.002:
            continue

        future = close[i+1: i+FORWARD_DAYS+1]
        cond   = _extract(df, i)
        if cond is None:
            continue

        low_broken = any(c < close[i] * (1 - BREAK_BUFFER) for c in future)

        if low_broken:
            losses.append({"conditions": cond})
        else:
            max_gain = (float(np.max(future)) - close[i]) / close[i]
            avg_vol  = float(np.mean(volume[i-20:i])) if i >= 20 else float(np.mean(volume[:i]))
            vol_ok   = volume[i] > avg_vol * VOL_THRESHOLD
            bounce_ok = max_gain >= BOUNCE_MIN

            if bounce_ok and vol_ok:
                wins.append({"conditions": cond, "gain": round(max_gain, 4)})
            # else: neutral — held but no real demand confirmation

    return wins, losses


# ── Threshold Scoring ─────────────────────────────────────────────────────────

def _indicator_score(current_val, win_vals, direction):
    """
    يقيس مدى قرب القيمة الحالية من النطاق المواتي في الارتدادات التاريخية.
    يستخدم sigmoid حول الـ median للارتدادات الناجحة.
    يُرجع 0.0 → 1.0
    """
    if not win_vals:
        return 0.5

    win_median = float(np.median(win_vals))
    win_std    = float(np.std(win_vals)) + 1e-9

    if direction == "lower":
        # كلما انخفضت القيمة عن الـ median، كلما كانت الإشارة أقوى
        z = (current_val - win_median) / win_std
    else:
        # كلما ارتفعت القيمة عن الـ median، كلما كانت الإشارة أقوى
        z = (win_median - current_val) / win_std

    # sigmoid: z=0 → 0.5, z=-2 → 0.88, z=+2 → 0.12
    return float(1 / (1 + np.exp(z * 1.5)))


def _threshold_score(current_cond, wins, weights=None):
    """
    يحسب الـ Pattern Score الكلي (0-100) بجمع نقاط المؤشرات الستة موزونة.
    weights: لو None يستخدم الـ global WEIGHTS
    """
    if weights is None:
        weights = WEIGHTS

    total  = 0.0
    detail = {}

    for feat, weight in weights.items():
        win_vals  = [w["conditions"][feat] for w in wins]
        cur_val   = current_cond[feat]
        direction = DIRECTION[feat]

        sc = _indicator_score(cur_val, win_vals, direction)
        total += sc * weight
        detail[feat] = round(sc, 3)

    return round(total * 100, 1), detail


# ── Main API ──────────────────────────────────────────────────────────────────

def analyze_entry_patterns(df, symbol=None, context=None):
    """
    الدالة الرئيسية.

    context: dict من get_signal_context — يُستخدم لاختيار الأوزان المناسبة
             وحساب volume confidence.

    Returns:
    {
        "ok":                   bool
        "pattern_score":        0-100   (جودة الإعداد الحالي)
        "effective_score":      0-100   (pattern × win_rate)
        "volume_adjusted_score":0-100   (effective × volume_confidence)
        "volume_confidence":    0-1     (نسبة الحجم للمتوسط، مقيّدة بـ 1)
        "win_rate":             0-1
        "avg_gain":             float   (متوسط الربح %)
        "similar_count":        int
        "low_reliability":      bool
        "context_mode":         str     (ramadan | normal)
        "detail":               dict
        "label":                str
    }
    """
    empty = {"ok": False, "pattern_score": 0, "effective_score": 0,
             "volume_adjusted_score": 0, "volume_confidence": 1.0,
             "win_rate": 0, "avg_gain": 0, "similar_count": 0,
             "expected_bounce": 0, "bounce_p75": 0, "bounce_best": 0,
             "low_reliability": False, "context_mode": "normal", "detail": {},
             "label": "Insufficient history"}

    if df is None or len(df) < MIN_HISTORY:
        n = len(df) if df is not None else 0
        return {**empty, "label": f"Insufficient data ({n} bars, need {MIN_HISTORY})"}

    current_cond = _extract(df, len(df) - 1)
    if current_cond is None:
        return {**empty, "label": "Could not extract current conditions"}

    wins, losses = _find_reversals(df.iloc[:-1])

    if len(wins) < MIN_REVERSALS:
        return {**empty, "label": f"Limited history — {len(wins)} reversals found (need {MIN_REVERSALS})"}

    weights = _load_per_stock_weights(symbol, context) if symbol else WEIGHTS
    pattern_score, detail = _threshold_score(current_cond, wins, weights)

    total_decided = len(wins) + len(losses)
    win_rate = len(wins) / total_decided if total_decided > 0 else 0.0
    all_gains = [w["gain"] for w in wins]
    avg_gain  = float(np.mean(all_gains))

    # ── Bounce statistics (أهم من win_rate للاستراتيجية بدون stop loss) ─────
    expected_bounce = round(float(np.mean(all_gains))        * 100, 1)
    bounce_p75      = round(float(np.percentile(all_gains, 75)) * 100, 1)
    bounce_best     = round(float(np.percentile(all_gains, 90)) * 100, 1)

    # Effective score = pattern quality × historical reliability
    effective_score = round(pattern_score * win_rate, 1)
    low_reliability = win_rate < 0.25

    # Volume confidence: إشارة على حجم ضعيف أقل موثوقية
    volume_vs_adv    = (context or {}).get("volume_vs_adv")
    volume_confidence = float(min(1.0, volume_vs_adv)) if volume_vs_adv else 1.0
    volume_adjusted_score = round(effective_score * volume_confidence, 1)

    is_ram       = (context or {}).get("is_ramadan", False)
    context_mode = "ramadan" if is_ram else "normal"

    # Label
    if pattern_score >= 70:
        label = f"Strong setup — {len(wins)}/{total_decided} reversals won, avg +{avg_gain*100:.1f}%"
    elif pattern_score >= 50:
        label = f"Moderate setup — {len(wins)}/{total_decided} reversals won, avg +{avg_gain*100:.1f}%"
    elif pattern_score >= 35:
        label = f"Weak setup — conditions partially match historical reversals"
    else:
        label = f"Poor setup — current conditions differ from historical reversal patterns"

    if low_reliability:
        label += f" | ⚠️ Low reliability ({win_rate*100:.0f}% bounced)"
    if volume_confidence < 0.6:
        label += f" | ⚠️ Low volume day ({volume_confidence*100:.0f}% of ADV)"
    if is_ram:
        label += " | 🌙 Ramadan weights applied"

    return {
        "ok":                    True,
        "pattern_score":         pattern_score,
        "effective_score":       effective_score,
        "volume_adjusted_score": volume_adjusted_score,
        "volume_confidence":     round(volume_confidence, 3),
        "win_rate":              round(win_rate, 3),
        "avg_gain":              round(avg_gain * 100, 2),
        "expected_bounce":       expected_bounce,   # متوسط الارتداد من هذا المستوى
        "bounce_p75":            bounce_p75,         # 75% من الحالات تصل لهذا
        "bounce_best":           bounce_best,         # 90% من الحالات
        "similar_count":         len(wins),
        "low_reliability":       low_reliability,
        "context_mode":          context_mode,
        "detail":                detail,
        "label":                 label,
    }
