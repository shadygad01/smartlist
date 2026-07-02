"""
drift_lab.py — Drift Detection, Bias Flags & System Health Lab
Delegates to system_audit, extend_metrics, extended_logger.
"""

import json
import sqlite3
from datetime import datetime

try:
    import system_audit
    _HAS_SYSTEM_AUDIT = True
except Exception as e:
    _HAS_SYSTEM_AUDIT = False
    print(f"[warn] system_audit import failed: {e}")

try:
    import extend_metrics
    _HAS_EXTEND_METRICS = True
except Exception as e:
    _HAS_EXTEND_METRICS = False
    print(f"[warn] extend_metrics import failed: {e}")

try:
    import extended_logger
    _HAS_EXTENDED_LOGGER = True
except Exception as e:
    _HAS_EXTENDED_LOGGER = False
    print(f"[warn] extended_logger import failed: {e}")


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
    """Run drift detection, bias flags, and health check by delegating to audit modules."""
    result = {
        "drift_indicators": {},
        "bias_flags": [],
        "health_report": {},
        "extended_metrics_status": {},
        "n_signals": 0,
        "run_at": datetime.now().isoformat(),
    }

    n_signals = 0
    report_path = None

    # system_audit — comprehensive audit
    if _HAS_SYSTEM_AUDIT:
        try:
            system_audit.main()
            import os, json as _json
            audit_json = "system_audit_results.json"
            if os.path.exists(audit_json):
                with open(audit_json, encoding="utf-8") as f:
                    audit_data = _json.load(f)
                n_signals = max(n_signals, audit_data.get("n_signals", 0))
                conclusions = audit_data.get("conclusions", {})
                result["drift_indicators"] = {
                    "n_signals": audit_data.get("n_signals"),
                    "n_rejected": audit_data.get("n_rejected"),
                    "baseline_r20d": audit_data.get("baseline_r20d"),
                    "baseline_pf": audit_data.get("baseline_pf"),
                    "overfitting_audit": audit_data.get("overfitting_audit", []),
                    "top_discoveries": audit_data.get("top_discoveries", []),
                }
                result["bias_flags"] = (
                    conclusions.get("q3_filters_hurting", []) +
                    conclusions.get("q6_remove_entirely", [])
                )
                result["health_report"] = {
                    "architecture": conclusions.get("q7_architecture", ""),
                    "highest_impact": conclusions.get("q8_highest_impact", ""),
                    "system_status": conclusions.get("q9_system_status", ""),
                    "filter_damage": audit_data.get("filter_damage", [])[:5],
                }
                # Find latest HTML report
                import glob
                htmls = sorted(glob.glob("reports/system_audit_report_*.html"), reverse=True)
                if htmls:
                    report_path = htmls[0]
        except Exception as e:
            result["system_audit_error"] = str(e)
            print(f"[warn] system_audit failed: {e}")

    # extend_metrics — compute long-term forward metrics
    if _HAS_EXTEND_METRICS:
        try:
            extend_metrics.run(force=False)
            result["extended_metrics_status"] = {"status": "computed", "windows": extend_metrics.WINDOWS}
        except Exception as e:
            result["extend_metrics_error"] = str(e)
            print(f"[warn] extend_metrics failed: {e}")

    # extended_logger — check log health
    if _HAS_EXTENDED_LOGGER:
        try:
            import os
            log_path = extended_logger.EXTENDED_LOG
            if os.path.exists(log_path):
                import json as _json
                with open(log_path, encoding="utf-8") as f:
                    log_data = _json.load(f)
                log_signals = log_data.get("signals", [])
                n_signals = max(n_signals, len(log_signals))
                result["extended_logger_status"] = {
                    "log_file": log_path,
                    "n_logged": len(log_signals),
                    "version": log_data.get("version"),
                }
            else:
                result["extended_logger_status"] = {"log_file": log_path, "exists": False}
        except Exception as e:
            result["extended_logger_error"] = str(e)
            print(f"[warn] extended_logger check failed: {e}")

    result["n_signals"] = n_signals
    _log_experiment(db_path, "drift", n_signals, result, report_path=report_path)
    return result


if __name__ == "__main__":
    import sys
    print(run(sys.argv[1] if len(sys.argv) > 1 else "egx_research.db"))
