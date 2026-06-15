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

        # Extract feature importance
        feat_imp = {}
        if "feature_importance" in raw:
            feat_imp = raw["feature_importance"]
        elif "mfe_importance" in raw:
            feat_imp = raw["mfe_importance"]

        # Extract top features list
        top_features = []
        if isinstance(feat_imp, dict):
            sorted_feats = sorted(feat_imp.items(), key=lambda x: x[1] if isinstance(x[1], (int, float)) else 0, reverse=True)
            top_features = [k for k, _ in sorted_feats[:10]]

        # Model comparison
        model_comparison = raw.get("model_comparison", {})

        # Signal count
        n_signals = raw.get("n_signals", raw.get("n_mature", 0))

        result.update({
            "feature_importance": feat_imp,
            "top_features": top_features,
            "model_comparison": model_comparison,
            "n_signals": n_signals,
            "weight_suggestions": raw.get("weight_suggestions", {}),
            "mutual_info": raw.get("mutual_info", {}),
        })

    except Exception as e:
        result["error"] = str(e)
        print(f"[warn] factor_lab run_research failed: {e}")

    _log_experiment(db_path, "factor", result.get("n_signals", 0), result)
    return result


if __name__ == "__main__":
    import sys
    print(run(sys.argv[1] if len(sys.argv) > 1 else "egx_research.db"))
