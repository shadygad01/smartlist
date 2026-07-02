"""
factor_lab.py — Feature Importance Analysis Lab
Delegates to research_engine.run_research() for RF/GBM feature importance.
"""

import json
import sqlite3
from datetime import datetime

try:
    import research_engine
    _HAS_RESEARCH_ENGINE = True
except Exception as e:
    _HAS_RESEARCH_ENGINE = False
    print(f"[warn] research_engine import failed: {e}")


def _log_experiment(db_path, lab, n_signals, result_dict, report_path=None):
    try:
        conn = sqlite3.connect(db_path)
        conn.execute(
            "INSERT OR IGNORE INTO experiment_log (lab, run_at, n_signals, result_json, report_path) VALUES (?,?,?,?,?)",
            (lab, datetime.now().isoformat(), n_signals, json.dumps(result_dict, default=str)[:10000], report_path)
        )
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"[warn] experiment_log write failed: {e}")


def run(db_path="egx_research.db") -> dict:
    """Run feature importance analysis using RF/GBM via research_engine."""
    result = {
        "feature_importance": {},
        "top_features": [],
        "model_comparison": {},
        "n_signals": 0,
        "run_at": datetime.now().isoformat(),
    }

    if not _HAS_RESEARCH_ENGINE:
        result["error"] = "research_engine not available"
        _log_experiment(db_path, "factor", 0, result)
        return result

    try:
        raw = research_engine.run_research(db_path=db_path, verbose=False)

        # Signal count — lives under meta
        meta = raw.get("meta") or {}
        n_signals = meta.get("n_signals", meta.get("n_mature", 0))

        # Feature importance — lives under rf_mfe or rf_bq sub-dict
        feat_imp = {}
        for model_key in ("rf_mfe", "rf_bq", "gbm_mfe", "gbm_bq"):
            sub = raw.get(model_key) or {}
            if isinstance(sub, dict):
                fi = sub.get("feature_importance", sub.get("importance", {}))
                if fi and isinstance(fi, dict):
                    feat_imp = fi
                    break

        # Fallback: mutual_information dict
        if not feat_imp:
            mi = raw.get("mutual_information") or {}
            if isinstance(mi, dict) and mi:
                feat_imp = {k: v for k, v in mi.items() if isinstance(v, (int, float))}

        # Top features
        top_features = []
        if isinstance(feat_imp, dict) and feat_imp:
            sorted_feats = sorted(feat_imp.items(), key=lambda x: abs(x[1]) if isinstance(x[1], (int, float)) else 0, reverse=True)
            top_features = [k for k, _ in sorted_feats[:10]]

        # Model comparison
        model_comparison = raw.get("model_comparison_mfe") or raw.get("model_comparison") or {}

        # Weight suggestions (research_engine already computes these)
        ws_raw = raw.get("weight_suggestions") or {}
        weight_suggestions = dict(ws_raw) if isinstance(ws_raw, dict) else {
            k: v for k, v in ws_raw
        } if hasattr(ws_raw, "__iter__") else {}

        result.update({
            "feature_importance": feat_imp,
            "top_features": top_features,
            "model_comparison": model_comparison,
            "n_signals": n_signals,
            "weight_suggestions": weight_suggestions,
            "mutual_info": raw.get("mutual_information", {}),
            "mfe_mean": meta.get("mfe_mean"),
            "bq_mean": meta.get("bq_mean"),
        })

    except Exception as e:
        result["error"] = str(e)
        print(f"[warn] factor_lab run_research failed: {e}")

    _log_experiment(db_path, "factor", result.get("n_signals", 0), result)
    return result


if __name__ == "__main__":
    import sys
    print(run(sys.argv[1] if len(sys.argv) > 1 else "egx_research.db"))
