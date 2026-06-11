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

MIN_SAMPLES     = 30     # حد أدنى للتدريب
TRAIN_SPLIT_PCT = 0.70   # تقسيم زمني — أول 70% للتدريب

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
    p.add_argument("--db",   default=DB_PATH,              help="DB path")
    p.add_argument("--out",  default="research_results.json", help="Output JSON path")
    p.add_argument("--quiet", action="store_true")
    args = p.parse_args()

    res = run_research(db_path=args.db, verbose=not args.quiet)
    save_research(res, args.out)

    n = res["meta"].get("n_signals", 0)
    if n < MIN_SAMPLES:
        print(f"\n⚠  Only {n} mature signals — {MIN_SAMPLES - n} more needed for ML models.")
    for w in res.get("warnings", []):
        print(f"  ⚠  {w}")
