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


# ── Constants ─────────────────────────────────────────────────────────────────
MIN_GAIN      = 0.07
STOP_LOSS     = 0.06
FORWARD_DAYS  = 15
MIN_HISTORY   = 30
MIN_REVERSALS = 3
MIN_DECIDED   = 100   # أقل عدد إشارات محسومة لتحديث الأوزان

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


def _calc_weights_from_signals(decided, min_count=30):
    """
    يحسب الأوزان من قائمة إشارات محسومة باستخدام Point-Biserial Correlation.
    يُرجع dict أوزان أو None لو البيانات مش كافية.
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
            labels.append(1 if s["outcome"] == "win" else 0)

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


def update_weights_from_log(log_file="signal_log.json"):
    """
    يحسب أوزان global + per-stock من signal_log.json.
    يحفظ النتيجة في learned_weights.json.
    يُرجع الأوزان الجديدة أو None لو البيانات مش كافية.
    """
    if not os.path.exists(log_file):
        return None

    try:
        with open(log_file) as f:
            data = json.load(f)
    except Exception:
        return None

    decided = [s for s in data.get("signals", [])
               if s.get("outcome") in ("win", "loss") and s.get("indicators")]

    if len(decided) < MIN_DECIDED:
        return None

    # ── Global weights ────────────────────────────────────────────────
    global_weights = _calc_weights_from_signals(decided, min_count=MIN_DECIDED)
    if global_weights is None:
        return None

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
        "weights":    global_weights,
        "per_stock":  per_stock,
        "based_on":   len(decided),
        "updated_at": str(datetime.date.today()),
    }
    with open(LEARNED_WEIGHTS_FILE, "w") as f:
        json.dump(out, f, indent=2)

    print(f"  🔄 Global weights updated from {len(decided)} signals:")
    for k, v in sorted(global_weights.items(), key=lambda x: -x[1]):
        old = DEFAULT_WEIGHTS[k]
        arrow = "↑" if v > old else "↓" if v < old else "="
        print(f"     {k:<12} {old:.2f} → {v:.4f} {arrow}")
    print(f"  🔄 Per-stock weights learned for {len(per_stock)} stocks")

    return global_weights


def _load_per_stock_weights(symbol):
    """يُرجع الأوزان الخاصة بسهم معين، أو الـ global، أو الافتراضية."""
    if os.path.exists(LEARNED_WEIGHTS_FILE):
        try:
            with open(LEARNED_WEIGHTS_FILE) as f:
                data = json.load(f)
            per_stock = data.get("per_stock", {})
            if symbol in per_stock:
                return per_stock[symbol]["weights"]
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
    win  = price hit +MIN_GAIN before -STOP_LOSS
    loss = price hit -STOP_LOSS before +MIN_GAIN
    neutral (neither within FORWARD_DAYS) = ignored
    """
    close  = df["Close"].values
    n      = len(close)
    wins   = []
    losses = []

    for i in range(50, n - FORWARD_DAYS):
        if close[i] > min(close[max(0, i-5):i+1]) * 1.002:
            continue
        future = close[i+1: i+FORWARD_DAYS+1]
        gain   = (float(np.max(future)) - close[i]) / close[i]
        loss   = (close[i] - float(np.min(future))) / close[i]

        cond = _extract(df, i)
        if cond is None:
            continue

        if gain >= MIN_GAIN and loss < STOP_LOSS:
            wins.append({"conditions": cond, "gain": round(gain, 4)})
        elif loss >= STOP_LOSS:
            losses.append({"conditions": cond, "loss": round(loss, 4)})

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

def analyze_entry_patterns(df, symbol=None):
    """
    الدالة الرئيسية.

    Returns:
    {
        "ok":            bool
        "pattern_score": 0-100
        "win_rate":      0-1   (نسبة الارتدادات الناجحة في التاريخ)
        "avg_gain":      float (متوسط الربح %)
        "similar_count": int   (عدد الارتدادات التاريخية المستخدمة)
        "detail":        dict  (نقطة كل مؤشر)
        "label":         str
    }
    """
    empty = {"ok": False, "pattern_score": 0, "win_rate": 0,
             "avg_gain": 0, "similar_count": 0, "detail": {},
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

    weights = _load_per_stock_weights(symbol) if symbol else WEIGHTS
    pattern_score, detail = _threshold_score(current_cond, wins, weights)

    total_decided = len(wins) + len(losses)
    win_rate = len(wins) / total_decided if total_decided > 0 else 0.0
    avg_gain = float(np.mean([w["gain"] for w in wins]))

    # Label
    if pattern_score >= 70:
        label = f"Strong setup — {len(wins)}/{total_decided} reversals won, avg +{avg_gain*100:.1f}%"
    elif pattern_score >= 50:
        label = f"Moderate setup — {len(wins)}/{total_decided} reversals won, avg +{avg_gain*100:.1f}%"
    elif pattern_score >= 35:
        label = f"Weak setup — conditions partially match historical reversals"
    else:
        label = f"Poor setup — current conditions differ from historical reversal patterns"

    return {
        "ok":            True,
        "pattern_score": pattern_score,
        "win_rate":      round(win_rate, 3),
        "avg_gain":      round(avg_gain * 100, 2),
        "similar_count": len(wins),
        "detail":        detail,
        "label":         label,
    }
