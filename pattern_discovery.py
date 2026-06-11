"""
Pattern Discovery Engine — EGX Research Platform
=================================================
يستخرج خصائص القاع رقمياً ويكتشف الأنماط المشتركة تلقائياً.
لا يحفظ أسماء نماذج — يجد clusters من البيانات.

الأنماط تُكتشف بـ K-Means على مجموعة من المتغيرات الرقمية
وتُقيَّم بناءً على MFE و BQ Score الفعليين.
"""
import sqlite3
import json
from typing import Optional

try:
    import numpy as np
    import pandas as pd
    NP_OK = True
except ImportError:
    NP_OK = False

try:
    from sklearn.preprocessing import StandardScaler
    from sklearn.cluster import KMeans
    from sklearn.decomposition import PCA
    SKLEARN_OK = True
except ImportError:
    SKLEARN_OK = False


# المتغيرات المستخدمة في التجميع — تشمل snap_* الجديدة + المتغيرات الموجودة
CLUSTER_FEATURES = [
    # Snapshot features (numerical bottom characteristics)
    "snap_wick_ratio", "snap_compression", "snap_consol_len",
    "snap_bos", "snap_choch", "snap_pivot_str",
    "snap_num_touches", "snap_sweep_size", "snap_vol_exp",
    "snap_dist_lo", "snap_prem_disc",
    # Existing SMC features
    "ind_stoch_rsi", "rsi_val", "vol_spike",
    "sv_hit", "hvn_hit", "ob_quality",
    "discount_depth", "r3_liquidity", "r8_demand",
    "avwap_gap", "ctx_mult", "sweep_detected",
    "wick_rejection", "equal_lows",
]

N_CLUSTERS     = 4
MIN_SAMPLES    = 15
MIN_SNAP_COLS  = 3    # حد أدنى لأعمدة snap_* للتفعيل الكامل


def _load_signals_with_bq(db_path: str = "egx_research.db") -> "pd.DataFrame":
    conn = sqlite3.connect(db_path)
    q = """
    SELECT s.*, bq.bq_score, bq.mfe_20d, bq.mae_20d, bq.r20d, bq.classification,
           bq.mfe_40d, bq.mfe_60d
    FROM signals s
    JOIN bottom_quality bq ON s.id = bq.signal_id
    WHERE bq.mfe_20d IS NOT NULL
    ORDER BY s.signal_date ASC
    """
    try:
        df = pd.read_sql_query(q, conn)
    finally:
        conn.close()
    return df


def _cluster_label(mfe_mean: Optional[float]) -> str:
    if mfe_mean is None:
        return "Unknown"
    if mfe_mean >= 0.15:
        return "Excellent Bottom"
    if mfe_mean >= 0.08:
        return "Good Bottom"
    if mfe_mean >= 0.03:
        return "Neutral Bottom"
    return "Weak Bottom"


def _build_cluster_profile(df: "pd.DataFrame", labels: "np.ndarray",
                            used_feats: list) -> list:
    profiles = []
    global_means = {f: float(df[f].mean()) for f in used_feats if f in df.columns}

    for c in sorted(set(labels)):
        mask = labels == c
        grp = df[mask]
        n   = int(mask.sum())

        mfe_m = float(grp["mfe_20d"].mean()) if "mfe_20d" in grp.columns else None
        mae_m = float(grp["mae_20d"].mean()) if "mae_20d" in grp.columns else None
        bq_m  = float(grp["bq_score"].mean()) if "bq_score" in grp.columns else None

        # Feature signatures: cluster mean + diff from global
        signatures = {}
        for feat in used_feats:
            if feat not in grp.columns:
                continue
            c_mean = float(grp[feat].mean())
            g_mean = global_means.get(feat, 0.0)
            signatures[feat] = {
                "cluster_mean": round(c_mean, 4),
                "diff_from_global": round(c_mean - g_mean, 4),
            }

        # Top distinguishing features (largest abs diff)
        top_feats = sorted(
            [(f, abs(v["diff_from_global"])) for f, v in signatures.items()],
            key=lambda x: -x[1]
        )[:5]

        # Classification breakdown
        cls_dist = {}
        if "classification" in grp.columns:
            cls_dist = grp["classification"].value_counts().to_dict()

        # Symbol distribution
        sym_dist = {}
        if "symbol" in grp.columns:
            sym_dist = grp["symbol"].value_counts().head(5).to_dict()

        profiles.append({
            "cluster_id":     int(c),
            "cluster_label":  _cluster_label(mfe_m),
            "n":              n,
            "mfe_mean":       round(mfe_m, 4) if mfe_m is not None else None,
            "mae_mean":       round(mae_m, 4) if mae_m is not None else None,
            "bq_mean":        round(bq_m,  2) if bq_m  is not None else None,
            "signatures":     signatures,
            "top_features":   [f for f, _ in top_feats],
            "cls_breakdown":  cls_dist,
            "symbol_dist":    sym_dist,
        })

    # Sort best → worst by MFE
    profiles.sort(key=lambda x: (x.get("mfe_mean") or -999), reverse=True)
    return profiles


def _feature_importance_between_clusters(
    X: "np.ndarray", labels: "np.ndarray",
    used_feats: list, n_clusters: int
) -> list:
    """
    يقيس أهمية كل متغير في التمييز بين الـ clusters.
    المقياس: between-cluster variance / total variance.
    """
    importances = []
    for i, feat in enumerate(used_feats):
        col = X[:, i]
        total_var = float(np.var(col)) + 1e-9
        cluster_means = np.array([
            float(np.mean(col[labels == c])) if (labels == c).any() else 0.0
            for c in range(n_clusters)
        ])
        between_var = float(np.var(cluster_means))
        importances.append((feat, round(between_var / total_var, 4)))

    importances.sort(key=lambda x: -x[1])
    return importances


def _mfe_distribution(df: "pd.DataFrame") -> dict:
    """MFE distribution: حساب البنكات لرسم توزيع MFE."""
    if "mfe_20d" not in df.columns or df["mfe_20d"].isna().all():
        return {}
    vals = df["mfe_20d"].dropna().values * 100  # تحويل لـ %
    buckets = {
        "<0%":     int((vals < 0).sum()),
        "0–3%":    int(((vals >= 0) & (vals < 3)).sum()),
        "3–8%":    int(((vals >= 3) & (vals < 8)).sum()),
        "8–15%":   int(((vals >= 8) & (vals < 15)).sum()),
        "15–25%":  int(((vals >= 15) & (vals < 25)).sum()),
        ">25%":    int((vals >= 25).sum()),
    }
    return {
        "buckets": buckets,
        "mean":   round(float(np.mean(vals)), 2),
        "median": round(float(np.median(vals)), 2),
        "p75":    round(float(np.percentile(vals, 75)), 2),
        "p90":    round(float(np.percentile(vals, 90)), 2),
    }


def _mae_distribution(df: "pd.DataFrame") -> dict:
    """MAE distribution: حساب البنكات لرسم توزيع MAE."""
    if "mae_20d" not in df.columns or df["mae_20d"].isna().all():
        return {}
    vals = df["mae_20d"].dropna().values * 100  # تحويل لـ %
    vals = np.abs(vals)  # MAE سالب دائماً → نأخذ القيمة المطلقة
    buckets = {
        "0–2%":   int((vals < 2).sum()),
        "2–5%":   int(((vals >= 2) & (vals < 5)).sum()),
        "5–10%":  int(((vals >= 5) & (vals < 10)).sum()),
        "10–15%": int(((vals >= 10) & (vals < 15)).sum()),
        ">15%":   int((vals >= 15).sum()),
    }
    return {
        "buckets": buckets,
        "mean":   round(float(np.mean(vals)), 2),
        "median": round(float(np.median(vals)), 2),
        "p75":    round(float(np.percentile(vals, 75)), 2),
        "worst":  round(float(np.max(vals)), 2),
    }


# ── Public API ──────────────────────────────────────────────────────────────────

def run_pattern_discovery(
    db_path: str = "egx_research.db",
    min_samples: int = MIN_SAMPLES,
    n_clusters: int = N_CLUSTERS,
) -> dict:
    """
    Main entry point.
    يحمّل الإشارات الناضجة، يُجمّعها بـ K-Means،
    ويُرجع cluster profiles + feature importance.
    """
    if not NP_OK:
        return {"error": "numpy/pandas not installed", "n_used": 0}
    if not SKLEARN_OK:
        return {"error": "scikit-learn not installed — run: pip install scikit-learn",
                "n_used": 0}

    try:
        df = _load_signals_with_bq(db_path)
    except Exception as e:
        return {"error": f"DB load failed: {e}", "n_used": 0}

    if len(df) < min_samples:
        return {
            "error": f"Insufficient data: {len(df)} mature signals (need {min_samples}+)",
            "n_used": len(df),
            "mfe_distribution": _mfe_distribution(df) if len(df) >= 5 else {},
            "mae_distribution": _mae_distribution(df) if len(df) >= 5 else {},
        }

    # حدد المتغيرات المتاحة
    used_feats = [f for f in CLUSTER_FEATURES if f in df.columns]
    snap_count = sum(1 for f in used_feats if f.startswith("snap_"))
    if len(used_feats) < 4:
        return {"error": f"Not enough features: only {len(used_feats)} available",
                "n_used": len(df)}

    # نظّف البيانات
    X_raw = df[used_feats].copy().fillna(df[used_feats].median())
    scaler = StandardScaler()
    X = scaler.fit_transform(X_raw)

    # K-Means clustering
    actual_k = min(n_clusters, max(2, len(df) // 5))
    km = KMeans(n_clusters=actual_k, random_state=42, n_init=10, max_iter=300)
    labels = km.fit_predict(X)

    # Cluster profiles
    profiles = _build_cluster_profile(df, labels, used_feats)

    # Feature importance between clusters
    feat_imp = _feature_importance_between_clusters(X, labels, used_feats, actual_k)

    # PCA coords (للرسم)
    pca_coords = []
    if X.shape[1] >= 2:
        pca = PCA(n_components=2, random_state=42)
        coords = pca.fit_transform(X)
        mfe_vals = df["mfe_20d"].values if "mfe_20d" in df.columns else [None]*len(df)
        sym_vals = df["symbol"].values  if "symbol"  in df.columns else [""]*len(df)
        for i in range(len(df)):
            pca_coords.append({
                "x": round(float(coords[i, 0]), 3),
                "y": round(float(coords[i, 1]), 3),
                "cluster": int(labels[i]),
                "mfe":    round(float(mfe_vals[i]), 4) if mfe_vals[i] is not None else None,
                "symbol": str(sym_vals[i]),
            })

    return {
        "n_used":          len(df),
        "n_clusters":      actual_k,
        "snap_features_available": snap_count,
        "features_used":   used_feats,
        "clusters":        profiles,
        "top_discriminating_features": feat_imp[:10],
        "mfe_distribution": _mfe_distribution(df),
        "mae_distribution": _mae_distribution(df),
        "pca_coords":      pca_coords[:300],
    }


if __name__ == "__main__":
    import argparse, json as _json
    p = argparse.ArgumentParser()
    p.add_argument("--db",      default="egx_research.db")
    p.add_argument("--min",     type=int, default=MIN_SAMPLES)
    p.add_argument("--clusters",type=int, default=N_CLUSTERS)
    p.add_argument("--out",     default="")
    args = p.parse_args()

    result = run_pattern_discovery(args.db, args.min, args.clusters)

    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            _json.dump(result, f, ensure_ascii=False, indent=2, default=str)
        print(f"[PatternDiscovery] Saved → {args.out}")
    else:
        print(_json.dumps(result, ensure_ascii=False, indent=2, default=str))
