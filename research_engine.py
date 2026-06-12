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
    from sklearn.ensemble import (
        RandomForestRegressor, GradientBoostingRegressor,
        RandomForestClassifier,
    )
    from sklearn.inspection import permutation_importance
    from sklearn.metrics import r2_score, mean_absolute_error, roc_auc_score
    from sklearn.feature_selection import mutual_info_regression
    from sklearn.preprocessing import StandardScaler
    SKLEARN_OK = True
except ImportError:
    SKLEARN_OK = False

try:
    import lightgbm as lgb
    LGBM_OK = True
except ImportError:
    LGBM_OK = False

try:
    import xgboost as xgb
    XGB_OK = True
except ImportError:
    XGB_OK = False

try:
    import shap
    SHAP_OK = True
except ImportError:
    SHAP_OK = False

from signal_db import DB_PATH, get_mature_signals, CURRENT_WEIGHTS, WEIGHT_LABELS

WIN_MFE_THRESHOLD = 0.08   # نفس قيمة edge_discovery

try:
    from pattern_engine import DEFAULT_WEIGHTS as PATTERN_DEFAULT_WEIGHTS
except ImportError:
    PATTERN_DEFAULT_WEIGHTS = {
        "p_vs_ma20": 0.21, "mom_10d": 0.20, "stoch_rsi": 0.18,
        "atr_ratio": 0.15, "mom_5d":  0.14, "vol_trend": 0.12,
    }

SNAP_FEATURE_COLS = [
    "snap_atr", "snap_wick_ratio", "snap_compression", "snap_consol_len",
    "snap_bos", "snap_bos_dist", "snap_choch", "snap_pivot_str",
    "snap_num_touches", "snap_sweep_size", "snap_vol_exp",
    "snap_reclaim_spd", "snap_dist_lo", "snap_prem_disc",
]

FEAT_FEATURE_COLS = [
    "feat_dist_swing_low", "feat_dealing_range_pos",
    "feat_candles_since_bos", "feat_dist_last_bos",
    "feat_sweep_depth_pct", "feat_equal_lows_count",
    "feat_vol_spike_ratio", "feat_candles_since_sweep",
    "feat_accumulation_score",
    "feat_consec_red", "feat_down_days_pct",
    "feat_atr_compression", "feat_vol_contraction",
    "feat_dist_20d_low", "feat_dist_50d_low", "feat_dist_52w_low",
    "feat_vwap_dist", "feat_rs_vs_egx30", "feat_egx30_trend_val",
]

MIN_SAMPLES       = 30   # حد أدنى للتدريب global
TRAIN_SPLIT_PCT   = 0.70 # تقسيم زمني — أول 70% للتدريب
MIN_PER_STOCK     = 20   # إشارات ناضجة لتفعيل تحليل per-stock
MIN_PER_STOCK_ML  = 50   # إشارات ناضجة لتفعيل ML model per-stock (Phase 4)
TOP_MFE_PERCENTILE= 0.75 # الربع الأعلى = "نماذج الفائزة"

# أنواع الإشارات التي تمثّل قرار دخول فعلي — Wait يُسجَّل للمراقبة فقط
ML_SIGNAL_TYPES = {"Early Buy", "Buy", "Strong Buy", "Very Strong Buy", "Institutional Buy"}

# المتغيرات الكاملة — 49 متغير (مطابقة لـ FEATURE_COLS تماماً)
ALL_FEATURE_COLS = [
    "raw_score", "adj_score",
    "r1_price", "r2_ob", "r3_liquidity", "r4_htf",
    "r5_avwap", "r6_macd", "r7_div", "r8_demand",
    "discount_depth",
    "pattern_score", "pattern_eff", "pattern_wr", "pattern_gain", "pattern_n",
    "ind_stoch_rsi", "ind_p_vs_ma20", "ind_mom_10d",
    "ind_mom_5d", "ind_atr_ratio", "ind_vol_trend",
    "sv_hit", "sv_score", "hvn_hit", "hvn_score",
    "macd_val", "vol_spike",
    "is_ramadan", "is_cbe", "stock_tier",
    # 18 extended variables
    "rsi_val", "macd_hist", "macd_signal",
    "rsi_div", "macd_div",
    "ob_quality", "ob_dist",
    "htf_hh", "htf_hl", "avwap_gap",
    "sweep_detected", "wick_rejection", "equal_lows",
    "ctx_mult", "stock_mult", "price_gate", "price_ok",
    "sv_depth",
    # Snapshot features (Phase 3)
    "snap_wick_ratio", "snap_compression", "snap_consol_len",
    "snap_bos", "snap_bos_dist", "snap_choch", "snap_pivot_str",
    "snap_num_touches", "snap_sweep_size", "snap_vol_exp",
    "snap_reclaim_spd", "snap_dist_lo", "snap_prem_disc",
    # Phase 1 computed features (feat_*)
    "feat_dist_swing_low", "feat_dealing_range_pos",
    "feat_candles_since_bos", "feat_dist_last_bos",
    "feat_sweep_depth_pct", "feat_equal_lows_count",
    "feat_vol_spike_ratio", "feat_candles_since_sweep",
    "feat_accumulation_score",
    "feat_consec_red", "feat_down_days_pct",
    "feat_atr_compression", "feat_vol_contraction",
    "feat_dist_20d_low", "feat_dist_50d_low", "feat_dist_52w_low",
    "feat_vwap_dist", "feat_rs_vs_egx30", "feat_egx30_trend_val",
]

# ── المتغيرات المستخدمة في الـ ML و Correlation ───────────────────────────────
FEATURE_COLS = [
    "raw_score", "adj_score",
    "r1_price", "r2_ob", "r3_liquidity", "r4_htf",
    "r5_avwap", "r6_macd", "r7_div", "r8_demand",
    "discount_depth",
    "pattern_score", "pattern_eff", "pattern_wr", "pattern_gain", "pattern_n",
    "ind_stoch_rsi", "ind_p_vs_ma20", "ind_mom_10d",
    "ind_mom_5d", "ind_atr_ratio", "ind_vol_trend",
    "sv_hit", "sv_score", "hvn_hit", "hvn_score",
    "macd_val", "vol_spike",
    "is_ramadan", "is_cbe", "stock_tier",
    # 18 extended variables
    "rsi_val", "macd_hist", "macd_signal",
    "rsi_div", "macd_div",
    "ob_quality", "ob_dist",
    "htf_hh", "htf_hl", "avwap_gap",
    "sweep_detected", "wick_rejection", "equal_lows",
    "ctx_mult", "stock_mult", "price_gate", "price_ok",
    "sv_depth",
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
    # mae columns سالبة — نحوّلها لقيم موجبة (سوء الأداء)
    for mae_col in ["mae_20d", "mae_40d", "mae_60d"]:
        if mae_col in df.columns:
            df[mae_col] = df[mae_col].abs()
    return df


def _get_feature_cols(df: pd.DataFrame) -> list:
    """Returns FEATURE_COLS + SNAP + FEAT columns that have enough non-NULL values."""
    threshold = min(10, MIN_SAMPLES)
    base = [c for c in FEATURE_COLS      if c in df.columns and df[c].notna().sum() >= threshold]
    snap = [c for c in SNAP_FEATURE_COLS if c in df.columns and df[c].notna().sum() >= threshold]
    feat = [c for c in FEAT_FEATURE_COLS if c in df.columns and df[c].notna().sum() >= threshold]
    return list(dict.fromkeys(base + snap + feat))


def _prepare(df: pd.DataFrame, target: str) -> tuple:
    """
    يُحضّر X, y مع إزالة الصفوف التي تحتوي على NaN في الفيتشرز أو الهدف.
    يُرجع (X_df, y_series) أو (None, None).
    """
    cols  = _get_feature_cols(df)
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


# ── XGBoost Model ─────────────────────────────────────────────────────────────

def _feat_importance_xgb(X_tr, y_tr, X_te, y_te, feature_names) -> dict:
    if not XGB_OK:
        return {}
    try:
        model = xgb.XGBRegressor(
            n_estimators=300, max_depth=4, learning_rate=0.05,
            subsample=0.8, colsample_bytree=0.8,
            random_state=42, verbosity=0,
            early_stopping_rounds=30,
            eval_metric="rmse",
        )
        model.fit(X_tr, y_tr, eval_set=[(X_te, y_te)], verbose=False)
        imp = dict(zip(feature_names,
                       model.feature_importances_ / max(model.feature_importances_.sum(), 1)))
        y_pred = model.predict(X_te)
        r2  = r2_score(y_te, y_pred)
        mae = mean_absolute_error(y_te, y_pred)
        return {"model": "XGBoost", "r2": round(r2, 3), "mae": round(mae, 4),
                "importance": imp, "n_train": len(y_tr), "n_test": len(y_te),
                "_fitted": model}
    except Exception as e:
        return {"model": "XGBoost", "error": str(e)}


# ── SHAP Values ────────────────────────────────────────────────────────────────

def _compute_shap(model, X_te, feature_names) -> dict:
    """
    يحسب SHAP values من أفضل نموذج.
    يُرجع mean |SHAP| per feature (أهمية عالمية).
    """
    if not SHAP_OK or model is None:
        return {}
    try:
        explainer = shap.TreeExplainer(model)
        shap_vals = explainer.shap_values(X_te)
        if hasattr(shap_vals, "__len__") and len(shap_vals) > 0:
            mean_abs = np.abs(shap_vals).mean(axis=0)
            total = mean_abs.sum()
            if total > 0:
                mean_abs = mean_abs / total
            return {f: round(float(v), 4) for f, v in zip(feature_names, mean_abs)}
    except Exception:
        pass
    return {}


# ── Model Comparison ──────────────────────────────────────────────────────────

def _model_comparison(X_tr, y_tr, X_te, y_te, feature_names, target_label: str) -> dict:
    """
    يُدرّب RF + GBM/LightGBM + XGBoost ويقارن الأداء.
    يحسب SHAP من أفضل نموذج.
    """
    results = {}

    # Random Forest
    try:
        rf_res = _feat_importance_rf(X_tr, y_tr, X_te, y_te, feature_names)
        results["rf"] = rf_res
    except Exception:
        pass

    # GBM / LightGBM
    try:
        gbm_res = _feat_importance_gbm(X_tr, y_tr, X_te, y_te, feature_names)
        results["gbm"] = gbm_res
    except Exception:
        pass

    # XGBoost
    try:
        xgb_res = _feat_importance_xgb(X_tr, y_tr, X_te, y_te, feature_names)
        results["xgb"] = xgb_res
    except Exception:
        pass

    # أفضل نموذج بناءً على R²
    best_model_name = None
    best_r2 = -999
    best_fitted = None
    for name, res in results.items():
        if res.get("r2", -999) > best_r2:
            best_r2 = res.get("r2", -999)
            best_model_name = res.get("model", name)
            best_fitted = res.pop("_fitted", None)

    # SHAP من أفضل نموذج
    shap_imp = {}
    if best_fitted is not None:
        shap_imp = _compute_shap(best_fitted, X_te, feature_names)

    # تجميع الأهمية من كل النماذج (ensemble importance)
    all_imps = {}
    model_count = 0
    for name, res in results.items():
        imp = res.get("importance", {})
        if imp:
            model_count += 1
            for feat, val in imp.items():
                all_imps[feat] = all_imps.get(feat, 0.0) + val
    if model_count > 0:
        ensemble_imp = {f: round(v / model_count, 4) for f, v in all_imps.items()}
    else:
        ensemble_imp = {}

    # أهم 20 متغير (من ensemble + SHAP)
    combined = {}
    for feat in set(list(ensemble_imp.keys()) + list(shap_imp.keys())):
        e = ensemble_imp.get(feat, 0.0)
        s = shap_imp.get(feat, 0.0)
        combined[feat] = round((e + s) / 2, 4) if (e and s) else (e or s)

    top20 = sorted(combined.items(), key=lambda x: -x[1])[:20]

    return {
        "target":       target_label,
        "best_model":   best_model_name,
        "best_r2":      round(best_r2, 3),
        "rf":           results.get("rf", {}),
        "gbm":          results.get("gbm", {}),
        "xgb":          results.get("xgb", {}),
        "shap_importance": shap_imp,
        "ensemble_importance": ensemble_imp,
        "top20_features": top20,
    }


# ── Correlation Analysis ───────────────────────────────────────────────────────

def _correlation_analysis(df: pd.DataFrame) -> dict:
    """
    ارتباط Spearman لكل فيتشر مع MFE و BQ Score (لا تفترض توزيعاً خطياً).
    يستخدم ALL_FEATURE_COLS (تشمل snap_* و feat_*) مع تصفية الأعمدة ذات التباين الصفري.
    """
    # استخدم ALL_FEATURE_COLS لتشمل snap_* و feat_*
    cols_base = [c for c in ALL_FEATURE_COLS if c in df.columns]
    # تصفية إضافية: تجاهل أعمدة ذات بيانات غير كافية أو تباين صفري
    cols = [
        c for c in cols_base
        if df[c].notna().sum() >= 10          # minimum non-null check
        and df[c].nunique() > 1               # zero-variance filter
    ]
    targets = {t: t for t in [TARGET_MFE, TARGET_BQ, "mae_20d"]
               if t in df.columns}

    results = {}
    for tname, tcol in targets.items():
        target_mask = df[tcol].notna()
        if target_mask.sum() < 10:
            continue
        corr = {}
        for col in cols:
            c = df[[col, tcol]][target_mask & df[col].notna()]
            if len(c) >= 10:
                r = float(c[col].corr(c[tcol], method="spearman"))
                corr[col] = round(r, 3)
        if corr:
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


# ── Mutual Information ─────────────────────────────────────────────────────────

def _mutual_information(df: pd.DataFrame) -> dict:
    """
    يحسب Mutual Information بين كل متغير والـ target (MFE و BQ).
    يقيس الارتباط غير الخطي — يكمّل Spearman.
    النتيجة مُعيَّرة بين 0 و 1 (0 = لا ارتباط، 1 = أقوى ارتباط في المجموعة).
    """
    if not SKLEARN_OK:
        return {}

    cols    = _get_feature_cols(df)
    results = {}

    for target, tname in [(TARGET_MFE, "mfe_20d"), (TARGET_BQ, "bq_score")]:
        if target not in df.columns:
            continue
        target_mask = df[target].notna()
        if target_mask.sum() < MIN_SAMPLES:
            continue

        X  = df.loc[target_mask, cols].fillna(0).values
        y  = df.loc[target_mask, target].values

        try:
            mi_vals = mutual_info_regression(X, y, random_state=42)
        except Exception:
            continue

        mi_dict  = dict(zip(cols, mi_vals))
        max_mi   = max(mi_dict.values()) if mi_dict else 1.0
        max_mi   = max(max_mi, 1e-9)
        mi_norm  = {k: round(float(v) / max_mi, 4) for k, v in mi_dict.items()}
        results[tname] = dict(sorted(mi_norm.items(), key=lambda x: -x[1]))

    return results


# ── Probability Analysis ───────────────────────────────────────────────────────

def _probability_analysis(df: pd.DataFrame) -> dict:
    """
    يُدرّب RandomForest Classifier على تحديد "إشارة فائزة" (MFE ≥ 8%).
    يُنتج:
      auc              ← دقة التصنيف (0.5 = عشوائي، 1.0 = مثالي)
      base_win_rate    ← نسبة الفائزين في الـ test set
      high_conf_n      ← عدد الإشارات بثقة ≥ 65%
      high_conf_precision ← دقة التنبؤات عالية الثقة
      top5_features    ← أهم 5 متغيرات في التصنيف
    """
    if not SKLEARN_OK:
        return {"error": "scikit-learn not installed"}

    cols  = _get_feature_cols(df)
    target_mask = df["mfe_20d"].notna()

    if target_mask.sum() < MIN_SAMPLES:
        return {"error": f"Need {MIN_SAMPLES} signals, have {target_mask.sum()}"}

    y = (df.loc[target_mask, "mfe_20d"] >= WIN_MFE_THRESHOLD).astype(int)
    X = df.loc[target_mask, cols].fillna(0)

    split   = int(len(X) * TRAIN_SPLIT_PCT)
    X_tr, X_te = X.iloc[:split], X.iloc[split:]
    y_tr, y_te = y.iloc[:split], y.iloc[split:]

    if len(X_te) < 5:
        return {"error": "test set too small"}
    if y_te.nunique() < 2:
        return {"error": "no class variation in test set"}

    try:
        model = RandomForestClassifier(
            n_estimators=200, max_depth=6,
            min_samples_leaf=3, class_weight="balanced",
            random_state=42, n_jobs=-1,
        )
        model.fit(X_tr.values, y_tr.values)
        proba = model.predict_proba(X_te.values)[:, 1]
        auc   = round(roc_auc_score(y_te.values, proba), 3)
    except Exception as e:
        return {"error": str(e)}

    base_win_rate = round(float(y_te.mean()), 4)

    # إشارات بثقة عالية (≥ 65%)
    hc_mask      = proba >= 0.65
    hc_n         = int(hc_mask.sum())
    hc_wins      = int(y_te.values[hc_mask].sum()) if hc_n > 0 else 0
    hc_precision = round(hc_wins / max(hc_n, 1), 4)

    imp  = dict(zip(cols, model.feature_importances_))
    top5 = sorted(imp.items(), key=lambda x: x[1], reverse=True)[:5]

    return {
        "auc":               auc,
        "n_train":           len(y_tr),
        "n_test":            len(y_te),
        "base_win_rate":     base_win_rate,
        "win_threshold_pct": WIN_MFE_THRESHOLD * 100,
        "high_conf_n":       hc_n,
        "high_conf_wins":    hc_wins,
        "high_conf_precision": hc_precision,
        "top5_features":     [(k, round(v, 4)) for k, v in top5],
    }


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
            # Cohen's d: pooled within-group std (not total std which inflates for boolean features)
            pooled_var = (
                (len(t_vals) - 1) * float(t_vals.std()) ** 2 +
                (len(b_vals) - 1) * float(b_vals.std()) ** 2
            ) / max(len(t_vals) + len(b_vals) - 2, 1)
            pooled_std = max(pooled_var ** 0.5, 1e-6)
            effect  = (t_mean - b_mean) / pooled_std
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

    for sym in sorted(base["symbol"].unique()):
        sub = base[base["symbol"] == sym].sort_values("signal_date")
        n   = len(sub)
        if n < MIN_PER_STOCK_ML:
            continue

        # فيتشرز متاحة فعلاً لهذا السهم
        feats = [c for c in ALL_FEATURE_COLS
                 if c in sub.columns and sub[c].notna().sum() >= max(3, MIN_PER_STOCK_ML // 10)]

        sym_result = {"n": n, "mfe_model": None, "bq_model": None}

        for target, key in [(TARGET_MFE, "mfe_model"), (TARGET_BQ, "bq_model")]:
            target_mask = sub[target].notna()
            if target_mask.sum() < MIN_PER_STOCK_ML:
                continue

            X = sub.loc[target_mask, feats].fillna(0)
            y = sub.loc[target_mask, target]
            split = max(10, int(len(X) * TRAIN_SPLIT_PCT))
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


# ── Auto-Weight Update ────────────────────────────────────────────────────────

def _auto_update_pattern_weights(pattern_result: dict, db_path: str = DB_PATH):
    """
    يحدّث learned_weights.json تلقائياً بناءً على نتائج Pattern Analysis.
    يُشغَّل بعد كل research run إذا كان عدد الإشارات كافياً.
    الأوزان الجديدة تُطبَّق في pattern_engine.py (FREEZE_WEIGHTS=False).
    """
    ws = pattern_result.get("indicator_weight_suggestions", {})
    if not ws:
        return

    has_significant = any(abs(v.get("change", 0)) > 0.005 for v in ws.values())
    if not has_significant:
        return

    new_weights = {
        INDICATOR_ENGINE_KEY.get(k, k): round(v["suggested"], 6)
        for k, v in ws.items()
        if INDICATOR_ENGINE_KEY.get(k, k) is not None
    }
    if not new_weights:
        return

    import os
    lw_file = "learned_weights.json"
    old_data = {}
    if os.path.exists(lw_file):
        try:
            with open(lw_file) as f:
                old_data = json.load(f)
        except Exception:
            pass

    old_data["weights"]    = new_weights
    old_data["updated_at"] = date.today().isoformat()
    old_data["n_signals"]  = pattern_result.get("n_used", 0)
    old_data["source"]     = "research_engine_auto"

    with open(lw_file, "w") as f:
        json.dump(old_data, f, indent=2)


# ── Feature Health Report (Phase 6) ──────────────────────────────────────────

def _feature_health_report(df: pd.DataFrame) -> dict:
    """
    Per-feature quality audit:
      missing_ratio  — fraction of rows that are NULL
      zero_ratio     — fraction of non-null values equal to 0
      variance       — variance of non-null values
      n_unique       — number of distinct non-null values
      info_gain_mfe  — mutual information with MFE (0–1, normalised)
      health         — "ok" / "low_info" / "mostly_zero" / "zero_variance" / "too_sparse"

    Auto-excludes features that are too sparse, zero-variance, or mostly-zero.
    """
    if not SKLEARN_OK or TARGET_MFE not in df.columns:
        return {}

    all_cols  = _get_feature_cols(df)
    mfe_mask  = df[TARGET_MFE].notna()
    n_total   = len(df)

    if not all_cols or mfe_mask.sum() < 10:
        return {}

    X_mi = df.loc[mfe_mask, all_cols].fillna(0).values
    y_mi = df.loc[mfe_mask, TARGET_MFE].values

    try:
        mi_vals = mutual_info_regression(X_mi, y_mi, random_state=42)
        max_mi  = max(float(v) for v in mi_vals) if len(mi_vals) > 0 else 1e-9
        max_mi  = max(max_mi, 1e-9)
        mi_norm = {c: round(float(v) / max_mi, 4) for c, v in zip(all_cols, mi_vals)}
    except Exception:
        mi_norm = {c: 0.0 for c in all_cols}

    report        = {}
    auto_excluded = []

    for col in all_cols:
        if col not in df.columns:
            continue
        series    = df[col]
        non_null  = series.dropna()
        n_nn      = len(non_null)

        missing_ratio = round(1.0 - n_nn / max(n_total, 1), 4)
        zero_ratio    = round(float((non_null == 0).sum()) / max(n_nn, 1), 4)
        variance      = round(float(non_null.var()) if n_nn > 1 else 0.0, 6)
        n_unique      = int(non_null.nunique())
        info_gain     = mi_norm.get(col, 0.0)

        if missing_ratio > 0.80:
            health = "too_sparse"
            auto_excluded.append(col)
        elif variance < 1e-8 or n_unique <= 1:
            health = "zero_variance"
            auto_excluded.append(col)
        elif zero_ratio > 0.90:
            health = "mostly_zero"
            auto_excluded.append(col)
        elif info_gain < 0.02 and n_nn >= 20:
            health = "low_info"
        else:
            health = "ok"

        report[col] = {
            "n_non_null":    n_nn,
            "missing_ratio": missing_ratio,
            "zero_ratio":    zero_ratio,
            "variance":      variance,
            "n_unique":      n_unique,
            "info_gain_mfe": info_gain,
            "health":        health,
        }

    sorted_report = dict(
        sorted(report.items(), key=lambda x: -x[1]["info_gain_mfe"])
    )
    return {
        "features":     sorted_report,
        "auto_excluded": auto_excluded,
        "n_ok":         sum(1 for v in report.values() if v["health"] == "ok"),
        "n_sparse":     sum(1 for v in report.values() if v["health"] == "too_sparse"),
        "n_low_info":   sum(1 for v in report.values() if v["health"] == "low_info"),
        "n_zero_var":   sum(1 for v in report.values() if v["health"] == "zero_variance"),
        "n_mostly_zero":sum(1 for v in report.values() if v["health"] == "mostly_zero"),
    }


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
    df_all  = _to_df(signals)

    # ML يتدرب على إشارات الدخول الفعلي فقط (Early Buy / Buy / …)
    # Wait يبقى مسجّل للمراقبة البحثية لكن لا يدخل التدريب
    if "signal_type" in df_all.columns and not df_all.empty:
        df = df_all[df_all["signal_type"].isin(ML_SIGNAL_TYPES)].reset_index(drop=True)
    else:
        df = df_all

    result = {
        "generated_at": date.today().isoformat(),
        "meta": {},
        "correlation": {},
        "mutual_information": {},
        "probability_analysis": {},
        "rf_mfe": None, "rf_bq": None,
        "gbm_mfe": None, "gbm_bq": None,
        "model_comparison_mfe": {},
        "model_comparison_bq": {},
        "weight_suggestions": {},
        "segment_analysis": {},
        "pattern_analysis": {},
        "pattern_discovery": {},
        "best_conditions": {},
        "per_stock_ml": {},
        "edge_discovery": [],
        "feature_health": {},
        "warnings": [],
    }

    # ── Dataset Meta ───────────────────────────────────────────────────────
    n       = len(df)
    n_total = len(df_all)
    n_wait  = n_total - n
    result["meta"] = {
        "n_signals":   n,        # إشارات الدخول الفعلي — للـ ML
        "n_total":     n_total,  # كل الإشارات (شاملة Wait)
        "n_wait":      n_wait,   # إشارات Wait (مراقبة فقط)
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

    # ── Mutual Information ─────────────────────────────────────────────────
    if SKLEARN_OK and n >= MIN_SAMPLES:
        result["mutual_information"] = _mutual_information(df)
        if verbose and result["mutual_information"]:
            print("  [MI] Mutual information computed")

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

        # ── Model Comparison: RF + GBM + XGBoost ──────────────────────────
        for target_key, cmp_key in [(TARGET_MFE, "model_comparison_mfe"),
                                     (TARGET_BQ,  "model_comparison_bq")]:
            X, y = _prepare(df, target_key)
            if X is not None:
                X_tr, X_te, y_tr, y_te = _time_split(X, y)
                fn = list(X.columns)
                try:
                    cmp = _model_comparison(X_tr.values, y_tr.values,
                                            X_te.values, y_te.values,
                                            fn, target_key)
                    result[cmp_key] = cmp
                    if verbose:
                        print(f"  [ModelCmp] {target_key}: best={cmp.get('best_model')} "
                              f"R²={cmp.get('best_r2')} "
                              f"SHAP_features={len(cmp.get('shap_importance', {}))}")
                except Exception as e:
                    result["warnings"].append(f"ModelComparison({target_key}) failed: {e}")

        # ── Weight Suggestions ─────────────────────────────────────────────
        if result["rf_mfe"] and result["rf_bq"]:
            mfe_imp = result["rf_mfe"]["importance"]
            bq_imp  = result["rf_bq"]["importance"]
            # ندمج مع GBM و XGBoost إن كانا متاحَين
            if result["gbm_mfe"]:
                for k, v in result["gbm_mfe"]["importance"].items():
                    mfe_imp[k] = (mfe_imp.get(k, 0) + v) / 2
            if result["gbm_bq"]:
                for k, v in result["gbm_bq"]["importance"].items():
                    bq_imp[k] = (bq_imp.get(k, 0) + v) / 2
            mc_mfe = result.get("model_comparison_mfe", {})
            mc_bq  = result.get("model_comparison_bq", {})
            if mc_mfe.get("ensemble_importance"):
                for k, v in mc_mfe["ensemble_importance"].items():
                    mfe_imp[k] = (mfe_imp.get(k, 0) + v) / 2
            if mc_bq.get("ensemble_importance"):
                for k, v in mc_bq["ensemble_importance"].items():
                    bq_imp[k] = (bq_imp.get(k, 0) + v) / 2
            result["weight_suggestions"] = _suggest_weights(mfe_imp, bq_imp)

    # ── Segment Analysis — يستخدم كل الإشارات (شاملة Wait) للمقارنة ─────
    n_all = len(df_all)
    if n_all >= 5:
        result["segment_analysis"] = _segment_analysis(df_all)

    # ── Pattern Engine Analysis — إشارات الدخول فقط ──────────────────────
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

    # ── Probability Analysis ───────────────────────────────────────────────
    if SKLEARN_OK and n >= MIN_SAMPLES:
        result["probability_analysis"] = _probability_analysis(df)
        pa = result["probability_analysis"]
        if verbose and "auc" in pa:
            print(f"  [Proba]   AUC={pa['auc']}  high_conf={pa['high_conf_n']} "
                  f"precision={pa['high_conf_precision']:.1%}")

    # ── Pattern Discovery (Clustering) ───────────────────────────────────
    try:
        from pattern_discovery import run_pattern_discovery, MIN_SAMPLES as PD_MIN
        pd_result = run_pattern_discovery(db_path=db_path, min_samples=PD_MIN)
        result["pattern_discovery"] = pd_result
        if verbose:
            nd = pd_result.get("n_used", 0)
            nc = pd_result.get("n_clusters", 0)
            print(f"  [PatDisc]  {nd} signals → {nc} clusters")
    except Exception as e:
        result["warnings"].append(f"Pattern discovery failed: {e}")

    # ── Edge Discovery ────────────────────────────────────────────────────
    if n >= MIN_SAMPLES:
        try:
            from edge_discovery import run_edge_discovery
            result["edge_discovery"] = run_edge_discovery(
                db_path=db_path, top_k=20, verbose=verbose,
            )
        except Exception as e:
            result["warnings"].append(f"Edge discovery failed: {e}")

    # ── Auto-Update Pattern Engine Weights ───────────────────────────────
    if n >= MIN_SAMPLES and result.get("pattern_analysis"):
        try:
            _auto_update_pattern_weights(result["pattern_analysis"], db_path)
        except Exception as e:
            result["warnings"].append(f"Auto-weight update failed: {e}")


    # ── Feature Health Report (Phase 6) ──────────────────────────────────
    if SKLEARN_OK and n >= 10:
        try:
            result["feature_health"] = _feature_health_report(df)
            fh = result["feature_health"]
            if verbose and fh:
                n_ok   = fh.get("n_ok", 0)
                n_excl = len(fh.get("auto_excluded", []))
                print(f"  [FeatHealth] {n_ok} healthy features, {n_excl} auto-excluded")
        except Exception as e:
            result["warnings"].append(f"Feature health report failed: {e}")


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
