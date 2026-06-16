"""
دراسة وفحص مؤشرات Pattern Engine
===================================
يختبر كل مؤشر على حدة ويقارن التركيبات المختلفة على بيانات مصطنعة واقعية
"""

import numpy as np
import pandas as pd
from scipy import stats

np.random.seed(42)

# ═══════════════════════════════════════════════════════
# 1. توليد بيانات واقعية تحاكي سوق EGX
# ═══════════════════════════════════════════════════════

def generate_egx_like(n=500, seed=None):
    """يولد بيانات تحاكي سهم EGX فعلي: ترندات + consolidation + أحداث حجم"""
    if seed: np.random.seed(seed)

    close = [50.0]
    volume_base = 500_000

    for i in range(n - 1):
        phase = (i // 40) % 4
        if phase == 0:   drift = 0.002   # uptrend
        elif phase == 1: drift = -0.003  # downtrend
        elif phase == 2: drift = 0.0     # sideways
        else:            drift = -0.001  # slow bleed

        noise = np.random.randn() * 0.012
        close.append(max(1.0, close[-1] * (1 + drift + noise)))

    close = np.array(close)

    # حجم تداول: يرتفع عند التقلب
    volatility = np.abs(np.diff(close, prepend=close[0]) / close)
    volume = (volume_base * (1 + 3 * volatility + np.random.exponential(0.3, n))).astype(int)

    # شمعات OHLC
    daily_range = close * np.random.uniform(0.005, 0.025, n)
    open_  = close * (1 + np.random.randn(n) * 0.005)
    high   = np.maximum(close, open_) + daily_range * np.random.uniform(0.2, 0.8, n)
    low    = np.minimum(close, open_) - daily_range * np.random.uniform(0.2, 0.8, n)
    low    = np.maximum(low, close * 0.5)

    dates = pd.date_range("2022-01-01", periods=n, freq="B")
    return pd.DataFrame({"Open": open_, "High": high, "Low": low,
                         "Close": close, "Volume": volume}, index=dates)


# ═══════════════════════════════════════════════════════
# 2. حساب المؤشرات الحالية + المقترحة
# ═══════════════════════════════════════════════════════

def _rsi(close, period=14):
    delta = close.diff()
    ag = delta.clip(lower=0).ewm(alpha=1/period, min_periods=period, adjust=False).mean()
    al = (-delta).clip(lower=0).ewm(alpha=1/period, min_periods=period, adjust=False).mean()
    rsi = pd.Series(100.0, index=close.index)
    mask = al > 0
    rsi[mask] = 100 - (100 / (1 + ag[mask] / al[mask]))
    rsi[ag == 0] = 0.0
    return rsi

def _stoch_rsi(close, period=14, smooth=3):
    rsi = _rsi(close, period)
    rsi_min = rsi.rolling(period).min()
    rsi_max = rsi.rolling(period).max()
    stoch = (rsi - rsi_min) / (rsi_max - rsi_min + 1e-9)
    return stoch.rolling(smooth).mean()

def _atr(df, period=14):
    tr = pd.concat([
        df["High"] - df["Low"],
        (df["High"] - df["Close"].shift()).abs(),
        (df["Low"]  - df["Close"].shift()).abs()
    ], axis=1).max(axis=1)
    return tr.ewm(alpha=1/period, adjust=False).mean()

def extract_all_features(df, idx):
    """يستخرج 12 مؤشر: 7 حاليين + 5 جدد"""
    if idx < 50 or idx >= len(df): return None

    close  = df["Close"]
    volume = df["Volume"]
    opens  = df["Open"]
    highs  = df["High"]
    lows   = df["Low"]

    p0 = float(close.iloc[idx])
    p3 = float(close.iloc[idx-3])
    p5 = float(close.iloc[idx-5])
    p10= float(close.iloc[idx-10])

    # ── المؤشرات الحالية ──────────────────────────────
    rsi_val   = float(_rsi(close).iloc[idx]) / 100.0

    vol_avg   = float(volume.iloc[idx-20:idx].mean())
    vol_ratio = min(float(volume.iloc[idx]) / vol_avg, 5.0) / 5.0 if vol_avg > 0 else 0.5

    mom_3d    = np.clip((p0 - p3) / p3, -0.2, 0.2) / 0.2 if p3 > 0 else 0
    mom_5d    = np.clip((p0 - p5) / p5, -0.2, 0.2) / 0.2 if p5 > 0 else 0

    o = float(opens.iloc[idx])
    h = float(highs.iloc[idx])
    l = float(lows.iloc[idx])
    c = p0
    rng = h - l
    hammer = (min(o,c) - l) / rng if rng > 0 else 0
    body   = abs(c - o) / rng    if rng > 0 else 0

    ma20 = float(close.iloc[idx-20:idx].mean())
    p_vs_ma20 = np.clip(p0 / ma20, 0.5, 1.5) / 1.5 if ma20 > 0 else 0.5

    # ── المؤشرات المقترحة الجديدة ─────────────────────

    # Stochastic RSI (أسرع استجابة من RSI)
    stoch_rsi = float(_stoch_rsi(close).iloc[idx])
    stoch_rsi = np.clip(stoch_rsi, 0, 1)

    # ATR Ratio: التقلب الحالي نسبة لمعدل التقلب
    atr_series = _atr(df)
    atr_now  = float(atr_series.iloc[idx])
    atr_avg  = float(atr_series.iloc[idx-20:idx].mean())
    atr_ratio = np.clip(atr_now / atr_avg, 0, 3) / 3 if atr_avg > 0 else 0.5

    # Volume Trend: هل الحجم كان بينخفض قبل الارتداد (علامة استنزاف البائعين)
    vol_trend = float(volume.iloc[idx-5:idx].mean()) / float(volume.iloc[idx-15:idx-5].mean())
    vol_trend = np.clip(vol_trend, 0, 2) / 2 if vol_trend > 0 else 0.5

    # Price vs MA50 (أكثر استقراراً من MA20)
    ma50 = float(close.iloc[max(0,idx-50):idx].mean())
    p_vs_ma50 = np.clip(p0 / ma50, 0.5, 1.5) / 1.5 if ma50 > 0 else 0.5

    # Momentum 10d (زاوية أوسع)
    mom_10d = np.clip((p0 - p10) / p10, -0.3, 0.3) / 0.3 if p10 > 0 else 0

    return {
        # حاليين
        "rsi":        rsi_val,
        "vol_ratio":  vol_ratio,
        "mom_3d":     mom_3d,
        "mom_5d":     mom_5d,
        "hammer":     hammer,
        "body":       body,
        "p_vs_ma20":  p_vs_ma20,
        # جدد
        "stoch_rsi":  stoch_rsi,
        "atr_ratio":  atr_ratio,
        "vol_trend":  vol_trend,
        "p_vs_ma50":  p_vs_ma50,
        "mom_10d":    mom_10d,
    }


# ═══════════════════════════════════════════════════════
# 3. رصد الارتدادات
# ═══════════════════════════════════════════════════════

def find_events(df, min_gain=0.07, stop_loss=0.06, fwd=15):
    close = df["Close"].values
    n = len(close)
    wins, losses = [], []

    for i in range(50, n - fwd):
        if close[i] > min(close[max(0,i-5):i+1]) * 1.002:
            continue
        future = close[i+1:i+fwd+1]
        g = (np.max(future) - close[i]) / close[i]
        l = (close[i] - np.min(future)) / close[i]
        feat = extract_all_features(df, i)
        if feat is None: continue
        if g >= min_gain and l < stop_loss:
            wins.append(feat)
        elif l >= stop_loss and g < min_gain:
            losses.append(feat)

    return wins, losses


# ═══════════════════════════════════════════════════════
# 4. قياس قوة كل مؤشر (Point-Biserial Correlation)
# ═══════════════════════════════════════════════════════

def indicator_power(wins, losses):
    """يقيس قدرة كل مؤشر على التمييز بين الارتدادات الناجحة والفاشلة"""
    if not wins or not losses: return {}

    feat_names = list(wins[0].keys())
    results = {}

    for feat in feat_names:
        win_vals  = [w[feat] for w in wins]
        loss_vals = [l[feat] for l in losses]

        all_vals = win_vals + loss_vals
        labels   = [1]*len(win_vals) + [0]*len(loss_vals)

        corr, pval = stats.pointbiserialr(labels, all_vals)

        results[feat] = {
            "corr":      round(corr, 4),
            "pval":      round(pval, 4),
            "win_mean":  round(np.mean(win_vals), 4),
            "loss_mean": round(np.mean(loss_vals), 4),
            "separation":round(abs(np.mean(win_vals) - np.mean(loss_vals)), 4),
            "significant": pval < 0.05,
        }

    return dict(sorted(results.items(), key=lambda x: abs(x[1]["corr"]), reverse=True))


# ═══════════════════════════════════════════════════════
# 5. مقارنة طرق الـ Similarity
# ═══════════════════════════════════════════════════════

def cosine_sim(a, b):
    na, nb = np.linalg.norm(a), np.linalg.norm(b)
    return float(np.dot(a, b) / (na * nb)) if na > 0 and nb > 0 else 0.0

def weighted_sim(a, b, weights):
    diff = np.abs(a - b) * weights
    return float(1 / (1 + np.sum(diff)))

def evaluate_method(wins, losses, feat_subset, weights=None, thr=0.55):
    """يقيس دقة طريقة similarity معينة بـ leave-one-out"""
    correct = 0
    total   = 0

    all_events = [(f, 1) for f in wins] + [(f, 0) for f in losses]

    for i, (feat_i, label_i) in enumerate(all_events):
        vec_i = np.array([feat_i[k] for k in feat_subset])

        sims_win = []
        sims_loss = []

        for j, (feat_j, label_j) in enumerate(all_events):
            if i == j: continue
            vec_j = np.array([feat_j[k] for k in feat_subset])

            if weights is not None:
                sim = weighted_sim(vec_i, vec_j, np.array(weights))
            else:
                sim = cosine_sim(vec_i, vec_j)

            if sim >= thr:
                if label_j == 1: sims_win.append(sim)
                else:            sims_loss.append(sim)

        if not sims_win and not sims_loss: continue
        total += 1
        pred = 1 if len(sims_win) >= len(sims_loss) else 0
        if pred == label_i: correct += 1

    return round(correct / total, 4) if total > 0 else 0.0


# ═══════════════════════════════════════════════════════
# 6. اختبار التركيبات المختلفة
# ═══════════════════════════════════════════════════════

COMBINATIONS = {
    "Current_7":  ["rsi", "vol_ratio", "mom_3d", "mom_5d", "hammer", "body", "p_vs_ma20"],
    "Proposed_5": ["stoch_rsi", "vol_ratio", "atr_ratio", "hammer", "p_vs_ma50"],
    "Proposed_6": ["stoch_rsi", "vol_ratio", "atr_ratio", "vol_trend", "hammer", "p_vs_ma50"],
    "Best_RSI_Vol": ["rsi", "vol_ratio", "hammer", "p_vs_ma50", "atr_ratio"],
    "All_12":     ["rsi","vol_ratio","mom_3d","mom_5d","hammer","body","p_vs_ma20",
                   "stoch_rsi","atr_ratio","vol_trend","p_vs_ma50","mom_10d"],
    "No_Momentum":["rsi", "vol_ratio", "hammer", "body", "p_vs_ma50", "atr_ratio", "vol_trend"],
}

WEIGHTED_PROPOSED = {
    "feats":   ["stoch_rsi", "vol_ratio", "atr_ratio", "hammer", "p_vs_ma50"],
    "weights": [0.30,         0.25,        0.20,         0.15,     0.10],
}


# ═══════════════════════════════════════════════════════
# 7. التشغيل الكامل
# ═══════════════════════════════════════════════════════

def run_study(n_simulations=8):
    print("=" * 65)
    print("  PATTERN ENGINE — INDICATOR STUDY")
    print("=" * 65)

    all_power  = {k: [] for k in extract_all_features(generate_egx_like(200), 100).keys()}
    combo_accs = {k: [] for k in COMBINATIONS}
    weighted_accs = []
    event_counts  = []

    for sim in range(n_simulations):
        df = generate_egx_like(n=600, seed=sim*17)
        wins, losses = find_events(df)
        if len(wins) + len(losses) < 10: continue
        event_counts.append((len(wins), len(losses)))

        # قوة المؤشرات
        power = indicator_power(wins, losses)
        for feat, metrics in power.items():
            all_power[feat].append(abs(metrics["corr"]))

        # دقة التركيبات
        for name, feats in COMBINATIONS.items():
            acc = evaluate_method(wins, losses, feats)
            combo_accs[name].append(acc)

        # Weighted
        acc_w = evaluate_method(wins, losses,
                                WEIGHTED_PROPOSED["feats"],
                                WEIGHTED_PROPOSED["weights"])
        weighted_accs.append(acc_w)

    # ── نتائج قوة المؤشرات ──────────────────────────────────────
    print(f"\n{'─'*65}")
    print(f"  A. INDICATOR POWER  (Point-Biserial Correlation)")
    print(f"     avg over {n_simulations} simulations | higher = better")
    print(f"{'─'*65}")
    print(f"  {'Indicator':<14} {'Avg |Corr|':>10}  {'Grade':>6}  {'Keep?':>6}")
    print(f"  {'─'*13} {'─'*10}  {'─'*6}  {'─'*6}")

    feat_scores = {}
    for feat, corrs in all_power.items():
        avg = round(np.mean(corrs), 4) if corrs else 0
        feat_scores[feat] = avg

    for feat, avg in sorted(feat_scores.items(), key=lambda x: -x[1]):
        tag  = "★★★" if avg >= 0.15 else ("★★" if avg >= 0.08 else ("★" if avg >= 0.04 else "✗"))
        keep = "YES" if avg >= 0.05 else "NO"
        new  = " [NEW]" if feat in ["stoch_rsi","atr_ratio","vol_trend","p_vs_ma50","mom_10d"] else ""
        print(f"  {feat+new:<20} {avg:>10.4f}  {tag:>6}  {keep:>6}")

    # ── نتائج التركيبات ──────────────────────────────────────────
    print(f"\n{'─'*65}")
    print(f"  B. COMBINATION ACCURACY  (leave-one-out)")
    print(f"     % of events correctly classified")
    print(f"{'─'*65}")
    print(f"  {'Combination':<22} {'Accuracy':>10}  {'Rank':>6}")
    print(f"  {'─'*21} {'─'*10}  {'─'*6}")

    combo_results = {}
    for name, accs in combo_accs.items():
        combo_results[name] = round(np.mean(accs), 4) if accs else 0

    # أضف Weighted
    combo_results["Weighted_Proposed"] = round(np.mean(weighted_accs), 4) if weighted_accs else 0

    ranked = sorted(combo_results.items(), key=lambda x: -x[1])
    for rank, (name, acc) in enumerate(ranked, 1):
        marker = " ◄ BEST" if rank == 1 else (" ◄ current" if name == "Current_7" else "")
        print(f"  {name:<22} {acc:>10.4f}  {rank:>6}{marker}")

    # ── إحصائيات البيانات ────────────────────────────────────────
    avg_wins   = np.mean([e[0] for e in event_counts])
    avg_losses = np.mean([e[1] for e in event_counts])
    print(f"\n{'─'*65}")
    print(f"  C. DATA STATS")
    print(f"     Avg wins/sim: {avg_wins:.1f}   Avg losses/sim: {avg_losses:.1f}")
    print(f"     Win rate baseline: {avg_wins/(avg_wins+avg_losses)*100:.1f}%")

    # ── التوصية النهائية ─────────────────────────────────────────
    best_combo = ranked[0][0]
    best_acc   = ranked[0][1]
    current_acc= combo_results["Current_7"]
    improvement = round((best_acc - current_acc) * 100, 1)

    print(f"\n{'═'*65}")
    print(f"  RECOMMENDATION")
    print(f"{'═'*65}")
    print(f"  Current accuracy  : {current_acc:.4f}")
    print(f"  Best combination  : {best_combo}")
    print(f"  Best accuracy     : {best_acc:.4f}")
    print(f"  Improvement       : +{improvement}%")

    # أفضل المؤشرات للاحتفاظ بها
    keep_feats = [f for f, s in sorted(feat_scores.items(), key=lambda x: -x[1]) if s >= 0.05]
    print(f"\n  Top indicators to keep ({len(keep_feats)}):")
    for f in keep_feats[:8]:
        tag = "[NEW]" if f in ["stoch_rsi","atr_ratio","vol_trend","p_vs_ma50","mom_10d"] else "[curr]"
        print(f"    {tag} {f}  ({feat_scores[f]:.4f})")

    print(f"{'═'*65}\n")

    return feat_scores, combo_results


if __name__ == "__main__":
    feat_scores, combo_results = run_study(n_simulations=10)
