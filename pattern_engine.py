"""
Pattern Recognition + Backtesting Engine
=========================================
يرصد الأنماط التاريخية الناجحة قبل كل ارتداد ويقيس تشابه الوضع الحالي بها.
يُرجع:
  - win_rate: نسبة نجاح الأنماط المشابهة تاريخياً
  - avg_gain: متوسط الربح عند النجاح
  - pattern_score: درجة التشابه مع الأنماط الناجحة (0-100)
  - similar_count: عدد الحالات المشابهة في التاريخ
  - label: وصف موجز
"""

import numpy as np
import pandas as pd


# ── Constants ─────────────────────────────────────────────────────────────────
MIN_GAIN       = 0.07   # ارتداد ناجح = +7% على الأقل
STOP_LOSS      = 0.06   # وقف خسارة = -6%
FORWARD_DAYS   = 15     # نتيجة الارتداد خلال 15 يوم تداول
MIN_HISTORY    = 60     # أقل عدد شمعات مطلوب للتحليل
SIMILARITY_THR = 0.55   # حد أدنى للتشابه لاعتبار الحالة "مشابهة"


# ── RSI helper ────────────────────────────────────────────────────────────────
def _rsi_series(close, period=14):
    delta = close.diff()
    gain  = delta.clip(lower=0)
    loss  = (-delta).clip(lower=0)
    ag    = gain.ewm(alpha=1/period, min_periods=period, adjust=False).mean()
    al    = loss.ewm(alpha=1/period, min_periods=period, adjust=False).mean()
    rsi   = pd.Series(100.0, index=close.index)
    mask  = al > 0
    rsi[mask]    = 100 - (100 / (1 + ag[mask] / al[mask]))
    rsi[ag == 0] = 0.0
    return rsi


# ── Extract conditions at index i ─────────────────────────────────────────────
def _extract_conditions(df, idx):
    """
    يستخرج 7 مؤشرات تصف حالة السوق عند نقطة معينة:
    rsi, vol_ratio, momentum_3d, momentum_5d,
    hammer_ratio, body_ratio, price_vs_ma20
    """
    close  = df["Close"]
    volume = df["Volume"]
    opens  = df["Open"]
    highs  = df["High"]
    lows   = df["Low"]

    n = len(close)
    if idx < 20 or idx >= n:
        return None

    # RSI
    rsi_val = float(_rsi_series(close).iloc[idx])

    # Volume ratio vs 20-day average
    vol_avg = float(volume.iloc[max(0, idx-20):idx].mean())
    vol_ratio = float(volume.iloc[idx]) / vol_avg if vol_avg > 0 else 1.0

    # Momentum
    p0 = float(close.iloc[idx])
    p3 = float(close.iloc[max(0, idx-3)])
    p5 = float(close.iloc[max(0, idx-5)])
    momentum_3d = (p0 - p3) / p3 if p3 > 0 else 0.0
    momentum_5d = (p0 - p5) / p5 if p5 > 0 else 0.0

    # Candle shape
    o = float(opens.iloc[idx])
    h = float(highs.iloc[idx])
    l = float(lows.iloc[idx])
    c = float(close.iloc[idx])
    candle_range = h - l
    body         = abs(c - o)
    lower_wick   = min(o, c) - l
    hammer_ratio = lower_wick / candle_range if candle_range > 0 else 0.0
    body_ratio   = body / candle_range        if candle_range > 0 else 0.0

    # Price vs 20-day MA
    ma20 = float(close.iloc[max(0, idx-20):idx].mean())
    price_vs_ma20 = p0 / ma20 if ma20 > 0 else 1.0

    return np.array([
        rsi_val / 100.0,   # normalize to [0,1]
        min(vol_ratio, 5.0) / 5.0,
        max(-0.2, min(0.2, momentum_3d)) / 0.2,
        max(-0.2, min(0.2, momentum_5d)) / 0.2,
        hammer_ratio,
        body_ratio,
        max(0.5, min(1.5, price_vs_ma20)) / 1.5,
    ], dtype=float)


# ── Cosine similarity ─────────────────────────────────────────────────────────
def _cosine_sim(a, b):
    na = np.linalg.norm(a)
    nb = np.linalg.norm(b)
    if na == 0 or nb == 0:
        return 0.0
    return float(np.dot(a, b) / (na * nb))


# ── Find historical reversals ─────────────────────────────────────────────────
def _find_reversals(df):
    """
    يجد كل اللحظات التاريخية التي ارتد فيها السعر بشكل ناجح.
    يُرجع قائمة من: {idx, conditions, gain, days_to_peak, outcome}
    """
    close  = df["Close"].values
    n      = len(close)
    result = []

    for i in range(20, n - FORWARD_DAYS):
        # شرط: أدنى سعر في آخر 5 أيام (local low)
        window_low = min(close[max(0, i-5):i+1])
        if close[i] > window_low * 1.002:
            continue

        future = close[i+1: i+FORWARD_DAYS+1]
        max_f  = float(np.max(future))
        min_f  = float(np.min(future))

        gain = (max_f - close[i]) / close[i]
        loss = (close[i] - min_f) / close[i]

        if gain >= MIN_GAIN and loss < STOP_LOSS:
            cond = _extract_conditions(df, i)
            if cond is not None:
                days_to_peak = int(np.argmax(future)) + 1
                result.append({
                    "idx":          i,
                    "date":         str(df.index[i].date()),
                    "gain":         round(gain, 4),
                    "loss":         round(loss, 4),
                    "days_to_peak": days_to_peak,
                    "outcome":      "win",
                    "conditions":   cond,
                })

    return result


def _find_failures(df):
    """
    يجد اللحظات التي وصل فيها السعر لأدنى نقطة لكنه فشل (وصل وقف الخسارة أولاً)
    """
    close  = df["Close"].values
    n      = len(close)
    result = []

    for i in range(20, n - FORWARD_DAYS):
        window_low = min(close[max(0, i-5):i+1])
        if close[i] > window_low * 1.002:
            continue

        future = close[i+1: i+FORWARD_DAYS+1]
        max_f  = float(np.max(future))
        min_f  = float(np.min(future))

        gain = (max_f - close[i]) / close[i]
        loss = (close[i] - min_f) / close[i]

        # فشل = وقف الخسارة وصل قبل الهدف
        if loss >= STOP_LOSS and gain < MIN_GAIN:
            cond = _extract_conditions(df, i)
            if cond is not None:
                result.append({
                    "idx":        i,
                    "conditions": cond,
                    "outcome":    "loss",
                })

    return result


# ── Main API ──────────────────────────────────────────────────────────────────
def analyze_entry_patterns(df):
    """
    الدالة الرئيسية — تُعطى DataFrame للسهم وتُرجع dict يضاف لنتيجة analyze().

    Returns:
    {
        "pattern_score":   0-100  (تشابه الوضع الحالي بالأنماط الناجحة)
        "win_rate":        0-1    (نسبة نجاح تاريخية للأنماط المشابهة)
        "avg_gain":        float  (متوسط الربح عند النجاح %)
        "avg_days":        int    (متوسط عدد الأيام للوصول للهدف)
        "similar_count":   int    (عدد الحالات المشابهة في التاريخ)
        "label":           str    (وصف نصي)
        "ok":              bool
    }
    """
    empty = {"ok": False, "pattern_score": 0, "win_rate": 0,
             "avg_gain": 0, "avg_days": 0, "similar_count": 0,
             "label": "Insufficient history"}

    if df is None or len(df) < MIN_HISTORY:
        return empty

    # الوضع الحالي (آخر شمعة مكتملة = قبل الأخيرة إن وجد اليوم الحالي)
    current_idx = len(df) - 1
    current_cond = _extract_conditions(df, current_idx)
    if current_cond is None:
        return empty

    # استخراج الأنماط التاريخية (باستثناء آخر FORWARD_DAYS شمعة)
    df_hist = df.iloc[:-1]   # نستثني آخر شمعة من البحث التاريخي

    wins   = _find_reversals(df_hist)
    losses = _find_failures(df_hist)

    if len(wins) + len(losses) < 5:
        return {**empty, "label": "Not enough historical reversals to evaluate"}

    # حساب التشابه مع كل حالة
    win_sims  = [_cosine_sim(current_cond, w["conditions"]) for w in wins]
    loss_sims = [_cosine_sim(current_cond, l["conditions"]) for l in losses]

    # فقط الحالات المشابهة (فوق الحد الأدنى)
    sim_wins   = [s for s in win_sims  if s >= SIMILARITY_THR]
    sim_losses = [s for s in loss_sims if s >= SIMILARITY_THR]

    total_similar = len(sim_wins) + len(sim_losses)

    if total_similar == 0:
        return {**empty, "label": "No similar historical patterns found"}

    win_rate  = len(sim_wins) / total_similar
    avg_gain  = float(np.mean([wins[i]["gain"]         for i, s in enumerate(win_sims)  if s >= SIMILARITY_THR])) if sim_wins else 0.0
    avg_days  = int(np.mean([wins[i]["days_to_peak"]   for i, s in enumerate(win_sims)  if s >= SIMILARITY_THR])) if sim_wins else 0

    # Pattern score: win_rate × avg_similarity_of_wins × 100
    avg_sim_wins = float(np.mean(sim_wins)) if sim_wins else 0.0
    raw_score    = win_rate * avg_sim_wins * 100
    pattern_score = min(100, round(raw_score, 1))

    # Label
    if pattern_score >= 70:
        label = f"Strong match — {total_similar} similar cases, {win_rate*100:.0f}% won, avg +{avg_gain*100:.1f}% in {avg_days}d"
    elif pattern_score >= 45:
        label = f"Moderate match — {total_similar} similar cases, {win_rate*100:.0f}% won"
    elif win_rate >= 0.6:
        label = f"Weak similarity but {win_rate*100:.0f}% win rate on {total_similar} cases"
    else:
        label = f"Low confidence — {total_similar} similar cases, only {win_rate*100:.0f}% won"

    return {
        "ok":            True,
        "pattern_score": pattern_score,
        "win_rate":      round(win_rate, 3),
        "avg_gain":      round(avg_gain * 100, 2),
        "avg_days":      avg_days,
        "similar_count": total_similar,
        "label":         label,
    }


# ── Quick backtest of current scoring rules ───────────────────────────────────
def backtest_signal_quality(df, score_fn, symbol):
    """
    يأخذ الـ df التاريخي ويحاكي: لو كنا أعطينا إشارة في يوم X (score >= 35)،
    ما النتيجة الفعلية؟

    score_fn: callable(df_slice) → int  (يُعطى df حتى اليوم X)
    يُرجع: {trades, wins, losses, win_rate, avg_gain, avg_loss, expectancy}
    """
    if df is None or len(df) < MIN_HISTORY + FORWARD_DAYS:
        return None

    trades, wins_data, losses_data = [], [], []
    close = df["Close"].values

    for i in range(MIN_HISTORY, len(df) - FORWARD_DAYS):
        df_slice = df.iloc[:i+1]
        try:
            score = score_fn(df_slice)
        except Exception:
            continue

        if score < 35:
            continue

        entry  = close[i]
        future = close[i+1: i+FORWARD_DAYS+1]
        max_f  = float(np.max(future))
        min_f  = float(np.min(future))

        gain = (max_f - entry) / entry
        loss = (entry - min_f) / entry

        if gain >= MIN_GAIN and loss < STOP_LOSS:
            outcome = "win"
            wins_data.append(gain)
        elif loss >= STOP_LOSS:
            outcome = "loss"
            losses_data.append(-STOP_LOSS)
        else:
            outcome = "neutral"

        trades.append({"date": str(df.index[i].date()), "outcome": outcome,
                        "gain": gain, "loss": loss, "entry": entry})

    if not trades:
        return None

    n_wins   = len(wins_data)
    n_losses = len(losses_data)
    n_total  = len(trades)

    avg_gain_val = float(np.mean(wins_data))   if wins_data   else 0.0
    avg_loss_val = float(np.mean(losses_data)) if losses_data else 0.0
    wr           = n_wins / n_total if n_total > 0 else 0.0
    expectancy   = wr * avg_gain_val + (1 - wr) * avg_loss_val

    return {
        "total_trades": n_total,
        "wins":         n_wins,
        "losses":       n_losses,
        "win_rate":     round(wr, 3),
        "avg_gain_pct": round(avg_gain_val * 100, 2),
        "avg_loss_pct": round(avg_loss_val * 100, 2),
        "expectancy":   round(expectancy * 100, 2),
    }
