"""
regime_lab.py — Regime & Multi-Period Performance Lab
Delegates to behavior_report and multi_period_analyzer.
"""

import json
import sqlite3
from datetime import datetime

try:
    import behavior_report
    _HAS_BEHAVIOR_REPORT = True
except Exception as e:
    _HAS_BEHAVIOR_REPORT = False
    print(f"[warn] behavior_report import failed: {e}")

try:
    import multi_period_analyzer
    _HAS_MULTI_PERIOD = True
except Exception as e:
    _HAS_MULTI_PERIOD = False
    print(f"[warn] multi_period_analyzer import failed: {e}")


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
    """Run regime performance breakdown by delegating to behavior_report and multi_period_analyzer."""
    result = {
        "behavior": {},
        "multi_period": {},
        "n_signals": 0,
        "run_at": datetime.now().isoformat(),
    }

    n_signals = 0
    report_path = None

    # behavior_report
    if _HAS_BEHAVIOR_REPORT:
        try:
            html = behavior_report.run(send_email=False)
            import os
            rp = behavior_report.REPORT_FILE
            report_path = rp if os.path.exists(rp) else None
            # Collect basic stats from the underlying data
            signals = behavior_report._load_signals()
            resolved = [s for s in signals if s.get("outcome") not in ("pending", None)]
            n_resolved = len(resolved)
            n_signals = max(n_signals, len(signals))
            st = behavior_report._stats(resolved)
            result["behavior"] = {
                "n_resolved": n_resolved,
                "n_pending": len(signals) - n_resolved,
                "win_rate": st.get("win_rate"),
                "avg_ret": st.get("avg_ret"),
                "avg_mfe": st.get("avg_mfe"),
                "pf": st.get("pf"),
                "report_file": report_path,
            }
        except Exception as e:
            result["behavior_error"] = str(e)
            print(f"[warn] behavior_report failed: {e}")

    # multi_period_analyzer
    if _HAS_MULTI_PERIOD:
        try:
            out_path = multi_period_analyzer.run()
            result["multi_period"] = {
                "report_file": out_path,
                "periods": multi_period_analyzer.PERIOD_LABELS,
            }
            if report_path is None:
                report_path = out_path
        except Exception as e:
            result["multi_period_error"] = str(e)
            print(f"[warn] multi_period_analyzer failed: {e}")

    result["n_signals"] = n_signals
    _log_experiment(db_path, "regime", n_signals, result, report_path=report_path)
    return result


if __name__ == "__main__":
    import sys
    print(run(sys.argv[1] if len(sys.argv) > 1 else "egx_research.db"))
