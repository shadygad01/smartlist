"""
Pattern Discovery Engine — EGX Research Platform
=================================================
يستخرج خصائص القاع رقمياً ويكتشف الأنماط المشتركة تلقائياً.

الخوارزميات المستخدمة (يُختار الأفضل بـ silhouette score):
  1. K-Means           — الأساسي، سريع وقابل للتفسير
  2. HDBSCAN           — يكتشف clusters بدون تحديد عددها مسبقاً
  3. AgglomerativeClustering (Hierarchical) — هرمي، أفضل في البيانات الصغيرة

الـ clusters مُرتَّبة بـ MFE تنازلياً ويُستخرج منها "Top 5 Bottom Fingerprints".
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
    from sklearn.metrics import silhouette_score
    SKLEARN_OK = True
except ImportError:
    SKLEARN_OK = False

try:
    from sklearn.cluster import HDBSCAN, AgglomerativeClustering, DBSCAN
    ADVANCED_CLUSTERING = True
except ImportError:
    ADVANCED_CLUSTERING = False


# المتغيرات المستخدمة في التجميع
CLUSTER_FEATURES = [
    # Phase 1: computed feat_* columns
    "feat_dist_swing_low", "feat_dealing_range_pos",
    "feat_sweep_depth_pct", "feat_equal_lows_count",
    "feat_vol_spike_ratio", "feat_accumulation_score",
    "feat_consec_red", "feat_down_days_pct",
    "feat_atr_compression", "feat_vol_contraction",
    "feat_dist_20d_low", "feat_dist_52w_low",
    "feat_vwap_dist",
    # Snapshot features (recomputed snap_*)
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

N_CLUSTERS    = 4
MIN_SAMPLES   = 15
MIN_SNAP_COLS = 3


def _load_signals_with_bq(db_path: str = "egx_research.db") -> "pd.DataFrame":
    conn = sqlite3.connect(db_path)
    q = """
    SELECT s.*, bq.bq_score, bq.mfe_20d, bq.mae_20d, bq.r20d, bq.classification,
           bq.mfe_40d, bq.mfe_60d, bq.time_to_recovery, bq.drawdown_duration
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


def _run_clustering(X: "np.ndarray", n_clusters: int) -> "tuple[np.ndarray, str, float]":
    """
    Tries K-Means, HDBSCAN, and Hierarchical clustering.
    Returns (labels, algorithm_name, silhouette_score) using the best result.
    """
    results = []

    # 1. K-Means
    try:
        km  = KMeans(n_clusters=n_clusters, random_state=42, n_init=10, max_iter=300)
        lbl = km.fit_predict(X)
        if len(set(lbl)) >= 2:
            s = float(silhouette_score(X, lbl))
            results.append(("KMeans", lbl.copy(), s))
    except Exception:
        pass

    if ADVANCED_CLUSTERING:
        # 2. HDBSCAN — density-based, no fixed k
        try:
            min_cs = max(4, len(X) // 12)
            hdb    = HDBSCAN(min_cluster_size=min_cs, min_samples=3, store_centers="centroid")
            lbl    = hdb.fit_predict(X)
            valid  = lbl != -1
            if valid.sum() >= 10 and len(set(lbl[valid])) >= 2:
                s = float(silhouette_score(X[valid], lbl[valid]))
                # reassign noise points to the nearest valid cluster centroid
                if (~valid).sum() > 0:
                    from sklearn.neighbors import NearestNeighbors
                    nn = NearestNeighbors(n_neighbors=1).fit(X[valid])
                    _, idx = nn.kneighbors(X[~valid])
                    lbl[~valid] = lbl[valid][idx.flatten()]
                results.append(("HDBSCAN", lbl.copy(), s))
        except Exception:
            pass

        # 3. Hierarchical (Ward linkage)
        try:
            hc  = AgglomerativeClustering(n_clusters=n_clusters, linkage="ward")
            lbl = hc.fit_predict(X)
            if len(set(lbl)) >= 2:
                s = float(silhouette_score(X, lbl))
                results.append(("Hierarchical", lbl.copy(), s))
        except Exception:
            pass

    if not results:
        km  = KMeans(n_clusters=min(n_clusters, 2), random_state=42, n_init=5)
        lbl = km.fit_predict(X)
        return lbl, "KMeans(fallback)", -1.0

    best = max(results, key=lambda x: x[2])
    return best[1], best[0], best[2]


def _build_cluster_profile(df: "pd.DataFrame", labels: "np.ndarray",
                            used_feats: list) -> list:
    profiles = []
    global_means = {f: float(df[f].mean()) for f in used_feats if f in df.columns}

    for c in sorted(set(labels)):
        mask = labels == c
        grp  = df[mask]
        n    = int(mask.sum())

        mfe_m = float(grp["mfe_20d"].mean()) if "mfe_20d" in grp.columns else None
        mae_m = float(grp["mae_20d"].mean()) if "mae_20d" in grp.columns else None
        bq_m  = float(grp["bq_score"].mean()) if "bq_score" in grp.columns else None
        ttr_m = float(grp["time_to_recovery"].mean()) if "time_to_recovery" in grp.columns and grp["time_to_recovery"].notna().any() else None
        ddr_m = float(grp["drawdown_duration"].mean()) if "drawdown_duration" in grp.columns and grp["drawdown_duration"].notna().any() else None

        signatures = {}
        for feat in used_feats:
            if feat not in grp.columns:
                continue
            c_mean = float(grp[feat].mean())
            g_mean = global_means.get(feat, 0.0)
            signatures[feat] = {
                "cluster_mean":    round(c_mean, 4),
                "diff_from_global": round(c_mean - g_mean, 4),
            }

        top_feats = sorted(
            [(f, abs(v["diff_from_global"])) for f, v in signatures.items()],
            key=lambda x: -x[1]
        )[:5]

        cls_dist = {}
        if "classification" in grp.columns:
            cls_dist = grp["classification"].value_counts().to_dict()

        sym_dist = {}
        if "symbol" in grp.columns:
            sym_dist = grp["symbol"].value_counts().head(5).to_dict()

        profiles.append({
            "cluster_id":         int(c),
            "cluster_label":      _cluster_label(mfe_m),
            "n":                  n,
            "mfe_mean":           round(mfe_m, 4) if mfe_m is not None else None,
            "mae_mean":           round(mae_m, 4) if mae_m is not None else None,
            "bq_mean":            round(bq_m,  2) if bq_m  is not None else None,
            "time_to_recovery_mean": round(ttr_m, 1) if ttr_m is not None else None,
            "drawdown_duration_mean": round(ddr_m, 1) if ddr_m is not None else None,
            "signatures":         signatures,
            "top_features":       [f for f, _ in top_feats],
            "cls_breakdown":      cls_dist,
            "symbol_dist":        sym_dist,
        })

    profiles.sort(key=lambda x: (x.get("mfe_mean") or -999), reverse=True)
    return profiles


def _feature_importance_between_clusters(
    X: "np.ndarray", labels: "np.ndarray",
    used_feats: list, n_clusters: int
) -> list:
    importances = []
    for i, feat in enumerate(used_feats):
        col       = X[:, i]
        total_var = float(np.var(col)) + 1e-9
        cluster_means = np.array([
            float(np.mean(col[labels == c])) if (labels == c).any() else 0.0
            for c in range(n_clusters)
        ])
        between_var = float(np.var(cluster_means))
        importances.append((feat, round(between_var / total_var, 4)))

    importances.sort(key=lambda x: -x[1])
    return importances


def _top_fingerprints(profiles: list, n_top: int = 5) -> list:
    """
    Extracts top-N bottom fingerprints: patterns sorted best→worst by MFE.
    Each fingerprint contains key distinguishing features and metrics.
    """
    fingerprints = []
    for i, cv in enumerate(profiles[:n_top]):
        sigs      = cv.get("signatures", {})
        top_feats = cv.get("top_features", [])[:4]
        fp = {
            "rank":      i + 1,
            "cluster_id": cv.get("cluster_id"),
            "label":     cv.get("cluster_label", "Unknown"),
            "n":         cv.get("n", 0),
            "mfe_mean":  cv.get("mfe_mean"),
            "mae_mean":  cv.get("mae_mean"),
            "bq_mean":   cv.get("bq_mean"),
            "time_to_recovery_mean": cv.get("time_to_recovery_mean"),
            "drawdown_duration_mean": cv.get("drawdown_duration_mean"),
            "key_features": top_feats,
            "feature_values": {
                f: {
                    "mean":       round(sigs[f]["cluster_mean"], 4),
                    "vs_global":  round(sigs[f]["diff_from_global"], 4),
                }
                for f in top_feats if f in sigs
            },
        }
        fingerprints.append(fp)
    return fingerprints


def _mfe_distribution(df: "pd.DataFrame") -> dict:
    if "mfe_20d" not in df.columns or df["mfe_20d"].isna().all():
        return {}
    vals = df["mfe_20d"].dropna().values * 100
    buckets = {
        "<0%":    int((vals < 0).sum()),
        "0–3%":   int(((vals >= 0) & (vals < 3)).sum()),
        "3–8%":   int(((vals >= 3) & (vals < 8)).sum()),
        "8–15%":  int(((vals >= 8) & (vals < 15)).sum()),
        "15–25%": int(((vals >= 15) & (vals < 25)).sum()),
        ">25%":   int((vals >= 25).sum()),
    }
    return {
        "buckets": buckets,
        "mean":   round(float(np.mean(vals)), 2),
        "median": round(float(np.median(vals)), 2),
        "p75":    round(float(np.percentile(vals, 75)), 2),
        "p90":    round(float(np.percentile(vals, 90)), 2),
    }


def _mae_distribution(df: "pd.DataFrame") -> dict:
    if "mae_20d" not in df.columns or df["mae_20d"].isna().all():
        return {}
    vals = np.abs(df["mae_20d"].dropna().values * 100)
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
    Loads mature signals, runs best-of-three clustering (KMeans / HDBSCAN / Hierarchical),
    returns cluster profiles + feature importance + top fingerprints.
    """
    if not NP_OK:
        return {"error": "numpy/pandas not installed", "n_used": 0}
    if not SKLEARN_OK:
        return {"error": "scikit-learn not installed", "n_used": 0}

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

    min_nonull = max(4, min_samples // 5)
    used_feats = [
        f for f in CLUSTER_FEATURES
        if f in df.columns and df[f].notna().sum() >= min_nonull
    ]
    snap_count = sum(1 for f in used_feats if f.startswith("snap_"))
    feat_count = sum(1 for f in used_feats if f.startswith("feat_"))

    if len(used_feats) < 4:
        return {
            "error": f"Not enough features with data: only {len(used_feats)} available (need 4+)",
            "n_used": len(df),
        }

    medians = df[used_feats].median()
    X_raw   = df[used_feats].copy().fillna(medians).fillna(0.0)
    scaler  = StandardScaler()
    X       = scaler.fit_transform(X_raw)

    # Best-of-three clustering
    actual_k = min(n_clusters, max(2, len(df) // 5))
    labels, algo_used, sil_score = _run_clustering(X, actual_k)

    n_actual_clusters = len(set(labels))
    profiles  = _build_cluster_profile(df, labels, used_feats)
    feat_imp  = _feature_importance_between_clusters(X, labels, used_feats, n_actual_clusters)
    top_fps   = _top_fingerprints(profiles, n_top=5)

    # PCA coords
    pca_coords = []
    if X.shape[1] >= 2:
        pca    = PCA(n_components=2, random_state=42)
        coords = pca.fit_transform(X)
        mfe_vals = df["mfe_20d"].values if "mfe_20d" in df.columns else [None]*len(df)
        sym_vals = df["symbol"].values  if "symbol"  in df.columns else [""]*len(df)
        for i in range(len(df)):
            pca_coords.append({
                "x":       round(float(coords[i, 0]), 3),
                "y":       round(float(coords[i, 1]), 3),
                "cluster": int(labels[i]),
                "mfe":     round(float(mfe_vals[i]), 4) if mfe_vals[i] is not None else None,
                "symbol":  str(sym_vals[i]),
            })

    return {
        "n_used":                  len(df),
        "n_clusters":              n_actual_clusters,
        "algorithm":               algo_used,
        "silhouette_score":        round(sil_score, 4) if sil_score > -1 else None,
        "snap_features_available": snap_count,
        "feat_features_available": feat_count,
        "features_used":           used_feats,
        "clusters":                profiles,
        "top_fingerprints":        top_fps,
        "top_discriminating_features": feat_imp[:10],
        "mfe_distribution":        _mfe_distribution(df),
        "mae_distribution":        _mae_distribution(df),
        "pca_coords":              pca_coords[:300],
    }


if __name__ == "__main__":
    import argparse, json as _json
    p = argparse.ArgumentParser()
    p.add_argument("--db",       default="egx_research.db")
    p.add_argument("--min",      type=int, default=MIN_SAMPLES)
    p.add_argument("--clusters", type=int, default=N_CLUSTERS)
    p.add_argument("--out",      default="")
    args = p.parse_args()

    result = run_pattern_discovery(args.db, args.min, args.clusters)

    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            _json.dump(result, f, ensure_ascii=False, indent=2, default=str)
        print(f"[PatternDiscovery] Saved → {args.out}")
    else:
        print(_json.dumps(result, ensure_ascii=False, indent=2, default=str))
