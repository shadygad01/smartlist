"""
parameter_lab.py — Parameter Sensitivity Analysis Lab
Delegates to logic_analyzer (and study_indicators if available).
"""

import json
import sqlite3
from datetime import datetime

try:
    import logic_analyzer
    _HAS_LOGIC_ANALYZER = True
except Exception as e:
    _HAS_LOGIC_ANALYZER = False
    print(f"[warn] logic_analyzer import failed: {e}")

try:
    import study_indicators
    _HAS_STUDY_INDICATORS = True
except Exception as e:
    _HAS_STUDY_INDICATORS = False
    # study_indicators is optional


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
    """Run parameter sensitivity analysis by delegating to logic_analyzer."""
    result = {
        "sensitivity": {},
        "function_impact": {},
        "recommendations": [],
        "critical_findings": [],
        "n_signals": 0,
        "run_at": datetime.now().isoformat(),
    }

    n_signals = 0

    if _HAS_LOGIC_ANALYZER:
        try:
            logic_analyzer.main(db_path=db_path)
            # Read results JSON if produced
            import os, json as _json
            results_file = "logic_analysis_results.json"
            if os.path.exists(results_file):
                with open(results_file, encoding="utf-8") as f:
                    logic_results = _json.load(f)
                n_signals = logic_results.get("n_signals", 0)
                result.update({
                    "sensitivity": logic_results.get("function_impact", {}),
                    "recommendations": logic_results.get("summary_recommendations", []),
                    "critical_findings": logic_results.get("critical_findings", []),
                    "n_signals": n_signals,
                    "baseline_r20d": logic_results.get("baseline_r20d"),
                    "baseline_mfe": logic_results.get("baseline_mfe"),
                })
        except Exception as e:
            result["logic_analyzer_error"] = str(e)
            print(f"[warn] logic_analyzer failed: {e}")

    if _HAS_STUDY_INDICATORS:
        try:
            # study_indicators works on synthetic data — wrap any top-level callable
            si_result = {}
            if hasattr(study_indicators, "run"):
                si_result = study_indicators.run() or {}
            elif hasattr(study_indicators, "main"):
                si_result = study_indicators.main() or {}
            if si_result:
                result["study_indicators"] = si_result
        except Exception as e:
            result["study_indicators_error"] = str(e)
            print(f"[warn] study_indicators failed: {e}")

    result["n_signals"] = n_signals
    _log_experiment(db_path, "parameter", n_signals, result)
    return result


if __name__ == "__main__":
    import sys
    print(run(sys.argv[1] if len(sys.argv) > 1 else "egx_research.db"))
