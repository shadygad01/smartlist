"""
Research Engine
===============
تحليل ML للبيانات المتراكمة — يُنتج توصيات فقط، لا يُعدّل النظام.

الهدف: تحديد المتغيرات التي تتنبأ بـ:
  1. MFE عالي (أفضل مؤشر لجودة الـ bottom)
  2. BQ Score عالي (تقييم شامل لجودة الـ bottom)
  3. أدنى Drawdown (MAE)

المخرجات: توصيات نصية فقط — بدون تعديل تلقائي للنظام.

الحماية من الـ overfitting:
  - تقسيم زمني (70% تدريب / 30% اختبار بالترتيب التاريخي)
  - لا تسرّب مستقبلي — المتغيرات كلها من وقت الإشارة
  - حد أدنى 30 إشارة لتشغيل أي نموذج
"""

import json
import sys
from datetime import date, timedelta
from typing import Optional

try:
    import numpy as np
    import pandas as pd
except ImportError:
    sys.exit("Run: pip install numpy pandas")

try:
    from sklearn.ensemble import RandomForestRegressor, GradientBoostingRegressor
    from sklearn.inspection import permutation_importance
    from sklearn.metrics import r2_score, mean_absolute_error
    from sklearn.preprocessing import StandardScaler
    SKLEARN_OK = True
except ImportError:
    SKLEARN_OK = False

try:
    import lightgbm as lgb
    LGBM_OK = True
except ImportError:
    LGBM_OK = False

from signal_db import DB_PATH, get_mature_signals, CURRENT_WEIGHTS, WEIGHT_LABELS

try:
    from pattern_engine import DEFAULT_WEIGHTS as PATTERN_DEFAULT_WEIGHTS
except ImportError:
    PATTERN_DEFAULT_WEIGHTS = {
        "p_vs_ma20": 0.21, "mom_10d": 0.20, "stoch_rsi": 0.18,
        "atr_ratio": 0.15, "mom_5d":  0.14, "vol_trend": 0.12,
    }

MIN_SAMPLES       = 30   # حد أدنى للتدريب global
TRAIN_SPLIT_PCT   = 0.70 # تقسيم زمني — أول 70% للتدريب
MIN_PER_STOCK     = 20   # إشارات ناضجة لتفعيل تحليل per-stock
MIN_PER_STOCK_ML  = 30   # إشارات ناضجة لتفعيل ML model per-stock
TOP_MFE_PERCENTILE= 0.75 # الربع الأعلى = "نماذج الفائزة"

# المتغيرات الكاملة بعد إضافة sv/hvn/macd/vol_spike
ALL_FEATURE_COLS = [
    "raw_score", "adj_score",
    "r1_price", "r2_ob", "r3_liquidity", "r4_htf",
    "r5_avwap", "r6_macd", "r7_div", "r8_demand",
    "discount_depth",
    "pattern_score", "pattern_eff", "pattern_wr", "pattern_gain",
    "ind_stoch_rsi", "ind_p_vs_ma20", "ind_mom_10d",
    "ind_mom_5d", "ind_atr_ratio", "ind_vol_trend",
    "sv_hit", "sv_score", "hvn_hit", "hvn_score",
    "macd_val", "vol_spike",
    "is_ramadan", "is_cbe", "stock_tier",
]

# ── المتغيرات المستخدمة في الـ ML ─────────────────────────────────────────────
# كلها من وقت الإشارة (صفر تسرّب مستقبلي)
FEATURE_COLS = [
    "raw_score", "adj_score",
    "r1_price", "r2_ob", "r3_liquidity", "r4_htf",
    "r5_avwap", "r6_macd", "r7_div", "r8_demand",
    "discount_depth",
    "pattern_score", "pattern_eff", "pattern_wr", "pattern_gain", "pattern_n",
    "ind_stoch_rsi", "ind_p_vs_ma20", "ind_mom_10d",
    "ind_mom_5d", "ind_atr_ratio", "ind_vol_trend",
    "is_ramadan", "is_cbe", "stock_tier",
]

# ── المتغيرات المستهدفة — الأولوية للـ MFE و BQ ─────────────────────────────
TARGET_MFE = "mfe_20d"     # الأساسي: أقصى ربح غير محقق
TARGET_BQ  = "bq_score"   # الشامل: تقييم جودة الـ bottom
TARGET_MAE = "mae_20d"     # سالب: نريد تقليله (ندخله كـ abs)

# ── Pattern Engine — ارتباط بـ DB columns ─────────────────────────────────────
PATTERN_INDICATOR_COLS = [
    "ind_stoch_rsi", "ind_p_vs_ma20", "ind_mom_10d",
    "ind_mom_5d",    "ind_atr_ratio", "ind_vol_trend",
]
# الاتجاه المتوقع لكل مؤشر (lower = قيمة منخفضة تعني إشارة أفضل)
PATTERN_EXPECTED_DIR = {
    "ind_stoch_rsi": "lower",   # oversold = جيد
    "ind_p_vs_ma20": "lower",   # تحت MA20 = جيد
    "ind_mom_10d":   "lower",   # نزل كفاية = جيد
    "ind_mom_5d":    "lower",   # نزل كفاية = جيد
    "ind_atr_ratio": "higher",  # تقلب متزايد = جيد
    "ind_vol_trend": "lower",   # الحجم يخف = جيد
}
# ربط عمود DB بمفتاح pattern_engine.DEFAULT_WEIGHTS
INDICATOR_ENGINE_KEY = {
    "ind_stoch_rsi": "stoch_rsi",
    "ind_p_vs_ma20": "p_vs_ma20",
    "ind_mom_10d":   "mom_10d",
    "ind_mom_5d":    "mom_5d",
    "ind_atr_ratio": "atr_ratio",
    "ind_vol_trend": "vol_trend",
}


# ── Helpers ────────────────────────────────────────────────────────────────────

def _to_df(signals: list) -> pd.DataFrame:
    df = pd.DataFrame(signals)
    if df.empty:
        return df
    df = df.sort_values("signal_date").reset_index(drop=True)
    # mae_20d سالبة — نحوّلها لقيمة موجبة (سوء الأداء)
    if "mae_20d" in df.columns:
        df["mae_20d"] = df["mae_20d"].abs()
    return df


def _prepare(df: pd.DataFrame, target: str) -> tuple:
    """
    يُحضّر X, y مع إزالة الصفوف التي تحتوي على NaN في الفيتشرز أو الهدف.
    يُرجع (X_df, y_series) أو (None, None).
    """
    cols  = [c for c in FEATURE_COLS if c in df.columns]
    valid = df[cols + [target]].dropna()
    if len(valid) < MIN_SAMPLES:
        return None, None
    return valid[cols], valid[target]


def _time_split(X: pd.DataFrame, y: pd.Series):
    """تقسيم زمني — لا خلط بين المستقبل والماضي."""
    n     = len(X)
    split = int(n * TRAIN_SPLIT_PCT)
    return (X.iloc[:split], X.iloc[split:],
            y.iloc[:split], y.iloc[split:])


def _feat_importance_rf(X_tr, y_tr, X_te, y_te, feature_names) -> dict:
    """RandomForest feature importance + permutation importance."""
    model = RandomForestRegressor(
        n_estimators=200, max_depth=6,
        min_samples_leaf=3, random_state=42, n_jobs=-1,
    )
    model.fit(X_tr, y_tr)
    y_pred = model.predict(X_te)
    r2  = r2_score(y_te, y_pred)
    mae = mean_absolute_error(y_te, y_pred)

    # permutation importance على مجموعة الاختبار (أكثر دقة من impurity)
    perm = permutation_importance(model, X_te, y_te, n_repeats=15, random_state=42)
    imp  = dict(zip(feature_names, perm.importances_mean))

    return {"model": "RandomForest", "r2": round(r2, 3), "mae": round(mae, 4),
            "importance": imp, "n_train": len(y_tr), "n_test": len(y_te)}


def _feat_importance_gbm(X_tr, y_tr, X_te, y_te, feature_names) -> dict:
    """GBM (LightGBM إن كان متاحاً، وإلا sklearn GBM)."""
    if LGBM_OK:
        model = lgb.LGBMRegressor(
            n_estimators=300, learning_rate=0.05, max_depth=5,
            num_leaves=31, min_child_samples=5, random_state=42,
            verbose=-1,
        )
        model.fit(X_tr, y_tr,
                  eval_set=[(X_te, y_te)],
                  callbacks=[lgb.early_stopping(30, verbose=False),
                              lgb.log_evaluation(-1)])
        imp = dict(zip(feature_names,
                       model.feature_importances_ / max(model.feature_importances_.sum(), 1)))
        label = "LightGBM"
    else:
        model = GradientBoostingRegressor(
            n_estimators=200, max_depth=4, learning_rate=0.05,
            min_samples_leaf=3, random_state=42,
        )
        model.fit(X_tr, y_tr)
        imp = dict(zip(feature_names, model.feature_importances_))
        label = "GBM(sklearn)"

    y_pred = model.predict(X_te)
    r2  = r2_score(y_te, y_pred)
    mae = mean_absolute_error(y_te, y_pred)
    return {"model": label, "r2": round(r2, 3), "mae": round(mae, 4),
            "importance": imp, "n_train": len(y_tr), "n_test": len(y_te)}


# ── Correlation Analysis ───────────────────────────────────────────────────────

def _correlation_analysis(df: pd.DataFrame) -> dict:
    """
    ارتباط Spearman لكل فيتشر مع MFE و BQ Score (لا تفترض توزيعاً خطياً).
    """
    cols  = [c for c in FEATURE_COLS if c in df.columns]
    targets = {t: t for t in [TARGET_MFE, TARGET_BQ, "mae_20d"]
               if t in df.columns}

    results = {}
    for tname, tcol in targets.items():
        valid = df[cols + [tcol]].dropna()
        if len(valid) < 10:
            continue
        corr = {}
        for col in cols:
            c = valid[[col, tcol]].dropna()
            if len(c) >= 10:
                r = float(c[col].corr(c[tcol], method="spearman"))
                corr[col] = round(r, 3)
        # ترتيب تنازلي حسب القيمة المطلقة
        results[tname] = dict(sorted(corr.items(), key=lambda x: abs(x[1]), reverse=True))

    return results


# ── Weight Suggestions ─────────────────────────────────────────────────────────

def _suggest_weights(mfe_imp: dict, bq_imp: dict) -> dict:
    """
    يقترح تعديلات على الأوزان الحالية بناءً على متوسط الـ importance مع MFE و BQ.
    يتحفّظ جداً: لا يقترح تغييراً > 30% من الوزن الحالي.

    يُرجع: {
        "r1_price": {"current": 30, "suggested": 28, "change": -2, "reason": "..."},
        ...
    }
    """
    # المتغيرات التي ترتبط بمكونات smc فقط
    smc_map = {
        "r1_price":    ["r1_price"],
        "r2_ob":       ["r2_ob"],
        "r3_liquidity":["r3_liquidity"],
        "r4_htf":      ["r4_htf"],
        "r5_avwap":    ["r5_avwap"],
        "r6_macd":     ["r6_macd"],
        "r7_div":      ["r7_div"],
        "r8_demand":   ["r8_demand"],
    }

    suggestions = {}
    for comp, feat_keys in smc_map.items():
        # متوسط الـ importance من النموذجين للمتغيرات المرتبطة بهذا المكون
        imp_vals = []
        for k in feat_keys:
            if k in mfe_imp:
                imp_vals.append(mfe_imp[k])
            if k in bq_imp:
                imp_vals.append(bq_imp[k])

        if not imp_vals:
            suggestions[comp] = {
                "current":   CURRENT_WEIGHTS[comp],
                "suggested": CURRENT_WEIGHTS[comp],
                "change":    0,
                "reason":    "insufficient data",
            }
            continue

        avg_imp = sum(imp_vals) / len(imp_vals)

        # نُحوّل الـ importance النسبية إلى وزن مقترح
        total_imp = sum(
            sum(mfe_imp.get(k, 0) + bq_imp.get(k, 0) for k in ks)
            for ks in smc_map.values()
        ) or 1

        target_share = avg_imp / total_imp
        current_share = CURRENT_WEIGHTS[comp] / 100

        # تعديل محدود: لا نقترح أكثر من 30% تغيير
        max_delta = CURRENT_WEIGHTS[comp] * 0.30
        raw_delta = (target_share - current_share) * 100
        delta     = max(-max_delta, min(max_delta, raw_delta))

        suggested = round(CURRENT_WEIGHTS[comp] + delta)
        suggested = max(1, suggested)   # لا وزن صفري

        direction = "higher" if delta > 0 else "lower"
        reason = (f"importance rank vs MFE+BQ suggests {direction} weight; "
                  f"avg_importance={avg_imp:.4f}")

        suggestions[comp] = {
            "current":   CURRENT_WEIGHTS[comp],
            "suggested": suggested,
            "change":    suggested - CURRENT_WEIGHTS[comp],
            "reason":    reason,
        }

    return suggestions


# ── Segment Analysis ───────────────────────────────────────────────────────────

def _segment_analysis(df: pd.DataFrame) -> dict:
    """
    يُحلّل أداء الإشارات حسب:
      - نطاقات الـ score (35-50, 50-65, 65-80, 80+)
      - القطاع
      - ظروف السوق (market_regime)
      - Tier (جودة السهم)
    ويقيس الأداء بـ MFE و BQ Score فقط.
    """
    results = {}

    def _agg(sub: pd.DataFrame, label: str) -> dict:
        if len(sub) < 3:
            return {"n": len(sub), "note": "insufficient data"}
        out = {"n": len(sub)}
        for col in [TARGET_MFE, TARGET_BQ, "mae_20d", "r20d"]:
            if col in sub.columns:
                clean = sub[col].dropna()
                if len(clean) > 0:
                    out[f"{col}_mean"] = round(float(clean.mean()), 4)
                    out[f"{col}_med"]  = round(float(clean.median()), 4)
                    out[f"{col}_p75"]  = round(float(clean.quantile(0.75)), 4)
        return out

    # ── Score Buckets ──────────────────────────────────────────────────────
    buckets = [(35, 50), (50, 65), (65, 80), (80, 101)]
    score_res = {}
    for lo, hi in buckets:
        sub = df[(df["raw_score"] >= lo) & (df["raw_score"] < hi)]
        score_res[f"{lo}-{hi-1}"] = _agg(sub, f"score_{lo}")
    results["by_score_bucket"] = score_res

    # ── Market Regime ──────────────────────────────────────────────────────
    if "market_regime" in df.columns:
        mr_res = {}
        for regime in df["market_regime"].dropna().unique():
            sub = df[df["market_regime"] == regime]
            mr_res[regime] = _agg(sub, regime)
        results["by_market_regime"] = mr_res

    # ── Sector ────────────────────────────────────────────────────────────
    if "sector" in df.columns:
        sec_res = {}
        for sector in df["sector"].dropna().unique():
            if not sector:
                continue
            sub = df[df["sector"] == sector]
            if len(sub) >= 3:
                sec_res[sector] = _agg(sub, sector)
        results["by_sector"] = sec_res

    # ── Stock Tier ────────────────────────────────────────────────────────
    if "stock_tier" in df.columns:
        tier_res = {}
        for tier in sorted(df["stock_tier"].dropna().unique()):
            sub = df[df["stock_tier"] == tier]
            tier_res[str(tier)] = _agg(sub, f"tier_{tier}")
        results["by_tier"] = tier_res

    # ── Context (Ramadan / CBE) ────────────────────────────────────────────
    ctx_res = {}
    for flag, col in [("ramadan", "is_ramadan"), ("cbe", "is_cbe")]:
        if col in df.columns:
            for val in [0, 1]:
                sub = df[df[col] == val]
                ctx_res[f"{flag}={val}"] = _agg(sub, flag)
    results["by_context"] = ctx_res

    # ── Discount Depth Buckets ─────────────────────────────────────────────
    if "discount_depth" in df.columns:
        dd_res = {}
        for lo, hi in [(0, 0.33), (0.33, 0.67), (0.67, 1.01)]:
            sub = df[(df["discount_depth"] >= lo) & (df["discount_depth"] < hi)]
            label = f"depth_{lo:.2f}-{hi:.2f}"
            dd_res[label] = _agg(sub, label)
        results["by_discount_depth"] = dd_res

    return results


# ── Pattern Analysis ──────────────────────────────────────────────────────────

def _pattern_analysis(df: pd.DataFrame) -> dict:
    """
    تحليل Pattern Recognition Engine بالكامل — يستخدم MFE و BQ كـ target.

    المشكلة المعالَجة:
      الـ AUC study الأصلية في pattern_engine استخدمت win/loss (7% = win) كـ target.
      هذا النظام بحثي يستخدم MFE و BQ Score — أدق وأنسب لاستراتيجية الـ bottom fishing.
      النتيجة: قد نكتشف أن ترتيب أهمية المؤشرات مختلف عند القياس بـ MFE.

    المخرجات:
      indicator_correlations    ← Spearman(كل مؤشر, MFE) و Spearman(كل مؤشر, BQ)
      direction_validation      ← هل اتجاه كل مؤشر يتوافق مع البيانات الفعلية؟
      pattern_score_buckets     ← MFE و BQ عند pattern_score 0-30 / 30-50 / 50-70 / 70+
      effective_score_buckets   ← نفس الشيء مع effective_score
      combined_smc_pattern      ← هل pattern يضيف قيمة فوق SMC وحده؟
      entry_zone_analysis       ← أي منطقة دخول (z1/z2/z3) تُنتج MFE أعلى؟
      indicator_weight_suggestions ← أوزان مقترحة مبنية على MFE (لا تُطبَّق تلقائياً)
    """
    result = {
        "indicator_correlations":       {},
        "direction_validation":         {},
        "pattern_score_buckets":        {},
        "effective_score_buckets":      {},
        "combined_smc_pattern":         {},
        "entry_zone_analysis":          {},
        "indicator_weight_suggestions": {},
        "per_stock_analysis":           {},
        "n_used": 0,
    }

    base = df.dropna(subset=["mfe_20d", "bq_score"])
    if len(base) < 5:
        return result
    result["n_used"] = len(base)

    def _agg(sub):
        if len(sub) < 2:
            return {"n": len(sub)}
        out = {"n": len(sub)}
        for col in ["mfe_20d", "bq_score", "mae_20d"]:
            if col in sub.columns:
                c = sub[col].dropna()
                if len(c):
                    out[f"{col}_mean"] = round(float(c.mean()), 4)
                    out[f"{col}_med"]  = round(float(c.median()), 4)
        return out

    # ── 1. Spearman لكل مؤشر مع MFE و BQ ─────────────────────────────────
    ind_corr = {}
    for col in PATTERN_INDICATOR_COLS:
        if col not in base.columns:
            continue
        c = base[[col, "mfe_20d", "bq_score"]].dropna()
        if len(c) < 5:
            continue
        corr_mfe = float(c[col].corr(c["mfe_20d"], method="spearman"))
        corr_bq  = float(c[col].corr(c["bq_score"], method="spearman"))
        ind_corr[col] = {"corr_mfe": round(corr_mfe, 3), "corr_bq": round(corr_bq, 3)}
    result["indicator_correlations"] = ind_corr

    # ── 2. Direction Validation ───────────────────────────────────────────
    # "lower" يعني نتوقع corr سالب مع MFE (قيمة منخفضة = نتيجة أفضل)
    dir_val = {}
    for col, exp_dir in PATTERN_EXPECTED_DIR.items():
        if col not in ind_corr:
            continue
        corr      = ind_corr[col]["corr_mfe"]
        exp_sign  = -1 if exp_dir == "lower" else +1
        confirmed = ((corr < 0) == (exp_sign < 0))
        strength  = abs(corr)

        if strength < 0.05:
            verdict = "إشارة ضعيفة — بيانات غير كافية"
        elif confirmed and strength >= 0.15:
            verdict = "مؤكَّد"
        elif confirmed:
            verdict = "مؤكَّد جزئياً"
        else:
            verdict = "تعارض في الاتجاه — يحتاج مراجعة"

        dir_val[col] = {
            "expected":  exp_dir,
            "corr_mfe":  round(corr, 3),
            "confirmed": confirmed,
            "verdict":   verdict,
        }
    result["direction_validation"] = dir_val

    # ── 3. Pattern Score Buckets ──────────────────────────────────────────
    if "pattern_score" in base.columns:
        ps = {}
        for lo, hi in [(0, 30), (30, 50), (50, 70), (70, 101)]:
            sub = base[(base["pattern_score"] >= lo) & (base["pattern_score"] < hi)]
            ps[f"{lo}-{hi-1}"] = _agg(sub)
        result["pattern_score_buckets"] = ps

    # ── 4. Effective Score Buckets ────────────────────────────────────────
    if "pattern_eff" in base.columns:
        eff = {}
        for lo, hi in [(0, 20), (20, 40), (40, 60), (60, 101)]:
            sub = base[(base["pattern_eff"] >= lo) & (base["pattern_eff"] < hi)]
            eff[f"{lo}-{hi-1}"] = _agg(sub)
        result["effective_score_buckets"] = eff

    # ── 5. Combined SMC + Pattern ─────────────────────────────────────────
    # هل الجمع بين SMC عالي + Pattern عالي يُنتج MFE أعلى؟
    if "raw_score" in base.columns and "pattern_score" in base.columns:
        hs = base["raw_score"]    >= 60
        hp = base["pattern_score"] >= 50
        result["combined_smc_pattern"] = {
            "high_smc_high_pattern": _agg(base[hs & hp]),
            "high_smc_low_pattern":  _agg(base[hs & ~hp]),
            "low_smc_high_pattern":  _agg(base[~hs & hp]),
            "low_smc_low_pattern":   _agg(base[~hs & ~hp]),
        }

    # ── 6. Entry Zone Analysis ────────────────────────────────────────────
    if all(c in base.columns for c in ["zone1", "zone2", "zone3", "price"]):
        def _nearest(row):
            p = row["price"]
            dists = {}
            for z, col in [("z1", "zone1"), ("z2", "zone2"), ("z3", "zone3")]:
                v = row[col]
                if v and v > 0:
                    dists[z] = abs(p - v)
            return min(dists, key=dists.get) if dists else "unknown"

        base = base.copy()
        base["nearest_zone"] = base.apply(_nearest, axis=1)
        result["entry_zone_analysis"] = {
            z: _agg(base[base["nearest_zone"] == z])
            for z in ["z1", "z2", "z3"]
        }

    # ── 7. Indicator Weight Suggestions (مبنية على MFE لا AUC win/loss) ───
    if len(ind_corr) >= 4:
        # نجمع |corr_mfe| + 0.5×|corr_bq| كمقياس لأهمية كل مؤشر
        scores = {
            col: abs(v["corr_mfe"]) + 0.5 * abs(v["corr_bq"])
            for col, v in ind_corr.items()
        }
        total = sum(scores.values()) or 1
        ws = {}
        for col, score in scores.items():
            eng_key = INDICATOR_ENGINE_KEY.get(col)
            if not eng_key:
                continue
            cur_w  = PATTERN_DEFAULT_WEIGHTS.get(eng_key, 1/6)
            sug_w  = score / total
            # نُحدّد التغيير بحد أقصى 50% من الوزن الحالي
            delta  = max(-cur_w * 0.50, min(cur_w * 0.50, sug_w - cur_w))
            final  = round(cur_w + delta, 4)
            ws[eng_key] = {
                "current":          cur_w,
                "suggested":        final,
                "change":           round(final - cur_w, 4),
                "combined_corr":    round(score, 4),
                "note":             "MFE+BQ Spearman — لا AUC(win/loss)",
            }
        result["indicator_weight_suggestions"] = ws

    # ── 8. Per-Stock Hybrid Analysis ──────────────────────────────────────
    if "symbol" in base.columns:
        result["per_stock_analysis"] = _per_stock_pattern_analysis(base, ind_corr)

    return result


# ── Best Conditions Profile ───────────────────────────────────────────────────

def _best_conditions_profile(df: pd.DataFrame) -> dict:
    """
    لكل سهم عنده ≥ 10 إشارات ناضجة:
      - يفصل أفضل 25% بـ MFE (Top Quartile) عن الباقي
      - لكل متغير يحسب: متوسط في الـ Top vs الباقي، والفرق
      - يُرتّب المتغيرات حسب قوة التمييز
      - ينتج "بصمة الـ bottom المثالي" لكل سهم

    الهدف: "لسهم ETEL — الإشارات اللي أدّت لـ MFE > 18% كانت دايماً عندها هذه الشروط"
    """
    result = {}
    base   = df.dropna(subset=["mfe_20d", "symbol"])
    feats  = [c for c in ALL_FEATURE_COLS if c in base.columns]

    for sym in sorted(base["symbol"].unique()):
        sub = base[base["symbol"] == sym].dropna(subset=["mfe_20d"])
        n   = len(sub)
        if n < 10:
            continue

        mfe_thresh = float(sub["mfe_20d"].quantile(TOP_MFE_PERCENTILE))
        top    = sub[sub["mfe_20d"] >= mfe_thresh]
        bottom = sub[sub["mfe_20d"] <  mfe_thresh]
        n_top  = len(top)

        conditions = {}
        for feat in feats:
            t_vals = top[feat].dropna()
            b_vals = bottom[feat].dropna()
            if len(t_vals) < 2 or len(b_vals) < 2:
                continue

            t_mean  = float(t_vals.mean())
            b_mean  = float(b_vals.mean())
            t_std   = float(sub[feat].std()) or 1.0
            # effect size (Cohen's d simplified)
            effect  = (t_mean - b_mean) / t_std
            conditions[feat] = {
                "top_mean":    round(t_mean, 4),
                "bottom_mean": round(b_mean, 4),
                "diff":        round(t_mean - b_mean, 4),
                "effect_size": round(effect, 3),
            }

        # ترتيب حسب |effect_size|
        ranked = dict(sorted(
            conditions.items(),
            key=lambda x: abs(x[1]["effect_size"]),
            reverse=True,
        ))

        # ── وصف نصي لأهم 5 شروط ─────────────────────────────────────────
        top5_desc = []
        for feat, v in list(ranked.items())[:5]:
            direction = "أعلى" if v["diff"] > 0 else "أقل"
            top5_desc.append(
                f"{feat}: {direction} ({v['top_mean']:.3f} vs {v['bottom_mean']:.3f})"
            )

        result[sym] = {
            "n":           n,
            "n_top":       n_top,
            "mfe_threshold": round(mfe_thresh, 4),
            "conditions":  ranked,
            "top5_summary": top5_desc,
        }

    return result


# ── Per-Stock ML Models ────────────────────────────────────────────────────────

def _per_stock_ml(df: pd.DataFrame) -> dict:
    """
    لكل سهم عنده ≥ MIN_PER_STOCK_ML إشارة ناضجة:
      - يدرّب RandomForest مستقل على مجموعة المتغيرات الكاملة
      - يستخدم MFE كـ target الأساسي
      - يستخدم BQ Score كـ target ثانوي
      - يُرجع feature importance + R² + أهم 5 متغيرات لكل نموذج

    يُطبَّق time-split: أول 70% تدريب، آخر 30% اختبار (ترتيب زمني).
    """
    if not SKLEARN_OK:
        return {"error": "scikit-learn not installed"}

    result = {}
    base   = df.dropna(subset=["mfe_20d", "symbol"])
    feats  = [c for c in ALL_FEATURE_COLS if c in base.columns]

    for sym in sorted(base["symbol"].unique()):
        sub = base[base["symbol"] == sym].sort_values("signal_date")
        n   = len(sub)
        if n < MIN_PER_STOCK_ML:
            continue

        sym_result = {"n": n, "mfe_model": None, "bq_model": None}

        for target, key in [(TARGET_MFE, "mfe_model"), (TARGET_BQ, "bq_model")]:
            valid = sub[feats + [target]].dropna()
            if len(valid) < MIN_PER_STOCK_ML:
                continue

            X = valid[feats]
            y = valid[target]
            split = max(10, int(len(valid) * TRAIN_SPLIT_PCT))
            X_tr, X_te = X.iloc[:split], X.iloc[split:]
            y_tr, y_te = y.iloc[:split], y.iloc[split:]

            if len(X_te) < 3:
                continue

            try:
                model = RandomForestRegressor(
                    n_estimators=150, max_depth=5,
                    min_samples_leaf=2, random_state=42, n_jobs=-1,
                )
                model.fit(X_tr.values, y_tr.values)
                y_pred = model.predict(X_te.values)
                r2     = round(r2_score(y_te.values, y_pred), 3)

                imp  = dict(zip(feats, model.feature_importances_))
                top5 = sorted(imp.items(), key=lambda x: x[1], reverse=True)[:5]

                sym_result[key] = {
                    "r2":       r2,
                    "n_train":  len(y_tr),
                    "n_test":   len(y_te),
                    "top5":     [(k, round(v, 4)) for k, v in top5],
                    "importance": {k: round(v, 4) for k, v in imp.items()},
                }
            except Exception as e:
                sym_result[key] = {"error": str(e)}

        if sym_result["mfe_model"] or sym_result["bq_model"]:
            result[sym] = sym_result

    return result


# ── Per-Stock Hybrid Analysis ──────────────────────────────────────────────────

def _per_stock_pattern_analysis(df: pd.DataFrame, global_corr: dict) -> dict:
    """
    السلوك الهجين:
      < MIN_PER_STOCK إشارة  → global mode  (يعتمد على التحليل الكلي)
      ≥ MIN_PER_STOCK إشارة  → per-stock mode (تحليل مستقل بمؤشرات السهم)

    يُرجع:
      mode_summary    ← قائمة بأوضاع كل سهم
      per_stock       ← نتائج مفصّلة للأسهم في per-stock mode
      min_required    ← الحد الأدنى المطلوب (MIN_PER_STOCK)
    """
    result = {
        "min_required": MIN_PER_STOCK,
        "mode_summary": {"global_mode": [], "per_stock_mode": []},
        "per_stock":    {},
    }

    base = df.dropna(subset=["mfe_20d", "bq_score"])

    def _sym_weights(sym_corr: dict) -> dict:
        scores = {
            col: abs(v["corr_mfe"]) + 0.5 * abs(v["corr_bq"])
            for col, v in sym_corr.items()
        }
        total = sum(scores.values()) or 1
        ws = {}
        for col, score in scores.items():
            eng_key = INDICATOR_ENGINE_KEY.get(col)
            if not eng_key:
                continue
            cur_w = PATTERN_DEFAULT_WEIGHTS.get(eng_key, 1/6)
            sug_w = score / total
            delta = max(-cur_w * 0.50, min(cur_w * 0.50, sug_w - cur_w))
            final = round(cur_w + delta, 4)
            ws[eng_key] = {
                "current":   cur_w,
                "suggested": final,
                "change":    round(final - cur_w, 4),
            }
        return ws

    for sym in sorted(base["symbol"].unique()):
        sub = base[base["symbol"] == sym]
        n   = len(sub)

        if n < MIN_PER_STOCK:
            result["mode_summary"]["global_mode"].append({
                "symbol":  sym,
                "n":       n,
                "needed":  MIN_PER_STOCK - n,
            })
            continue

        # ── هذا السهم عنده بيانات كافية ────────────────────────────────
        result["mode_summary"]["per_stock_mode"].append({"symbol": sym, "n": n})

        # Spearman لهذا السهم تحديداً
        sym_corr = {}
        for col in PATTERN_INDICATOR_COLS:
            if col not in sub.columns:
                continue
            c = sub[[col, "mfe_20d", "bq_score"]].dropna()
            if len(c) < 5:
                continue
            sym_corr[col] = {
                "corr_mfe": round(float(c[col].corr(c["mfe_20d"], method="spearman")), 3),
                "corr_bq":  round(float(c[col].corr(c["bq_score"], method="spearman")), 3),
            }

        # مقارنة مع الـ global (هل سلوك هذا السهم مختلف؟)
        vs_global = {}
        for col, sv in sym_corr.items():
            gc = global_corr.get(col, {})
            gc_mfe = gc.get("corr_mfe", 0) if isinstance(gc, dict) else gc
            diff   = sv["corr_mfe"] - gc_mfe
            vs_global[col] = {
                "global_corr": round(gc_mfe, 3),
                "stock_corr":  sv["corr_mfe"],
                "difference":  round(diff, 3),
                "diverges":    abs(diff) > 0.15,  # اختلاف ملحوظ عن الـ global
            }

        result["per_stock"][sym] = {
            "n":                     n,
            "indicator_correlations": sym_corr,
            "weight_suggestions":     _sym_weights(sym_corr) if len(sym_corr) >= 4 else {},
            "vs_global":              vs_global,
        }

    return result


# ── Export per-stock weights to pattern_engine ────────────────────────────────

def export_per_stock_weights(research_result: dict,
                              out_path: str = "learned_weights.json") -> bool:
    """
    يصدّر الأوزان المقترحة (global + per-stock) إلى learned_weights.json
    بصيغة متوافقة مع pattern_engine.py.

    تشغيل يدوي فقط:
        python research_engine.py --export-weights

    لتفعيل الأوزان في الماسح:
        1. راجع learned_weights.json
        2. غيّر FREEZE_WEIGHTS = False في pattern_engine.py
    """
    import datetime

    pat          = research_result.get("pattern_analysis", {})
    global_ws    = pat.get("indicator_weight_suggestions", {})
    per_stock_d  = pat.get("per_stock_analysis", {}).get("per_stock", {})
    n_used       = pat.get("n_used", 0)

    if not global_ws:
        print("[Export] No weight suggestions — run research first.")
        return False

    # ── Global weights (normalized) ───────────────────────────────────────
    raw_global = {k: v["suggested"] for k, v in global_ws.items()}
    total_g    = sum(raw_global.values()) or 1
    global_weights = {k: round(v / total_g, 4) for k, v in raw_global.items()}

    # ── Global directions (من التحقق إن كان متاحاً) ───────────────────────
    dir_val   = pat.get("direction_validation", {})
    global_directions = {}
    for col, dv in dir_val.items():
        eng_key = INDICATOR_ENGINE_KEY.get(col)
        if eng_key:
            global_directions[eng_key] = dv.get("expected", "lower")
    # أكمّل أي مفاتيح ناقصة من الاتجاه الافتراضي
    for col, eng_key in INDICATOR_ENGINE_KEY.items():
        if eng_key not in global_directions:
            global_directions[eng_key] = PATTERN_EXPECTED_DIR.get(col, "lower")

    # ── Per-stock weights ──────────────────────────────────────────────────
    per_stock_out = {}
    for sym, sym_data in per_stock_d.items():
        ws = sym_data.get("weight_suggestions", {})
        if not ws:
            continue
        raw_sym   = {k: v["suggested"] for k, v in ws.items()}
        total_sym = sum(raw_sym.values()) or 1
        norm_sym  = {k: round(v / total_sym, 4) for k, v in raw_sym.items()}
        per_stock_out[sym] = {
            "weights":   norm_sym,
            "directions": {k: global_directions.get(k, "lower") for k in norm_sym},
            "based_on":  sym_data["n"],
            "alpha":     round(min(0.85, sym_data["n"] / 200), 2),
        }

    out = {
        "weights":    global_weights,
        "directions": global_directions,
        "per_stock":  per_stock_out,
        "based_on":   n_used,
        "alpha":      round(min(0.85, n_used / 500), 2),
        "updated_at": str(datetime.date.today()),
        "source":     "research_engine — MFE+BQ Spearman",
        "note":       "Set FREEZE_WEIGHTS=False in pattern_engine.py to activate",
    }

    try:
        with open(out_path, "w") as f:
            json.dump(out, f, indent=2)
    except Exception as e:
        print(f"[Export] Write failed: {e}")
        return False

    n_ps = len(per_stock_out)
    print(f"[Export] Weights saved → {out_path}")
    print(f"  Global:    {global_weights}")
    print(f"  Per-stock: {list(per_stock_out.keys()) or 'none yet'}")
    print(f"  Based on:  {n_used} mature signals, {n_ps} stocks in per-stock mode")
    print(f"\n  To activate: set FREEZE_WEIGHTS = False in pattern_engine.py")
    return True


# ── Main API ───────────────────────────────────────────────────────────────────

def run_research(db_path: str = DB_PATH, verbose: bool = True) -> dict:
    """
    ينفّذ التحليل الكامل على الإشارات الناضجة.
    يُرجع نتائج JSON قابلة للاستخدام في research_report.py.

    المخرجات:
      meta          ← إحصائيات الـ dataset
      correlation   ← Spearman correlations مع MFE و BQ
      rf_mfe        ← نتائج RandomForest على MFE
      rf_bq         ← نتائج RandomForest على BQ
      gbm_mfe       ← نتائج GBM على MFE
      gbm_bq        ← نتائج GBM على BQ
      weight_suggestions ← توصيات تعديل الأوزان
      segment_analysis   ← تحليل قطاعي ونطاقي
      warnings      ← تحذيرات (حجم البيانات، جودة النموذج)
    """
    signals = get_mature_signals(db_path=db_path)
    df      = _to_df(signals)

    result = {
        "generated_at": date.today().isoformat(),
        "meta": {},
        "correlation": {},
        "rf_mfe": None, "rf_bq": None,
        "gbm_mfe": None, "gbm_bq": None,
        "weight_suggestions": {},
        "segment_analysis": {},
        "pattern_analysis": {},
        "best_conditions": {},
        "per_stock_ml": {},
        "warnings": [],
    }

    # ── Dataset Meta ───────────────────────────────────────────────────────
    n = len(df)
    result["meta"] = {
        "n_signals":   n,
        "date_range":  [
            str(df["signal_date"].min()) if n else None,
            str(df["signal_date"].max()) if n else None,
        ],
        "symbols":     sorted(df["symbol"].unique().tolist()) if n else [],
        "mfe_mean":    round(float(df[TARGET_MFE].mean()), 4) if n else None,
        "bq_mean":     round(float(df[TARGET_BQ].mean()),  1) if n else None,
        "mae_mean":    round(float(df["mae_20d"].abs().mean()), 4) if n else None,
    }

    if n < MIN_SAMPLES:
        result["warnings"].append(
            f"Only {n} mature signals — need at least {MIN_SAMPLES} for reliable ML. "
            f"Correlations only."
        )

    # ── Correlation (always available if ≥10 signals) ─────────────────────
    if n >= 10:
        result["correlation"] = _correlation_analysis(df)

    # ── ML Models (only if ≥ MIN_SAMPLES) ────────────────────────────────
    if not SKLEARN_OK:
        result["warnings"].append("scikit-learn not installed — ML models skipped.")
    elif n >= MIN_SAMPLES:
        for target_key, rf_key, gbm_key in [
            (TARGET_MFE, "rf_mfe", "gbm_mfe"),
            (TARGET_BQ,  "rf_bq",  "gbm_bq"),
        ]:
            X, y = _prepare(df, target_key)
            if X is None:
                result["warnings"].append(f"Insufficient data for {target_key} model.")
                continue

            X_tr, X_te, y_tr, y_te = _time_split(X, y)
            fn = list(X.columns)

            try:
                rf_res  = _feat_importance_rf(X_tr.values, y_tr.values,
                                               X_te.values, y_te.values, fn)
                result[rf_key] = rf_res
                if verbose:
                    print(f"  [ML] RF({target_key}): R²={rf_res['r2']}  "
                          f"train={rf_res['n_train']}  test={rf_res['n_test']}")
            except Exception as e:
                result["warnings"].append(f"RF({target_key}) failed: {e}")

            try:
                gbm_res = _feat_importance_gbm(X_tr.values, y_tr.values,
                                                X_te.values, y_te.values, fn)
                result[gbm_key] = gbm_res
                if verbose:
                    print(f"  [ML] {gbm_res['model']}({target_key}): "
                          f"R²={gbm_res['r2']}")
            except Exception as e:
                result["warnings"].append(f"GBM({target_key}) failed: {e}")

        # ── Weight Suggestions ─────────────────────────────────────────────
        if result["rf_mfe"] and result["rf_bq"]:
            mfe_imp = result["rf_mfe"]["importance"]
            bq_imp  = result["rf_bq"]["importance"]
            # ندمج مع GBM إن كان متاحاً
            if result["gbm_mfe"]:
                for k, v in result["gbm_mfe"]["importance"].items():
                    mfe_imp[k] = (mfe_imp.get(k, 0) + v) / 2
            if result["gbm_bq"]:
                for k, v in result["gbm_bq"]["importance"].items():
                    bq_imp[k] = (bq_imp.get(k, 0) + v) / 2
            result["weight_suggestions"] = _suggest_weights(mfe_imp, bq_imp)

    # ── Segment Analysis (always) ─────────────────────────────────────────
    if n >= 5:
        result["segment_analysis"] = _segment_analysis(df)

    # ── Pattern Engine Analysis ───────────────────────────────────────────
    if n >= 5:
        result["pattern_analysis"] = _pattern_analysis(df)

    # ── Best Conditions Profile (per-stock) ───────────────────────────────
    if n >= 10:
        result["best_conditions"] = _best_conditions_profile(df)
        n_profiled = len(result["best_conditions"])
        if verbose and n_profiled:
            print(f"  [BestCond] Profiled {n_profiled} stocks (top-25% MFE analysis)")

    # ── Per-Stock ML Models ───────────────────────────────────────────────
    if SKLEARN_OK and n >= MIN_PER_STOCK_ML:
        result["per_stock_ml"] = _per_stock_ml(df)
        n_ml = len(result["per_stock_ml"])
        if verbose and n_ml:
            print(f"  [StockML]  Trained models for {n_ml} stocks")
        if verbose and result["pattern_analysis"].get("n_used"):
            ws = result["pattern_analysis"].get("indicator_weight_suggestions", {})
            changed = [k for k, v in ws.items() if abs(v.get("change", 0)) > 0.005]
            if changed:
                print(f"  [Pattern] Weight changes suggested for: {', '.join(changed)}")

    # ── Low R² Warning ────────────────────────────────────────────────────
    for key in ["rf_mfe", "rf_bq"]:
        m = result.get(key)
        if m and m.get("r2", 1) < 0.05:
            result["warnings"].append(
                f"{key}: R²={m['r2']} — weak predictive signal. "
                f"More data needed before acting on weight suggestions."
            )

    if verbose:
        print(f"[Research] Done — {n} signals analysed. "
              f"Warnings: {len(result['warnings'])}")

    return result


def save_research(result: dict, path: str = "research_results.json"):
    """يحفظ نتائج التحليل في JSON."""
    with open(path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2, default=str)
    print(f"[Research] Results saved → {path}")


# ── CLI ────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser(description="EGX Research Engine")
    p.add_argument("--db",             default=DB_PATH,              help="DB path")
    p.add_argument("--out",            default="research_results.json", help="Output JSON path")
    p.add_argument("--quiet",          action="store_true")
    p.add_argument("--export-weights", action="store_true",
                   help="Export per-stock weights to learned_weights.json")
    args = p.parse_args()

    res = run_research(db_path=args.db, verbose=not args.quiet)
    save_research(res, args.out)

    if args.export_weights:
        export_per_stock_weights(res)

    n = res["meta"].get("n_signals", 0)
    if n < MIN_SAMPLES:
        print(f"\n⚠  Only {n} mature signals — {MIN_SAMPLES - n} more needed for ML models.")
    for w in res.get("warnings", []):
        print(f"  ⚠  {w}")
